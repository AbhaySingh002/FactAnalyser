"""Schema-constrained fact extraction via Groq llama-3.3-70b-versatile."""

from __future__ import annotations

import os
import time
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from rapidfuzz import fuzz

from .. import db

PROMPT_VER = "v1"
EXTRACTION_MODEL = "llama-3.3-70b-versatile"
MIN_QUOTE_SIMILARITY = 85.0
FALLBACK_CONFIDENCE = 0.15

SYSTEM_PROMPT = (
    "You are a factual extraction engine for financial/legal documents. "
    "Extract ONLY discrete claims explicitly present. Every fact MUST include a verbatim quote from the chunk. "
    "Never infer values. Return only JSON matching the schema: "
    '{"facts": [{"entity": str, "entity_type": str|null, "attribute": str, "raw_value": str, '
    '"value_number": float|null, "unit": str|null, "currency": str|null, "period": str|null, '
    '"scope": str|null, "quote": str, "confidence": float}]}'
)


class FactExtract(BaseModel):
    entity: str
    entity_type: str | None = None
    attribute: str
    raw_value: str
    value_number: float | None = None
    unit: str | None = None
    currency: str | None = None
    period: str | None = None
    scope: str | None = None
    quote: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class FactExtractResponse(BaseModel):
    facts: list[FactExtract] = []


def _get_client() -> OpenAI | None:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")


def extract_facts_from_chunk(
    chunk_id: str,
    text: str,
    chunk_type: str,
    heading: str | None = None,
) -> list[FactExtract]:
    """Extract structured facts from chunk with one retry on schema failure."""
    client = _get_client()
    if not client:
        # ponytail: fallback if GROQ_API_KEY not set in dev
        return [
            FactExtract(
                entity="unknown",
                attribute="extraction_failure",
                raw_value="missing_api_key",
                quote=text[:300],
                confidence=FALLBACK_CONFIDENCE,
            )
        ]

    user_content = f"Context:\nChunk Type: {chunk_type}\nHeading: {heading or 'None'}\n\nChunk Text:\n{text}"
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    t0 = time.monotonic()
    total_tokens = 0

    try:
        resp = client.chat.completions.create(
            model=EXTRACTION_MODEL,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
        )
        total_tokens += resp.usage.total_tokens if resp.usage else 0
        raw_json = resp.choices[0].message.content or "{}"
        parsed = FactExtractResponse.model_validate_json(raw_json)
        facts = parsed.facts

    except (ValidationError, Exception) as err:
        # ONE retry appending validation error
        try:
            retry_messages = list(messages) + [
                {"role": "assistant", "content": locals().get("raw_json", "")},
                {"role": "user", "content": f"The output did not conform to schema: {err}. Output valid JSON now."},
            ]
            retry_resp = client.chat.completions.create(
                model=EXTRACTION_MODEL,
                messages=retry_messages,
                response_format={"type": "json_object"},
                temperature=0,
            )
            total_tokens += retry_resp.usage.total_tokens if retry_resp.usage else 0
            raw_retry = retry_resp.choices[0].message.content or "{}"
            parsed = FactExtractResponse.model_validate_json(raw_retry)
            facts = parsed.facts
        except Exception:
            # Final failure fallback
            facts = [
                FactExtract(
                    entity="unknown",
                    attribute="extraction_failure",
                    raw_value="validation_error",
                    quote=text[:300],
                    confidence=FALLBACK_CONFIDENCE,
                )
            ]

    latency_ms = int((time.monotonic() - t0) * 1000)

    # Fuzzy quote verification against chunk text
    for f in facts:
        if f.attribute == "extraction_failure":
            continue
        sim = fuzz.partial_ratio(f.quote.lower(), text.lower())
        if sim < MIN_QUOTE_SIMILARITY:
            f.confidence = round(min(f.confidence, 0.4), 2)

    db.audit(
        "fact.extract",
        target={"chunk_id": str(chunk_id)},
        meta={
            "model": EXTRACTION_MODEL,
            "prompt_ver": PROMPT_VER,
            "tokens": total_tokens,
            "latency_ms": latency_ms,
            "fact_count": len(facts),
        },
    )

    return facts
