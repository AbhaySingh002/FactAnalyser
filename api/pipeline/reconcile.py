"""Deterministic pairwise cross-document reconciliation producing fact relations with audited reasoning.

Evaluates facts across documents to determine:
- corroborates
- contradicts
- contextual_variance
- needs_review

Rules:
R1: Low confidence on either side (< 0.5) -> needs_review
R2: Differing context axes (period, scope, entity, unconvertible unit/currency) -> contextual_variance
R3: Convertible units (FX rates, percentage vs fraction) -> convert first
R4: Same context numeric comparison: within TOL(0.01) -> corroborates, else contradicts
R5: Non-numeric claims: string equality / address postal-match / rapidfuzz > 90 -> corroborates;
    opposition verb set -> contradicts; else needs_review
"""

from __future__ import annotations

import re
from rapidfuzz import fuzz

from .. import db

# ── Documented Constants & Thresholds ────────────────────────────────
TOL = 0.01  # 1% relative tolerance
TOLERANCE = TOL
SEMANTIC_SWEEP_THRESHOLD = 0.86

FX_RATES = {
    "USD": 1.0,
    "INR": 0.012,       # ~83.3 INR per USD
    "EUR": 1.08,
    "GBP": 1.27,
    "JPY": 0.0067,
    "CNY": 0.14,
}
FX_RATES_TO_USD = FX_RATES

OPPOSITION_PAIRS: list[tuple[set[str], set[str]]] = [
    (
        {"resigned", "ceased", "stepped down", "inactive", "rejected", "terminated"},
        {"active", "appointed", "continues", "approved", "renewed"},
    ),
    (
        {"false", "no", "loss", "decrease"},
        {"true", "yes", "profit", "increase"},
    ),
]


def _detect_opposition(text_a: str, text_b: str) -> tuple[str, str] | None:
    """Detect direct opposition between two claim texts using defined verb/polarity pairs."""
    ta = text_a.lower()
    tb = text_b.lower()
    for neg_set, pos_set in OPPOSITION_PAIRS:
        neg_a = any(re.search(rf"\b{re.escape(w)}\b", ta) for w in neg_set)
        pos_a = any(re.search(rf"\b{re.escape(w)}\b", ta) for w in pos_set)
        neg_b = any(re.search(rf"\b{re.escape(w)}\b", tb) for w in neg_set)
        pos_b = any(re.search(rf"\b{re.escape(w)}\b", tb) for w in pos_set)

        if (neg_a and pos_b) or (pos_a and neg_b):
            wa = next((w for w in (neg_set | pos_set) if re.search(rf"\b{re.escape(w)}\b", ta)), "negative")
            wb = next((w for w in (neg_set | pos_set) if re.search(rf"\b{re.escape(w)}\b", tb)), "positive")
            return wa, wb
    return None


