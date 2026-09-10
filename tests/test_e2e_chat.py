import asyncio
import httpx
import json
import pytest

@pytest.mark.anyio
async def test_research_chat_stream():
    url = "http://127.0.0.1:8000/chat/stream"
    payload = {
        "message": "What is the ARR and how does it compare to the pitch deck?"
    }
    
    print("Testing Research Chat SSE Stream...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            async with client.stream("POST", url, json=payload, headers={"Authorization": "Bearer dev-secret-key"}) as response:
                if response.status_code != 200:
                    print(f"Failed with status: {response.status_code}")
                    return
                
                async for line in response.aiter_lines():
                    line = line.strip()
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if data["type"] == "step":
                            print(f"[STEP] {data['step'].get('title')} - {data['step'].get('status')}")
                        elif data["type"] == "block":
                            print(f"[BLOCK] Extracted structured block: {data['block'].get('type')}")
                        elif data["type"] == "done":
                            print("[DONE] Research complete.")
                            print(f"Citations attached: {len(data.get('citations', []))}")
                            print(f"Blocks attached: {len(data.get('blocks', []))}")
        except Exception as e:
            print(f"Error during SSE connection: {e}")


def test_research_chat_citation_and_blocks_unit():
    """Verify run_research_chat yields steps, parses structured blocks, and maps numbered citations."""
    from unittest.mock import patch
    from api.pipeline.research import run_research_chat

    fake_fact = {
        "id": "uuid-fact-12345",
        "entity": "Acme Corp",
        "entity_canon": "acme corp",
        "attribute": "Revenue",
        "attribute_canon": "revenue",
        "raw_value": "$100M",
        "period": "FY2023",
        "scope": "consolidated",
        "filename": "acme_10k.pdf",
        "page": 41,
        "quote": "Total revenue reached $100M.",
        "confidence": 0.96,
    }

    mock_llm_answer = (
        "Acme Corp reported $100M in revenue for FY2023 [1].\n\n"
        "```json:block\n"
        '{"type": "metrics", "title": "Key Indicators", "items": [{"label": "Revenue", "value": "$100M"}]}\n'
        "```"
    )

    with patch("api.pipeline.research.db.search_facts", return_value=[fake_fact]), \
         patch("api.pipeline.research.db.search_facts_keyword", return_value=[]), \
         patch("api.pipeline.research.embed_text", return_value=[0.1] * 768), \
         patch("api.pipeline.models.complete") as mock_complete:

        # When deep_research=False, verification is skipped.
        # 1st call: intent decomposition, 2nd call: synthesis
        mock_complete.side_effect = [
            ('{"intent": "Revenue check", "sub_queries": ["Acme Revenue"], "needs_external_web": false}', "model"),
            (mock_llm_answer, "model"),
        ]

        events = list(run_research_chat("What is Acme revenue?", deep_research=False, web_search=False))
        parsed_events = [json.loads(e) for e in events]

        types = [e["type"] for e in parsed_events]
        assert "step" in types
        assert "block" in types
        assert "text" in types
        assert "done" in types

        # Check block extraction
        block_event = next(e for e in parsed_events if e["type"] == "block")
        assert block_event["block"]["type"] == "metrics"
        assert block_event["block"]["title"] == "Key Indicators"

        # Check done event and citations
        done_event = next(e for e in parsed_events if e["type"] == "done")
        citations = done_event["citations"]
        assert len(citations) == 1
        assert citations[0]["index"] == 1
        assert citations[0]["fact_id"] == "uuid-fact-12345"
        assert citations[0]["filename"] == "acme_10k.pdf"
        assert citations[0]["page"] == 41
        assert citations[0]["quote"] == "Total revenue reached $100M."
        assert citations[0]["raw_value"] == "$100M"


def test_research_chat_deep_research_multi_citation():
    """Verify deep research mode runs verification loop and handles multiple citations and chart blocks."""
    from unittest.mock import patch
    from api.pipeline.research import run_research_chat

    f1 = {"id": "fact-1", "entity": "Beta LLC", "attribute": "EBITDA", "raw_value": "$40M", "filename": "doc1.pdf", "page": 10, "quote": "EBITDA $40M"}
    f2 = {"id": "fact-2", "entity": "Beta LLC", "attribute": "ARR", "raw_value": "$120M", "filename": "doc2.pdf", "page": 5, "quote": "ARR reached $120M"}

    mock_answer = (
        "Beta LLC EBITDA was $40M [1] and ARR reached $120M [2].\n\n"
        "```json:block\n"
        '{"type": "chart", "chartType": "bar", "title": "Growth", "data": [{"year": "2023", "arr": 120}]}\n'
        "```"
    )

    with patch("api.pipeline.research.db.search_facts", return_value=[f1, f2]), \
         patch("api.pipeline.research.db.search_facts_keyword", return_value=[]), \
         patch("api.pipeline.research.embed_text", return_value=[0.1] * 768), \
         patch("api.pipeline.models.complete") as mock_complete:

        mock_complete.side_effect = [
            ('{"intent": "Financial audit", "sub_queries": ["Beta metrics"], "needs_external_web": false}', "model"),
            ('{"ready": true}', "model"),
            (mock_answer, "model"),
        ]

        events = list(run_research_chat("Audit Beta LLC", deep_research=True, web_search=False))
        parsed = [json.loads(e) for e in events]

        done = next(e for e in parsed if e["type"] == "done")
        assert len(done["citations"]) == 2
        assert done["citations"][0]["index"] == 1
        assert done["citations"][0]["fact_id"] == "fact-1"
        assert done["citations"][1]["index"] == 2
        assert done["citations"][1]["fact_id"] == "fact-2"

        block = next(e for e in parsed if e["type"] == "block")
        assert block["block"]["type"] == "chart"
        assert block["block"]["title"] == "Growth"



