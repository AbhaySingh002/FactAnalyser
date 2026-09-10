"""Persist parsed structure to normalized database entities.

Handles:
1. document_pages: 100% of pages recorded with dimensions and route status.
2. document_sections: heading and narrative hierarchy.
3. document_tables: headers, markdown representation, cell grid, and financial unit/currency hints.
4. document_chunks: reading-order preserved text and table chunks with coordinate provenance.
5. OCR chunks for scanned pages.
"""

from __future__ import annotations

import re
from typing import Any
from ..pipeline.parse import PageParseResult, ChunkData, TableData, SectionData
from .. import db


def persist_parsed_pages(document_id: str, pages: list[PageParseResult]) -> dict[str, int]:
    """Insert pages, sections, tables, and chunks into normalized relational tables."""
    total_sections = 0
    total_tables = 0
    total_chunks = 0

    for page in pages:
        # 1. Guarantee page entry exists
        db.insert_page(
            document_id=document_id,
            page=page.page_number,
            width=page.width,
            height=page.height,
            png_key=None,  # updated during render
            route=page.route,
            char_count=page.char_count,
            table_count=page.table_count,
        )

        # 2. Insert sections and keep id mapping
        section_id_map: dict[str, str] = {}
        for sec in page.sections:
            sec_row = db.insert_section(
                document_id=document_id,
                page_number=page.page_number,
                title=sec.title,
                level=sec.level,
                section_type=sec.section_type,
                reading_order=sec.reading_order,
            )
            if sec_row and "id" in sec_row:
                section_id_map[sec.title] = str(sec_row["id"])
                total_sections += 1

        # 3. Insert tables and keep id mapping by table_index
        table_id_map: dict[int, str] = {}
        for tbl in page.tables:
            tbl_row = db.insert_table(
                document_id=document_id,
                page_number=page.page_number,
                table_index=tbl.table_index,
                bbox=tbl.bbox,
                markdown_repr=tbl.markdown_repr,
                headers=tbl.headers,
                grid=tbl.cells_data,
                title=tbl.title,
                unit_hint=tbl.unit_hint,
                currency_hint=tbl.currency_hint,
                period_hint=tbl.period_hint,
            )
            if tbl_row and "id" in tbl_row:
                table_id_map[tbl.table_index] = str(tbl_row["id"])
                total_tables += 1

        # 4. Insert chunks with foreign keys to table and section
        for ch in page.chunks:
            sec_id = section_id_map.get(ch.heading or "")
            tbl_id = table_id_map.get(ch.table_index) if ch.table_index is not None else None

            db.insert_chunk(
                document_id=document_id,
                page=ch.page_number,
                chunk_type=ch.chunk_type,
                text=ch.text,
                bbox=ch.bbox,
                heading=ch.heading,
                ocr_provider="pymupdf",
                section_id=sec_id,
                table_id=tbl_id,
                reading_order=ch.reading_order,
            )
            total_chunks += 1

    return {
        "pages": len(pages),
        "sections": total_sections,
        "tables": total_tables,
        "chunks": total_chunks,
    }


def persist_text_chunks(document_id: str, chunks: list[ChunkData]):
    """Compatibility helper: insert parsed text/table/heading chunks into document_chunks."""
    for c in chunks:
        db.insert_chunk(
            document_id=document_id,
            page=c.page_number,
            chunk_type=c.chunk_type,
            text=c.text,
            bbox=c.bbox,
            heading=c.heading,
            ocr_provider="pymupdf",
            reading_order=c.reading_order,
        )


def persist_ocr_chunks(document_id: str, page: int, markdown: str, provider: str):
    """Split OCR markdown by headings/tables into chunks and insert."""
    blocks = _split_markdown(markdown)
    for idx, block in enumerate(blocks):
        db.insert_chunk(
            document_id=document_id,
            page=page,
            chunk_type=block["type"],
            text=block["text"],
            bbox=None,  # Vision OCR does not yield native PDF points
            heading=block.get("heading"),
            ocr_provider=provider,
            reading_order=idx + 1,
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
        text=f"[OCR Transcription Failed] Page {page} could not be transcribed{err_msg}",
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
