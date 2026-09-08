"""Grounded Fact-Centric RAG chatbot backend with strict citations.

Answers questions ONLY from stored facts with verifiable citations:
- Fact-centric retrieval (top-8 cosine via pgvector + top-5 keyword via SQL)
- Strict grounded context lines: [F{id}] {entity} {attribute} = {raw} ({period}, {scope}) — {filename} p.{page}: "{quote}"
- Strict refusal if facts are absent/insufficient: "The knowledge layer has no grounded fact for this."
- Citation validation: citations array equals the set of cited ids in answer
"""

from __future__ import annotations

import os
import re
from openai import OpenAI

from .. import db
from .embed import embed_text

CHAT_MODEL = "llama-3.3-70b-versatile"
REFUSAL_MESSAGE = "The knowledge layer has no grounded fact for this."

SYSTEM_PROMPT = (
    "Answer in markdown using ONLY the context. Cite every claim as [F{id}]. "
    f"If context is insufficient reply exactly: {REFUSAL_MESSAGE}"
)


def _get_client() -> OpenAI | None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1", timeout=60.0)


def answer_question(message: str, history: list[dict] | None = None) -> dict:
    """Execute grounded fact-centric RAG: retrieve facts -> prompt Groq -> cite facts."""
    query = message.strip()
    if not query:
        return {"answer": REFUSAL_MESSAGE, "citations": []}

    # 1. Retrieval: Vector top-8 + Keyword top-5 on entity/attribute columns
    q_vec = embed_text(query)
    vector_facts = db.search_facts(query_vector=q_vec, limit=8)

    words = [
        w for w in re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", query.lower())
        if w not in {"what", "when", "where", "which", "whose", "does", "have", "with", "from", "that", "this", "were", "been"}
    ]
    keyword_facts = db.search_facts_keyword(tokens=words[:5], limit=5)

    # Merge, dedupe, and filter confidence >= 0.4, cap at 40
    all_facts_map: dict[str, dict] = {}
    for f in vector_facts + keyword_facts:
        if float(f.get("confidence") or 0.0) >= 0.4:
            all_facts_map[str(f["id"])] = f

    candidate_facts = list(all_facts_map.values())[:40]

    # Empty retrieval -> deterministic refusal without LLM call (no hallucination path)
    if not candidate_facts:
        db.audit(
            "chat",
            meta={
                "query": query,
                "retrieved": [],
                "cited": [],
                "answer_len": len(REFUSAL_MESSAGE),
            },
        )
        return {"answer": REFUSAL_MESSAGE, "citations": []}

    # 2. Build Context Lines
    # Map index (1..N) and fact UUID for citation resolution
    index_to_fact: dict[str, dict] = {}
    uuid_to_fact: dict[str, dict] = {}
    context_lines = []

    for i, f in enumerate(candidate_facts):
        idx_str = str(i + 1)
        fid_str = str(f["id"])
        index_to_fact[idx_str] = f
        uuid_to_fact[fid_str] = f

        ent = f.get("entity_canon") or f.get("entity") or "Unknown"
        att = f.get("attribute_canon") or f.get("attribute") or "Value"
        raw = f.get("raw_value") or ""
        period = f.get("period") or "N/A"
        scope = f.get("scope") or "N/A"
        fn = f.get("filename") or "document"
        page = f.get("page")
        page_str = str(page + 1) if page is not None else "?"
        quote = f.get("quote") or ""

        # [F{id}] {entity} {attribute} = {raw_value} ({period}, {scope}) — {filename} p.{page}: "{quote}"
        context_lines.append(f'[F{idx_str}] {ent} {att} = {raw} ({period}, {scope}) — {fn} p.{page_str}: "{quote}"')

    context_block = "\n".join(context_lines)

    # 3. Call Groq
    client = _get_client()
    if not client:
        # ponytail: fallback if GROQ_API_KEY unset in local dev/testing
        return {"answer": REFUSAL_MESSAGE, "citations": []}

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        for h in history[-4:]:
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
        # Extract citation tokens like [F1] or [F{uuid}]
        cited_token_matches = re.findall(r"\[F([a-zA-Z0-9_\-]+)\]", final_answer)
        seen_fact_ids = set()
        citations = []
        valid_tokens = set()

        for token in cited_token_matches:
            fact = index_to_fact.get(token) or uuid_to_fact.get(token)
            if fact:
                fid = str(fact["id"])
                valid_tokens.add(token)
                if fid not in seen_fact_ids:
                    seen_fact_ids.add(fid)
                    citations.append({
                        "fact_id": fid,
                        "filename": fact.get("filename"),
                        "page": fact.get("page"),
                        "quote": fact.get("quote"),
                    })

        # Remove hallucinated tokens not matching any retrieved fact
        for token in set(cited_token_matches):
            if token not in valid_tokens:
                final_answer = re.sub(rf"\[F{re.escape(token)}\]", "", final_answer).strip()

        # If answer has no valid citations and didn't output exact refusal, force refusal
        if not citations and REFUSAL_MESSAGE not in final_answer:
            final_answer = REFUSAL_MESSAGE

    db.audit(
        "chat",
        meta={
            "query": query,
            "retrieved": [str(f["id"]) for f in candidate_facts],
            "cited": [c["fact_id"] for c in citations],
            "answer_len": len(final_answer),
        },
    )

    return {"answer": final_answer, "citations": citations}