def reconcile_pair(fact_a: dict, fact_b: dict) -> tuple[str, str, list[str], float]:
    """Evaluate two facts through deterministic rules R1..R5.

    Returns (relation, explanation, rules_applied, confidence).
    """
    conf_a = float(fact_a.get("confidence") or 1.0)
    conf_b = float(fact_b.get("confidence") or 1.0)
    rel_conf = round(min(conf_a, conf_b), 2)
    rules_applied: list[str] = []

    # ── R1: Low-confidence extraction on either side ─────────────────
    if conf_a < 0.5 or conf_b < 0.5:
        rules_applied.append("R1:low_confidence")
        if conf_a < 0.5 and conf_b < 0.5:
            explanation = f"Low confidence extraction on both sides (fact A: {conf_a:.2f}, fact B: {conf_b:.2f})"
        elif conf_a < 0.5:
            explanation = f"Low confidence extraction on fact A ({conf_a:.2f})"
        else:
            explanation = f"Low confidence extraction on fact B ({conf_b:.2f})"
        return "needs_review", explanation, rules_applied, rel_conf

    # ── R2 & R3: Context axis differences and unit conversions ───────
    diff_axes: list[str] = []

    p_a = (fact_a.get("period") or "").strip().upper()
    p_b = (fact_b.get("period") or "").strip().upper()
    if p_a and p_b and p_a != p_b:
        diff_axes.append(f"periods differ: {p_a} vs {p_b}")
        rules_applied.append("R2:context_diff:period")

    s_a = (fact_a.get("scope") or "").strip().lower()
    s_b = (fact_b.get("scope") or "").strip().lower()
    if s_a and s_b and s_a != s_b:
        diff_axes.append(f"scopes differ: {s_a} vs {s_b}")
        rules_applied.append("R2:context_diff:scope")

    e_a = (fact_a.get("entity_canon") or "").strip().lower()
    e_b = (fact_b.get("entity_canon") or "").strip().lower()
    if e_a and e_b and e_a != e_b:
        diff_axes.append(f"entities differ: {e_a} vs {e_b}")
        rules_applied.append("R2:context_diff:entity")

    val_a = fact_a.get("norm_value")
    val_b = fact_b.get("norm_value")
    val_a_f = float(val_a) if val_a is not None else None
    val_b_f = float(val_b) if val_b is not None else None
    converted_b = val_b_f

    curr_a = (fact_a.get("currency") or "").strip().upper()
    curr_b = (fact_b.get("currency") or "").strip().upper()
    unit_a = (fact_a.get("norm_unit") or "").strip().lower()
    unit_b = (fact_b.get("norm_unit") or "").strip().lower()

    if val_a_f is not None and val_b_f is not None:
        # Currency conversion
        if curr_a and curr_b and curr_a != curr_b:
            if curr_a in FX_RATES and curr_b in FX_RATES:
                fx_rate = FX_RATES[curr_b] / FX_RATES[curr_a]
                converted_b = val_b_f * fx_rate
                rules_applied.append(f"R3:FX:{curr_b}->{curr_a}@{fx_rate:.4f}")
            else:
                diff_axes.append(f"currencies differ without convertible FX rate: {curr_a} vs {curr_b}")
                rules_applied.append("R2:context_diff:currency")

        # Percentage vs fraction conversion
        if unit_a != unit_b:
            if unit_a == "pct" and unit_b in ("count", None, "text", "") and 0 <= val_b_f <= 1.0:
                converted_b = val_b_f * 100.0
                rules_applied.append("R3:fraction_to_pct")
            elif unit_b == "pct" and unit_a in ("count", None, "text", "") and 0 <= val_a_f <= 1.0:
                val_a_f = val_a_f * 100.0
                rules_applied.append("R3:fraction_to_pct")
            elif unit_a and unit_b:
                diff_axes.append(f"units differ: {unit_a} vs {unit_b}")
                rules_applied.append("R2:context_diff:unit")

    # If any context axes differ -> contextual_variance
    if diff_axes:
        explanation = f"Contextual variance: {'; '.join(diff_axes)}; values not compared"
        return "contextual_variance", explanation, rules_applied, rel_conf

    # ── R4: Same context, numeric comparison ─────────────────────────
    if val_a_f is not None and converted_b is not None:
        denom = max(abs(val_a_f), abs(converted_b), 1e-9)
        rel_delta = abs(val_a_f - converted_b) / denom

        if rel_delta <= TOL:
            rules_applied.append("R4:tolerance_match")
            explanation = (
                f"Values match within 1% tolerance after unit normalization "
                f"({val_a_f:g} vs {converted_b:g})"
            )
            return "corroborates", explanation, rules_applied, rel_conf
        else:
            rules_applied.append("R4:value_mismatch")
            explanation = (
                f"Contradiction: same entity, period, scope; values differ by "
                f"{rel_delta * 100:.1f}%; no transformation explains the gap ({val_a_f:g} vs {converted_b:g})"
            )
            return "contradicts", explanation, rules_applied, rel_conf

    # ── R5: Non-numeric claims ───────────────────────────────────────
    raw_a = (fact_a.get("raw_value") or fact_a.get("quote") or "").strip().lower()
    raw_b = (fact_b.get("raw_value") or fact_b.get("quote") or "").strip().lower()

    opp = _detect_opposition(raw_a, raw_b)
    if opp:
        wa, wb = opp
        rules_applied.append(f"R5:verb_opposition:{wa}_vs_{wb}")
        return "contradicts", f"Direct opposition detected ('{wa}' vs '{wb}')", rules_applied, rel_conf

    postal_a = re.findall(r"\b\d{5,6}\b", raw_a)
    postal_b = re.findall(r"\b\d{5,6}\b", raw_b)
    postal_match = bool(postal_a and postal_b and set(postal_a) & set(postal_b))

    sim = fuzz.token_sort_ratio(raw_a, raw_b)
    if raw_a == raw_b or sim > 90 or postal_match:
        rules_applied.append("R5:string_match")
        return "corroborates", f"Non-numeric claims corroborate: matching text or address (similarity {sim:.1f}%)", rules_applied, rel_conf

    rules_applied.append("R5:unmatched_text")
    return "needs_review", f"Needs review: non-numeric claims differ without direct opposition ('{raw_a[:40]}' vs '{raw_b[:40]}')", rules_applied, rel_conf


