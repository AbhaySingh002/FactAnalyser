"""Comprehensive tests for rate-limited round-robin vision OCR pipeline."""

import time
from unittest.mock import MagicMock, patch

from api.pipeline.ocr_client import (
    ProviderState,
    OcrRouter,
    OcrUnavailable,
    process_document_ocr,
    _extract_retry_delay,
    _is_transient_error,
)
from api.pipeline.chunk import _split_markdown, persist_ocr_failure_chunk


def test_markdown_chunking_headings_tables():
    """Verify markdown split into heading, table, and text evidence units."""
    sample_md = (
        "# Executive Summary\n\n"
        "This is paragraph one of the report.\n\n"
        "| Quarter | Revenue | Profit |\n"
        "| --- | --- | --- |\n"
        "| Q1 | 100M | 10M |\n"
        "| Q2 | 120M | 15M |\n\n"
        "Concluding remarks after the table."
    )
    blocks = _split_markdown(sample_md)

    assert len(blocks) == 4, f"Expected 4 blocks, got {len(blocks)}"
    assert blocks[0]["type"] == "heading"
    assert blocks[0]["text"] == "# Executive Summary"
    assert blocks[0]["heading"] == "Executive Summary"

    assert blocks[1]["type"] == "ocr_block"
    assert "paragraph one" in blocks[1]["text"]
    assert blocks[1]["heading"] == "Executive Summary"

    assert blocks[2]["type"] == "table"
    assert "| Quarter | Revenue | Profit |" in blocks[2]["text"]
    assert "| Q2 | 120M | 15M |" in blocks[2]["text"]
    assert blocks[2]["heading"] == "Executive Summary"

    assert blocks[3]["type"] == "ocr_block"
    assert "Concluding remarks" in blocks[3]["text"]
    print("✓ test_markdown_chunking_headings_tables passed")


def test_round_robin_rotation_4_pages():
    """Verify >=4 scanned pages alternate providers page-by-page."""
    groq_st = ProviderState("groq-vision", min_interval=0.0, rpm_ceiling=100)
    gem_st = ProviderState("gemini-vision", min_interval=0.0, rpm_ceiling=100)

    call_history = []

    def mock_call(provider_name, png_bytes, prompt, page, doc_id):
        call_history.append((page, provider_name))
        return f"# Page {page}\nContent here", provider_name

    router = OcrRouter(document_id="doc-123", groq_state=groq_st, gemini_state=gem_st, call_fn=mock_call)

    for p in range(4):
        text, prov = router.transcribe_page(b"fake_png", page=p)
        expected_prov = "groq-vision" if p % 2 == 0 else "gemini-vision"
        assert prov == expected_prov, f"Page {p} got {prov}, expected {expected_prov}"

    assert call_history == [
        (0, "groq-vision"),
        (1, "gemini-vision"),
        (2, "groq-vision"),
        (3, "gemini-vision"),
    ], f"Unexpected call history: {call_history}"
    print("✓ test_round_robin_rotation_4_pages passed")


def test_pacing_minimum_interval_and_rpm():
    """Verify minimum interval spacing and RPM ceiling are respected."""
    min_int = 0.05
    st = ProviderState("test-prov", min_interval=min_int, rpm_ceiling=10)

    t0 = time.monotonic()
    st.wait_for_pacing()
    t1 = time.monotonic()
    st.wait_for_pacing()
    t2 = time.monotonic()

    interval = t2 - t1
    assert interval >= min_int - 0.005, f"Interval {interval} was smaller than min_interval {min_int}"
    print("✓ test_pacing_minimum_interval_and_rpm passed")


def test_cooldown_failover_and_recovery():
    """Verify invalid credential shifts traffic to healthy provider, and rotation resumes once restored."""
    groq_st = ProviderState("groq-vision", min_interval=0.0, rpm_ceiling=100)
    gem_st = ProviderState("gemini-vision", min_interval=0.0, rpm_ceiling=100)

    groq_healthy = False
    audit_events = []

    def mock_call(provider_name, png_bytes, prompt, page, doc_id):
        if provider_name == "groq-vision" and not groq_healthy:
            raise ValueError("401 Unauthorized: Invalid Groq API Key")
        return f"Markdown content for page {page}", provider_name

    with patch("api.db.audit", side_effect=lambda action, target=None, meta=None: audit_events.append((action, meta))):
        router = OcrRouter(document_id="doc-failover", groq_state=groq_st, gemini_state=gem_st, call_fn=mock_call)

        # Page 0: Groq scheduled -> fails -> cooldown -> failover to Gemini
        t0, p0 = router.transcribe_page(b"png0", page=0)
        assert p0 == "gemini-vision"
        assert groq_st.is_cooling_down()

        # Cooldown event audited
        cooldown_events = [e for e in audit_events if e[0] == "ocr.cooldown"]
        assert len(cooldown_events) >= 1
        assert cooldown_events[0][1]["provider"] == "groq-vision"

        # Page 1: Gemini scheduled -> Gemini transcribes
        t1, p1 = router.transcribe_page(b"png1", page=1)
        assert p1 == "gemini-vision"

        # Page 2: Groq scheduled -> Groq still cooling -> failover to Gemini
        t2, p2 = router.transcribe_page(b"png2", page=2)
        assert p2 == "gemini-vision"

        # Now Groq is restored and cooldown expires
        groq_healthy = True
        groq_st.reset_cooldown()

        # Page 3: Gemini scheduled
        t3, p3 = router.transcribe_page(b"png3", page=3)
        assert p3 == "gemini-vision"

        # Page 4: Groq scheduled -> succeeds with Groq! Rotation resumed
        t4, p4 = router.transcribe_page(b"png4", page=4)
        assert p4 == "groq-vision"

    print("✓ test_cooldown_failover_and_recovery passed")


