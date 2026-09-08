import asyncio
import collections
import hashlib
import os
import time
import traceback

from fastapi import BackgroundTasks, FastAPI, UploadFile, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from . import db, storage
from .pipeline.parse import parse_pdf
from .pipeline.render_pages import render_and_upload
from .pipeline.ocr_client import ocr_page, OcrUnavailable, process_document_ocr
from .pipeline.chunk import persist_text_chunks, persist_ocr_chunks
from .pipeline.extract import extract_facts_from_chunk, EXTRACTION_MODEL, PROMPT_VER
from .pipeline.normalize import (
    normalize_number_and_unit,
    normalize_period,
    canonicalize_entity,
    canonicalize_attribute,
)
from .pipeline.embed import embed_texts, embed_text
from .pipeline.reconcile import reconcile_document
from .pipeline.chat import answer_question

app = FastAPI(title="Fact Knowledge Layer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_ORIGIN", "*")],
    allow_methods=["*"],
    allow_headers=["*"],
)

_ip_rate_limits: dict[str, collections.deque[float]] = collections.defaultdict(collections.deque)
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "20"))


@app.middleware("http")
async def guards_middleware(request: Request, call_next):
    # Skip rate limiting for health checks
    if request.url.path != "/health":
        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.monotonic()
        window = _ip_rate_limits[client_ip]

        while window and window[0] <= now - 60.0:
            window.popleft()

        if len(window) >= RATE_LIMIT_PER_MINUTE:
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded (max 20 req/min)"},
            )
        window.append(now)

    try:
        return await asyncio.wait_for(call_next(request), timeout=60.0)
    except asyncio.TimeoutError:
        return JSONResponse(status_code=504, content={"error": "Request timed out after 60s"})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": str(exc)})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": str(exc)})


class ChatPayload(BaseModel):
    message: str
    history: list[dict] = []



# ── pipeline ─────────────────────────────────────────────────────────

def run_pipeline(doc_id: str, job_id: str, pdf_bytes: bytes):
    """Full pipeline: parse -> route -> extract -> normalize -> embed."""
    try:
        # 1. Stage: parse (layout parse + page-by-page render to R2)
        db.set_job(job_id, stage="parse", status="running")
        chunks, text_pages, scan_pages, error_pages = parse_pdf(pdf_bytes)
        pages_meta = render_and_upload(pdf_bytes, doc_id)
        db.update_document_page_count(doc_id, len(pages_meta))

        for page_num, pmeta in pages_meta.items():
            if page_num in error_pages:
                route = "error"
            elif page_num in scan_pages:
                route = "scan"
            else:
                route = "text"
            db.insert_page(doc_id, page_num, pmeta.get("width"), pmeta.get("height"), pmeta.get("r2_key"), route)

        db.set_job(job_id, stage="parse", status="done")

        # 2. Stage: route (persist text chunks to DB)
        db.set_job(job_id, stage="route", status="running")
        persist_text_chunks(doc_id, chunks)
        db.set_job(job_id, stage="route", status="done")

        # 3. Stage: ocr (rate-limited round-robin vision OCR for scan pages)
        db.set_job(job_id, stage="ocr", status="running")
        process_document_ocr(doc_id, scan_pages, pages_meta)
        db.set_job(job_id, stage="ocr", status="done")


        # 4. Stage: extract — structured claims per chunk with Groq
        db.set_job(job_id, stage="extract", status="running")
        db_chunks = db.get_chunks_for_document(doc_id)
        extracted_facts: list[tuple[dict, object]] = []

        for ch in db_chunks:
            try:
                facts = extract_facts_from_chunk(
                    chunk_id=str(ch["id"]),
                    text=ch["text"] or "",
                    chunk_type=ch.get("chunk_type") or "paragraph",
                    heading=ch.get("heading"),
                )
                for f in facts:
                    extracted_facts.append((ch, f))
            except Exception as ex:
                db.audit("chunk.extract_error", target={"chunk_id": str(ch["id"])}, meta={"error": str(ex)})
        db.set_job(job_id, stage="extract", status="done")

        # 5. Stage: normalize — deterministic numbers, currency, period, canonical names
        db.set_job(job_id, stage="normalize", status="running")
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
                })
            except Exception as ex:
                db.audit("fact.normalize_error", target={"chunk_id": str(ch["id"])}, meta={"error": str(ex)})
        db.set_job(job_id, stage="normalize", status="done")

        # 6. Stage: embed — batch embed with Gemini into pgvector
        db.set_job(job_id, stage="embed", status="running")
        if normalized_records:
            embed_texts_input = [
                f"{r.get('entity_canon') or r.get('entity') or ''} {r.get('attribute_canon') or r.get('attribute') or ''} {r.get('raw_value') or ''} {r.get('period') or ''} {r.get('scope') or ''} :: {r.get('quote') or ''}".strip()
                for r in normalized_records
            ]
            vectors = embed_texts(embed_texts_input)
            for r, vec in zip(normalized_records, vectors):
                r["embedding"] = vec

            db.insert_facts(normalized_records)

        db.set_job(job_id, stage="embed", status="done")

        # 7. Stage: reconcile — pairwise reconciliation against other documents
        db.set_job(job_id, stage="reconcile", status="running")
        reconcile_document(doc_id)
        db.set_job(job_id, stage="done", status="done")

    except Exception as e:
        db.set_job(job_id, stage="failed", status="failed", error=str(e))
        db.audit("pipeline_error", target={"document_id": doc_id, "job_id": job_id},
                 meta={"error": str(e), "traceback": traceback.format_exc()})





