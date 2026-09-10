from dotenv import load_dotenv
load_dotenv()

import asyncio
import collections
import hashlib
import os
import time
import traceback
import json
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, UploadFile, HTTPException, Request, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from . import db, storage
from .worker import run_pipeline_for_document, worker_loop, poll_and_execute_once
from .pipeline.embed import embed_texts, embed_text
from .pipeline.research import run_research_chat
from .pipeline.financial_calc import calculate_ratio, cross_foot, calculate_growth
from .pipeline.analyze import run_analysis
from .auth import auth_middleware

_stop_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db._ensure_pool()
    _stop_event.clear()
    worker_task = asyncio.create_task(worker_loop(poll_interval=1.5, stop_event=_stop_event))
    yield
    _stop_event.set()
    worker_task.cancel()
    try:
        await worker_task
    except (asyncio.CancelledError, Exception):
        pass
    if getattr(db.pool, "_opened", False):
        try:
            db.pool.close()
        except Exception:
            pass


app = FastAPI(title="Fact Knowledge Layer API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("FRONTEND_ORIGIN", "*")],
    allow_methods=["*"],
    allow_headers=["*"],
)

_ip_rate_limits: dict[str, collections.deque[float]] = collections.defaultdict(collections.deque)
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))


@app.middleware("http")
async def guards_middleware(request: Request, call_next):
    async def auth_and_call():
        auth_resp = await auth_middleware(request, call_next)
        return auth_resp

    # Skip rate limiting for health checks and static page images
    if request.url.path not in ("/health", "/"):
        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.monotonic()
        window = _ip_rate_limits[client_ip]

        while window and window[0] <= now - 60.0:
            window.popleft()

        if len(window) >= RATE_LIMIT_PER_MINUTE:
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded"},
            )
        window.append(now)

    try:
        return await asyncio.wait_for(auth_and_call(), timeout=60.0)
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


def _iso(val):
    return val.isoformat() if hasattr(val, "isoformat") else val


class ChatPayload(BaseModel):
    message: str
    history: list[dict] = []
    deep_research: bool = True
    web_search: bool = True


# ── Health & Status ──────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True, "service": "fact-knowledge-layer", "version": "1.0.0"}


# ── Document Management & Upload ─────────────────────────────────────

@app.post("/documents")
@app.post("/documents/upload")
async def upload_document(file: UploadFile, background_tasks: BackgroundTasks):
    """Upload PDF document, validate header, store, and enqueue for background ingestion."""
    if not file or not file.filename:
        raise HTTPException(400, detail="Missing file in upload request")

    data = await file.read()
    if not data or len(data) == 0:
        raise HTTPException(400, detail="Uploaded file is empty")

    # File validation: magic bytes check for PDF
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, detail="Uploaded file is not a valid PDF document (missing %PDF header)")

    if len(data) > 100 * 1024 * 1024:  # 100MB ceiling
        raise HTTPException(400, detail="File exceeds maximum allowed size of 100MB")

    sha = hashlib.sha256(data).hexdigest()

    # Deduplication check
    existing = db.get_document_by_sha(sha)
    if existing:
        job = db.get_job_for_document(existing["id"])
        return {
            "document_id": str(existing["id"]),
            "job_id": str(job["id"]) if job else None,
            "dedupe": True,
            "filename": existing.get("filename"),
            "status": existing.get("status", "processed"),
        }

    r2_key = storage.put_pdf(sha, data)
    doc = db.new_document(
        filename=file.filename or "unknown.pdf",
        sha256=sha,
        r2_key=r2_key,
        file_size_bytes=len(data),
    )
    job = db.new_job(doc["id"], stage="queued", status="pending")

    db.audit(
        "document.uploaded",
        target={"document_id": str(doc["id"])},
        meta={"filename": file.filename, "sha256": sha, "size_bytes": len(data)},
    )

    # Immediately trigger processing in background or let worker pick it up
    background_tasks.add_task(poll_and_execute_once)

    return {
        "document_id": str(doc["id"]),
        "job_id": str(job["id"]),
        "filename": doc["filename"],
        "status": "pending",
    }