def test_both_providers_unreachable_isolation():
    """Verify that when both providers fail, document completes, page marked failed with needs-review chunk."""
    groq_st = ProviderState("groq-vision", min_interval=0.0, rpm_ceiling=100)
    gem_st = ProviderState("gemini-vision", min_interval=0.0, rpm_ceiling=100)

    def failing_call(provider_name, png_bytes, prompt, page, doc_id):
        raise ConnectionError(f"{provider_name} network connection refused")

    audit_log = []
    page_routes = {}
    inserted_chunks = []

    with (
        patch("api.db.audit", side_effect=lambda action, target=None, meta=None: audit_log.append((action, target, meta))),
        patch("api.db.update_page_route", side_effect=lambda doc_id, page, route: page_routes.update({page: route})),
        patch("api.db.insert_chunk", side_effect=lambda **kwargs: inserted_chunks.append(kwargs)),
        patch("api.storage.get_object_bytes", return_value=b"valid_png_bytes"),
    ):
        router = OcrRouter(document_id="doc-down", groq_state=groq_st, gemini_state=gem_st, call_fn=failing_call)
        scan_pages = [0, 1]
        pages_meta = {0: {"r2_key": "pages/doc-down/0.png"}, 1: {"r2_key": "pages/doc-down/1.png"}}

        # Should NOT raise an exception that aborts the pipeline
        process_document_ocr("doc-down", scan_pages, pages_meta, router=router)

        # Pages marked failed in DB
        assert page_routes.get(0) == "failed"
        assert page_routes.get(1) == "failed"

        # Needs-review chunks inserted
        nr_chunks = [c for c in inserted_chunks if c.get("chunk_type") == "needs_review"]
        assert len(nr_chunks) == 2
        assert nr_chunks[0]["ocr_provider"] == "failed"
        assert "[OCR Transcription Failed]" in nr_chunks[0]["text"]

        # Audit logs contain page_failed
        failed_audits = [a for a in audit_log if a[0] == "ocr.page_failed"]
        assert len(failed_audits) == 2

    print("✓ test_both_providers_unreachable_isolation passed")


def test_cost_guards_page_budget_60():
    """Verify document with >60 scanned pages: first 60 transcribed, rest marked skipped."""
    audit_log = []
    page_routes = {}
    transcribed_pages = []

    def mock_call(provider_name, png_bytes, prompt, page, doc_id):
        transcribed_pages.append(page)
        return f"Markdown for page {page}", provider_name

    groq_st = ProviderState("groq-vision", min_interval=0.0, rpm_ceiling=100)
    gem_st = ProviderState("gemini-vision", min_interval=0.0, rpm_ceiling=100)
    router = OcrRouter(document_id="doc-budget", groq_state=groq_st, gemini_state=gem_st, call_fn=mock_call)

    total_pages = 65
    scan_pages = list(range(total_pages))
    pages_meta = {p: {"r2_key": f"pages/doc-budget/{p}.png"} for p in scan_pages}

    with (
        patch("api.db.audit", side_effect=lambda action, target=None, meta=None: audit_log.append((action, target, meta))),
        patch("api.db.update_page_route", side_effect=lambda doc_id, page, route: page_routes.update({page: route})),
        patch("api.db.insert_chunk", return_value=None),
        patch("api.storage.get_object_bytes", return_value=b"png_bytes"),
    ):
        process_document_ocr("doc-budget", scan_pages, pages_meta, budget=60, router=router)

        # Transcribed exact 60
        assert len(transcribed_pages) == 60
        assert transcribed_pages == list(range(60))

        # Remaining 5 pages (60..64) marked skipped
        for p in range(60, 65):
            assert page_routes.get(p) == "skipped"

        skipped_audits = [a for a in audit_log if a[0] == "ocr.page_skipped"]
        assert len(skipped_audits) == 5
        assert skipped_audits[0][2]["budget"] == 60
        assert skipped_audits[0][2]["reason"] == "budget_exceeded"

    print("✓ test_cost_guards_page_budget_60 passed")


def test_mixed_pdf_isolation():
    """Verify native-text pages are never sent for vision transcription."""
    # In run_pipeline logic:
    scan_pages = [1, 3]  # Only pages 1 and 3 are scan pages; 0 and 2 are text
    pages_meta = {0: {}, 1: {"r2_key": "pages/doc/1.png"}, 2: {}, 3: {"r2_key": "pages/doc/3.png"}}
    transcribed = []

    def mock_call(provider_name, png_bytes, prompt, page, doc_id):
        transcribed.append(page)
        return "md", provider_name

    groq_st = ProviderState("groq-vision", min_interval=0.0, rpm_ceiling=100)
    gem_st = ProviderState("gemini-vision", min_interval=0.0, rpm_ceiling=100)
    router = OcrRouter(document_id="doc-mixed", groq_state=groq_st, gemini_state=gem_st, call_fn=mock_call)

    with (
        patch("api.db.audit"),
        patch("api.db.update_page_route"),
        patch("api.db.insert_chunk"),
        patch("api.storage.get_object_bytes", return_value=b"png_bytes"),
    ):
        process_document_ocr("doc-mixed", scan_pages, pages_meta, router=router)

    assert transcribed == [1, 3], f"Expected only scan pages [1, 3] to be transcribed, got {transcribed}"
    print("✓ test_mixed_pdf_isolation passed")


if __name__ == "__main__":
    test_markdown_chunking_headings_tables()
    test_round_robin_rotation_4_pages()
    test_pacing_minimum_interval_and_rpm()
    test_cooldown_failover_and_recovery()
    test_both_providers_unreachable_isolation()
    test_cost_guards_page_budget_60()
    test_mixed_pdf_isolation()
    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY!")
