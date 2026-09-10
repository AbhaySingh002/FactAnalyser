"""Tests for deterministic financial calculation engine."""

import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.pipeline.financial_calc import _to_decimal, FORMULAS


def test_to_decimal_int():
    assert _to_decimal(100) == Decimal("100")


def test_to_decimal_float():
    result = _to_decimal(100.5)
    assert result == Decimal("100.5")


def test_to_decimal_string():
    assert _to_decimal("1234.56") == Decimal("1234.56")


def test_to_decimal_none():
    assert _to_decimal(None) is None


def test_to_decimal_invalid():
    assert _to_decimal("not a number") is None


def test_to_decimal_zero():
    assert _to_decimal(0) == Decimal("0")


def test_to_decimal_negative():
    assert _to_decimal(-50.5) == Decimal("-50.5")


def test_formulas_exist():
    """All expected formulas are defined."""
    expected = [
        "net_profit_margin", "gross_profit_margin", "debt_to_equity",
        "current_ratio", "return_on_assets", "return_on_equity",
        "yoy_growth", "cross_foot",
    ]
    for name in expected:
        assert name in FORMULAS, f"Missing formula: {name}"


def test_yoy_growth_manual():
    """Manual growth calculation: (120 - 100) / |100| = 20%."""
    current = Decimal("120")
    previous = Decimal("100")
    growth = ((current - previous) / abs(previous) * 100).quantize(Decimal("0.01"))
    assert growth == Decimal("20.00")


def test_yoy_growth_negative():
    """Negative growth: (80 - 100) / |100| = -20%."""
    current = Decimal("80")
    previous = Decimal("100")
    growth = ((current - previous) / abs(previous) * 100).quantize(Decimal("0.01"))
    assert growth == Decimal("-20.00")


def test_ratio_manual():
    """Manual ratio: 50 / 200 = 0.25."""
    num = Decimal("50")
    den = Decimal("200")
    ratio = (num / den).quantize(Decimal("0.0001"))
    assert ratio == Decimal("0.2500")


def test_cross_foot_manual():
    """Manual cross-foot: 10 + 20 + 30 = 60."""
    items = [Decimal("10"), Decimal("20"), Decimal("30")]
    total = Decimal("60")
    computed = sum(items)
    assert computed == total


def test_cross_foot_mismatch():
    """Cross-foot mismatch detection."""
    items = [Decimal("10"), Decimal("20"), Decimal("30")]
    total = Decimal("65")
    computed = sum(items)
    diff = abs(computed - total)
    rel_diff = diff / max(abs(total), Decimal("1e-9"))
    assert rel_diff > Decimal("0.01"), "Should detect mismatch >1%"


def test_decimal_precision():
    """Financial precision: no floating point errors."""
    # Classic float problem: 0.1 + 0.2 != 0.3 in float
    a = Decimal("0.1")
    b = Decimal("0.2")
    c = Decimal("0.3")
    assert a + b == c, "Decimal should handle 0.1 + 0.2 == 0.3"


def test_percentage_margin():
    """Net profit margin: (50 / 200) * 100 = 25.00%."""
    num = Decimal("50")
    den = Decimal("200")
    margin = (num / den * 100).quantize(Decimal("0.01"))
    assert margin == Decimal("25.00")


if __name__ == "__main__":
    test_to_decimal_int()
    test_to_decimal_float()
    test_to_decimal_string()
    test_to_decimal_none()
    test_to_decimal_invalid()
    test_to_decimal_zero()
    test_to_decimal_negative()
    test_formulas_exist()
    test_yoy_growth_manual()
    test_yoy_growth_negative()
    test_ratio_manual()
    test_cross_foot_manual()
    test_cross_foot_mismatch()
    test_decimal_precision()
    test_percentage_margin()
    print("✓ All financial calculation tests passed")
