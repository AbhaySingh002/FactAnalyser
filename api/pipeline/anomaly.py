"""Statistical anomaly detection engine — all deterministic, no LLM.

Detects:
- Benford's Law violations (first-digit distribution)
- Z-score outliers (>3σ from group mean)
- Period-over-period swings (>50% change)
- Cross-footing mismatches (line items don't sum to total)

Each finding auto-creates a review_queue entry.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, asdict
from decimal import Decimal

from .. import db


# ── Benford's Law ────────────────────────────────────────────────────

BENFORD_EXPECTED = {
    1: 0.301, 2: 0.176, 3: 0.125, 4: 0.097,
    5: 0.079, 6: 0.067, 7: 0.058, 8: 0.051, 9: 0.046,
}


@dataclass
class AnomalyFinding:
    fact_id: str | None
    document_id: str
    anomaly_type: str       # 'benford', 'zscore', 'period_swing', 'cross_foot'
    severity: str           # 'low', 'medium', 'high'
    description: str
    details: dict


def _first_digit(val: float) -> int | None:
    """Extract leading non-zero digit."""
    if val == 0:
        return None
    s = f"{abs(val):.15g}"
    for ch in s:
        if ch.isdigit() and ch != "0":
            return int(ch)
    return None


def check_benfords_law(document_id: str) -> AnomalyFinding | None:
    """Check first-digit distribution of all numeric facts in a document against Benford's Law."""
    facts = db.get_facts_for_document(document_id)
    digits: list[int] = []

    for f in facts:
        nv = f.get("norm_value")
        if nv is not None:
            try:
                d = _first_digit(float(nv))
                if d:
                    digits.append(d)
            except (ValueError, TypeError):
                pass

    if len(digits) < 20:
        return None  # Too few data points for meaningful test

    # Observed distribution
    n = len(digits)
    observed: dict[int, float] = {}
    for d in range(1, 10):
        observed[d] = digits.count(d) / n

    # Chi-squared test (using counts for proper sensitivity)
    chi_sq = 0.0
    for d in range(1, 10):
        expected_count = BENFORD_EXPECTED[d] * n
        observed_count = digits.count(d)
        chi_sq += ((observed_count - expected_count) ** 2) / expected_count

    # Critical value for 8 df at p=0.05 is ~15.5
    if chi_sq > 15.5:
        severity = "high" if chi_sq > 25 else "medium"
        worst_digits = sorted(
            range(1, 10),
            key=lambda d: abs(observed.get(d, 0) - BENFORD_EXPECTED[d]),
            reverse=True,
        )[:3]
        return AnomalyFinding(
            fact_id=None,
            document_id=document_id,
            anomaly_type="benford",
            severity=severity,
            description=(
                f"Benford's Law violation detected (χ²={chi_sq:.2f}, p<0.05). "
                f"Digits {worst_digits} deviate most from expected distribution."
            ),
            details={
                "chi_squared": round(chi_sq, 4),
                "sample_size": n,
                "observed": {str(k): round(v, 4) for k, v in observed.items()},
                "expected": {str(k): round(v, 4) for k, v in BENFORD_EXPECTED.items()},
                "worst_digits": worst_digits,
            },
        )
    return None


def check_zscore_outliers(document_id: str, threshold: float = 3.0) -> list[AnomalyFinding]:
    """Flag facts with norm_value > threshold σ from the group mean."""
    facts = db.get_facts_for_document(document_id)

    # Group by (entity_canon, attribute_canon)
    groups: dict[str, list[dict]] = {}
    for f in facts:
        ec = f.get("entity_canon") or ""
        ac = f.get("attribute_canon") or ""
        nv = f.get("norm_value")
        if nv is not None and ec and ac:
            key = f"{ec}|{ac}"
            groups.setdefault(key, []).append(f)

    findings: list[AnomalyFinding] = []
    for key, group_facts in groups.items():
        values = []
        for gf in group_facts:
            try:
                values.append(float(gf["norm_value"]))
            except (ValueError, TypeError):
                pass

        if len(values) < 3:
            continue

        mean = statistics.mean(values)
        stdev = statistics.stdev(values)
        if stdev < 1e-9:
            continue

        for gf in group_facts:
            try:
                val = float(gf["norm_value"])
            except (ValueError, TypeError):
                continue

            z = abs(val - mean) / stdev
            if z > threshold:
                findings.append(AnomalyFinding(
                    fact_id=str(gf["id"]),
                    document_id=document_id,
                    anomaly_type="zscore",
                    severity="high" if z > 5 else "medium",
                    description=(
                        f"Statistical outlier: {gf.get('entity_canon')} {gf.get('attribute_canon')} = "
                        f"{gf.get('raw_value')} (z-score={z:.2f}, mean={mean:.2f}, stdev={stdev:.2f})"
                    ),
                    details={
                        "z_score": round(z, 4),
                        "value": val,
                        "group_mean": round(mean, 4),
                        "group_stdev": round(stdev, 4),
                        "group_key": key,
                        "group_size": len(values),
                    },
                ))

    return findings


