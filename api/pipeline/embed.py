"""Text embeddings — routes through unified models gateway.

Primary:  google/gemini-embedding-2:batch  via OpenRouter
Fallback: Gemini native API (text-embedding-004 / gemini-embedding-001)
Dev stub: zero-vector when no API keys are set (preserves CI behaviour)
"""

import logging
import os

from . import models as _models

logger = logging.getLogger(__name__)

EMBEDDING_DIMS = int(os.environ.get("EMBEDDING_DIMS", "768"))


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-embed strings.  Returns one float vector per input text."""
    if not texts:
        return []

    try:
        return _models.embed(texts)
    except Exception as e:
        logger.warning(f"embed_texts failed via models gateway: {e}. Using zero-vector stub.")
        return [[0.0] * EMBEDDING_DIMS for _ in texts]


def embed_text(text: str) -> list[float]:
    """Embed a single string."""
    res = embed_texts([text])
    return res[0] if res else [0.0] * EMBEDDING_DIMS