@app.get("/documents")
def list_documents():
    docs = db.list_documents()
    return [
        {**d, "id": str(d["id"]), "created_at": _iso(d.get("created_at"))}
        for d in docs
    ]


@app.get("/documents/{document_id}")
def get_document(document_id: str):
    doc = db.get_document(document_id)
    if not doc:
        raise HTTPException(404, detail=f"Document {document_id} not found")
    job = db.get_job_for_document(document_id)
    return {
        **doc,
        "id": str(doc["id"]),
        "created_at": _iso(doc.get("created_at")),
        "latest_job": {
            **job,
            "id": str(job["id"]),
            "updated_at": _iso(job.get("updated_at")),
        } if job else None,
    }


@app.get("/documents/{document_id}/pages")
def list_document_pages(document_id: str):
    pages = db.list_pages_for_document(document_id)
    return [
        {
            **p,
            "id": str(p["id"]) if "id" in p else None,
            "document_id": str(p["document_id"]),
            "image_url": storage.public_url(p["png_key"]) if p.get("png_key") else None,
            "created_at": _iso(p.get("created_at")),
        }
        for p in pages
    ]


@app.get("/documents/{document_id}/tables")
def list_document_tables(document_id: str):
    tables = db.get_tables_for_document(document_id)
    return [
        {
            **t,
            "id": str(t["id"]),
            "document_id": str(t["document_id"]),
            "created_at": _iso(t.get("created_at")),
        }
        for t in tables
    ]


@app.get("/documents/{document_id}/chunks")
def list_document_chunks(document_id: str, limit: int = 100):
    chunks = db.get_chunks_for_document(document_id, limit=limit)
    return [
        {
            **c,
            "id": str(c["id"]),
            "document_id": str(c["document_id"]),
            "created_at": _iso(c.get("created_at")),
        }
        for c in chunks
    ]


# ── Job Status & Progress Tracking ───────────────────────────────────

@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, detail="Job not found")
    return {
        **job,
        "id": str(job["id"]),
        "document_id": str(job["document_id"]),
        "updated_at": _iso(job.get("updated_at")),
    }


# ── Facts & Knowledge Layer ──────────────────────────────────────────

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
        limit=min(limit, 200),
    )
    return [
        {
            **f,
            "id": str(f["id"]),
            "document_id": str(f["document_id"]),
            "chunk_id": str(f["chunk_id"]) if f.get("chunk_id") else None,
            "table_id": str(f["table_id"]) if f.get("table_id") else None,
            "created_at": _iso(f.get("created_at")),
            "embedding": None,
            "quote": f.get("quote"),
            "page": f.get("page") or f.get("page_number"),
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
        raise HTTPException(404, detail="Fact not found")

    relations = [
        {
            **r,
            "relation_id": str(r["relation_id"]),
            "counterpart_id": str(r["counterpart_id"]),
            "created_at": _iso(r.get("created_at")),
        }
        for r in fact.get("relations", [])
    ]

    return {
        **fact,
        "id": str(fact["id"]),
        "document_id": str(fact["document_id"]),
        "chunk_id": str(fact["chunk_id"]) if fact.get("chunk_id") else None,
        "table_id": str(fact["table_id"]) if fact.get("table_id") else None,
        "created_at": _iso(fact.get("created_at")),
        "embedding": None,
        "relations": relations,
    }


# ── Evidence Provenance ──────────────────────────────────────────────

@app.get("/evidence/{fact_id}")
@app.get("/facts/{fact_id}/evidence")
def get_evidence(fact_id: str):
    """Full evidence provenance chain for a fact."""
    evidence = db.get_evidence_for_fact(fact_id)
    if not evidence:
        return {"evidence": [], "message": "No evidence records found for this fact"}
    return {
        "evidence": [
            {
                **e,
                "id": str(e["id"]),
                "document_id": str(e["document_id"]),
                "created_at": _iso(e.get("created_at")),
            }
            for e in evidence
        ]
    }


# ── Relations & Cross-Document Reconciliation ────────────────────────

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
            "created_at": _iso(r.get("created_at")),
        }
        for r in rels
    ]


@app.get("/matrix")
def get_matrix():
    return db.get_matrix_data()


# ── Page Imagery & Coordinates ───────────────────────────────────────

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


