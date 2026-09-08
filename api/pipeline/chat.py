"""Grounded Fact-Centric RAG chatbot backend with strict citations."""

from __future__ import annotations

import os
import re
from openai import OpenAI

from .. import db
from .embed import embed_text

CHAT_MODEL = "llama-3.3-70b-versatile"
REFUSAL_MESSAGE = "The knowledge layer has no grounded fact for this."

SYSTEM_PROMPT = (
    "You are a strict, factual Q&A engine for financial and legal due-diligence. "
    "Answer the user's question in concise markdown using ONLY the provided facts in the Context. "
    "Every single claim MUST be cited with the exact tag [F{id}] corresponding to the fact. "
    "Never quote text that is not present in the fact's quote. "
    "If the context does not contain sufficient grounded facts to directly answer the question, "
    f"you must answer with EXACTLY and ONLY: '{REFUSAL_MESSAGE}' and stop immediately."
)


def _get_client() -> OpenAI | None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")


def answer_question(message: str, history: list[dict] | None = None) -> dict:
    """Execute grounded fact-centric RAG: retrieve facts -> prompt Groq -> cite facts."""
    query = message.strip()
    if not query:
        return {"answer": REFUSAL_MESSAGE, "citations": []}

    # 1. Retrieval: Vector top-8 + Keyword top-5
    q_vec = embed_text(query)
    vector_facts = db.search_facts(query_vector=q_vec, limit=8)

    words = [
        w for w in re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", query.lower())
        if w not in {"what", "when", "where", "which", "whose", "does", "have", "with", "from", "that", "this", "were", "been"}
    ]
    keyword_facts = db.search_facts_keyword(tokens=words[:5], limit=5)

    # Merge, dedupe, and filter confidence > 0.4
    all_facts_map: dict[str, dict] = {}
    for f in vector_facts + keyword_facts:
        if float(f.get("confidence") or 0.0) > 0.4:
            all_facts_map[str(f["id"])] = f

    candidate_facts = list(all_facts_map.values())[:40]

    # Empty retrieval -> deterministic refusal without LLM call
    if not candidate_facts:
        db.audit(
            "chat",
            meta={
                "query": query,
                "retrieved_ids": [],
                "cited_ids": [],
                "answer_len": len(REFUSAL_MESSAGE),
            },
        )
        return {"answer": REFUSAL_MESSAGE, "citations": []}

    # 2. Build Context Block
    context_lines = []
    for f in candidate_facts:
        fid = str(f["id"])
        ent = f.get("entity_canon") or f.get("entity") or "Unknown"
        att = f.get("attribute_canon") or f.get("attribute") or "Value"
        raw = f.get("raw_value") or ""
        period = f.get("period") or "N/A"
        scope = f.get("scope") or "N/A"
        fn = f.get("filename") or "document"
        page = f.get("page")
        page_str = f"p.{page + 1}" if page is not None else "p.?"
        quote = f.get("quote") or ""
        context_lines.append(f'[F{fid}] {ent} {att} = {raw} ({period}, {scope}) — doc {fn} {page_str}: "{quote}"')

    context_block = "\n".join(context_lines)

    # 3. Call Groq
    client = _get_client()
    if not client:
        # ponytail: fallback if GROQ_API_KEY unset in local dev
        return {"answer": REFUSAL_MESSAGE, "citations": []}

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        for h in history[-4:]:  # last 2 turns
            if h.get("role") and h.get("content"):
                messages.append({"role": h["role"], "content": h["content"]})

    messages.append({
        "role": "user",
        "content": f"Context:\n{context_block}\n\nQuestion: {query}",
    })

    try:
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            temperature=0,
        )
        raw_answer = (resp.choices[0].message.content or "").strip()
    except Exception as ex:
        db.audit("chat.error", meta={"error": str(ex)})
        return {"answer": REFUSAL_MESSAGE, "citations": []}

    # 4. Check refusal or extract citations
    if REFUSAL_MESSAGE.lower() in raw_answer.lower():
        final_answer = REFUSAL_MESSAGE
        citations = []
    else:
        final_answer = raw_answer
        cited_ids = set(re.findall(r"\[F([a-f0-9\-]+)\]", final_answer, re.IGNORECASE))
        citations = []
        for f in candidate_facts:
            fid = str(f["id"])
            if fid in cited_ids:
                citations.append({
                    "fact_id": fid,
                    "page": f.get("page"),
                    "filename": f.get("filename"),
                    "quote": f.get("quote"),
                })

        # Constraint: citations array must equal the set of ids present in answer
        # If model hallucinated non-existent IDs, scrub them from answer or ensure exact match
        valid_fids = {c["fact_id"] for c in citations}
        # If any cited ID is invalid, remove it from text
        for cid in cited_ids:
            if cid not in valid_fids:
                final_answer = re.sub(rf"\[F{re.escape(cid)}\]", "", final_answer)

        # If answer has no valid citations and did not say refusal, fall back to refusal
        if not citations and len(final_answer) > 0 and REFUSAL_MESSAGE not in final_answer:
            final_answer = REFUSAL_MESSAGE

    db.audit(
        "chat",
        meta={
            "query": query,
            "retrieved_ids": [str(f["id"]) for f in candidate_facts],
            "cited_ids": [c["fact_id"] for c in citations],
            "answer_len": len(final_answer),
        },
    )

    return {"answer": final_answer, "citations": citations}
