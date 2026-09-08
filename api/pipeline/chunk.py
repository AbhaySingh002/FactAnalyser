"""Persist chunks to DB — text chunks from parse, OCR chunks from scan pages."""

from __future__ import annotations

import re

from ..pipeline.parse import ChunkData
from .. import db


def persist_text_chunks(document_id: str, chunks: list[ChunkData]):
    """Insert parsed text/table/heading chunks into the chunks table."""
    for c in chunks:
        db.insert_chunk(
            document_id=document_id,
            page=c.page,
            chunk_type=c.chunk_type,
            text=c.text,
            bbox=c.bbox,
            heading=c.heading,
            ocr_provider="pymupdf",
        )



def persist_ocr_chunks(document_id: str, page: int, markdown: str, provider: str):
    """Split OCR markdown by headings/tables into chunks and insert."""
    blocks = _split_markdown(markdown)
    for block in blocks:
        db.insert_chunk(
            document_id=document_id,
            page=page,
            chunk_type=block["type"],
            text=block["text"],
            bbox=None,  # OCR doesn't give bboxes
            heading=block.get("heading"),
            ocr_provider=provider,
        )


def persist_ocr_failure_chunk(document_id: str, page: int, error_history: list[str] | str | None = None):
    """Insert a visible needs-review chunk when OCR fails for a page."""
    err_msg = ""
    if error_history:
        if isinstance(error_history, list):
            err_msg = f": {'; '.join(str(e) for e in error_history)}"
        else:
            err_msg = f": {error_history}"
    db.insert_chunk(
        document_id=document_id,
        page=page,
        chunk_type="needs_review",
        text=f"[OCR Transcription Failed] Page {page + 1} could not be transcribed{err_msg}",
        bbox=None,
        heading="OCR Failed",
        ocr_provider="failed",
    )


def _split_markdown(md: str) -> list[dict]:
    """Split markdown preserving headings and table blocks as distinct evidence units."""
    blocks: list[dict] = []
    current_lines: list[str] = []
    current_type = "ocr_block"
    current_heading = None

    for line in md.split("\n"):
        stripped = line.strip()

        # Heading line -> flush previous text/table, emit heading chunk
        if re.match(r"^#{1,6}\s+", stripped):
            if current_lines:
                text = "\n".join(current_lines).strip()
                if text:
                    blocks.append({"type": current_type, "text": text, "heading": current_heading})
                current_lines = []

            heading_title = re.sub(r"^#{1,6}\s+", "", stripped).strip()
            current_heading = heading_title
            blocks.append({"type": "heading", "text": stripped, "heading": heading_title})
            current_type = "ocr_block"
            continue

        # Detect table rows
        if stripped.startswith("|") and stripped.endswith("|"):
            if current_type != "table" and current_lines:
                text = "\n".join(current_lines).strip()
                if text:
                    blocks.append({"type": current_type, "text": text, "heading": current_heading})
                current_lines = []
            current_type = "table"
            current_lines.append(line)
            continue

        # Non-table line after table -> flush table
        if current_type == "table" and stripped:
            text = "\n".join(current_lines).strip()
            if text:
                blocks.append({"type": "table", "text": text, "heading": current_heading})
            current_lines = []
            current_type = "ocr_block"

        current_lines.append(line)

    if current_lines:
        text = "\n".join(current_lines).strip()
        if text:
            blocks.append({"type": current_type, "text": text, "heading": current_heading})

    return blocks
