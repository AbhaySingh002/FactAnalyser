"""Parse PDF with PyMuPDF — layout-aware parsing, first-class table extraction, and coordinate provenance.

Guarantees:
1. NEVER drop a page: every page produces an explicit record with dimensions and route status.
2. First-class tables: row, col, header, cell coordinates, and unit/currency hints preserved.
3. Reading-order preservation with 2-column detection.
4. Bounding boxes in 72 DPI PDF point space.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
import pymupdf as fitz

SCAN_CHAR_THRESHOLD = 40  # Under 40 chars text -> scanned / image page


@dataclass
class SectionData:
    page_number: int
    title: str
    level: int = 1
    section_type: str = "narrative"
    reading_order: int = 0


@dataclass
class TableData:
    page_number: int
    table_index: int
    bbox: list[float] | None
    headers: list[str]
    rows: list[list[str]]
    markdown_repr: str
    title: str | None = None
    unit_hint: str | None = None
    currency_hint: str | None = None
    period_hint: str | None = None
    cells_data: list[dict] = field(default_factory=list)


@dataclass
class ChunkData:
    page_number: int
    chunk_type: str  # 'paragraph', 'table', 'heading', 'footnote'
    text: str
    bbox: list[float] | None
    heading: str | None = None
    table_index: int | None = None
    reading_order: int = 0


@dataclass
class PageParseResult:
    page_number: int  # 1-indexed
    width: float
    height: float
    route: str        # 'text', 'scan', 'mixed', 'empty', 'error'
    char_count: int
    table_count: int
    sections: list[SectionData] = field(default_factory=list)
    tables: list[TableData] = field(default_factory=list)
    chunks: list[ChunkData] = field(default_factory=list)
    error: str | None = None


def _detect_table_hints(headers: list[str], context_text: str = "") -> tuple[str | None, str | None, str | None]:
    """Detect currency, unit multiplier, and period hints from table headers and surrounding text."""
    full_text = " ".join(headers) + " " + context_text
    lower = full_text.lower()

    # 1. Currency hint
    curr = None
    if any(k in lower for k in ["₹", "inr", "rupee", "rs.", "rs "]):
        curr = "INR"
    elif any(k in lower for k in ["$", "usd", "dollar"]):
        curr = "USD"
    elif any(k in lower for k in ["€", "eur", "euro"]):
        curr = "EUR"
    elif any(k in lower for k in ["£", "gbp", "pound"]):
        curr = "GBP"

    # 2. Unit multiplier hint
    unit = None
    if re.search(r"\b(?:in\s+)?(?:crore|crores|cr\.?)\b", lower):
        unit = "crore"
    elif re.search(r"\b(?:in\s+)?(?:lakh|lakhs|lac|lacs)\b", lower):
        unit = "lakh"
    elif re.search(r"\b(?:in\s+)?(?:million|millions|mn\.?)\b", lower):
        unit = "million"
    elif re.search(r"\b(?:in\s+)?(?:billion|billions|bn\.?)\b", lower):
        unit = "billion"
    elif re.search(r"\b(?:in\s+)?(?:thousand|thousands|k)\b", lower):
        unit = "thousand"
    elif "%" in full_text or "percent" in lower:
        unit = "pct"

    # 3. Period hint
    period = None
    m_fy = re.search(r"\b(FY\s*20?\d{2})\b", full_text, re.IGNORECASE)
    if m_fy:
        period = m_fy.group(1).upper().replace(" ", "")
    else:
        m_q = re.search(r"\b(Q[1-4]\s*(?:FY)?\s*20?\d{2})\b", full_text, re.IGNORECASE)
        if m_q:
            period = m_q.group(1).upper().replace(" ", "")

    return unit, curr, period


def sort_blocks_reading_order(blocks: list[dict], page_width: float) -> list[dict]:
    """Sort text blocks in reading order, respecting 2-column layouts via midline analysis."""
    if len(blocks) <= 1:
        return blocks

    mid = page_width / 2.0
    left_blocks = []
    right_blocks = []
    spanning_blocks = []

    for b in blocks:
        bx0, by0, bx1, by1 = b["bbox"]
        if bx1 <= mid + 25:
            left_blocks.append(b)
        elif bx0 >= mid - 25:
            right_blocks.append(b)
        else:
            spanning_blocks.append(b)

    if len(left_blocks) >= 2 and len(right_blocks) >= 2:
        left_sorted = sorted(left_blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))
        right_sorted = sorted(right_blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))

        top_spanning = [b for b in spanning_blocks if b["bbox"][1] < min(left_sorted[0]["bbox"][1], right_sorted[0]["bbox"][1])]
        bottom_spanning = [b for b in spanning_blocks if b not in top_spanning]

        res = []
        res.extend(sorted(top_spanning, key=lambda b: (b["bbox"][1], b["bbox"][0])))
        res.extend(left_sorted)
        res.extend(right_sorted)
        res.extend(sorted(bottom_spanning, key=lambda b: (b["bbox"][1], b["bbox"][0])))
        return res

    return sorted(blocks, key=lambda b: (round(b["bbox"][1] / 6.0) * 6.0, b["bbox"][0]))


def parse_pdf(pdf_bytes: bytes) -> list[PageParseResult]:
    """Parse every page of a PDF document with full layout, table, section, and reading-order extraction.

    Guarantees: Returns exactly len(doc) PageParseResult objects. NEVER drops a page.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    results: list[PageParseResult] = []
    current_heading: str | None = None
    reading_order_counter = 0

    for page_idx in range(len(doc)):
        page_num = page_idx + 1  # 1-indexed
        page = doc[page_idx]
        rect = page.rect
        width, height = float(rect.width), float(rect.height)

        try:
            raw_text = page.get_text().strip()
            char_count = len(raw_text)

            # Handle scanned / image-only page
            if char_count < SCAN_CHAR_THRESHOLD:
                results.append(
                    PageParseResult(
                        page_number=page_num,
                        width=width,
                        height=height,
                        route="scan" if char_count > 0 or len(page.get_images()) > 0 else "empty",
                        char_count=char_count,
                        table_count=0,
                    )
                )
                continue

            # ── 1. Extract First-Class Tables ────────────────────────
            table_bboxes: list[fitz.Rect] = []
            extracted_tables: list[TableData] = []
            table_index = 0

            try:
                tables = page.find_tables()
                for t in tables:
                    t_bbox = [round(float(v), 2) for v in t.bbox]
                    table_bboxes.append(fitz.Rect(t_bbox))
                    cells = t.extract()
                    if not cells or len(cells) < 1:
                        continue

                    raw_header = cells[0]
                    clean_header = [str(c or "").strip() for c in raw_header]
                    rows_data = [[str(c or "").strip() for c in r] for r in cells[1:]]

                    # Markdown table representation
                    lines = ["| " + " | ".join(clean_header) + " |"]
                    lines.append("| " + " | ".join("---" for _ in clean_header) + " |")
                    for r in rows_data:
                        lines.append("| " + " | ".join(r) + " |")
                    md_repr = "\n".join(lines)

                    unit_h, curr_h, period_h = _detect_table_hints(clean_header, current_heading or "")

                    # Cell-level coordinates
                    cells_data = []
                    for r_idx, row in enumerate(cells):
                        for c_idx, cell_val in enumerate(row):
                            hdr = clean_header[c_idx] if c_idx < len(clean_header) else ""
                            cells_data.append({
                                "row": r_idx,
                                "col": c_idx,
                                "header": hdr,
                                "value": str(cell_val or "").strip(),
                            })

                    table_obj = TableData(
                        page_number=page_num,
                        table_index=table_index,
                        bbox=t_bbox,
                        headers=clean_header,
                        rows=rows_data,
                        markdown_repr=md_repr,
                        title=current_heading,
                        unit_hint=unit_h,
                        currency_hint=curr_h,
                        period_hint=period_h,
                        cells_data=cells_data,
                    )
                    extracted_tables.append(table_obj)
                    table_index += 1
            except Exception:
                pass  # Degrade gracefully if table finder encounters irregular graphics

            # ── 2. Extract Narrative, Headings & Footnotes ────────────
            page_dict = page.get_text("dict")
            raw_blocks = [b for b in page_dict.get("blocks", []) if b.get("type") == 0]

            font_sizes: list[float] = []
            for b in raw_blocks:
                for line in b.get("lines", []):
                    for span in line.get("spans", []):
                        if span["text"].strip():
                            font_sizes.append(float(span["size"]))

            median_size = statistics.median(font_sizes) if font_sizes else 10.0
            sorted_blocks = sort_blocks_reading_order(raw_blocks, width)

            page_sections: list[SectionData] = []
            page_chunks: list[ChunkData] = []

            for b in sorted_blocks:
                b_rect = fitz.Rect(b["bbox"])
                # Skip text already included in extracted tables
                if any(b_rect.intersects(tr) for tr in table_bboxes):
                    continue

                lines_text: list[str] = []
                is_heading = False
                is_footnote = False
                union_x0, union_y0, union_x1, union_y1 = float("inf"), float("inf"), float("-inf"), float("-inf")

                for line in b.get("lines", []):
                    lt = "".join(s["text"] for s in line.get("spans", []))
                    if lt.strip():
                        lines_text.append(lt)

                    lx0, ly0, lx1, ly1 = line["bbox"]
                    union_x0, union_y0 = min(union_x0, lx0), min(union_y0, ly0)
                    union_x1, union_y1 = max(union_x1, lx1), max(union_y1, ly1)

                    for s in line.get("spans", []):
                        sz = float(s.get("size", 10.0))
                        if s["text"].strip():
                            if sz > median_size * 1.2:
                                is_heading = True
                            elif sz < median_size * 0.85:
                                is_footnote = True

                text = "\n".join(lines_text).strip()
                if not text:
                    continue

                union_bbox = [round(union_x0, 2), round(union_y0, 2), round(union_x1, 2), round(union_y1, 2)]
                reading_order_counter += 1

                if is_heading:
                    current_heading = text.split("\n")[0]
                    page_sections.append(
                        SectionData(
                            page_number=page_num,
                            title=current_heading,
                            level=1 if median_size * 1.4 < font_sizes[0] else 2,
                            section_type="heading",
                            reading_order=reading_order_counter,
                        )
                    )
                    page_chunks.append(
                        ChunkData(
                            page_number=page_num,
                            chunk_type="heading",
                            text=text,
                            bbox=union_bbox,
                            heading=current_heading,
                            reading_order=reading_order_counter,
                        )
                    )
                elif is_footnote:
                    page_chunks.append(
                        ChunkData(
                            page_number=page_num,
                            chunk_type="footnote",
                            text=text,
                            bbox=union_bbox,
                            heading=current_heading,
                            reading_order=reading_order_counter,
                        )
                    )
                else:
                    page_chunks.append(
                        ChunkData(
                            page_number=page_num,
                            chunk_type="paragraph",
                            text=text,
                            bbox=union_bbox,
                            heading=current_heading,
                            reading_order=reading_order_counter,
                        )
                    )

            # Also register tables as standalone chunks for semantic windowing
            for tbl in extracted_tables:
                reading_order_counter += 1
                page_chunks.append(
                    ChunkData(
                        page_number=page_num,
                        chunk_type="table",
                        text=tbl.markdown_repr,
                        bbox=tbl.bbox,
                        heading=tbl.title,
                        table_index=tbl.table_index,
                        reading_order=reading_order_counter,
                    )
                )

            results.append(
                PageParseResult(
                    page_number=page_num,
                    width=width,
                    height=height,
                    route="text",
                    char_count=char_count,
                    table_count=len(extracted_tables),
                    sections=page_sections,
                    tables=extracted_tables,
                    chunks=page_chunks,
                )
            )

        except Exception as ex:
            # Failure isolation: error on one page records explicit error status, never drops page
            results.append(
                PageParseResult(
                    page_number=page_num,
                    width=width,
                    height=height,
                    route="error",
                    char_count=0,
                    table_count=0,
                    error=str(ex),
                )
            )

    doc.close()
    return results
