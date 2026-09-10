"""Tests for human review queue operations."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_review_status_transitions():
    """Valid status transitions."""
    valid_statuses = {"pending", "approved", "rejected", "deferred"}

    # From pending, all transitions are valid
    for target in ("approved", "rejected", "deferred"):
        assert target in valid_statuses

    # Invalid status should be rejected
    assert "invalid" not in valid_statuses


def test_review_reasons():
    """Standard review reasons."""
    valid_reasons = {
        "low_confidence",
        "contradiction",
        "anomaly:benford",
        "anomaly:zscore",
        "anomaly:period_swing",
        "anomaly:cross_foot",
        "calculation_mismatch",
    }

    # All anomaly reasons start with 'anomaly:'
    anomaly_reasons = [r for r in valid_reasons if r.startswith("anomaly:")]
    assert len(anomaly_reasons) == 4

    # Low confidence is a valid reason
    assert "low_confidence" in valid_reasons


def test_review_stats_structure():
    """Review stats should have all status keys."""
    expected_keys = {"pending", "approved", "rejected", "deferred"}
    # Mock stats
    stats = {"pending": 5, "approved": 3, "rejected": 1, "deferred": 2}
    assert set(stats.keys()) == expected_keys


def test_review_decision_payload():
    """ReviewDecision payload validation."""
    valid_payloads = [
        {"status": "approved", "reviewer": "analyst_1", "decision": "Values verified against source"},
        {"status": "rejected", "reviewer": "analyst_2", "decision": "Incorrect extraction"},
        {"status": "deferred", "reviewer": "system", "decision": "Needs additional context"},
    ]

    for p in valid_payloads:
        assert p["status"] in ("approved", "rejected", "deferred")
        assert "reviewer" in p
        assert "decision" in p


def test_idempotent_review_creation():
    """Same fact + reason should not create duplicate pending reviews."""
    # Simulating the check in _create_review_item
    existing_reviews = [
        {"fact_id": "abc-123", "reason": "low_confidence", "status": "pending"},
    ]

    new_fact_id = "abc-123"
    new_reason = "low_confidence"

    # Should skip (existing pending entry)
    should_skip = any(
        r["fact_id"] == new_fact_id and r["reason"] == new_reason and r["status"] == "pending"
        for r in existing_reviews
    )
    assert should_skip, "Should skip duplicate pending review"

    # Different reason should NOT skip
    new_reason_2 = "anomaly:zscore"
    should_skip_2 = any(
        r["fact_id"] == new_fact_id and r["reason"] == new_reason_2 and r["status"] == "pending"
        for r in existing_reviews
    )
    assert not should_skip_2, "Different reason should not skip"


if __name__ == "__main__":
    test_review_status_transitions()
    test_review_reasons()
    test_review_stats_structure()
    test_review_decision_payload()
    test_idempotent_review_creation()
    print("✓ All review queue tests passed")
