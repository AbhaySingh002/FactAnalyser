"""Durable background worker for financial document ingestion & evidence extraction.

FEATURES:
- Native PostgreSQL transactional queue via `FOR UPDATE SKIP LOCKED`.
- Resilient stage checkpointing, progress tracking, and heartbeats.
- Automatic retries with exponential backoff on transient errors.
- Runs embedded inside FastAPI lifespan OR standalone CLI daemon.
- Zero Redis / Celery dependencies (strict Ponytail / YAGNI principles).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
import traceback
from typing import Any

from . import db, storage
from .pipeline.parse import parse_pdf
from .pipeline.render_pages import render_and_upload
from .pipeline.ocr_client import process_document_ocr
from .pipeline.chunk import persist_parsed_pages
from .pipeline.extract import extract_facts_windowed, EXTRACTION_MODEL, PROMPT_VER
from .pipeline.normalize import (
    normalize_number_and_unit,
    normalize_period,
    canonicalize_entity,
    canonicalize_attribute,
)
from .pipeline.embed import embed_texts, embed_text
from .pipeline.evidence import create_evidence_for_chunk, link_fact_to_evidence
from .pipeline.reconcile import reconcile_document
from .pipeline.anomaly import run_anomaly_checks, populate_review_queue_from_anomalies, populate_review_queue_from_pipeline
from .pipeline.analyze import run_analysis

logger = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [worker] %(message)s")


def run_pipeline_for_document(doc_id: str, job_id: str, pdf_bytes: bytes):
    """Execute complete 10-stage financial fact ingestion pipeline."""
    t_start = time.monotonic()
    try:
        # ── Stage 1: Parse ──────────────────────────────────────────
        db.update_job_checkpoint(job_id, stage="parse", progress=0.10)
        parsed_pages = parse_pdf(pdf_bytes)
        db.update_document_page_count(doc_id, len(parsed_pages))

        # ── Stage 2: Render & Page Imagery ─────────────────────────
        db.update_job_checkpoint(job_id, stage="render", progress=0.20)
        pages_meta = render_and_upload(pdf_bytes, doc_id)

        # ── Stage 3: Structure Persistence (Pages, Sections, Tables, Chunks) ─
        db.update_job_checkpoint(job_id, stage="persist_structure", progress=0.30)
        structure_counts = persist_parsed_pages(doc_id, parsed_pages)

        # Update page images in document_pages
        for pno, pmeta in pages_meta.items():
            if pmeta.get("r2_key"):
                db.insert_page(
                    document_id=doc_id,
                    page=pno,
                    width=pmeta.get("width"),
                    height=pmeta.get("height"),
                    png_key=pmeta.get("r2_key"),
                )

        # ── Stage 4: OCR for Scanned Pages ─────────────────────────
        scan_pages = [p.page_number for p in parsed_pages if p.route in ("scan", "mixed")]
        if scan_pages:
            db.update_job_checkpoint(job_id, stage="ocr", progress=0.40)
            process_document_ocr(doc_id, scan_pages, pages_meta)

        # ── Stage 5: Fact Extraction (Tables First + Windowed Chunks) ──
        db.update_job_checkpoint(job_id, stage="extract", progress=0.50)
        db_chunks = db.get_chunks_for_document(doc_id)

        # Prioritize tables and chunks containing financial figures
        table_chunks = [ch for ch in db_chunks if ch.get("chunk_type") == "table"]
        numeric_chunks = [ch for ch in db_chunks if ch.get("chunk_type") != "table" and any(c.isdigit() for c in (ch.get("text") or ""))]
        narrative_chunks = [ch for ch in db_chunks if ch not in table_chunks and ch not in numeric_chunks]

        # Prioritize table + numeric disclosures; cap non-numeric narrative if too large
        candidate_chunks = table_chunks + numeric_chunks + narrative_chunks[:50]

        extracted_facts: list[tuple[dict, Any]] = []
        batched_results = extract_facts_windowed(candidate_chunks, window_size=2)
        for ch, facts in batched_results:
            for f in facts:
                extracted_facts.append((ch, f))

        # ── Stage 6: Deterministic Normalization ───────────────────
        db.update_job_checkpoint(job_id, stage="normalize", progress=0.65)
        normalized_records: list[dict] = []

        for ch, f in extracted_facts:
            try:
                norm_val, norm_unit, detected_curr = normalize_number_and_unit(f.raw_value, f.value_number)
                currency = detected_curr or f.currency
                period = normalize_period(f.period, f.raw_value)
                entity_canon = canonicalize_entity(f.entity)
                attr_canon = canonicalize_attribute(f.attribute, embed_text)

                normalized_records.append({
                    "chunk_id": ch["id"],
                    "document_id": doc_id,
                    "entity": f.entity,
                    "attribute": f.attribute,
                    "entity_canon": entity_canon,
                    "attribute_canon": attr_canon,
                    "raw_value": f.raw_value,
                    "norm_value": norm_val,
                    "norm_unit": norm_unit or f.unit,
                    "currency": currency,
                    "period": period,
                    "scope": f.scope,
                    "quote": f.quote,
                    "confidence": f.confidence,
                    "model": EXTRACTION_MODEL,
                    "prompt_ver": PROMPT_VER,
                    "page_number": ch.get("page") or ch.get("page_number") or 1,
                    "table_id": ch.get("table_id"),
                })
            except Exception as ex:
                db.audit("fact.normalize_error", target={"chunk_id": str(ch["id"])}, meta={"error": str(ex)})

        # ── Stage 7: Embeddings & Fact Graph Storage ──────────────
        db.update_job_checkpoint(job_id, stage="embed", progress=0.75)
        if normalized_records:
            embed_texts_input = [
                f"{r.get('entity_canon') or r.get('entity') or ''} {r.get('attribute_canon') or r.get('attribute') or ''} {r.get('raw_value') or ''} {r.get('period') or ''} {r.get('scope') or ''} :: {r.get('quote') or ''}".strip()
                for r in normalized_records
            ]
            try:
                vectors = embed_texts(embed_texts_input)
                for r, vec in zip(normalized_records, vectors):
                    r["embedding"] = vec
            except Exception as emb_err:
                logger.warning(f"Vector embedding skipped/failed: {emb_err}")

            db.insert_facts(normalized_records)

        # ── Stage 8: Provenance & Deduplicated Evidence ────────────
        db.update_job_checkpoint(job_id, stage="evidence", progress=0.85)
        try:
            all_chunks = db.get_chunks_for_document(doc_id)
            all_facts = db.get_facts_for_document(doc_id)
            chunk_by_id = {str(c["id"]): c for c in all_chunks}
            for fact in all_facts:
                chunk_id = str(fact.get("chunk_id") or "")
                chunk = chunk_by_id.get(chunk_id)
                if chunk:
                    ev = create_evidence_for_chunk(
                        document_id=doc_id,
                        chunk=chunk,
                        model_id=fact.get("model"),
                        prompt_hash_val=fact.get("prompt_hash"),
                    )
                    if ev and "id" in ev:
                        link_fact_to_evidence(str(fact["id"]), str(ev["id"]), role="source")
        except Exception as ev_err:
            db.audit("evidence.stage_error", target={"document_id": doc_id}, meta={"error": str(ev_err)})

        # ── Stage 9: Cross- & Intra-Document Reconciliation ───────
        db.update_job_checkpoint(job_id, stage="reconcile", progress=0.92)
        try:
            reconcile_document(doc_id)
        except Exception as rec_err:
            db.audit("reconcile.stage_error", target={"document_id": doc_id}, meta={"error": str(rec_err)})

        # ── Stage 10: Anomaly Verification & Review Queue ─────────
        db.update_job_checkpoint(job_id, stage="anomaly_check", progress=0.94)
        try:
            findings = run_anomaly_checks(doc_id)
            populate_review_queue_from_anomalies(doc_id, findings)
            populate_review_queue_from_pipeline(doc_id)
        except Exception as an_err:
            db.audit("anomaly.stage_error", target={"document_id": doc_id}, meta={"error": str(an_err)})

        # ── Stage 11: Cross-Document Analysis & Findings ─────────
        db.update_job_checkpoint(job_id, stage="analyze", progress=0.97)
        try:
            analysis_findings = run_analysis([doc_id])
            logger.info(f"Analysis generated {len(analysis_findings)} findings for doc {doc_id}")
        except Exception as al_err:
            db.audit("analyze.stage_error", target={"document_id": doc_id}, meta={"error": str(al_err)})

        # Mark Job and Document Completed
        db.complete_job(job_id)
        db.update_document_status(doc_id, "processed")

        elapsed = time.monotonic() - t_start
        db.audit(
            "pipeline.complete",
            target={"document_id": doc_id, "job_id": job_id},
            meta={"elapsed_seconds": round(elapsed, 2), "facts_count": len(normalized_records)},
        )
        logger.info(f"Pipeline completed for doc {doc_id} in {elapsed:.2f}s with {len(normalized_records)} facts.")

    except Exception as e:
        err_msg = str(e)
        logger.error(f"Pipeline failure on doc {doc_id}, job {job_id}: {err_msg}", exc_info=True)
        db.fail_job(job_id, error=err_msg, retry=True)
        db.audit(
            "pipeline.error",
            target={"document_id": doc_id, "job_id": job_id},
            meta={"error": err_msg, "traceback": traceback.format_exc()},
        )
        raise


def process_single_job(job: dict) -> bool:
    """Execute a claimed job record."""
    job_id = str(job["id"])
    doc_id = str(job["document_id"])
    logger.info(f"Processing claimed job {job_id} for document {doc_id}")

    doc = db.get_document(doc_id)
    if not doc:
        db.fail_job(job_id, error=f"Document {doc_id} not found", retry=False)
        return False

    r2_key = doc.get("r2_key")
    if not r2_key:
        db.fail_job(job_id, error="Document missing r2_key storage pointer", retry=False)
        return False

    try:
        pdf_bytes = storage.get_object_bytes(r2_key)
    except Exception as ex:
        db.fail_job(job_id, error=f"Storage read error: {ex}", retry=True)
        return False

    run_pipeline_for_document(doc_id, job_id, pdf_bytes)
    return True


def poll_and_execute_once() -> bool:
    """Atomically claim and execute one job. Returns True if a job was found and processed."""
    job = db.claim_next_job()
    if not job:
        return False
    return process_single_job(job)


async def worker_loop(poll_interval: float = 2.0, stop_event: asyncio.Event | None = None):
    """Asynchronous worker loop that continuously claims and processes pending jobs."""
    logger.info("Worker loop started.")
    while stop_event is None or not stop_event.is_set():
        try:
            # Run blocking DB claim and pipeline execution in worker thread pool
            processed = await asyncio.to_thread(poll_and_execute_once)
            if not processed:
                await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            logger.info("Worker loop cancelled.")
            break
        except Exception as e:
            logger.error(f"Error in worker loop: {e}", exc_info=True)
            await asyncio.sleep(poll_interval)


def main():
    """Standalone CLI daemon entrypoint: python -m api.worker."""
    logger.info("Starting Fact Knowledge Layer Standalone Worker...")
    try:
        while True:
            processed = poll_and_execute_once()
            if not processed:
                time.sleep(2.0)
    except KeyboardInterrupt:
        logger.info("Worker stopped by user.")


if __name__ == "__main__":
    main()
