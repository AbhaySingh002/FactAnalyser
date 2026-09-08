"""Render PDF pages as PNGs at 150 DPI page-by-page (memory-safe) and upload to R2."""

from __future__ import annotations

import pymupdf as fitz

from .. import storage


def render_and_upload(pdf_bytes: bytes, doc_id: str) -> dict[int, dict]:
    """Render each page at 150 DPI and stream to R2.

    Memory-safe: releases pixmap buffers immediately after uploading each page.
    Returns {page_num: {"r2_key": str, "width": int, "height": int}}.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_meta: dict[int, dict] = {}

    for page_num in range(len(doc)):
        try:
            page = doc[page_num]
            pix = page.get_pixmap(dpi=150)
            png_bytes = pix.tobytes("png")
            width, height = pix.width, pix.height
            pix = None  # Free pixmap buffer immediately

            r2_key = storage.put_page_png(doc_id, page_num, png_bytes)
            pages_meta[page_num] = {
                "r2_key": r2_key,
                "width": width,
                "height": height,
            }
        except Exception:
            pages_meta[page_num] = {
                "r2_key": None,
                "width": None,
                "height": None,
                "error": True,
            }

    doc.close()
    return pages_meta
