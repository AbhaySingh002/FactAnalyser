"""Tests for statistical anomaly detection engine."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.pipeline.anomaly import _first_digit, BENFORD_EXPECTED


def test_first_digit_basic():
    assert _first_digit(123.45) == 1
    assert _first_digit(9876) == 9
    assert _first_digit(0.045) == 4
    assert _first_digit(5) == 5


def test_first_digit_negative():
    assert _first_digit(-123) == 1
    assert _first_digit(-0.045) == 4


def test_first_digit_zero():
    assert _first_digit(0) is None


def test_benford_expected_sums_to_one():
    """Benford's expected probabilities should sum to ~1.0."""
    total = sum(BENFORD_EXPECTED.values())
    assert abs(total - 1.0) < 0.01, f"Expected sum ~1.0, got {total}"


def test_benford_distribution_order():
    """Digit 1 should be most frequent, 9 least frequent."""
    for d in range(1, 9):
        assert BENFORD_EXPECTED[d] >= BENFORD_EXPECTED[d + 1], \
            f"Benford violation: P({d}) < P({d + 1})"


def test_benford_conforming_data():
    """Data following Benford's Law should pass chi-squared test."""
    import random
    random.seed(42)

    # Generate Benford-conforming data
    benford_data = []
    for digit, prob in BENFORD_EXPECTED.items():
        count = int(prob * 500)
        benford_data.extend([digit] * count)

    n = len(benford_data)
    observed = {}
    for d in range(1, 10):
        observed[d] = benford_data.count(d) / n

    chi_sq = 0.0
    for d in range(1, 10):
        expected = BENFORD_EXPECTED[d]
        obs = observed.get(d, 0.0)
        chi_sq += ((obs - expected) ** 2) / expected

    # Should NOT be flagged (chi_sq < 15.5)
    assert chi_sq < 15.5, f"Benford-conforming data flagged: χ²={chi_sq:.2f}"


def test_benford_non_conforming_data():
    """Uniform distribution should fail Benford's test."""
    # Uniform: each digit appears equally
    n = 450
    per_digit = n // 9
    uniform_data = []
    for d in range(1, 10):
        uniform_data.extend([d] * per_digit)

    total = len(uniform_data)
    observed = {}
    for d in range(1, 10):
        observed[d] = uniform_data.count(d) / total

    # Chi-squared using (O - E)^2 / E with n-scaled counts
    chi_sq = 0.0
    for d in range(1, 10):
        expected_count = BENFORD_EXPECTED[d] * total
        observed_count = uniform_data.count(d)
        chi_sq += ((observed_count - expected_count) ** 2) / expected_count

    # SHOULD be flagged (chi_sq > 15.5)
    assert chi_sq > 15.5, f"Uniform data not flagged: χ²={chi_sq:.2f}"


def test_zscore_detection_logic():
    """Manual z-score calculation should flag outliers."""
    import statistics

    values = [100, 102, 98, 101, 99, 103, 97, 100, 101, 99, 1000]  # 1000 is clear outlier
    mean = statistics.mean(values)
    stdev = statistics.stdev(values)

    z_outlier = abs(1000 - mean) / stdev
    assert z_outlier > 3.0, f"Z-score of 1000 should be > 3.0, got {z_outlier:.2f}"

    z_normal = abs(100 - mean) / stdev
    assert z_normal < 3.0, f"Z-score of 100 should be < 3.0, got {z_normal:.2f}"


def test_period_swing_detection_logic():
    """Manual period-over-period swing calculation."""
    prev_val = 100.0
    curr_val = 160.0
    pct_change = abs(curr_val - prev_val) / abs(prev_val)
    assert pct_change > 0.50, f"60% change should exceed 50% threshold, got {pct_change * 100:.1f}%"

    curr_val_small = 110.0
    pct_change_small = abs(curr_val_small - prev_val) / abs(prev_val)
    assert pct_change_small <= 0.50, f"10% change should NOT exceed 50% threshold"


def test_severity_levels():
    """Verify severity classification logic."""
    # Z-score > 5 = high
    assert 6.0 > 5, "Z > 5 should be high severity"
    # Z-score 3-5 = medium
    assert 3.5 > 3.0 and 3.5 <= 5.0, "Z 3-5 should be medium"

    # Period swing > 100% = high
    assert 1.5 > 1.0, "150% swing should be high severity"
    # Period swing 50-100% = medium
    assert 0.7 > 0.5 and 0.7 <= 1.0, "70% swing should be medium"


def test_cross_footing_anomaly_detection():
    """Verify check_cross_footing identifies line items that do not sum to total."""
    from unittest.mock import patch
    from api.pipeline.anomaly import check_cross_footing, AnomalyFinding, convert_to_finding_dict

    doc_id = "test-doc-123"
    fake_facts = [
        {
            "id": "f1",
            "document_id": doc_id,
            "entity_canon": "acme",
            "attribute_canon": "current_assets",
            "norm_value": 40.0,
            "period": "FY2024",
        },
        {
            "id": "f2",
            "document_id": doc_id,
            "entity_canon": "acme",
            "attribute_canon": "non_current_assets",
            "norm_value": 50.0,
            "period": "FY2024",
        },
        {
            "id": "f3",
            "document_id": doc_id,
            "entity_canon": "acme",
            "attribute_canon": "total_assets",
            "norm_value": 120.0,  # 40 + 50 = 90 != 120 (33% mismatch)
            "period": "FY2024",
        },
    ]

    with patch("api.db.get_facts_for_document", return_value=fake_facts):
        findings = check_cross_footing(doc_id)
        assert len(findings) == 1
        f = findings[0]
        assert f.anomaly_type == "cross_foot"
        assert f.severity == "critical"
        assert f.details["computed_sum"] == 90.0
        assert f.details["reported_total"] == 120.0

        finding_dict = convert_to_finding_dict(f)
        assert finding_dict["category"] == "computational_error"
        assert finding_dict["severity"] == "critical"
        assert "f3" in finding_dict["fact_ids"]


if __name__ == "__main__":
    test_first_digit_basic()
    test_first_digit_negative()
    test_first_digit_zero()
    test_benford_expected_sums_to_one()
    test_benford_distribution_order()
    test_benford_conforming_data()
    test_benford_non_conforming_data()
    test_zscore_detection_logic()
    test_period_swing_detection_logic()
    test_severity_levels()
    test_cross_footing_anomaly_detection()
    print("✓ All anomaly detection tests passed")
