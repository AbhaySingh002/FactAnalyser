"""OCR client — rate-limited round-robin vision OCR with cooldown failover.

Providers:
- Groq vision (llama-4-scout)
- Gemini vision (gemini-2.0-flash)

Behavior:
1. Consecutive scanned pages alternate between providers in round-robin order.
2. Per-provider pacing (minimum interval + requests-per-minute ceiling) prevents rate limit exhaustion.
3. Cooldown with exponential backoff on failures, with automatic failover to the healthy provider.
4. Deterministic markdown output (temperature 0, table preserving, 60s hard timeout).
5. Error isolation: failures produce audit entries and visible needs-review chunks.
"""

from __future__ import annotations

import base64
import collections
import os
import random
import re
import time
from typing import Callable

from .. import db

# ── Configurable Constants ───────────────────────────────────────────
GROQ_MIN_INTERVAL: float = float(os.environ.get("GROQ_MIN_INTERVAL", "2.0"))
GROQ_RPM_CEILING: int = int(os.environ.get("GROQ_RPM_CEILING", "30"))

GEMINI_MIN_INTERVAL: float = float(os.environ.get("GEMINI_MIN_INTERVAL", "4.0"))
GEMINI_RPM_CEILING: int = int(os.environ.get("GEMINI_RPM_CEILING", "15"))

CALL_TIMEOUT_SECONDS: float = float(os.environ.get("OCR_TIMEOUT_SECONDS", "60.0"))
BASE_COOLDOWN_SECONDS: float = float(os.environ.get("OCR_BASE_COOLDOWN_SECONDS", "15.0"))
MAX_COOLDOWN_SECONDS: float = float(os.environ.get("OCR_MAX_COOLDOWN_SECONDS", "120.0"))
COOLDOWN_GROWTH_FACTOR: float = float(os.environ.get("OCR_COOLDOWN_GROWTH_FACTOR", "2.0"))

TRANSIENT_RETRY_BASE_SECONDS: float = float(os.environ.get("OCR_RETRY_BASE_SECONDS", "1.0"))
TRANSIENT_RETRY_JITTER_SECONDS: float = float(os.environ.get("OCR_RETRY_JITTER_SECONDS", "0.5"))

OCR_PAGE_BUDGET: int = int(os.environ.get("OCR_PAGE_BUDGET", "60"))

OCR_PROMPT = (
    "Transcribe this document page as markdown. Preserve tables as markdown tables with header rows, "
    "keep section headings and reading order. Output only the markdown without commentary or preamble."
)


class OcrUnavailable(Exception):
    pass


class ProviderState:
    """Tracks rate limiting, pacing, and cooldown state for a single vision provider."""

    def __init__(self, name: str, min_interval: float, rpm_ceiling: int):
        self.name = name
        self.min_interval = min_interval
        self.rpm_ceiling = rpm_ceiling
        self.last_call_time: float = 0.0
        self.call_timestamps: collections.deque[float] = collections.deque()
        self.cooldown_until: float = 0.0
        self.consecutive_cooldowns: int = 0

    def is_cooling_down(self) -> bool:
        return time.monotonic() < self.cooldown_until

    def wait_for_pacing(self):
        """Enforce min-interval spacing and requests-per-minute ceiling; prevents bursts."""
        now = time.monotonic()
        # 1. Min interval check
        elapsed = now - self.last_call_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
            now = time.monotonic()

        # 2. RPM ceiling rolling window (last 60s)
        while self.call_timestamps and self.call_timestamps[0] <= now - 60.0:
            self.call_timestamps.popleft()

        if len(self.call_timestamps) >= self.rpm_ceiling:
            sleep_needed = (self.call_timestamps[0] + 60.0) - now
            if sleep_needed > 0:
                time.sleep(sleep_needed)
                now = time.monotonic()
            while self.call_timestamps and self.call_timestamps[0] <= now - 60.0:
                self.call_timestamps.popleft()

        self.call_timestamps.append(now)
        self.last_call_time = now

    def trigger_cooldown(self, server_delay: float | None = None) -> float:
        """Enter cooldown with growing backoff, honoring any server-provided retry delay."""
        if server_delay and server_delay > 0:
            duration = max(server_delay, BASE_COOLDOWN_SECONDS * (COOLDOWN_GROWTH_FACTOR ** self.consecutive_cooldowns))
        else:
            duration = BASE_COOLDOWN_SECONDS * (COOLDOWN_GROWTH_FACTOR ** self.consecutive_cooldowns)
        duration = min(duration, MAX_COOLDOWN_SECONDS)

        self.consecutive_cooldowns += 1
        self.cooldown_until = time.monotonic() + duration
        return duration

    def reset_cooldown(self):
        self.consecutive_cooldowns = 0
        self.cooldown_until = 0.0


