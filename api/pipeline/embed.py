"""Gemini embeddings for facts and dynamic attribute namespaces."""

import os
from google import genai
from google.genai import types

EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_DIMS = 768


def _get_client() -> genai.Client | None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch embed strings using Gemini text-embedding-004 (768 dims)."""
    if not texts:
        return []

    client = _get_client()
    if not client:
        # ponytail: fallback mock 768-dim zero vector if GEMINI_API_KEY unset in dev/test
        return [[0.0] * EMBEDDING_DIMS for _ in texts]

    results: list[list[float]] = []
    batch_size = 50
    config = types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIMS)

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=batch,
            config=config,
        )
        if resp.embeddings:
            for emb in resp.embeddings:
                results.append(list(emb.values))
        else:
            results.extend([[0.0] * EMBEDDING_DIMS for _ in batch])

    return results


def embed_text(text: str) -> list[float]:
    """Embed single string (768 dims)."""
    res = embed_texts([text])
    return res[0] if res else [0.0] * EMBEDDING_DIMS
