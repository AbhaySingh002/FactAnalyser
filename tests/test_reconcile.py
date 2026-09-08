"""Tests for Stage 6: deterministic pairwise cross-document reconciliation."""

import uuid
from unittest.mock import MagicMock, patch

from api.pipeline.reconcile import (
    reconcile_pair,
    reconcile_document,
    TOL,
    FX_RATES,
)


def test_constants():
    """Verify named constants TOL and FX_RATES."""
    assert TOL == 0.01
    assert "USD" in FX_RATES and "INR" in FX_RATES
    print("✓ test_constants passed")


def test_r1_either_confidence_low():
    """Verify R1: either confidence < 0.5 triggers needs_review and cites low confidence side."""
    # A low
    rel_a, exp_a, r_a, _ = reconcile_pair({"confidence": 0.35}, {"confidence": 0.95})
    assert rel_a == "needs_review"
    assert "R1:low_confidence" in r_a
    assert "fact A: 0.35" in exp_a or "fact A (0.35)" in exp_a

    # B low
    rel_b, exp_b, r_b, _ = reconcile_pair({"confidence": 0.95}, {"confidence": 0.25})
    assert rel_b == "needs_review"
    assert "R1:low_confidence" in r_b
    assert "fact B: 0.25" in exp_b or "fact B (0.25)" in exp_b

    # Both low
    rel_both, exp_both, r_both, _ = reconcile_pair({"confidence": 0.3}, {"confidence": 0.4})
    assert rel_both == "needs_review"
    assert "both sides" in exp_both

    print("✓ test_r1_either_confidence_low passed")


def test_r2_context_axes_differ():
    """Verify R2: contextual_variance when periods, scopes, entities, or unconvertible currencies differ."""
    # Period diff
    rel, exp, r, _ = reconcile_pair(
        {"period": "FY2022", "norm_value": 500, "confidence": 0.9},
        {"period": "FY2023", "norm_value": 500, "confidence": 0.9},
    )
    assert rel == "contextual_variance"
    assert "R2:context_diff:period" in r
    assert "periods differ: FY2022 vs FY2023" in exp
    assert "values not compared" in exp

    # Scope diff
    rel, exp, r, _ = reconcile_pair(
        {"scope": "standalone", "norm_value": 500, "confidence": 0.9},
        {"scope": "consolidated", "norm_value": 500, "confidence": 0.9},
    )
    assert rel == "contextual_variance"
    assert "R2:context_diff:scope" in r
    assert "scopes differ" in exp

    # Entity diff
    rel, exp, r, _ = reconcile_pair(
        {"entity_canon": "acme inc", "norm_value": 500, "confidence": 0.9},
        {"entity_canon": "beta llc", "norm_value": 500, "confidence": 0.9},
    )
    assert rel == "contextual_variance"
    assert "R2:context_diff:entity" in r
    assert "entities differ" in exp

    # Currency unconvertible
    rel, exp, r, _ = reconcile_pair(
        {"currency": "XYZ", "norm_value": 500, "confidence": 0.9},
        {"currency": "USD", "norm_value": 500, "confidence": 0.9},
    )
    assert rel == "contextual_variance"
    assert "R2:context_diff:currency" in r

    print("✓ test_r2_context_axes_differ passed")


def test_r3_and_r4_numeric_corroboration_and_contradiction():
    """Verify R3 unit conversion & R4 tolerance comparison."""
    # Corroboration within 1%
    rel_corr, exp_corr, r_corr, _ = reconcile_pair(
        {"norm_value": 1000.0, "currency": "USD", "period": "FY2023", "confidence": 0.9},
        {"norm_value": 1005.0, "currency": "USD", "period": "FY2023", "confidence": 0.9},
    )
    assert rel_corr == "corroborates"
    assert "R4:tolerance_match" in r_corr
    assert "within 1% tolerance" in exp_corr

    # Contradiction > 1%
    rel_contra, exp_contra, r_contra, _ = reconcile_pair(
        {"norm_value": 1000.0, "currency": "USD", "period": "FY2023", "confidence": 0.9},
        {"norm_value": 1200.0, "currency": "USD", "period": "FY2023", "confidence": 0.9},
    )
    assert rel_contra == "contradicts"
    assert "R4:value_mismatch" in r_contra
    assert "differ by 20.0%" in exp_contra or "differ by 16.7%" in exp_contra
    assert "no transformation explains the gap" in exp_contra

    # Convertible FX: 100 USD vs ~8333.33 INR
    rel_fx, exp_fx, r_fx, _ = reconcile_pair(
        {"norm_value": 100.0, "currency": "USD", "period": "FY2023", "confidence": 0.9},
        {"norm_value": 8333.33, "currency": "INR", "period": "FY2023", "confidence": 0.9},
    )
    assert rel_fx == "corroborates"
    assert any("R3:FX" in rule for rule in r_fx)

    # Percentage vs fraction conversion: 0.25 count vs 25 pct
    rel_pct, exp_pct, r_pct, _ = reconcile_pair(
        {"norm_value": 25.0, "norm_unit": "pct", "period": "FY2023", "confidence": 0.9},
        {"norm_value": 0.25, "norm_unit": "count", "period": "FY2023", "confidence": 0.9},
    )
    assert rel_pct == "corroborates"
    assert "R3:fraction_to_pct" in r_pct

    print("✓ test_r3_and_r4_numeric_corroboration_and_contradiction passed")