# Shared provider state across calls
_groq_state = ProviderState("groq-vision", GROQ_MIN_INTERVAL, GROQ_RPM_CEILING)
_gemini_state = ProviderState("gemini-vision", GEMINI_MIN_INTERVAL, GEMINI_RPM_CEILING)


def _extract_retry_delay(err: Exception) -> float | None:
    """Extract retry delay seconds from HTTP headers or error messages if provided."""
    if hasattr(err, "response") and hasattr(err.response, "headers"):
        retry_header = err.response.headers.get("retry-after")
        if retry_header:
            try:
                return float(retry_header)
            except ValueError:
                pass
    msg = str(err).lower()
    m = re.search(r"(?:retry after|try again in|retry in)\s+([\d\.]+)\s*s?", msg)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    m_sec = re.search(r"seconds:\s*([\d\.]+)", msg)
    if m_sec:
        try:
            return float(m_sec.group(1))
        except ValueError:
            pass
    return None


def _is_transient_error(err: Exception) -> bool:
    """Detect transient errors eligible for one immediate jittered retry."""
    msg = str(err).lower()
    transient_indicators = [
        "429", "rate limit", "quota", "too many requests",
        "timeout", "timed out", "connection", "connect",
        "500", "502", "503", "504", "internal server error", "bad gateway",
        "service unavailable", "gateway timeout", "resource exhausted",
    ]
    return any(ind in msg for ind in transient_indicators)


# ── Provider Implementations (industry-pattern standard gateway) ───────

def _try_groq(
    png_bytes: bytes,
    prompt: str,
    api_key: str,
    page: int | None = None,
    document_id: str | None = None,
) -> tuple[str, str]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1", timeout=CALL_TIMEOUT_SECONDS)
    b64 = base64.b64encode(png_bytes).decode()

    t0 = time.monotonic()
    resp = client.chat.completions.create(
        model="llama-4-scout",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }],
        temperature=0,
    )
    latency = int((time.monotonic() - t0) * 1000)
    text = resp.choices[0].message.content or ""
    tokens = resp.usage.total_tokens if resp.usage else None

    target = {"document_id": document_id, "page": page} if (document_id or page is not None) else None
    meta = {
        "provider": "groq-vision",
        "latency_ms": latency,
        "approx_tokens": tokens,
    }
    if page is not None:
        meta["page"] = page
    db.audit("ocr", target=target, meta=meta)
    return text, "groq-vision"


def _try_gemini(
    png_bytes: bytes,
    prompt: str,
    api_key: str,
    page: int | None = None,
    document_id: str | None = None,
) -> tuple[str, str]:
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=int(CALL_TIMEOUT_SECONDS * 1000)),
    )

    t0 = time.monotonic()
    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[
            prompt,
            types.Part.from_bytes(data=png_bytes, mime_type="image/png"),
        ],
        config=types.GenerateContentConfig(temperature=0),
    )
    latency = int((time.monotonic() - t0) * 1000)
    text = resp.text or ""
    tokens = None
    if hasattr(resp, "usage_metadata") and resp.usage_metadata:
        tokens = getattr(resp.usage_metadata, "total_token_count", None)

    target = {"document_id": document_id, "page": page} if (document_id or page is not None) else None
    meta = {
        "provider": "gemini-vision",
        "latency_ms": latency,
        "approx_tokens": tokens,
    }
    if page is not None:
        meta["page"] = page
    db.audit("ocr", target=target, meta=meta)
    return text, "gemini-vision"


