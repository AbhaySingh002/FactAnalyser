"""Tests for evidence provenance — hash-chain integrity, fact linking, tamper detection."""

import hashlib
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.pipeline.evidence import _content_hash, _prompt_hash


def test_content_hash_deterministic():
    """Same inputs produce same hash."""
    h1 = _content_hash("Revenue was $100M", 3, "paragraph")
    h2 = _content_hash("Revenue was $100M", 3, "paragraph")
    assert h1 == h2, f"Hash mismatch: {h1} != {h2}"
    assert len(h1) == 64, "SHA-256 should produce 64 hex chars"


def test_content_hash_changes_on_different_input():
    """Different content produces different hash."""
    h1 = _content_hash("Revenue was $100M", 3, "paragraph")
    h2 = _content_hash("Revenue was $200M", 3, "paragraph")
    assert h1 != h2, "Different content should produce different hashes"


def test_content_hash_changes_on_different_page():
    """Same content on different page produces different hash."""
    h1 = _content_hash("Revenue was $100M", 3, "paragraph")
    h2 = _content_hash("Revenue was $100M", 5, "paragraph")
    assert h1 != h2, "Different page should produce different hashes"


def test_content_hash_changes_on_different_type():
    """Same content with different evidence_type produces different hash."""
    h1 = _content_hash("Revenue was $100M", 3, "paragraph")
    h2 = _content_hash("Revenue was $100M", 3, "table_cell")
    assert h1 != h2, "Different type should produce different hashes"


def test_prompt_hash_deterministic():
    """Same prompts produce same hash."""
    h1 = _prompt_hash("You are a factual extraction engine", "Extract facts from: revenue data")
    h2 = _prompt_hash("You are a factual extraction engine", "Extract facts from: revenue data")
    assert h1 == h2


def test_prompt_hash_changes_on_different_system():
    """Different system prompts produce different hashes."""
    h1 = _prompt_hash("System A", "User content")
    h2 = _prompt_hash("System B", "User content")
    assert h1 != h2


def test_content_hash_none_page():
    """None page should still produce a valid hash."""
    h = _content_hash("Some text", None, "ocr_text")
    assert len(h) == 64
    # Should be consistent
    h2 = _content_hash("Some text", None, "ocr_text")
    assert h == h2


if __name__ == "__main__":
    test_content_hash_deterministic()
    test_content_hash_changes_on_different_input()
    test_content_hash_changes_on_different_page()
    test_content_hash_changes_on_different_type()
    test_prompt_hash_deterministic()
    test_prompt_hash_changes_on_different_system()
    test_content_hash_none_page()
    print("✓ All evidence provenance tests passed")