def test_r5_non_numeric_opposition_and_string_match():
    """Verify R5 opposition verb mapping and string / address matching."""
    # Opposition verbs: resigned vs continues
    rel_opp, exp_opp, r_opp, _ = reconcile_pair(
        {"raw_value": "John Doe resigned as CFO", "confidence": 0.9},
        {"raw_value": "John Doe continues as CFO", "confidence": 0.9},
    )
    assert rel_opp == "contradicts"
    assert any("R5:verb_opposition" in rule for rule in r_opp)
    assert "Direct opposition detected" in exp_opp

    # Opposition: stepped down vs appointed
    rel_opp2, exp_opp2, r_opp2, _ = reconcile_pair(
        {"raw_value": "Jane Smith stepped down from the board", "confidence": 0.9},
        {"raw_value": "Jane Smith was appointed to the board", "confidence": 0.9},
    )
    assert rel_opp2 == "contradicts"
    assert any("R5:verb_opposition" in rule for rule in r_opp2)

    # Address match with postal code
    rel_addr, exp_addr, r_addr, _ = reconcile_pair(
        {"raw_value": "Registered Office: Bandra Kurla Complex, Mumbai 400051", "confidence": 0.9},
        {"raw_value": "BKC, Mumbai - 400051, Maharashtra", "confidence": 0.9},
    )
    assert rel_addr == "corroborates"
    assert "R5:string_match" in r_addr

    # Unmatched non-numeric text -> needs_review
    rel_diff, exp_diff, r_diff, _ = reconcile_pair(
        {"raw_value": "Company manufactures electric automobiles", "confidence": 0.9},
        {"raw_value": "Company produces solar power equipment", "confidence": 0.9},
    )
    assert rel_diff == "needs_review"
    assert "R5:unmatched_text" in r_diff

    print("✓ test_r5_non_numeric_opposition_and_string_match passed")


def test_incremental_reconciliation_and_audit():
    """Verify that reconcile_document only reconciles candidate pairs for the target document and audits every relation."""
    doc_id = "doc-new-4"
    fact_new = {"id": str(uuid.uuid4()), "document_id": doc_id, "norm_value": 100, "period": "FY2023", "confidence": 0.9}
    fact_old = {"id": str(uuid.uuid4()), "document_id": "doc-old-1", "norm_value": 100, "period": "FY2023", "confidence": 0.9}

    audit_records = []
    inserted_relations = []

    def mock_get_candidates(document_id, semantic_threshold):
        assert document_id == doc_id
        return [(fact_new, fact_old)]

    def mock_insert_relation(fact_a, fact_b, relation, explanation, rules_applied, confidence):
        rel = {
            "id": str(uuid.uuid4()),
            "fact_a": fact_a,
            "fact_b": fact_b,
            "relation": relation,
            "explanation": explanation,
            "rules_applied": rules_applied,
            "confidence": confidence,
        }
        inserted_relations.append(rel)
        return rel

    def mock_audit(action, target=None, meta=None):
        audit_records.append((action, target, meta))

    with (
        patch("api.db.get_candidate_pairs_for_reconciliation", side_effect=mock_get_candidates),
        patch("api.db.insert_fact_relation", side_effect=mock_insert_relation),
        patch("api.db.audit", side_effect=mock_audit),
    ):
        relations = reconcile_document(doc_id)
        assert len(relations) == 1
        assert relations[0]["relation"] == "corroborates"

        # Audit contains action='reconcile' with rule_path and pair_ids
        rec_audits = [a for a in audit_records if a[0] == "reconcile"]
        assert len(rec_audits) == 1
        assert "rule_path" in rec_audits[0][2]
        assert "pair_ids" in rec_audits[0][2]
        assert rec_audits[0][2]["pair_ids"] == [str(fact_new["id"]), str(fact_old["id"])]

    print("✓ test_incremental_reconciliation_and_audit passed")


if __name__ == "__main__":
    test_constants()
    test_r1_either_confidence_low()
    test_r2_context_axes_differ()
    test_r3_and_r4_numeric_corroboration_and_contradiction()
    test_r5_non_numeric_opposition_and_string_match()
    test_incremental_reconciliation_and_audit()
    print("\n🎉 ALL RECONCILIATION TESTS PASSED SUCCESSFULLY!")