# ── Round-Robin Router with Cooldown & Failover ───────────────────────

class OcrRouter:
    """Manages round-robin rotation, pacing, and cooldown failover between vision providers."""

    def __init__(
        self,
        document_id: str | None = None,
        groq_state: ProviderState | None = None,
        gemini_state: ProviderState | None = None,
        call_fn: Callable[[str, bytes, str, int | None, str | None], tuple[str, str]] | None = None,
    ):
        self.document_id = document_id
        self.groq_state = groq_state or _groq_state
        self.gemini_state = gemini_state or _gemini_state
        self.providers = [self.groq_state, self.gemini_state]
        self.next_provider_idx = 0
        self._call_fn = call_fn

    def _execute(self, provider_name: str, png_bytes: bytes, page: int | None) -> tuple[str, str]:
        if self._call_fn:
            return self._call_fn(provider_name, png_bytes, OCR_PROMPT, page, self.document_id)

        if provider_name == "groq-vision":
            key = os.environ.get("GROQ_API_KEY")
            if not key:
                raise ValueError("GROQ_API_KEY is not set or empty")
            return _try_groq(png_bytes, OCR_PROMPT, key, page=page, document_id=self.document_id)
        elif provider_name == "gemini-vision":
            key = os.environ.get("GEMINI_API_KEY")
            if not key:
                raise ValueError("GEMINI_API_KEY is not set or empty")
            return _try_gemini(png_bytes, OCR_PROMPT, key, page=page, document_id=self.document_id)
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

    def transcribe_page(self, png_bytes: bytes, page: int = 0) -> tuple[str, str]:
        """Transcribe a page using rate-limited round-robin with failover."""
        # 1. Determine scheduled provider
        scheduled_idx = self.next_provider_idx
        self.next_provider_idx = (self.next_provider_idx + 1) % len(self.providers)

        scheduled = self.providers[scheduled_idx]
        alternative = self.providers[1 - scheduled_idx]

        # 2. Select initial candidate order (failover to healthy if scheduled is cooling)
        if scheduled.is_cooling_down():
            if not alternative.is_cooling_down():
                candidates = [alternative, scheduled]
            else:
                # Both are cooling -> wait for earliest recovery
                earliest_recovery = min(scheduled.cooldown_until, alternative.cooldown_until)
                wait_sec = earliest_recovery - time.monotonic()
                if wait_sec > 0:
                    time.sleep(wait_sec)
                # After waiting, prioritize whichever is now recovered
                if not scheduled.is_cooling_down():
                    candidates = [scheduled, alternative]
                else:
                    candidates = [alternative, scheduled]
        else:
            candidates = [scheduled, alternative]

        error_history: list[str] = []

        # 3. Attempt execution across candidates
        for cand in candidates:
            # If still cooling, skip
            if cand.is_cooling_down():
                continue

            target = {"document_id": self.document_id, "page": page} if (self.document_id or page is not None) else None

            # Enforce pacing interval and RPM limit
            cand.wait_for_pacing()

            # Attempt 1
            t0 = time.monotonic()
            try:
                text, prov = self._execute(cand.name, png_bytes, page)
                cand.reset_cooldown()
                return text, prov
            except Exception as ex1:
                lat1 = int((time.monotonic() - t0) * 1000)
                db.audit("ocr.attempt_failed", target=target, meta={
                    "provider": cand.name, "page": page, "error": str(ex1), "latency_ms": lat1, "attempt": 1
                })

                # One retry with jittered backoff for transient errors
                if _is_transient_error(ex1):
                    retry_delay = TRANSIENT_RETRY_BASE_SECONDS + random.uniform(0, TRANSIENT_RETRY_JITTER_SECONDS)
                    time.sleep(retry_delay)
                    cand.wait_for_pacing()
                    t0_retry = time.monotonic()
                    try:
                        text, prov = self._execute(cand.name, png_bytes, page)
                        cand.reset_cooldown()
                        return text, prov
                    except Exception as ex2:
                        lat2 = int((time.monotonic() - t0_retry) * 1000)
                        db.audit("ocr.attempt_failed", target=target, meta={
                            "provider": cand.name, "page": page, "error": str(ex2), "latency_ms": lat2, "attempt": 2
                        })
                        final_ex = ex2
                else:
                    final_ex = ex1

                # Enter cooldown with growing backoff
                server_delay = _extract_retry_delay(final_ex)
                dur = cand.trigger_cooldown(server_delay)
                db.audit("ocr.cooldown", target=target, meta={
                    "provider": cand.name, "page": page, "cooldown_seconds": round(dur, 2), "error": str(final_ex)
                })
                error_history.append(f"{cand.name}: {final_ex}")

        # If all candidates failed
        db.audit("ocr.page_failed", target=target, meta={
            "page": page, "errors": error_history
        })
        raise OcrUnavailable(f"Both OCR providers failed for page {page}: {'; '.join(error_history)}")


