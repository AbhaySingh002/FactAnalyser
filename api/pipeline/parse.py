"""Parse PDF with PyMuPDF — layout-aware chunking with bboxes and reading-order preservation."""

from __future__ import annotations

import statistics
from dataclasses import dataclass

import pymupdf as fitz

SCAN_THRESHOLD = 40  # Characters below this threshold -> scanned/image page


@dataclass
class ChunkData:
    page: int
    chunk_type: str          # 'paragraph', 'table', 'heading'
    text: str
    bbox: list[float] | None  # [x0, y0, x1, y1] in PDF points (top-left origin)
    heading: str | None = None


def sort_blocks_reading_order(blocks: list[dict], page_width: float) -> list[dict]:
    """Sort text blocks by reading order, respecting 2-column layouts via x-gap heuristic."""
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

    # If both columns contain multiple blocks, sort column-wise
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

    # Single column or irregular: sort primarily by vertical position with a small 6pt quantization bucket
    return sorted(blocks, key=lambda b: (round(b["bbox"][1] / 6.0) * 6.0, b["bbox"][0]))


def parse_pdf(pdf_bytes: bytes) -> tuple[list[ChunkData], list[int], list[int], list[int]]:
    """Parse PDF bytes with layout awareness, heading propagation, and error isolation.

    Returns (chunks, text_pages, scan_pages, error_pages).
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    chunks: list[ChunkData] = []
    text_pages: list[int] = []
    scan_pages: list[int] = []
    error_pages: list[int] = []

    current_heading: str | None = None

    for page_num in range(len(doc)):
        try:
            page = doc[page_num]
            raw_text = page.get_text().strip()

            # Triage text vs scan
            if len(raw_text) < SCAN_THRESHOLD:
                scan_pages.append(page_num)
                continue

            text_pages.append(page_num)
            page_width = float(page.rect.width)

            # ── 1. Table Extraction (Markdown tables with header context) ─
            table_bboxes: list[fitz.Rect] = []
            try:
                tables = page.find_tables()
                for table in tables:
                    t_bbox = [float(v) for v in table.bbox]
                    table_bboxes.append(fitz.Rect(t_bbox))
                    cells = table.extract()
                    if not cells or len(cells) < 1:
                        continue

                    header = cells[0]
                    lines = ["| " + " | ".join(str(c or "").strip() for c in header) + " |"]
                    lines.append("| " + " | ".join("---" for _ in header) + " |")
                    for row in cells[1:]:
                        lines.append("| " + " | ".join(str(c or "").strip() for c in row) + " |")

                    chunks.append(
                        ChunkData(
                            page=page_num,
                            chunk_type="table",
                            text="\n".join(lines),
                            bbox=t_bbox,
                            heading=current_heading,
                        )
                    )
            except Exception:
                pass  # degrade gracefully if table finder fails on complex graphics

            # ── 2. Paragraph & Heading Extraction ────────────────────────
            page_dict = page.get_text("dict")
            raw_blocks = [b for b in page_dict.get("blocks", []) if b.get("type") == 0]

            # Collect font sizes to calculate median body size
            font_sizes: list[float] = []
            for b in raw_blocks:
                for line in b.get("lines", []):
                    for span in line.get("spans", []):
                        if span["text"].strip():
                            font_sizes.append(float(span["size"]))

            median_size = statistics.median(font_sizes) if font_sizes else 12.0

            # Sort blocks to preserve reading order (column-aware)
            sorted_blocks = sort_blocks_reading_order(raw_blocks, page_width)

            for b in sorted_blocks:
                b_rect = fitz.Rect(b["bbox"])
                # Skip text already encapsulated inside a table
                if any(b_rect.intersects(tr) for tr in table_bboxes):
                    continue

                para_lines: list[str] = []
                is_heading = False
                union_x0, union_y0, union_x1, union_y1 = float("inf"), float("inf"), float("-inf"), float("-inf")

                for line in b.get("lines", []):
                    line_text = "".join(span["text"] for span in line.get("spans", []))
                    if line_text.strip():
                        para_lines.append(line_text)

                    # Update union bounding box in PDF points
                    lx0, ly0, lx1, ly1 = line["bbox"]
                    union_x0 = min(union_x0, lx0)
                    union_y0 = min(union_y0, ly0)
                    union_x1 = max(union_x1, lx1)
                    union_y1 = max(union_y1, ly1)

                    for span in line.get("spans", []):
                        if span["text"].strip() and float(span["size"]) > median_size * 1.2:
                            is_heading = True

                text = "\n".join(para_lines).strip()
                if not text:
                    continue

                union_bbox = [round(union_x0, 2), round(union_y0, 2), round(union_x1, 2), round(union_y1, 2)]

                if is_heading:
                    current_heading = text.split("\n")[0]
                    chunks.append(
                        ChunkData(
                            page=page_num,
                            chunk_type="heading",
                            text=text,
                            bbox=union_bbox,
                            heading=current_heading,
                        )
                    )
                else:
                    chunks.append(
                        ChunkData(
                            page=page_num,
                            chunk_type="paragraph",
                            text=text,
                            bbox=union_bbox,
                            heading=current_heading,
                        )
                    )

        except Exception:
            # Failure isolation: one bad page does not abort document parsing
            error_pages.append(page_num)

    doc.close()
    return chunks, text_pages, scan_pages, error_pages
