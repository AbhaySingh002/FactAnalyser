"""Evidence provenance — hash-chained, tamper-evident evidence records.

Every extracted fact links to one or more evidence records. Each evidence
record stores a SHA-256 content hash for integrity verification and
the exact source coordinates (page, bbox, table cell) for audit replay.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from .. import db


def _content_hash(content: str, page: int | None, evidence_type: str) -> str:
    """SHA-256 of (content + page + evidence_type) for tamper detection."""
    payload = f"{content}|{page}|{evidence_type}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _prompt_hash(system_prompt: str, user_content: str) -> str:
    """SHA-256 of the prompt template for reproducibility tracking."""
    payload = f"{system_prompt}|||{user_content}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_evidence(
    document_id: str,
    page: int | None,
    evidence_type: str,
    content: str,
    bbox: list[float] | None = None,
    table_ref: dict | None = None,
    model_id: str | None = None,
    prompt_hash: str | None = None,
) -> dict:
    """Create or retrieve deduplicated evidence record with SHA-256 content hash."""
    return db.insert_evidence_snippet(
        document_id=str(document_id),
        page=page or 1,
        evidence_type=evidence_type,
        content=content,
        bbox=bbox,
        table_coord=table_ref,
        model_id=model_id,
        prompt_hash=prompt_hash,
    )


def link_fact_to_evidence(fact_id: str, evidence_id: str, role: str = "source"):
    """Link a fact to an evidence record in fact_evidence."""
    db.link_fact_to_evidence(str(fact_id), str(evidence_id), role=role)


def verify_evidence_integrity(evidence_id: str) -> bool:
    """Re-hash content and compare against stored hash — tamper detection."""
    db._ensure_pool()
    with db.pool.connection() as conn:
        row = conn.execute(
            "SELECT content, page, evidence_type, content_hash FROM evidence WHERE id = %s",
            (str(evidence_id),),
        ).fetchone()

    if not row:
        return False

    expected = _content_hash(row["content"], row["page"], row["evidence_type"])
    return expected == row["content_hash"]


def get_evidence_chain(fact_id: str) -> list[dict]:
    """Full provenance chain for a fact — all linked evidence records."""
    return db.get_evidence_for_fact(str(fact_id))


def get_evidence_by_hash(content_hash: str) -> dict | None:
    """Look up evidence by content hash — deduplication."""
    db._ensure_pool()
    with db.pool.connection() as conn:
        row = conn.execute(
            "SELECT * FROM evidence WHERE content_hash = %s LIMIT 1",
            (content_hash,),
        ).fetchone()
        return dict(row) if row else None


def create_evidence_for_chunk(
    document_id: str,
    chunk: dict,
    model_id: str | None = None,
    prompt_hash_val: str | None = None,
) -> dict:
    """Create evidence from a chunk record with coordinate and table provenance."""
    text = (chunk.get("text") or "").strip()
    page = chunk.get("page") or chunk.get("page_number") or 1
    chunk_type = chunk.get("chunk_type") or "paragraph"

    evidence_type_map = {
        "table": "table_cell",
        "paragraph": "paragraph",
        "heading": "heading",
        "footnote": "footnote",
        "ocr": "ocr_text",
        "ocr_block": "ocr_text",
    }
    ev_type = evidence_type_map.get(chunk_type, "paragraph")

    return create_evidence(
        document_id=document_id,
        page=page,
        evidence_type=ev_type,
        content=text,
        bbox=chunk.get("bbox"),
        table_ref=chunk.get("table_ref"),
        model_id=model_id,
        prompt_hash=prompt_hash_val,
    )


if __name__ == "__main__":
    h1 = _content_hash("Revenue was $50M", 14, "paragraph")
    h2 = _content_hash("Revenue was $50M", 14, "paragraph")
    assert h1 == h2, "Hash must be deterministic"
    p_h = _prompt_hash("System prompt", "User prompt")
    assert len(p_h) == 64, "Prompt hash must be SHA-256"
    print("✓ evidence self-check passed!")