def reconcile_document(document_id: str) -> list[dict]:
    """Incrementally reconcile facts of document_id against all existing facts."""
    candidate_pairs = db.get_candidate_pairs_for_reconciliation(
        document_id,
        semantic_threshold=SEMANTIC_SWEEP_THRESHOLD,
    )
    relations_created: list[dict] = []

    for fa, fb in candidate_pairs:
        relation, explanation, rules_applied, conf = reconcile_pair(fa, fb)
        rel = db.insert_fact_relation(
            fact_a=fa["id"],
            fact_b=fb["id"],
            relation=relation,
            explanation=explanation,
            rules_applied=rules_applied,
            confidence=conf,
        )
        relations_created.append(rel)

        db.audit(
            "reconcile",
            target={"relation_id": str(rel["id"]) if rel else None, "document_id": str(document_id)},
            meta={
                "rule_path": rules_applied,
                "pair_ids": [str(fa["id"]), str(fb["id"])],
                "relation": relation,
                "confidence": conf,
            },
        )

    db.audit(
        "reconcile.summary",
        target={"document_id": str(document_id)},
        meta={
            "pairs_evaluated": len(candidate_pairs),
            "relations_created": len(relations_created),
        },
    )

    return relations_created


if __name__ == "__main__":
    # Test R1: either confidence < 0.5
    rel1, exp1, r1, _ = reconcile_pair({"confidence": 0.4}, {"confidence": 0.9})
    assert rel1 == "needs_review" and "R1:low_confidence" in r1

    rel2, exp2, r2, _ = reconcile_pair({"confidence": 0.9}, {"confidence": 0.3})
    assert rel2 == "needs_review" and "R1:low_confidence" in r2

    # Test R2: period mismatch
    rel, exp, r, _ = reconcile_pair(
        {"period": "FY2022", "norm_value": 100},
        {"period": "FY2023", "norm_value": 100},
    )
    assert rel == "contextual_variance" and "R2:context_diff:period" in r
    assert "values not compared" in exp

    # Test R3 + R4: FX rate + within 1% tolerance
    rel, exp, r, _ = reconcile_pair(
        {"period": "FY2023", "norm_value": 100.0, "currency": "USD"},
        {"period": "FY2023", "norm_value": 8333.33, "currency": "INR"},
    )
    assert rel == "corroborates" and any("R3:FX" in x for x in r)

    # Test R4: numeric contradiction
    rel, exp, r, _ = reconcile_pair(
        {"period": "FY2023", "norm_value": 100.0},
        {"period": "FY2023", "norm_value": 150.0},
    )
    assert rel == "contradicts" and "R4:value_mismatch" in r

    # Test R5: opposition verb
    rel, exp, r, _ = reconcile_pair(
        {"raw_value": "Director resigned from office"},
        {"raw_value": "Director continues in office"},
    )
    assert rel == "contradicts" and any("R5:verb_opposition" in x for x in r)

    # Test R5: address match
    rel, exp, r, _ = reconcile_pair(
        {"raw_value": "123 MG Road, Bengaluru 560001"},
        {"raw_value": "123 M.G. Road, Bangalore 560001"},
    )
    assert rel == "corroborates" and "R5:string_match" in r

    print("✓ reconcile self-check passed")
