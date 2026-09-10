import json
import logging
import re
import time
import urllib.parse
import urllib.request
from typing import Iterator

from .. import db
from . import models
from .embed import embed_text

logger = logging.getLogger(__name__)

def search_duckduckgo(query: str, max_results: int = 3) -> list[dict]:
    """Extremely lazy/ponytail web search using DuckDuckGo HTML."""
    try:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8")
        
        results = []
        # Parse result snippets roughly using regex
        blocks = re.findall(r'<a class="result__snippet[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
        for href, snippet in blocks[:max_results]:
            snippet_clean = re.sub(r'<[^>]+>', '', snippet).strip()
            results.append({"url": href, "snippet": snippet_clean})
        return results
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed: {e}")
        return []

def _yield_step(step_id: str, title: str, status: str = "completed", **kwargs) -> str:
    step = {"id": step_id, "title": title, "status": status}
    step.update(kwargs)
    return json.dumps({"type": "step", "step": step})

def _yield_done(citations: list, blocks: list) -> str:
    return json.dumps({"type": "done", "citations": citations, "blocks": blocks})

def _yield_text(content: str) -> str:
    return json.dumps({"type": "text", "content": content})

def _yield_block(block: dict) -> str:
    return json.dumps({"type": "block", "block": block})


def run_research_chat(
    message: str,
    history: list[dict] | None = None,
    deep_research: bool = True,
    web_search: bool = True,
) -> Iterator[str]:
    """
    Yields SSE events: ResearchStep updates followed by final text and structured blocks.
    """
    query = message.strip()
    if not query:
        yield _yield_done([], [])
        return
        
    # Step 1: Intent & Decomposition
    yield _yield_step("s1", "Analyzing intent & decomposing query", status="running")
    
    prompt = (
        "You are a financial research orchestrator. Decompose the user's query into 1-3 specific search sub-queries.\n"
        f"Question: {query}\n\n"
        'Respond strictly in JSON format: {"intent": "...", "sub_queries": ["...", "..."], "needs_external_web": true/false}'
    )
    
    try:
        raw_json, _ = models.complete(
            messages=prompt,
            system="Return only JSON.",
            temperature=0.0,
            max_tokens=200
        )
        plan = json.loads(raw_json)
        sub_queries = plan.get("sub_queries", [query])
        needs_web = plan.get("needs_external_web", False) and web_search
        intent = plan.get("intent", "Analyze query")
    except Exception:
        sub_queries = [query]
        needs_web = False
        intent = "General research"

    yield _yield_step("s1", f"Analyzed intent: {intent}", detail=f"Decomposed into {len(sub_queries)} searches.")

    max_loops = 2 if deep_research else 1
    loop_count = 0
    candidate_facts = {}
    web_results = []
    
    while loop_count < max_loops:
        loop_count += 1
        
        # Step: Internal Knowledge Retrieval
        yield _yield_step(f"s2_{loop_count}", f"Querying internal document knowledge (Iteration {loop_count})", status="running")
        
        for sq in sub_queries:
            q_vec = embed_text(sq)
            v_facts = db.search_facts(query_vector=q_vec, limit=5)
            k_facts = db.search_facts_keyword(tokens=sq.split()[:5], limit=5)
            for f in v_facts + k_facts:
                fid = str(f["id"])
                if fid not in candidate_facts:
                    candidate_facts[fid] = f

        fact_list = list(candidate_facts.values())[:30]
        
        yield _yield_step(f"s2_{loop_count}", f"Internal knowledge retrieved (Iteration {loop_count})", sourcesCount=len(fact_list))

        # Step: External Web Research (if enabled)
        if needs_web and web_search:
            yield _yield_step(f"s3_{loop_count}", f"Executing external web research (Iteration {loop_count})", status="running")
            
            for sq in sub_queries[:2]:
                res = search_duckduckgo(sq)
                web_results.extend(res)
                
            yield _yield_step(f"s3_{loop_count}", f"External web research completed (Iteration {loop_count})", sourcesCount=len(web_results))

        if not deep_research:
            break

        # Step: Verification of Evidence
        yield _yield_step(f"s_verify_{loop_count}", f"Verifying collected evidence (Iteration {loop_count})", status="running")

        context_summary = ""
        for i, f in enumerate(fact_list[:15]):
            ent = f.get("entity_canon") or f.get("entity") or "Unknown"
            att = f.get("attribute_canon") or f.get("attribute") or "Value"
            raw = f.get("raw_value") or ""
            context_summary += f"- {ent} {att} = {raw}\n"
        for w in web_results[:5]:
            context_summary += f"- Web: {w['snippet']}\n"

        verify_prompt = (
            f"Question: {query}\n"
            f"Evidence Collected so far:\n{context_summary}\n"
            "Do we have enough concrete financial evidence to answer this question accurately? "
            "If yes, return {\"ready\": true}. If no, return {\"ready\": false, \"missing\": \"...\", \"next_queries\": [\"...\", \"...\"]} strictly in JSON."
        )
        
        try:
            ver_json, _ = models.complete(verify_prompt, system="Return only JSON.", temperature=0.0, max_tokens=200)
            ver_plan = json.loads(ver_json)
            is_ready = ver_plan.get("ready", True)
            missing = ver_plan.get("missing", "")
            next_qs = ver_plan.get("next_queries", [])
        except Exception:
            is_ready = True
            missing = ""
            next_qs = []

        if is_ready or not next_qs or loop_count >= max_loops:
            yield _yield_step(f"s_verify_{loop_count}", "Evidence verification complete (Ready)")
            break
        else:
            sub_queries = next_qs
            yield _yield_step(f"s_verify_{loop_count}", f"Missing evidence: {missing}. Formulated {len(next_qs)} new queries.")

    # Step 4: Final Synthesis
    yield _yield_step("s4", "Synthesizing and formatting response", status="running")
    
    context_lines = []
    index_to_fact = {}
    for i, f in enumerate(fact_list):
        idx_str = str(i + 1)
        index_to_fact[idx_str] = f
        ent = f.get("entity_canon") or f.get("entity") or "Unknown"
        att = f.get("attribute_canon") or f.get("attribute") or "Value"
        raw = f.get("raw_value") or ""
        period = f.get("period") or "N/A"
        scope = f.get("scope") or "N/A"
        fn = f.get("filename") or "document"
        page = f.get("page")
        page_str = str(page + 1) if page is not None else "?"
        quote = f.get("quote") or ""
        context_lines.append(f'[{idx_str}] {ent} {att} = {raw} ({period}, {scope}) — {fn} p.{page_str}: "{quote}"')

    if web_results:
        context_lines.append("\nExternal Web Context:")
        for i, w in enumerate(web_results):
            context_lines.append(f'[W{i+1}] {w["url"]}: {w["snippet"]}')
            
    context_block = "\n".join(context_lines)
    
    history_snippet = []
    if history:
        for h in history[-4:]:
            role = h.get("role", "user")
            content = h.get("content", "")
            history_snippet.append(f"{role}: {content}")

    system_prompt = (
        "You are an elite financial due-diligence assistant. You answer based ONLY on the provided Context.\n"
        "Citation rules:\n"
        "1. Cite internal facts strictly using numbered footnote notation [1], [2], etc., corresponding to the numbered context entries. (Do not cite non-existent indices).\n"
        "2. Cite external web results using [W1], [W2], etc.\n"
        "3. Place citations immediately following the specific statement, metric, or figure they support.\n\n"
        "Structured blocks:\n"
        "When appropriate to present data visually (such as trends, comparisons, metrics, or anomalies), embed JSON code blocks using ```json:block ... ```.\n"
        "Supported block formats:\n"
        "- Chart: ```json:block {\"type\": \"chart\", \"chartType\": \"bar\"|\"line\"|\"area\", \"title\": \"...\", \"data\": [{\"period\": \"...\", \"val\": 123}], \"config\": {\"xAxisKey\": \"period\", \"series\": [{\"dataKey\": \"val\", \"label\": \"...\"}]}} ```\n"
        "- Table: ```json:block {\"type\": \"table\", \"title\": \"...\", \"columns\": [{\"key\": \"...\", \"label\": \"...\"}], \"rows\": [{\"...\": \"...\"}]} ```\n"
        "- Metrics: ```json:block {\"type\": \"metrics\", \"title\": \"...\", \"items\": [{\"label\": \"...\", \"value\": \"...\", \"change\": \"+...%\", \"trend\": \"up\"|\"down\"|\"neutral\"}]} ```\n"
        "- Finding: ```json:block {\"type\": \"finding\", \"title\": \"...\", \"category\": \"variance\"|\"contradiction\"|\"corroboration\"|\"insight\", \"content\": \"...\", \"confidence\": 0.95} ```\n\n"
        "Format standard prose with clear markdown headings, bullet points, and concise financial summaries."
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"History:\n{chr(10).join(history_snippet)}\n\nContext:\n{context_block}\n\nQuestion: {query}"}
    ]
    
    try:
        raw_answer, used_model = models.complete(messages=messages, max_tokens=1500)
    except Exception as e:
        raw_answer = "Error generating synthesis: " + str(e)
        used_model = "error"
        
    yield _yield_step("s4", "Synthesis complete")

    # Extract [1], [2], or [F1], [F2] citations
    cited_token_matches = re.findall(r"\[(?:F)?([0-9]+)\]", raw_answer)
    seen_indices = set()
    citations = []
    for token in cited_token_matches:
        fact = index_to_fact.get(token)
        if fact and token not in seen_indices:
            seen_indices.add(token)
            fid = str(fact["id"])
            citations.append({
                "index": int(token),
                "fact_id": fid,
                "filename": fact.get("filename") or "document.pdf",
                "page": fact.get("page"),
                "quote": fact.get("quote"),
                "entity": fact.get("entity_canon") or fact.get("entity") or "",
                "attribute": fact.get("attribute_canon") or fact.get("attribute") or "",
                "raw_value": fact.get("raw_value") or "",
                "confidence": fact.get("confidence") or 0.95,
            })
            
    # Parse blocks out of the text in the backend
    blocks = []
    clean_answer = raw_answer
    block_matches = list(re.finditer(r"```(?:json:block|json)\s*(.*?)\s*```", clean_answer, flags=re.IGNORECASE | re.DOTALL))
    for match in reversed(block_matches):
        raw_json = match.group(1).strip()
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict) and "type" in parsed:
                if "id" not in parsed:
                    parsed["id"] = f"blk_{len(blocks)+1}_{int(time.time())}"
                blocks.append(parsed)
                clean_answer = clean_answer[:match.start()] + clean_answer[match.end():]
        except Exception:
            pass
            
    blocks.reverse() # Restore original order
    clean_answer = clean_answer.strip()

    for block in blocks:
        yield _yield_step(f"art-{block.get('id', len(blocks))}", f"Artifact created: {block.get('title', block.get('type'))}")
        yield _yield_block(block)

    # Stream the actual clean text response in small chunks
    chunk_size = 64
    for i in range(0, len(clean_answer), chunk_size):
        chunk = clean_answer[i:i + chunk_size]
        yield _yield_text(chunk)
        
    # Final done event
    yield _yield_step("s5", "Answer ready")
    yield _yield_done(citations, blocks)
