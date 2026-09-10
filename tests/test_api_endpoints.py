"""Comprehensive tests for API endpoints, Fact-Centric RAG chat, and guards."""

import uuid
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from api.main import app, _ip_rate_limits

# Client fixture is now provided by conftest.py


def test_matrix_endpoint(client):
    """Verify /matrix endpoint returns grid with severity badges."""
    matrix_mock = {
        "entities": ["acme corp", "beta llc"],
        "attributes": ["ebitda", "revenue"],
        "cells": {
            "acme corp|revenue": ["fact-1", "fact-2"],
            "beta llc|ebitda": ["fact-3"],
        },
        "cell_badges": {
            "acme corp|revenue": "contradicts",
            "beta llc|ebitda": "corroborates",
        },
        "cell_details": {
            "acme corp|revenue": {"fact_ids": ["fact-1", "fact-2"], "badge": "contradicts"},
            "beta llc|ebitda": {"fact_ids": ["fact-3"], "badge": "corroborates"},
        },
    }

    with patch("api.db.get_matrix_data", return_value=matrix_mock):
        resp = client.get("/matrix")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entities"] == ["acme corp", "beta llc"]
        assert "acme corp|revenue" in data["cells"]
        assert data["cells"]["acme corp|revenue"] == ["fact-1", "fact-2"]
        assert data["cell_badges"]["acme corp|revenue"] == "contradicts"
    print("✓ test_matrix_endpoint passed")


def test_facts_endpoint_with_query_and_relations_summary(client):
    """Verify /facts always includes quote, page, bbox, filename, confidence, relations_summary."""
    fact_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    fake_facts = [{
        "id": fact_id,
        "document_id": doc_id,
        "chunk_id": str(uuid.uuid4()),
        "entity": "Acme",
        "attribute": "Revenue",
        "entity_canon": "acme",
        "attribute_canon": "revenue",
        "raw_value": "$500M",
        "norm_value": 500000000.0,
        "norm_unit": "USD",
        "currency": "USD",
        "period": "FY2023",
        "scope": "consolidated",
        "quote": "Revenue for FY2023 was $500M.",
        "confidence": 0.95,
        "page": 2,
        "bbox": [10.0, 20.0, 100.0, 50.0],
        "filename": "acme-annual-report.pdf",
        "created_at": "2026-09-08T00:00:00Z",
        "relations_summary": ["corroborates", "contradicts"],
    }]

    with (
        patch("api.main.embed_text", return_value=[0.1] * 768),
        patch("api.db.search_facts", return_value=fake_facts),
    ):
        resp = client.get("/facts?q=revenue")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        item = items[0]
        assert item["id"] == fact_id
        assert item["quote"] == "Revenue for FY2023 was $500M."
        assert item["page"] == 2
        assert item["bbox"] == [10.0, 20.0, 100.0, 50.0]
        assert item["filename"] == "acme-annual-report.pdf"
        assert item["confidence"] == 0.95
        assert item["relations_summary"] == ["corroborates", "contradicts"]
    print("✓ test_facts_endpoint_with_query_and_relations_summary passed")


def test_fact_by_id_endpoint(client):
    """Verify /facts/{id} returns fact with relations array containing counterpart quote, page, and filename."""
    fact_id = str(uuid.uuid4())
    counterpart_id = str(uuid.uuid4())
    fake_detail = {
        "id": fact_id,
        "document_id": str(uuid.uuid4()),
        "chunk_id": str(uuid.uuid4()),
        "quote": "Main fact quote",
        "page": 1,
        "bbox": [0, 0, 10, 10],
        "filename": "main.pdf",
        "relations": [{
            "relation_id": str(uuid.uuid4()),
            "counterpart_id": counterpart_id,
            "relation": "contradicts",
            "explanation": "Values mismatch",
            "quote": "Counterpart quote",
            "page": 4,
            "document_filename": "counterpart.pdf",
        }],
    }

    with patch("api.db.get_fact_with_relations", return_value=fake_detail):
        resp = client.get(f"/facts/{fact_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == fact_id
        assert len(data["relations"]) == 1
        assert data["relations"][0]["counterpart_id"] == counterpart_id
        assert data["relations"][0]["quote"] == "Counterpart quote"
        assert data["relations"][0]["document_filename"] == "counterpart.pdf"
    print("✓ test_fact_by_id_endpoint passed")


def test_pages_image_and_meta(client):
    """Verify /pages returns page numbers with meta and image URLs."""
    doc_id = str(uuid.uuid4())
    page_row = {"png_key": f"pages/{doc_id}/1.png", "width": 612.0, "height": 792.0, "route": "text"}

    with (
        patch("api.db.get_page", return_value=page_row),
        patch("api.storage.public_url", return_value=f"https://r2.example.com/pages/{doc_id}/1.png"),
    ):
        # 1. 302 redirect
        resp_img = client.get(f"/pages/{doc_id}/1", follow_redirects=False)
        assert resp_img.status_code == 302
        assert resp_img.headers["location"] == f"https://r2.example.com/pages/{doc_id}/1.png"

        # 2. Meta endpoint
        resp_meta = client.get(f"/pages/{doc_id}/1/meta")
        assert resp_meta.status_code == 200
        meta = resp_meta.json()
        assert meta["width"] == 612.0
        assert meta["height"] == 792.0
        assert meta["page"] == 1
        assert meta["png_url"] == f"https://r2.example.com/pages/{doc_id}/1.png"
    print("✓ test_pages_image_and_meta passed")


def test_audit_fact_lineage(client):
    """Verify /facts/{id}/audit returns full ingestion lineage including OCR, chunking, and extraction logs."""
    fact_id = str(uuid.uuid4())
    fake_lineage = [
        {"id": 1, "action": "ocr", "at": "2026-09-08T00:01:00Z", "meta": {"provider": "groq-vision"}},
        {"id": 2, "action": "extract", "at": "2026-09-08T00:02:00Z", "meta": {"model": "llama-3.3-70b-versatile"}},
        {"id": 3, "action": "reconcile", "at": "2026-09-08T00:03:00Z", "meta": {"rule_path": ["R4:tolerance_match"]}},
    ]

    with patch("api.db.get_fact_lineage_audit", return_value=fake_lineage):
        resp = client.get(f"/audit?fact_id={fact_id}")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 3
        assert rows[0]["action"] == "ocr"
        assert rows[1]["action"] == "extract"
        assert rows[2]["action"] == "reconcile"
    print("✓ test_audit_fact_lineage passed")


def test_rate_limit_and_error_shapes(client):
    """Verify unified JSON error wrapper and 429 rate limit."""

    with (
        patch("api.main.RATE_LIMIT_PER_MINUTE", 20),
        patch("api.db.get_matrix_data", return_value={"entities": [], "attributes": [], "cells": {}}),
    ):
        # Fire 20 allowed requests
        for _ in range(20):
            r = client.get("/matrix")
            assert r.status_code == 200

        # 21st request triggers rate limit 429
        r21 = client.get("/matrix")
        assert r21.status_code == 429
        assert "error" in r21.json()
        assert "Rate limit exceeded" in r21.json()["error"]

    _ip_rate_limits.clear()
    print("✓ test_rate_limit_and_error_shapes passed")


if __name__ == "__main__":
    test_matrix_endpoint()
    test_facts_endpoint_with_query_and_relations_summary()
    test_fact_by_id_endpoint()
    test_pages_image_and_meta()
    test_audit_fact_lineage()
    test_rate_limit_and_error_shapes()
    print("\n🎉 ALL API & CHAT ENDPOINT TESTS PASSED SUCCESSFULLY!")