# ── endpoints ────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True}


@app.post("/documents")
async def upload_document(file: UploadFile, background_tasks: BackgroundTasks):
    data = await file.read()
    sha = hashlib.sha256(data).hexdigest()

    existing = db.get_document_by_sha(sha)
    if existing:
        job = db.get_job_for_document(existing["id"])
        return {"document_id": str(existing["id"]), "job_id": str(job["id"]) if job else None, "dedupe": True}

    r2_key = storage.put_pdf(sha, data)
    doc = db.new_document(filename=file.filename or "unknown.pdf", sha256=sha, r2_key=r2_key)
    job = db.new_job(doc["id"], stage="queued", status="pending")

    db.audit("document.uploaded", target={"document_id": str(doc["id"])}, meta={"filename": file.filename, "sha256": sha, "size_bytes": len(data)})

    background_tasks.add_task(run_pipeline, str(doc["id"]), str(job["id"]), data)

    return {"document_id": str(doc["id"]), "job_id": str(job["id"])}


@app.get("/documents")
def list_documents():
    docs = db.list_documents()
    return [
        {**d, "id": str(d["id"]), "created_at": d["created_at"].isoformat()}
        for d in docs
    ]


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, detail="job not found")
    return {**job, "id": str(job["id"]), "document_id": str(job["document_id"]), "updated_at": job["updated_at"].isoformat()}


@app.get("/relations")
def list_relations(type: str | None = None, document_id: str | None = None):
    rels = db.get_relations(relation_type=type, document_id=document_id)
    return [
        {
            **r,
            "id": str(r["id"]),
            "a_id": str(r["a_id"]),
            "b_id": str(r["b_id"]),
            "a_document_id": str(r["a_document_id"]),
            "b_document_id": str(r["b_document_id"]),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        for r in rels
    ]


@app.get("/matrix")
def get_matrix():
    return db.get_matrix_data()


@app.get("/facts")
def list_facts(
    document_id: str | None = None,
    entity_canon: str | None = None,
    attribute_canon: str | None = None,
    q: str | None = None,
    limit: int = 50,
):
    query_vector = embed_text(q) if q else None
    facts = db.search_facts(
        document_id=document_id,
        entity_canon=entity_canon,
        attribute_canon=attribute_canon,
        query_vector=query_vector,
        limit=min(limit, 100),
    )
    return [
        {
            **f,
            "id": str(f["id"]),
            "document_id": str(f["document_id"]),
            "chunk_id": str(f["chunk_id"]) if f.get("chunk_id") else None,
            "created_at": f["created_at"].isoformat() if f.get("created_at") else None,
            "embedding": None,
            "quote": f.get("quote"),
            "page": f.get("page"),
            "bbox": f.get("bbox"),
            "filename": f.get("filename"),
            "confidence": f.get("confidence"),
            "relations_summary": f.get("relations_summary") or [],
        }
        for f in facts
    ]


@app.get("/facts/{fact_id}")
def get_fact(fact_id: str):
    fact = db.get_fact_with_relations(fact_id)
    if not fact:
        raise HTTPException(404, detail="fact not found")

    relations = [
        {
            **r,
            "relation_id": str(r["relation_id"]),
            "counterpart_id": str(r["counterpart_id"]),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        }
        for r in fact.get("relations", [])
    ]

    return {
        **fact,
        "id": str(fact["id"]),
        "document_id": str(fact["document_id"]),
        "chunk_id": str(fact["chunk_id"]) if fact.get("chunk_id") else None,
        "created_at": fact["created_at"].isoformat() if fact.get("created_at") else None,
        "embedding": None,  # omit raw 768-dim vector from json response
        "relations": relations,
    }


@app.get("/pages/{document_id}/{page}")
def get_page_image(document_id: str, page: int):
    page_row = db.get_page(document_id, page)
    url = storage.public_url(page_row["png_key"] if page_row and page_row.get("png_key") else f"pages/{document_id}/{page}.png")
    headers = {}
    if page_row and page_row.get("width") and page_row.get("height"):
        headers["X-Page-Width"] = str(page_row["width"])
        headers["X-Page-Height"] = str(page_row["height"])
    return RedirectResponse(url=url, status_code=302, headers=headers)


@app.get("/pages/{document_id}/{page}/meta")
def get_page_meta(document_id: str, page: int):
    page_row = db.get_page(document_id, page)
    if not page_row:
        raise HTTPException(404, detail=f"Page {page} for document {document_id} not found")
    png_url = storage.public_url(page_row["png_key"] if page_row.get("png_key") else f"pages/{document_id}/{page}.png")
    return {
        "document_id": document_id,
        "page": page,
        "width": page_row.get("width"),
        "height": page_row.get("height"),
        "route": page_row.get("route"),
        "png_url": png_url,
    }



@app.get("/audit")
def get_audit(fact_id: str | None = None):
    if fact_id:
        rows = db.get_fact_lineage_audit(fact_id)
    else:
        with db.pool.connection() as conn:
            rows = conn.execute("SELECT * FROM audit ORDER BY at DESC LIMIT 100").fetchall()
    return [
        {
            **r,
            "id": str(r["id"]),
            "at": r["at"].isoformat() if r.get("at") else None,
        }
        for r in rows
    ]


@app.post("/chat")
def chat(payload: ChatPayload):
    return answer_question(payload.message, payload.history)


