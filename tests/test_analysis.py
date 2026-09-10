"""Phase 2 — Financial Intelligence Layer Tests.

Tests the analysis orchestrator: cross-document tie-outs, contradiction detection,
period-over-period analysis, missing disclosure detection, severity classification,
and findings persistence.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import app, _ip_rate_limits
from api.pipeline.analyze import (
    _severity_from_delta,
    _analyze_cross_document_tieouts,
    _analyze_period_changes,
    _check_intra_document_consistency,
    _analyze_missing_disclosures,
    _generate_explanations,
)
from api.pipeline.reconcile import reconcile_pair


# ── Test Helpers ─────────────────────────────────────────────────────

from tests.helpers import fake_fact as _fake_fact


# ── Severity Classification ─────────────────────────────────────────

@pytest.mark.parametrize("delta, expected", [
    (0.60, "critical"), (1.0, "critical"),
    (0.15, "high"), (0.49, "high"),
    (0.08, "medium"),
    (0.02, "low"), (0.0, "low"),
])
def test_severity_from_delta(delta, expected):
    assert _severity_from_delta(delta) == expected


# ── Reconcile Pair (Phase 1 engine, reused by Phase 2) ───────────────

class TestReconcilePair:
    def test_corroboration_within_tolerance(self):
        fa = _fake_fact(norm_value=100.0)
        fb = _fake_fact(norm_value=100.5)
        relation, explanation, rules, conf = reconcile_pair(fa, fb)
        assert relation == "corroborates"
        assert "R4:tolerance_match" in rules

    def test_contradiction_beyond_tolerance(self):
        fa = _fake_fact(norm_value=100.0)
        fb = _fake_fact(norm_value=150.0)
        relation, explanation, rules, conf = reconcile_pair(fa, fb)
        assert relation == "contradicts"
        assert "R4:value_mismatch" in rules

    def test_contextual_variance_different_periods(self):
        fa = _fake_fact(period="FY2022", norm_value=100.0)
        fb = _fake_fact(period="FY2024", norm_value=100.0)
        relation, explanation, rules, conf = reconcile_pair(fa, fb)
        assert relation == "contextual_variance"
        assert any("period" in r for r in rules)

    def test_contextual_variance_different_scope(self):
        fa = _fake_fact(scope="standalone", norm_value=100.0, period="FY2024")
        fb = _fake_fact(scope="consolidated", norm_value=100.0, period="FY2024")
        relation, explanation, rules, conf = reconcile_pair(fa, fb)
        assert relation == "contextual_variance"

    def test_low_confidence_needs_review(self):
        fa = _fake_fact(confidence=0.3)
        fb = _fake_fact(confidence=0.9)
        relation, _, rules, _ = reconcile_pair(fa, fb)
        assert relation == "needs_review"
        assert "R1:low_confidence" in rules

    def test_fx_conversion_corroborates(self):
        fa = _fake_fact(norm_value=100.0, currency="USD", period="FY2024")
        fb = _fake_fact(norm_value=8333.33, currency="INR", period="FY2024")
        relation, _, rules, _ = reconcile_pair(fa, fb)
        assert relation == "corroborates"
        assert any("R3:FX" in r for r in rules)

    def test_opposition_verbs_contradict(self):
        fa = _fake_fact(raw_value="Director resigned from office", norm_value=None)
        fb = _fake_fact(raw_value="Director continues in office", norm_value=None)
        relation, _, rules, _ = reconcile_pair(fa, fb)
        assert relation == "contradicts"
        assert any("R5:verb_opposition" in r for r in rules)


# ── Cross-Document Tie-Out Analysis ──────────────────────────────────

class TestCrossDocumentTieouts:
    def test_contradiction_generates_finding(self):
        doc_a = str(uuid.uuid4())
        doc_b = str(uuid.uuid4())
        fa = _fake_fact(document_id=doc_a, norm_value=8142.0, raw_value="8,142 Cr", filename="annual_report.pdf")
        fb = _fake_fact(document_id=doc_b, norm_value=7860.0, raw_value="7,860 Cr", filename="investor_pres.pdf")

        findings = _analyze_cross_document_tieouts([fa, fb])
        assert len(findings) >= 1
        contradiction = [f for f in findings if f["category"] == "contradiction"]
        assert len(contradiction) == 1
        assert contradiction[0]["severity"] in ("low", "medium", "high", "critical")
        assert doc_a in contradiction[0]["document_ids"] or doc_b in contradiction[0]["document_ids"]

    def test_corroboration_no_finding(self):
        doc_a = str(uuid.uuid4())
        doc_b = str(uuid.uuid4())
        fa = _fake_fact(document_id=doc_a, norm_value=8142.0)
        fb = _fake_fact(document_id=doc_b, norm_value=8142.0)

        findings = _analyze_cross_document_tieouts([fa, fb])
        contradictions = [f for f in findings if f["category"] == "contradiction"]
        assert len(contradictions) == 0

    def test_contextual_variance_info_severity(self):
        doc_a = str(uuid.uuid4())
        doc_b = str(uuid.uuid4())
        fa = _fake_fact(document_id=doc_a, period="FY2023", norm_value=100.0)
        fb = _fake_fact(document_id=doc_b, period="FY2024", norm_value=120.0)

        findings = _analyze_cross_document_tieouts([fa, fb])
        cv = [f for f in findings if f["category"] == "contextual_variance"]
        assert len(cv) == 1
        assert cv[0]["severity"] == "info"

    def test_severity_scales_with_delta(self):
        doc_a = str(uuid.uuid4())
        doc_b = str(uuid.uuid4())
        # 60% difference → critical
        fa = _fake_fact(document_id=doc_a, norm_value=100.0)
        fb = _fake_fact(document_id=doc_b, norm_value=40.0)

        findings = _analyze_cross_document_tieouts([fa, fb])
        contradictions = [f for f in findings if f["category"] == "contradiction"]
        assert len(contradictions) == 1
        assert contradictions[0]["severity"] == "critical"


# ── Intra-Document Consistency ───────────────────────────────────────

class TestIntraDocumentConsistency:
    def test_detects_internal_inconsistency(self):
        doc_id = str(uuid.uuid4())
        fa = _fake_fact(document_id=doc_id, norm_value=100.0, page=5)
        fb = _fake_fact(document_id=doc_id, norm_value=120.0, page=42)

        findings = []
        _check_intra_document_consistency([fa, fb], findings)
        assert len(findings) >= 1
        assert findings[0]["category"] == "contradiction"

    def test_consistent_values_no_finding(self):
        doc_id = str(uuid.uuid4())
        fa = _fake_fact(document_id=doc_id, norm_value=100.0, page=5)
        fb = _fake_fact(document_id=doc_id, norm_value=100.5, page=42)

        findings = []
        _check_intra_document_consistency([fa, fb], findings)
        assert len(findings) == 0


# ── Period-over-Period Analysis ──────────────────────────────────────

class TestPeriodChanges:
    def test_large_swing_generates_finding(self):
        fa = _fake_fact(period="FY2023", norm_value=100.0)
        fb = _fake_fact(period="FY2024", norm_value=200.0)

        findings = _analyze_period_changes([fa, fb])
        assert len(findings) >= 1
        assert findings[0]["category"] == "anomaly"
        assert "100.0%" in findings[0]["title"]

    def test_moderate_swing_no_finding(self):
        fa = _fake_fact(period="FY2023", norm_value=100.0)
        fb = _fake_fact(period="FY2024", norm_value=130.0)

        findings = _analyze_period_changes([fa, fb])
        # 30% change is below 50% threshold
        assert len(findings) == 0

    def test_decline_detected(self):
        fa = _fake_fact(period="FY2023", norm_value=200.0)
        fb = _fake_fact(period="FY2024", norm_value=50.0)

        findings = _analyze_period_changes([fa, fb])
        assert len(findings) >= 1
        assert "decreased" in findings[0]["title"]


# ── Evidence Chain & Provenance ──────────────────────────────────────

class TestProvenance:
    def test_findings_contain_fact_ids(self):
        doc_a = str(uuid.uuid4())
        doc_b = str(uuid.uuid4())
        fa = _fake_fact(document_id=doc_a, norm_value=100.0)
        fb = _fake_fact(document_id=doc_b, norm_value=200.0)

        findings = _analyze_cross_document_tieouts([fa, fb])
        assert len(findings) >= 1
        for f in findings:
            assert len(f["fact_ids"]) >= 2
            assert fa["id"] in f["fact_ids"]
            assert fb["id"] in f["fact_ids"]

    def test_findings_contain_document_ids(self):
        doc_a = str(uuid.uuid4())
        doc_b = str(uuid.uuid4())
        fa = _fake_fact(document_id=doc_a, norm_value=100.0)
        fb = _fake_fact(document_id=doc_b, norm_value=200.0)

        findings = _analyze_cross_document_tieouts([fa, fb])
        assert len(findings) >= 1
        for f in findings:
            assert len(f["document_ids"]) >= 1

    def test_findings_contain_details(self):
        doc_a = str(uuid.uuid4())
        doc_b = str(uuid.uuid4())
        fa = _fake_fact(document_id=doc_a, norm_value=100.0)
        fb = _fake_fact(document_id=doc_b, norm_value=200.0)

        findings = _analyze_cross_document_tieouts([fa, fb])
        assert len(findings) >= 1
        details = findings[0]["details"]
        assert "rel_delta_pct" in details
        assert "rules_applied" in details


# ── Missing Disclosures ──────────────────────────────────────────────

class TestMissingDisclosures:
    def test_detects_omitted_core_metric(self):
        doc_a = str(uuid.uuid4())
        doc_b = str(uuid.uuid4())
        mock_metric_rows = [
            {
                "entity_canon": "delhivery",
                "period": "FY2024",
                "document_id": doc_a,
                "filename": "annual_report.pdf",
                "metrics": ["total_revenue", "ebitda", "net_income"],
            },
            {
                "entity_canon": "delhivery",
                "period": "FY2024",
                "document_id": doc_b,
                "filename": "investor_deck.pdf",
                "metrics": ["total_revenue"],  # missing ebitda and net_income
            },
        ]
        with patch("api.db.get_distinct_metrics_by_entity_period", return_value=mock_metric_rows):
            findings = _analyze_missing_disclosures([doc_a, doc_b])
            assert len(findings) == 2
            missing_metrics = {f["details"]["missing_metric"] for f in findings}
            assert "ebitda" in missing_metrics
            assert "net_income" in missing_metrics
            assert all(f["category"] == "missing_disclosure" for f in findings)


# ── AI Explanations ──────────────────────────────────────────────────

class TestAIExplanations:
    def test_ai_explanation_populates_findings(self):
        findings = [
            {
                "category": "contradiction",
                "severity": "critical",
                "title": "Delhivery Revenue mismatch",
                "description": "Values differ by 60%",
                "details": {"rel_delta_pct": 60.0},
            }
        ]
        mock_llm_response = (
            '[{"index": 1, "explanation": "Revenue differs significantly due to potential restatement or scope differences."}]',
            "groq"
        )
        with patch("api.pipeline.models.complete", return_value=mock_llm_response):
            _generate_explanations(findings)
            assert findings[0].get("explanation") == "Revenue differs significantly due to potential restatement or scope differences."

    def test_ai_explanation_failure_is_non_fatal(self):
        findings = [
            {
                "category": "contradiction",
                "severity": "critical",
                "title": "Delhivery Revenue mismatch",
                "description": "Values differ by 60%",
            }
        ]
        with patch("api.pipeline.models.complete", side_effect=RuntimeError("LLM API timeout")):
            _generate_explanations(findings)
            # Should not raise exception, finding simply lacks explanation
            assert not findings[0].get("explanation")


# ── Findings API Endpoints ───────────────────────────────────────────

class TestFindingsAPIEndpoints:
    @pytest.fixture(autouse=True)
    def setUp(self):
        from api.main import app, _ip_rate_limits
        _ip_rate_limits.clear()
        self.client = TestClient(app)
        self.client.headers.update({"Authorization": "Bearer dev-secret-key"})

    def test_list_findings(self):
        fake_findings = [
            {
                "id": str(uuid.uuid4()),
                "case_id": str(uuid.uuid4()),
                "category": "contradiction",
                "severity": "high",
                "title": "Revenue mismatch",
                "description": "Differs by 15%",
                "fact_ids": [str(uuid.uuid4())],
                "relation_ids": [],
                "evidence_ids": [],
                "document_ids": [str(uuid.uuid4())],
                "details": {},
                "status": "open",
                "created_at": "2026-09-10T12:00:00Z",
            }
        ]
        with patch("api.db.get_findings", return_value=fake_findings):
            resp = self.client.get("/findings?category=contradiction")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["category"] == "contradiction"
            assert data[0]["severity"] == "high"

    def test_findings_summary(self):
        fake_summary = {
            "total": 5,
            "by_severity": {"critical": 1, "high": 2, "medium": 2, "low": 0, "info": 0},
            "by_category": {"contradiction": 3, "anomaly": 2},
            "by_status": {"open": 5, "confirmed": 0, "dismissed": 0, "resolved": 0},
        }
        with patch("api.db.get_findings_summary", return_value=fake_summary):
            resp = self.client.get("/findings/summary")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 5
            assert data["by_severity"]["critical"] == 1

    def test_get_finding_detail(self):
        fid = str(uuid.uuid4())
        fact_id = str(uuid.uuid4())
        fake_finding = {
            "id": fid,
            "case_id": None,
            "category": "contradiction",
            "severity": "critical",
            "title": "Revenue Contradiction",
            "description": "Discrepancy of 55%",
            "explanation": "Significant variance.",
            "fact_ids": [fact_id],
            "relation_ids": [],
            "evidence_ids": [],
            "document_ids": [],
            "details": {},
            "status": "open",
            "created_at": "2026-09-10T12:00:00Z",
        }
        fake_fact = {
            "id": fact_id,
            "entity_canon": "delhivery",
            "attribute_canon": "total_revenue",
            "raw_value": "8,142 Cr",
            "norm_value": 8142.0,
            "period": "FY2024",
            "scope": "standalone",
            "quote": "Revenue reached 8,142 Cr",
            "page": 42,
            "document_filename": "annual_report.pdf",
            "confidence": 0.95,
        }
        with (
            patch("api.db.get_finding", return_value=fake_finding),
            patch("api.db.get_fact_with_relations", return_value=fake_fact),
        ):
            resp = self.client.get(f"/findings/{fid}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == fid
            assert len(data["fact_details"]) == 1
            assert data["fact_details"][0]["entity_canon"] == "delhivery"

    def test_update_finding_status(self):
        fid = str(uuid.uuid4())
        updated = {
            "id": fid,
            "case_id": None,
            "status": "confirmed",
            "created_at": "2026-09-10T12:00:00Z",
        }
        with patch("api.db.update_finding_status", return_value=updated):
            resp = self.client.post(f"/findings/{fid}/status", json={"status": "confirmed"})
            assert resp.status_code == 200
            assert resp.json()["status"] == "confirmed"

    def test_trigger_analysis_endpoint(self):
        doc_1 = str(uuid.uuid4())
        doc_2 = str(uuid.uuid4())
        with (
            patch("api.db.audit"),
            patch("api.db.get_facts_grouped_for_analysis", return_value={}),
        ):
            resp = self.client.post("/analyze", json={"document_ids": [doc_1, doc_2]})
            assert resp.status_code == 200
            assert resp.json()["status"] == "analysis_started"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