# ── Audit Log ────────────────────────────────────────────────────────

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
            "at": _iso(r.get("at")),
        }
        for r in rows
    ]


# ── Review Queue ─────────────────────────────────────────────────────

@app.get("/review")
def list_reviews(status: str = "pending", limit: int = 50):
    items = db.get_review_queue(status=status, limit=min(limit, 100))
    return [
        {
            **r,
            "id": str(r["id"]),
            "fact_id": str(r["fact_id"]) if r.get("fact_id") else None,
            "relation_id": str(r["relation_id"]) if r.get("relation_id") else None,
            "created_at": _iso(r.get("created_at")),
            "reviewed_at": _iso(r.get("reviewed_at")),
        }
        for r in items
    ]


class ReviewDecision(BaseModel):
    status: str  # 'approved', 'rejected', 'deferred'
    reviewer: str = "user"
    decision: str = ""


@app.post("/review/{review_id}")
def resolve_review_item(review_id: str, payload: ReviewDecision):
    if payload.status not in ("approved", "rejected", "deferred"):
        raise HTTPException(400, detail="Status must be 'approved', 'rejected', or 'deferred'")
    result = db.resolve_review(review_id, payload.status, payload.reviewer, payload.decision)
    if not result:
        raise HTTPException(404, detail="Review item not found")
    return {
        **result,
        "id": str(result["id"]),
        "fact_id": str(result["fact_id"]) if result.get("fact_id") else None,
        "reviewed_at": _iso(result.get("reviewed_at")),
    }


@app.get("/review/stats")
def review_stats():
    return db.get_review_stats()


# ── Calculations ─────────────────────────────────────────────────────

class CalculatePayload(BaseModel):
    formula: str  # e.g., 'net_profit_margin', 'yoy_growth', 'cross_foot'
    numerator_fact_id: str | None = None
    denominator_fact_id: str | None = None
    current_fact_id: str | None = None
    previous_fact_id: str | None = None
    line_item_fact_ids: list[str] | None = None
    total_fact_id: str | None = None


@app.post("/calculate")
def run_calculation(payload: CalculatePayload):
    if payload.formula == "cross_foot":
        if not payload.line_item_fact_ids or not payload.total_fact_id:
            raise HTTPException(400, detail="cross_foot requires line_item_fact_ids and total_fact_id")
        result = cross_foot(payload.line_item_fact_ids, payload.total_fact_id)
    elif payload.formula in ("yoy_growth", "growth"):
        if not payload.current_fact_id or not payload.previous_fact_id:
            raise HTTPException(400, detail="growth requires current_fact_id and previous_fact_id")
        result = calculate_growth(payload.current_fact_id, payload.previous_fact_id)
    else:
        if not payload.numerator_fact_id or not payload.denominator_fact_id:
            raise HTTPException(400, detail="ratio requires numerator_fact_id and denominator_fact_id")
        result = calculate_ratio(payload.numerator_fact_id, payload.denominator_fact_id, payload.formula)

    return {
        **result,
        "id": str(result["id"]),
        "fact_id": str(result["fact_id"]) if result.get("fact_id") else None,
        "created_at": _iso(result.get("created_at")),
    }


@app.get("/calculations/{fact_id}")
@app.get("/facts/{fact_id}/calculations")
def get_calculations(fact_id: str):
    calcs = db.get_calculations_for_fact(fact_id)
    return [
        {
            **c,
            "id": str(c["id"]),
            "fact_id": str(c["fact_id"]) if c.get("fact_id") else None,
            "created_at": _iso(c.get("created_at")),
        }
        for c in calcs
    ]


# ── Anomalies ────────────────────────────────────────────────────────

@app.get("/anomalies/{document_id}")
def get_anomalies(document_id: str):
    anomalies = db.get_anomalies_for_document(document_id)
    return [
        {
            **a,
            "id": str(a["id"]),
            "fact_id": str(a["fact_id"]) if a.get("fact_id") else None,
            "created_at": _iso(a.get("created_at")),
            "reviewed_at": _iso(a.get("reviewed_at")),
        }
        for a in anomalies
    ]


# ── Research Chat ────────────────────────────────────────────────────

