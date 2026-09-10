"""Deterministic financial calculation engine — zero LLM involvement.

All arithmetic uses Python's decimal.Decimal for financial precision.
Every calculation stores its inputs, formula, and result for full audit replay.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import psycopg
from .. import db


# ── Built-in Financial Formulas ──────────────────────────────────────

FORMULAS: dict[str, str] = {
    "net_profit_margin": "net_income / total_revenue",
    "gross_profit_margin": "(total_revenue - cost_of_goods_sold) / total_revenue",
    "debt_to_equity": "total_debt / total_equity",
    "current_ratio": "current_assets / current_liabilities",
    "return_on_assets": "net_income / total_assets",
    "return_on_equity": "net_income / total_equity",
    "yoy_growth": "(current - previous) / abs(previous)",
    "cross_foot": "sum(line_items) == total",
}


def _to_decimal(val) -> Decimal | None:
    """Safely convert a value to Decimal."""
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _store_calculation(
    fact_id: str | None,
    formula: str,
    input_facts: list[dict],
    result: Decimal | None,
    result_unit: str | None = None,
    is_verified: bool = False,
    error: str | None = None,
) -> dict:
    """Persist a calculation record for audit trail."""
    with db.pool.connection() as conn:
        row = conn.execute(
            """INSERT INTO calculations (fact_id, formula, input_facts, result, result_unit, is_verified, error)
               VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s)
               RETURNING *""",
            (
                str(fact_id) if fact_id else None,
                formula,
                psycopg.types.json.Json(input_facts),
                float(result) if result is not None else None,
                result_unit,
                is_verified,
                error,
            ),
        ).fetchone()
        return dict(row)


def _get_fact_value(fact_id: str) -> tuple[Decimal | None, str | None]:
    """Get (norm_value, norm_unit) from a fact."""
    with db.pool.connection() as conn:
        row = conn.execute(
            "SELECT norm_value, norm_unit FROM facts WHERE id = %s",
            (str(fact_id),),
        ).fetchone()
    if not row:
        return None, None
    return _to_decimal(row["norm_value"]), row.get("norm_unit")


# ── Core Calculation Functions ───────────────────────────────────────

def calculate_ratio(
    numerator_fact_id: str,
    denominator_fact_id: str,
    formula_name: str = "ratio",
) -> dict:
    """Calculate a ratio between two facts. Returns a calculation record."""
    num_val, num_unit = _get_fact_value(numerator_fact_id)
    den_val, den_unit = _get_fact_value(denominator_fact_id)

    input_facts = [
        {"fact_id": numerator_fact_id, "label": "numerator", "value": str(num_val)},
        {"fact_id": denominator_fact_id, "label": "denominator", "value": str(den_val)},
    ]

    if num_val is None or den_val is None:
        return _store_calculation(
            fact_id=None,
            formula=FORMULAS.get(formula_name, formula_name),
            input_facts=input_facts,
            result=None,
            error="Missing input values",
        )

    if den_val == 0:
        return _store_calculation(
            fact_id=None,
            formula=FORMULAS.get(formula_name, formula_name),
            input_facts=input_facts,
            result=None,
            error="Division by zero",
        )

    result = (num_val / den_val).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    result_unit = "ratio"
    if formula_name in ("net_profit_margin", "gross_profit_margin", "return_on_assets", "return_on_equity"):
        result = (result * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        result_unit = "pct"

    return _store_calculation(
        fact_id=None,
        formula=FORMULAS.get(formula_name, formula_name),
        input_facts=input_facts,
        result=result,
        result_unit=result_unit,
    )


def cross_foot(
    line_item_fact_ids: list[str],
    expected_total_fact_id: str,
    tolerance: Decimal = Decimal("0.01"),
) -> dict:
    """Verify that line items sum to the expected total (cross-footing)."""
    line_values: list[Decimal] = []
    input_facts: list[dict] = []

    for fid in line_item_fact_ids:
        val, unit = _get_fact_value(fid)
        input_facts.append({"fact_id": fid, "label": "line_item", "value": str(val)})
        if val is not None:
            line_values.append(val)

    total_val, total_unit = _get_fact_value(expected_total_fact_id)
    input_facts.append({"fact_id": expected_total_fact_id, "label": "expected_total", "value": str(total_val)})

    if not line_values or total_val is None:
        return _store_calculation(
            fact_id=expected_total_fact_id,
            formula="cross_foot: sum(line_items) == total",
            input_facts=input_facts,
            result=None,
            error="Missing input values",
        )

    computed_sum = sum(line_values)
    diff = abs(computed_sum - total_val)
    denom = max(abs(total_val), Decimal("1e-9"))
    rel_diff = diff / denom
    is_verified = rel_diff <= tolerance

    return _store_calculation(
        fact_id=expected_total_fact_id,
        formula="cross_foot: sum(line_items) == total",
        input_facts=input_facts,
        result=computed_sum,
        result_unit=total_unit,
        is_verified=is_verified,
        error=None if is_verified else f"Mismatch: computed {computed_sum} vs expected {total_val} (diff {rel_diff * 100:.2f}%)",
    )


def calculate_growth(
    current_fact_id: str,
    previous_fact_id: str,
) -> dict:
    """Calculate year-over-year or period-over-period growth."""
    curr_val, _ = _get_fact_value(current_fact_id)
    prev_val, _ = _get_fact_value(previous_fact_id)

    input_facts = [
        {"fact_id": current_fact_id, "label": "current", "value": str(curr_val)},
        {"fact_id": previous_fact_id, "label": "previous", "value": str(prev_val)},
    ]

    if curr_val is None or prev_val is None:
        return _store_calculation(
            fact_id=current_fact_id,
            formula=FORMULAS["yoy_growth"],
            input_facts=input_facts,
            result=None,
            error="Missing input values",
        )

    if prev_val == 0:
        return _store_calculation(
            fact_id=current_fact_id,
            formula=FORMULAS["yoy_growth"],
            input_facts=input_facts,
            result=None,
            error="Previous period value is zero — infinite growth",
        )

    growth = ((curr_val - prev_val) / abs(prev_val) * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return _store_calculation(
        fact_id=current_fact_id,
        formula=FORMULAS["yoy_growth"],
        input_facts=input_facts,
        result=growth,
        result_unit="pct",
    )


def verify_calculation(calc_id: str) -> bool:
    """Re-execute a stored calculation and compare results — audit replay."""
    with db.pool.connection() as conn:
        row = conn.execute(
            "SELECT * FROM calculations WHERE id = %s", (str(calc_id),)
        ).fetchone()

    if not row:
        return False

    stored_result = _to_decimal(row.get("result"))
    if stored_result is None:
        return True  # Error calculations verify as "consistent"

    # Re-gather inputs
    input_facts = row.get("input_facts") or []
    values = {}
    for inp in input_facts:
        fid = inp.get("fact_id")
        if fid:
            val, _ = _get_fact_value(fid)
            values[inp.get("label", fid)] = val

    # Re-execute based on formula
    formula = row.get("formula", "")
    try:
        if "cross_foot" in formula:
            line_items = [v for k, v in values.items() if k == "line_item" and v is not None]
            recomputed = sum(line_items) if line_items else None
        elif "yoy_growth" in formula or "growth" in formula:
            curr = values.get("current")
            prev = values.get("previous")
            if curr is not None and prev is not None and prev != 0:
                recomputed = ((curr - prev) / abs(prev) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                recomputed = None
        else:
            # Generic ratio
            num = values.get("numerator")
            den = values.get("denominator")
            if num is not None and den is not None and den != 0:
                recomputed = (num / den).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            else:
                recomputed = None
    except Exception:
        return False

    if recomputed is None:
        return stored_result is None

    return abs(recomputed - stored_result) < Decimal("0.01")


def get_calculations_for_fact(fact_id: str) -> list[dict]:
    """Get all calculations linked to a fact."""
    with db.pool.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM calculations WHERE fact_id = %s ORDER BY created_at ASC",
            (str(fact_id),),
        ).fetchall()
        return [dict(r) for r in rows]