def check_period_swings(document_id: str, swing_threshold: float = 0.50) -> list[AnomalyFinding]:
    """Flag facts with >50% swing in the same metric across consecutive periods."""
    facts = db.get_facts_for_document(document_id)

    # Group by (entity_canon, attribute_canon)
    groups: dict[str, list[dict]] = {}
    for f in facts:
        ec = f.get("entity_canon") or ""
        ac = f.get("attribute_canon") or ""
        period = f.get("period") or ""
        nv = f.get("norm_value")
        if nv is not None and ec and ac and period:
            key = f"{ec}|{ac}"
            groups.setdefault(key, []).append(f)

    findings: list[AnomalyFinding] = []
    for key, group_facts in groups.items():
        # Sort by period string (works for FY2022, FY2023, 2022, 2023 formats)
        sorted_facts = sorted(group_facts, key=lambda f: f.get("period") or "")

        for i in range(1, len(sorted_facts)):
            prev_f = sorted_facts[i - 1]
            curr_f = sorted_facts[i]
            try:
                prev_val = float(prev_f["norm_value"])
                curr_val = float(curr_f["norm_value"])
            except (ValueError, TypeError):
                continue

            if abs(prev_val) < 1e-9:
                continue

            pct_change = abs(curr_val - prev_val) / abs(prev_val)
            if pct_change > swing_threshold:
                findings.append(AnomalyFinding(
                    fact_id=str(curr_f["id"]),
                    document_id=document_id,
                    anomaly_type="period_swing",
                    severity="high" if pct_change > 1.0 else "medium",
                    description=(
                        f"Period-over-period swing: {curr_f.get('entity_canon')} {curr_f.get('attribute_canon')} "
                        f"changed {pct_change * 100:.1f}% from {prev_f.get('period')} ({prev_val:g}) "
                        f"to {curr_f.get('period')} ({curr_val:g})"
                    ),
                    details={
                        "pct_change": round(pct_change * 100, 2),
                        "previous_period": prev_f.get("period"),
                        "previous_value": prev_val,
                        "current_period": curr_f.get("period"),
                        "current_value": curr_val,
                        "previous_fact_id": str(prev_f["id"]),
                    },
                ))

    return findings


# ── 4. Cross-Footing Verification ────────────────────────────────────

CROSS_FOOT_PATTERNS = [
    # (tuple_of_line_item_attributes, total_attribute)
    (("current_assets", "non_current_assets"), "total_assets"),
    (("current_liabilities", "non_current_liabilities"), "total_liabilities"),
    (("total_liabilities", "total_equity"), "total_assets"),
    (("total_liabilities", "shareholders_equity"), "total_assets"),
]


def check_cross_footing(document_id: str, tolerance: float = 0.01) -> list[AnomalyFinding]:
    """Auto-discover line-item to total relationships in facts and verify sums."""
    facts = db.get_facts_for_document(document_id)
    findings: list[AnomalyFinding] = []

    # Group by (entity_canon, period)
    entity_period_facts: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for f in facts:
        nv = f.get("norm_value")
        period = f.get("period")
        if nv is not None and period:
            key = (f.get("entity_canon") or "", str(period))
            entity_period_facts[key].append(f)

    for (ec, period), p_facts in entity_period_facts.items():
        facts_by_attr: dict[str, dict] = {
            f.get("attribute_canon", "").lower(): f for f in p_facts
        }

        for line_attrs, total_attr in CROSS_FOOT_PATTERNS:
            if total_attr in facts_by_attr and all(la in facts_by_attr for la in line_attrs):
                total_f = facts_by_attr[total_attr]
                line_fs = [facts_by_attr[la] for la in line_attrs]
                try:
                    total_val = float(total_f["norm_value"])
                    line_vals = [float(lf["norm_value"]) for lf in line_fs]
                except (ValueError, TypeError):
                    continue

                if abs(total_val) < 1e-9:
                    continue

                computed = sum(line_vals)
                diff = abs(computed - total_val)
                rel_diff = diff / max(abs(total_val), 1e-9)

                if rel_diff > tolerance:
                    severity = "critical" if rel_diff > 0.20 else "high"
                    findings.append(AnomalyFinding(
                        fact_id=str(total_f["id"]),
                        document_id=document_id,
                        anomaly_type="cross_foot",
                        severity=severity,
                        description=(
                            f"Cross-footing mismatch for {ec or 'Entity'} ({period}): "
                            f"sum of {', '.join(line_attrs)} is {computed:g}, but "
                            f"{total_attr} is reported as {total_val:g} (diff {rel_diff * 100:.1f}%)"
                        ),
                        details={
                            "computed_sum": round(computed, 4),
                            "reported_total": round(total_val, 4),
                            "relative_diff_pct": round(rel_diff * 100, 2),
                            "line_items": {la: float(facts_by_attr[la]["norm_value"]) for la in line_attrs},
                            "total_attribute": total_attr,
                            "period": period,
                            "line_fact_ids": [str(lf["id"]) for lf in line_fs],
                        },
                    ))

    return findings


