"""Financial intelligence analysis engine — Phase 2.

Orchestrates cross-document tie-outs, contradiction detection, anomaly integration,
missing disclosure detection, and finding generation with severity classification.

All arithmetic is deterministic (Python Decimal). LLM is used ONLY for generating
human-readable explanations after deterministic findings are produced.

Entry point: run_analysis(document_ids=None) → list[dict]
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from .. import db
from .reconcile import reconcile_pair
from .anomaly import run_anomaly_checks, AnomalyFinding
from . import models

logger = logging.getLogger("analyze")

# ── Severity thresholds ──────────────────────────────────────────────

# ponytail: simple thresholds, add config when users need tuning
CRITICAL_THRESHOLD = 0.50   # >50% relative delta
HIGH_THRESHOLD = 0.10       # >10%
MEDIUM_THRESHOLD = 0.05     # >5%
# below 5% → low

# Key financial metrics that should appear across documents
CORE_FINANCIAL_METRICS = {
    "total_revenue", "revenue", "net_income", "net_profit", "total_assets",
    "total_liabilities", "total_equity", "shareholders_equity",
    "operating_profit", "ebitda", "cash_and_cash_equivalents",
    "profit_before_tax", "profit_after_tax", "earnings_per_share",
    "cost_of_goods_sold", "gross_profit", "depreciation_and_amortization",
}


def _to_decimal(val) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _severity_from_delta(rel_delta: float) -> str:
    """Classify severity from relative delta magnitude."""
    if rel_delta > CRITICAL_THRESHOLD:
        return "critical"
    elif rel_delta > HIGH_THRESHOLD:
        return "high"
    elif rel_delta > MEDIUM_THRESHOLD:
        return "medium"
    return "low"


# ── 1. Cross-Document Tie-Out Analysis ───────────────────────────────

def _analyze_cross_document_tieouts(
    facts: list[dict],
    document_ids: list[str] | None = None,
) -> list[dict]:
    """Compare identical (entity, metric, period) facts across different documents.

    Uses the existing reconcile_pair() engine for deterministic comparison,
    then generates structured findings from the results.
    """
    # Group facts by (entity_canon, attribute_canon)
    groups: dict[str, list[dict]] = defaultdict(list)
    for f in facts:
        key = f"{f.get('entity_canon', '')}|{f.get('attribute_canon', '')}"
        groups[key].append(f)

    findings: list[dict] = []

    for key, group_facts in groups.items():
        if len(group_facts) < 2:
            continue

        # Get unique document_ids in this group
        doc_ids_in_group = set(str(f["document_id"]) for f in group_facts)
        if len(doc_ids_in_group) < 2:
            # Intra-document: same metric appears twice in same doc (potential internal inconsistency)
            _check_intra_document_consistency(group_facts, findings)
            continue

        # Collect periods present per document to avoid redundant cross-period comparisons
        doc_periods: dict[str, set[str]] = defaultdict(set)
        for f in group_facts:
            p = (f.get("period") or "").strip().upper()
            if p:
                doc_periods[str(f["document_id"])].add(p)

        # Cross-document comparison: compare each pair across documents
        case_id = str(uuid.uuid4())
        compared = set()

        for i, fa in enumerate(group_facts):
            for j, fb in enumerate(group_facts):
                if i >= j:
                    continue
                doc_a = str(fa["document_id"])
                doc_b = str(fb["document_id"])
                if doc_a == doc_b:
                    continue

                pa = (fa.get("period") or "").strip().upper()
                pb = (fb.get("period") or "").strip().upper()

                # If periods differ but either document has a matching period fact in the other doc,
                # skip cross-period noise (the matching period pair will handle the tie-out).
                if pa and pb and pa != pb:
                    if (pa in doc_periods[doc_b]) or (pb in doc_periods[doc_a]):
                        continue

                pair_key = tuple(sorted([str(fa["id"]), str(fb["id"])]))
                if pair_key in compared:
                    continue
                compared.add(pair_key)

                relation, explanation, rules_applied, conf = reconcile_pair(fa, fb)

                if relation == "contradicts":
                    val_a = _to_decimal(fa.get("norm_value"))
                    val_b = _to_decimal(fb.get("norm_value"))
                    rel_delta = 0.0
                    if val_a is not None and val_b is not None:
                        denom = max(abs(val_a), abs(val_b), Decimal("1e-9"))
                        rel_delta = float(abs(val_a - val_b) / denom)

                    findings.append({
                        "case_id": case_id,
                        "category": "contradiction",
                        "severity": _severity_from_delta(rel_delta),
                        "title": f"{fa.get('entity_canon', 'Entity')} — {fa.get('attribute_canon', 'Metric')} contradicts across documents",
                        "description": explanation,
                        "fact_ids": [str(fa["id"]), str(fb["id"])],
                        "document_ids": list(set([str(fa["document_id"]), str(fb["document_id"])])),
                        "details": {
                            "rules_applied": rules_applied,
                            "confidence": conf,
                            "rel_delta_pct": round(rel_delta * 100, 2),
                            "value_a": str(fa.get("norm_value")),
                            "value_b": str(fb.get("norm_value")),
                            "period": fa.get("period"),
                            "file_a": fa.get("filename"),
                            "file_b": fb.get("filename"),
                            "page_a": fa.get("page"),
                            "page_b": fb.get("page"),
                        },
                    })

                elif relation == "contextual_variance":
                    findings.append({
                        "case_id": case_id,
                        "category": "contextual_variance",
                        "severity": "info",
                        "title": f"{fa.get('entity_canon', 'Entity')} — {fa.get('attribute_canon', 'Metric')} differs by context",
                        "description": explanation,
                        "fact_ids": [str(fa["id"]), str(fb["id"])],
                        "document_ids": list(set([str(fa["document_id"]), str(fb["document_id"])])),
                        "details": {
                            "rules_applied": rules_applied,
                            "confidence": conf,
                            "file_a": fa.get("filename"),
                            "file_b": fb.get("filename"),
                        },
                    })

                elif relation == "needs_review":
                    findings.append({
                        "case_id": case_id,
                        "category": "contradiction",
                        "severity": "low",
                        "title": f"{fa.get('entity_canon', 'Entity')} — {fa.get('attribute_canon', 'Metric')} needs manual review",
                        "description": explanation,
                        "fact_ids": [str(fa["id"]), str(fb["id"])],
                        "document_ids": list(set([str(fa["document_id"]), str(fb["document_id"])])),
                        "details": {
                            "rules_applied": rules_applied,
                            "confidence": conf,
                        },
                    })
                # corroborates → no finding needed (good news is not a finding)

    return findings


def _check_intra_document_consistency(
    group_facts: list[dict],
    findings: list[dict],
):
    """Check for internal inconsistencies within a single document."""
    if len(group_facts) < 2:
        return

    # Compare numeric values within the same document
    values: list[tuple[dict, Decimal]] = []
    for f in group_facts:
        v = _to_decimal(f.get("norm_value"))
        if v is not None:
            values.append((f, v))

    if len(values) < 2:
        return

    # Check if any pair differs beyond tolerance (1%)
    for i, (fa, va) in enumerate(values):
        for j, (fb, vb) in enumerate(values):
            if i >= j:
                continue
            # Only compare if periods and scopes match
            pa = (fa.get("period") or "").strip().upper()
            pb = (fb.get("period") or "").strip().upper()
            if pa and pb and pa != pb:
                continue
            sa = (fa.get("scope") or "").strip().lower()
            sb = (fb.get("scope") or "").strip().lower()
            if sa and sb and sa != sb:
                continue

            denom = max(abs(va), abs(vb), Decimal("1e-9"))
            rel_delta = float(abs(va - vb) / denom)
            if rel_delta > 0.01:  # >1% — internal inconsistency
                findings.append({
                    "category": "contradiction",
                    "severity": _severity_from_delta(rel_delta),
                    "title": f"Internal inconsistency: {fa.get('entity_canon')} {fa.get('attribute_canon')} reported differently on pages {fa.get('page')} and {fb.get('page')}",
                    "description": (
                        f"Same metric reported as {fa.get('raw_value')} (p.{fa.get('page')}) "
                        f"and {fb.get('raw_value')} (p.{fb.get('page')}) within the same document."
                    ),
                    "fact_ids": [str(fa["id"]), str(fb["id"])],
                    "document_ids": [str(fa["document_id"])],
                    "details": {
                        "rel_delta_pct": round(rel_delta * 100, 2),
                        "value_a": str(va),
                        "value_b": str(vb),
                        "page_a": fa.get("page"),
                        "page_b": fb.get("page"),
                    },
                })


# ── 2. Period-over-Period Analysis ───────────────────────────────────

def _analyze_period_changes(facts: list[dict]) -> list[dict]:
    """Detect unusual period-over-period changes across the entire fact base."""
    # Group by (entity_canon, attribute_canon)
    groups: dict[str, list[dict]] = defaultdict(list)
    for f in facts:
        nv = f.get("norm_value")
        period = f.get("period")
        if nv is not None and period:
            key = f"{f.get('entity_canon', '')}|{f.get('attribute_canon', '')}"
            groups[key].append(f)

    findings: list[dict] = []

    for key, gf in groups.items():
        sorted_facts = sorted(gf, key=lambda f: f.get("period") or "")

        for i in range(1, len(sorted_facts)):
            prev = sorted_facts[i - 1]
            curr = sorted_facts[i]
            try:
                prev_val = float(prev["norm_value"])
                curr_val = float(curr["norm_value"])
            except (ValueError, TypeError):
                continue

            if abs(prev_val) < 1e-9:
                continue

            pct_change = (curr_val - prev_val) / abs(prev_val)
            abs_pct = abs(pct_change)

            if abs_pct > 0.50:  # >50% swing is notable
                severity = "critical" if abs_pct > 1.0 else "high" if abs_pct > 0.50 else "medium"
                direction = "increased" if pct_change > 0 else "decreased"
                findings.append({
                    "category": "anomaly",
                    "severity": severity,
                    "title": (
                        f"{curr.get('entity_canon')} {curr.get('attribute_canon')} "
                        f"{direction} {abs_pct * 100:.1f}% from {prev.get('period')} to {curr.get('period')}"
                    ),
                    "description": (
                        f"Period-over-period change: {prev.get('raw_value')} ({prev.get('period')}) → "
                        f"{curr.get('raw_value')} ({curr.get('period')}). "
                        f"This {abs_pct * 100:.1f}% {direction[:-1]}e requires investigation."
                    ),
                    "fact_ids": [str(prev["id"]), str(curr["id"])],
                    "document_ids": list(set([str(prev["document_id"]), str(curr["document_id"])])),
                    "details": {
                        "pct_change": round(pct_change * 100, 2),
                        "previous_value": prev_val,
                        "current_value": curr_val,
                        "previous_period": prev.get("period"),
                        "current_period": curr.get("period"),
                        "file_prev": prev.get("filename"),
                        "file_curr": curr.get("filename"),
                    },
                })

    return findings


# ── 3. Missing Disclosure Detection ──────────────────────────────────

def _analyze_missing_disclosures(document_ids: list[str] | None = None) -> list[dict]:
    """Detect metrics present in one document but absent from another for the same entity/period."""
    metric_rows = db.get_distinct_metrics_by_entity_period(document_ids)

    # Group by (entity, period) → list of (document_id, filename, metrics_set)
    entity_period_docs: dict[str, list[dict]] = defaultdict(list)
    for r in metric_rows:
        key = f"{r['entity_canon']}|{r['period']}"
        entity_period_docs[key].append({
            "document_id": str(r["document_id"]),
            "filename": r["filename"],
            "metrics": set(r["metrics"]),
        })

    findings: list[dict] = []

    for key, docs in entity_period_docs.items():
        if len(docs) < 2:
            continue

        entity, period = key.split("|", 1)

        # Union of all metrics across all documents
        all_metrics = set()
        for d in docs:
            all_metrics.update(d["metrics"])

        # Only flag core financial metrics
        core_in_scope = all_metrics & CORE_FINANCIAL_METRICS
        if not core_in_scope:
            continue

        for d in docs:
            missing = core_in_scope - d["metrics"]
            if not missing:
                continue

            # Check if any other document has these metrics
            providing_docs = []
            for od in docs:
                if od["document_id"] != d["document_id"]:
                    provided = missing & od["metrics"]
                    if provided:
                        providing_docs.append((od["filename"], provided))

            if not providing_docs:
                continue

            for od_filename, provided_metrics in providing_docs:
                for metric in provided_metrics:
                    findings.append({
                        "category": "missing_disclosure",
                        "severity": "medium",
                        "title": f"{entity} — {metric} missing from {d['filename']}",
                        "description": (
                            f"Metric '{metric}' for {entity} ({period}) is reported in "
                            f"{od_filename} but absent from {d['filename']}."
                        ),
                        "fact_ids": [],
                        "document_ids": [d["document_id"]],
                        "details": {
                            "entity": entity,
                            "period": period,
                            "missing_metric": metric,
                            "present_in": od_filename,
                            "absent_from": d["filename"],
                        },
                    })

    return findings


# ── 4. Anomaly Integration ───────────────────────────────────────────

def _convert_anomaly_findings(
    document_id: str,
    anomaly_findings: list[AnomalyFinding],
) -> list[dict]:
    """Convert AnomalyFinding dataclasses to findings table format."""
    converted: list[dict] = []
    for af in anomaly_findings:
        converted.append({
            "category": "anomaly",
            "severity": af.severity,
            "title": f"Statistical anomaly ({af.anomaly_type})",
            "description": af.description,
            "fact_ids": [af.fact_id] if af.fact_id else [],
            "document_ids": [document_id],
            "details": af.details,
        })
    return converted


# ── 5. AI Contextual Explanations (surgical) ─────────────────────────

def _generate_explanations(findings_to_explain: list[dict]) -> None:
    """Use LLM to generate human-readable explanations for the top findings.

    Modifies findings in-place by setting the 'explanation' key.
    Called AFTER all deterministic analysis is complete.
    """
    if not findings_to_explain:
        return

    # Only explain critical + high severity findings to save tokens
    to_explain = [
        f for f in findings_to_explain
        if f.get("severity") in ("critical", "high") and not f.get("explanation")
    ][:20]  # ponytail: cap at 20 findings per batch

    if not to_explain:
        return

    # Build a concise prompt with finding summaries
    finding_summaries = []
    for i, f in enumerate(to_explain):
        summary = (
            f"[{i+1}] Category: {f['category']}, Severity: {f['severity']}\n"
            f"    Title: {f['title']}\n"
            f"    Description: {f['description']}\n"
            f"    Details: {f.get('details', {})}"
        )
        finding_summaries.append(summary)

    prompt = (
        "You are a senior financial analyst reviewing due diligence findings.\n"
        "For each finding below, write a concise 2-3 sentence explanation that:\n"
        "1. Explains the financial significance of the discrepancy.\n"
        "2. Suggests what could cause it (restatement, reclassification, error, etc.).\n"
        "3. Recommends what an analyst should verify.\n\n"
        "Findings:\n" + "\n\n".join(finding_summaries) + "\n\n"
        "Respond with a JSON array of objects: [{\"index\": 1, \"explanation\": \"...\"}]"
    )

    try:
        raw, provider = models.complete(
            messages=prompt,
            system="You are a financial due diligence expert. Return only valid JSON.",
            temperature=0.0,
            max_tokens=2000,
        )

        import json
        # Try to parse JSON from response
        # Handle potential markdown code fences
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean
            clean = clean.rsplit("```", 1)[0] if "```" in clean else clean
        explanations = json.loads(clean)

        for exp in explanations:
            idx = exp.get("index", 0) - 1
            if 0 <= idx < len(to_explain):
                to_explain[idx]["explanation"] = exp.get("explanation", "")

    except Exception as ex:
        logger.warning(f"AI explanation generation failed (non-fatal): {ex}")
        # Findings remain without AI explanations — deterministic data is intact


# ── Orchestrator ─────────────────────────────────────────────────────

def run_analysis(document_ids: list[str] | None = None) -> list[dict]:
    """Execute the full analysis pipeline and persist findings.

    Args:
        document_ids: Scope analysis to specific documents, or None for all.

    Returns:
        List of created finding dicts.
    """
    logger.info(f"Starting analysis pipeline (scope: {document_ids or 'all documents'})")

    # 1. Fetch all facts for analysis
    facts = db.get_facts_grouped_for_analysis(document_ids)
    logger.info(f"Loaded {len(facts)} facts for analysis")

    all_findings: list[dict] = []

    # 2. Cross-document tie-outs
    tieout_findings = _analyze_cross_document_tieouts(facts, document_ids)
    all_findings.extend(tieout_findings)
    logger.info(f"Cross-document tie-outs: {len(tieout_findings)} findings")

    # 3. Period-over-period analysis
    period_findings = _analyze_period_changes(facts)
    all_findings.extend(period_findings)
    logger.info(f"Period-over-period: {len(period_findings)} findings")

    # 4. Missing disclosure detection
    missing_findings = _analyze_missing_disclosures(document_ids)
    all_findings.extend(missing_findings)
    logger.info(f"Missing disclosures: {len(missing_findings)} findings")

    # 5. Statistical anomaly integration (per-document)
    if document_ids:
        for doc_id in document_ids:
            try:
                anomalies = run_anomaly_checks(doc_id)
                converted = _convert_anomaly_findings(doc_id, anomalies)
                all_findings.extend(converted)
                logger.info(f"Anomaly checks for {doc_id}: {len(converted)} findings")
            except Exception as ex:
                logger.warning(f"Anomaly check failed for {doc_id}: {ex}")

    # 6. AI contextual explanations (surgical, non-fatal)
    try:
        _generate_explanations(all_findings)
    except Exception as ex:
        logger.warning(f"AI explanation step failed (non-fatal): {ex}")

    # 7. Persist findings
    persisted: list[dict] = []
    for f in all_findings:
        try:
            row = db.insert_finding(
                category=f["category"],
                severity=f["severity"],
                title=f["title"],
                description=f["description"],
                fact_ids=f.get("fact_ids"),
                relation_ids=f.get("relation_ids"),
                evidence_ids=f.get("evidence_ids"),
                document_ids=f.get("document_ids"),
                details=f.get("details"),
                explanation=f.get("explanation"),
                case_id=f.get("case_id"),
            )
            persisted.append(row)
        except Exception as ex:
            logger.warning(f"Failed to persist finding '{f.get('title')}': {ex}")

    # 8. Audit
    db.audit(
        "analysis.complete",
        meta={
            "document_ids": document_ids,
            "total_facts_analyzed": len(facts),
            "findings_generated": len(persisted),
            "by_category": {
                cat: sum(1 for f in persisted if f.get("category") == cat)
                for cat in {"contradiction", "anomaly", "missing_disclosure", "contextual_variance"}
            },
        },
    )

    logger.info(f"Analysis complete: {len(persisted)} findings persisted")
    return persisted


if __name__ == "__main__":
    # Self-check: verify severity classification
    assert _severity_from_delta(0.60) == "critical"
    assert _severity_from_delta(0.15) == "high"
    assert _severity_from_delta(0.08) == "medium"
    assert _severity_from_delta(0.02) == "low"
    print("✓ analyze self-check passed")

