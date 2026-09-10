"""Tests for unified model gateway, fallback routing, and hybrid retrieval."""

import os
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv
load_dotenv()

from api.pipeline import models
from api.pipeline.extract import extract_facts_batched, FactExtractResponse, FactExtract


def test_complete_failover():
    """Verify models.complete cascades from failing model to working model."""
    text, used_model = models.complete(
        messages="Respond with PONG",
        models=["fake-model-404", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"],
        max_tokens=10,
    )
    assert text is not None
    assert used_model in ["openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
    print(f"✓ test_complete_failover passed (fell over to {used_model})")


def test_batch_extraction_schema():
    """Verify batch extraction groups facts by chunk_id correctly."""
    chunks = [
        {"id": "c1", "chunk_type": "paragraph", "text": "Delhivery reported revenue of 5000 Cr in FY22."},
        {"id": "c2", "chunk_type": "paragraph", "text": "Net loss was 100 Cr in FY22."},
    ]
    # Mock models.complete to test grouping logic deterministically
    mock_resp = FactExtractResponse(facts=[
        FactExtract(chunk_id="c1", entity="Delhivery", attribute="revenue", raw_value="5000 Cr", quote="revenue of 5000 Cr", confidence=1.0),
        FactExtract(chunk_id="c2", entity="Delhivery", attribute="net loss", raw_value="100 Cr", quote="Net loss was 100 Cr", confidence=1.0),
    ])
    with patch("api.pipeline.models.complete", return_value=(mock_resp.model_dump_json(), "gemini-3.6-flash")):
        results = extract_facts_batched(chunks)
        assert len(results) == 2
        assert len(results[0][1]) == 1
        assert results[0][1][0].attribute == "revenue"
        assert len(results[1][1]) == 1
        assert results[1][1][0].attribute == "net loss"
    print("✓ test_batch_extraction_schema passed")




if __name__ == "__main__":
    test_complete_failover()
    test_batch_extraction_schema()
    print("🎉 ALL GATEWAY TESTS PASSED!")