@app.post("/chat")
def chat(payload: ChatPayload):
    # Wait for the generator to yield the done event to get the final answer if used synchronously
    # Though usually /chat/stream is preferred.
    final_text = ""
    citations = []
    blocks = []
    for raw_chunk in run_research_chat(
        payload.message,
        payload.history,
        deep_research=payload.deep_research,
        web_search=payload.web_search,
    ):
        try:
            chunk = json.loads(raw_chunk)
            if chunk.get("type") == "text":
                final_text += chunk.get("content", "")
            elif chunk.get("type") == "block":
                blocks.append(chunk.get("block"))
            elif chunk.get("type") == "done":
                citations = chunk.get("citations", [])
                if chunk.get("blocks"):
                    blocks = chunk.get("blocks")
        except:
            pass
    return {"answer": final_text, "citations": citations, "blocks": blocks}


@app.post("/chat/stream")
async def chat_stream(payload: ChatPayload):
    """Streaming chat via Server-Sent Events."""
    from fastapi.responses import StreamingResponse

    def generate():
        for chunk_str in run_research_chat(
            payload.message,
            payload.history,
            deep_research=payload.deep_research,
            web_search=payload.web_search,
        ):
            yield f"data: {chunk_str}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Findings & Analysis ──────────────────────────────────────────────

@app.get("/findings")
def list_findings(
    category: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    document_id: str | None = None,
    limit: int = 100,
):
    findings = db.get_findings(
        category=category,
        severity=severity,
        status=status,
        document_id=document_id,
        limit=min(limit, 200),
    )
    return [
        {
            **f,
            "id": str(f["id"]),
            "case_id": str(f["case_id"]) if f.get("case_id") else None,
            "created_at": _iso(f.get("created_at")),
        }
        for f in findings
    ]


@app.get("/findings/summary")
def findings_summary():
    return db.get_findings_summary()


@app.get("/findings/{finding_id}")
def get_finding_detail(finding_id: str):
    finding = db.get_finding(finding_id)
    if not finding:
        raise HTTPException(404, detail="Finding not found")

    # Enrich with fact details for drilldown
    fact_details = []
    for fid in (finding.get("fact_ids") or []):
        fact = db.get_fact_with_relations(str(fid))
        if fact:
            fact_details.append({
                "id": str(fact["id"]),
                "entity_canon": fact.get("entity_canon"),
                "attribute_canon": fact.get("attribute_canon"),
                "raw_value": fact.get("raw_value"),
                "norm_value": fact.get("norm_value"),
                "period": fact.get("period"),
                "scope": fact.get("scope"),
                "quote": fact.get("quote"),
                "page": fact.get("page"),
                "filename": fact.get("document_filename"),
                "confidence": fact.get("confidence"),
            })

    return {
        **finding,
        "id": str(finding["id"]),
        "case_id": str(finding["case_id"]) if finding.get("case_id") else None,
        "created_at": _iso(finding.get("created_at")),
        "fact_details": fact_details,
    }


class FindingStatusUpdate(BaseModel):
    status: str  # 'confirmed', 'dismissed', 'resolved'


@app.post("/findings/{finding_id}/status")
def update_finding(finding_id: str, payload: FindingStatusUpdate):
    if payload.status not in ("confirmed", "dismissed", "resolved", "open"):
        raise HTTPException(400, detail="Status must be 'open', 'confirmed', 'dismissed', or 'resolved'")
    result = db.update_finding_status(finding_id, payload.status)
    if not result:
        raise HTTPException(404, detail="Finding not found")
    return {
        **result,
        "id": str(result["id"]),
        "created_at": _iso(result.get("created_at")),
    }


class AnalyzePayload(BaseModel):
    document_ids: list[str] | None = None


@app.post("/analyze")
async def trigger_analysis(payload: AnalyzePayload, background_tasks: BackgroundTasks):
    """Trigger on-demand analysis. Runs in background to avoid HTTP timeouts."""
    db.audit("analysis.triggered", meta={"document_ids": payload.document_ids})

    background_tasks.add_task(run_analysis, payload.document_ids)

    return {
        "status": "analysis_started",
        "document_ids": payload.document_ids,
        "message": "Analysis is running in the background. Poll /findings for results.",
    }