def convert_to_finding_dict(af: AnomalyFinding) -> dict:
    """Convert an AnomalyFinding dataclass to a dict suitable for the findings table."""
    return {
        "category": "computational_error" if af.anomaly_type == "cross_foot" else "anomaly",
        "severity": af.severity,
        "title": f"Anomaly ({af.anomaly_type}): {af.description[:80]}",
        "description": af.description,
        "fact_ids": [af.fact_id] if af.fact_id else [],
        "document_ids": [af.document_id],
        "details": af.details,
    }


# ── Orchestrator ─────────────────────────────────────────────────────

def run_anomaly_checks(document_id: str) -> list[AnomalyFinding]:
    """Run all anomaly detection checks for a document and return findings."""
    findings: list[AnomalyFinding] = []

    # 1. Benford's Law
    benford = check_benfords_law(document_id)
    if benford:
        findings.append(benford)

    # 2. Z-score outliers
    findings.extend(check_zscore_outliers(document_id))

    # 3. Period-over-period swings
    findings.extend(check_period_swings(document_id))

    # 4. Cross-footing line item checks
    findings.extend(check_cross_footing(document_id))

    # Audit log
    db.audit(
        "anomaly_check",
        target={"document_id": str(document_id)},
        meta={
            "findings_count": len(findings),
            "types": list(set(f.anomaly_type for f in findings)),
        },
    )

    return findings


def populate_review_queue_from_anomalies(
    document_id: str,
    findings: list[AnomalyFinding],
) -> int:
    """Create review_queue entries from anomaly findings. Returns count created."""
    created = 0
    for finding in findings:
        if finding.fact_id:
            _create_review_item(
                fact_id=finding.fact_id,
                reason=f"anomaly:{finding.anomaly_type}",
                details=finding.description,
            )
            created += 1
    return created


def populate_review_queue_from_pipeline(document_id: str) -> int:
    """Auto-populate review queue from low-confidence facts and contradictions."""
    created = 0

    # 1. Low-confidence facts
    facts = db.get_facts_for_document(document_id)
    for f in facts:
        conf = float(f.get("confidence") or 1.0)
        if conf < 0.5:
            _create_review_item(
                fact_id=str(f["id"]),
                reason="low_confidence",
                details=f"Extraction confidence {conf:.2f} below 0.5 threshold",
            )
            created += 1

    # 2. Contradictions from reconciliation
    relations = db.get_relations(relation_type="contradicts", document_id=document_id)
    for r in relations:
        _create_review_item(
            fact_id=str(r.get("a_id")),
            relation_id=str(r.get("id")),
            reason="contradiction",
            details=r.get("explanation") or "Cross-document contradiction detected",
        )
        created += 1

    return created


def _create_review_item(
    fact_id: str,
    reason: str,
    details: str = "",
    relation_id: str | None = None,
):
    """Insert into review_queue (idempotent — skips if pending entry exists)."""
    with db.pool.connection() as conn:
        existing = conn.execute(
            """SELECT id FROM review_queue
               WHERE fact_id = %s AND reason = %s AND status = 'pending'""",
            (str(fact_id), reason),
        ).fetchone()
        if existing:
            return

        conn.execute(
            """INSERT INTO review_queue (fact_id, relation_id, reason, status, decision)
               VALUES (%s, %s, %s, 'pending', %s)""",
            (str(fact_id), str(relation_id) if relation_id else None, reason, details),
        )