_default_router = OcrRouter()


def ocr_page(png_bytes: bytes) -> tuple[str, str]:
    """OCR a page image using the shared rate-limited round-robin router.

    Returns (markdown_text, provider). Preserves original module contract.
    """
    return _default_router.transcribe_page(png_bytes, page=0)


def process_document_ocr(
    doc_id: str,
    scan_pages: list[int],
    pages_meta: dict,
    budget: int = OCR_PAGE_BUDGET,
    router: OcrRouter | None = None,
) -> None:
    """Execute rate-limited round-robin vision OCR over scan pages for stage 'ocr'."""
    from .. import storage
    from .chunk import persist_ocr_chunks, persist_ocr_failure_chunk

    if router is None:
        router = OcrRouter(document_id=doc_id)

    # Cost guard: cap OCR at budget
    pages_to_ocr = scan_pages[:budget]
    pages_to_skip = scan_pages[budget:]

    for p_num in pages_to_skip:
        db.update_page_route(doc_id, p_num, "skipped")
        db.audit(
            "ocr.page_skipped",
            target={"document_id": doc_id, "page": p_num},
            meta={"page": p_num, "reason": "budget_exceeded", "budget": budget},
        )

    for p_num in pages_to_ocr:
        png_key = pages_meta.get(p_num, {}).get("r2_key") if pages_meta else None
        png_bytes = None
        if png_key and hasattr(storage, "get_object_bytes"):
            try:
                png_bytes = storage.get_object_bytes(png_key)
            except Exception as s_err:
                db.audit("ocr.storage_error", target={"document_id": doc_id, "page": p_num}, meta={"error": str(s_err)})

        if not png_bytes:
            db.update_page_route(doc_id, p_num, "failed")
            persist_ocr_failure_chunk(doc_id, p_num, "Page image not available in storage")
            continue

        try:
            md_text, provider = router.transcribe_page(png_bytes, page=p_num)
            persist_ocr_chunks(doc_id, p_num, md_text, provider)
        except OcrUnavailable as ocr_err:
            db.update_page_route(doc_id, p_num, "failed")
            persist_ocr_failure_chunk(doc_id, p_num, str(ocr_err))
        except Exception as ex:
            db.update_page_route(doc_id, p_num, "failed")
            persist_ocr_failure_chunk(doc_id, p_num, str(ex))
