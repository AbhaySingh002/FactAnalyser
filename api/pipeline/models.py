"""Unified multi-model gateway with automatic fallback cascades for completion & vision.

Supports OpenRouter (free models & SDK), Google Gemini, and Groq/OpenAI.
Tries configured candidate models in sequence until one succeeds.
Decouples backend from provider quirks, deprecations, and rate limits.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── Primary model (always tried first) ──────────────────────────────
PRIMARY_CHAT_MODEL = "openai/gpt-4o-mini"
PRIMARY_EMBEDDING_MODEL = "google/gemini-embedding-2:batch"

OPENROUTER_FREE_CHAT_MODELS = [
    "openai/gpt-4o-mini",          # primary — reliable, fast, 128k ctx
    "openai/gpt-4o-mini:free",
    "amazon/nova-2-lite-v1:free",
    "amazon/nova-2-lite-v1",
    "openrouter/free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3.5-lightning:free",
    "liquid/lfm-2.5-2.6b:free",
    "nex-agi/nex-n2.5-pro:free",
    "nex-agi/nex-n2.5-mini:free",
    "cohere/north-mini-code:free",
    "dots-studio/dots-3-note-preview:free",
]

OPENROUTER_FREE_VISION_MODELS = [
    "openai/gpt-4o-mini",          # primary — supports vision
    "openai/gpt-4o-mini:free",
    "amazon/nova-2-lite-v1:free",
    "amazon/nova-2-lite-v1",
    "openrouter/free",
    "nex-agi/nex-n2.5-pro:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "dots-studio/dots-3-note-preview:free",
]

DEFAULT_CHAT_MODELS = (
    OPENROUTER_FREE_CHAT_MODELS[:5]
    + ["qwen/qwen3.8-27b", "openai/gpt-oss-20b", "gemini-3.6-flash"]
)
DEFAULT_VISION_MODELS = (
    OPENROUTER_FREE_VISION_MODELS[:5]
    + ["gemini-3.6-flash", "openai/gpt-oss-20b"]
)
DEFAULT_EXTRACTION_MODELS = [
    "openai/gpt-4o-mini",          # primary extraction model
    "openai/gpt-4o-mini:free",
    "amazon/nova-2-lite-v1:free",
    "amazon/nova-2-lite-v1",
    "gemini-3.6-flash",
    "openai/gpt-oss-20b",
]



def _get_model_list(env_var: str, defaults: list[str]) -> list[str]:
    val = os.environ.get(env_var, "").strip()
    return [m.strip() for m in val.split(",") if m.strip()] if val else defaults


def _get_openrouter_client():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    from openrouter import OpenRouter
    return OpenRouter(api_key=key)


def _get_gemini_client():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    from google import genai
    return genai.Client(api_key=key)


def _get_groq_client():
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    from openai import OpenAI
    return OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1", timeout=60.0)


def _is_openrouter(model_name: str) -> bool:
    name = model_name.lower()
    return (
        ":free" in name
        or name.startswith("openrouter/")
        or name.startswith("amazon/")
        or name.startswith("openai/gpt-4")
        or (
            "/" in name
            and not name.startswith("openai/gpt-oss")
            and not name.startswith("qwen/qwen3.")
            and not name.startswith("meta-llama/")
        )
    )



def fetch_available_free_models() -> dict[str, list[str]]:
    """Query OpenRouter SDK for all live free models (cached in process)."""
    client = _get_openrouter_client()
    if not client:
        return {"chat": OPENROUTER_FREE_CHAT_MODELS, "vision": OPENROUTER_FREE_VISION_MODELS}

    try:
        res = client.models.list()
        all_models = getattr(res.result, "data", [])
        free_chat = []
        free_vision = []
        for m in all_models:
            prompt_p = getattr(m.pricing, "prompt", "1") if m.pricing else "1"
            compl_p = getattr(m.pricing, "completion", "1") if m.pricing else "1"
            is_free = (str(prompt_p) == "0" and str(compl_p) == "0") or ":free" in m.id
            if is_free:
                free_chat.append(m.id)
                modalities = getattr(m.architecture, "input_modalities", []) if m.architecture else []
                if "image" in modalities:
                    free_vision.append(m.id)

        return {
            "chat": free_chat or OPENROUTER_FREE_CHAT_MODELS,
            "vision": free_vision or OPENROUTER_FREE_VISION_MODELS,
        }
    except Exception as e:
        logger.warning(f"Could not fetch dynamic free models from OpenRouter: {e}")
        return {"chat": OPENROUTER_FREE_CHAT_MODELS, "vision": OPENROUTER_FREE_VISION_MODELS}


def complete(
    messages: list[dict] | str,
    system: str | None = None,
    models: list[str] | None = None,
    response_schema: Any | None = None,
    temperature: float = 0.0,
    max_tokens: int = 2000,
) -> tuple[str, str]:
    """Execute text completion with automatic multi-model fallback cascade across OpenRouter, Gemini, and Groq.

    Returns (response_text, model_used).
    """
    candidate_models = models or _get_model_list("CHAT_MODELS", DEFAULT_CHAT_MODELS)
    errors: list[str] = []

    for model in candidate_models:
        is_gemini = "gemini" in model.lower()
        is_openrouter = _is_openrouter(model)
        try:
            if is_gemini:
                client = _get_gemini_client()
                if not client:
                    continue
                from google.genai import types

                if isinstance(messages, str):
                    prompt_text = messages
                else:
                    parts = []
                    for m in messages:
                        prefix = f"{m.get('role', 'user').upper()}: " if m.get("role") != "user" else ""
                        parts.append(f"{prefix}{m.get('content', '')}")
                    prompt_text = "\n\n".join(parts)

                config_kwargs: dict[str, Any] = {"temperature": temperature}
                if system:
                    config_kwargs["system_instruction"] = system
                if response_schema:
                    config_kwargs["response_mime_type"] = "application/json"
                    config_kwargs["response_schema"] = response_schema

                resp = client.models.generate_content(
                    model=model,
                    contents=prompt_text,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                text = resp.text or ""
                return text, model

            elif is_openrouter:
                client = _get_openrouter_client()
                if not client:
                    continue

                call_messages: list[dict] = []
                if system:
                    call_messages.append({"role": "system", "content": system})

                if isinstance(messages, str):
                    call_messages.append({"role": "user", "content": messages})
                else:
                    call_messages.extend(messages)

                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": call_messages,
                    "temperature": temperature,
                }
                if response_schema:
                    kwargs["response_format"] = {"type": "json_object"}

                try:
                    res = client.chat.send(**kwargs)
                except Exception as or_err:
                    err_text = str(or_err)
                    if "use this slug instead:" in err_text:
                        suggested_slug = err_text.split("use this slug instead:")[-1].strip().rstrip(")")
                        kwargs["model"] = suggested_slug
                        res = client.chat.send(**kwargs)
                    else:
                        raise or_err

                text = res.choices[0].message.content or ""
                used_model = getattr(res, "model", model) or model
                return text, used_model


            else:
                # Groq / OpenAI compatible
                client = _get_groq_client()
                if not client:
                    continue

                call_messages: list[dict] = []
                if system:
                    call_messages.append({"role": "system", "content": system})

                if isinstance(messages, str):
                    call_messages.append({"role": "user", "content": messages})
                else:
                    call_messages.extend(messages)

                req_kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": call_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if response_schema:
                    req_kwargs["response_format"] = {"type": "json_object"}

                resp = client.chat.completions.create(**req_kwargs)
                text = resp.choices[0].message.content or ""
                return text, model

        except Exception as e:
            err_msg = f"{model} failed: {e}"
            logger.warning(err_msg)
            errors.append(err_msg)
            continue

    raise RuntimeError(f"All models failed in cascade: {'; '.join(errors)}")


def vision(
    images: list[bytes] | bytes,
    prompt: str,
    models: list[str] | None = None,
) -> tuple[str, str]:
    """Execute vision OCR with automatic multi-model fallback cascade across OpenRouter, Gemini, and Groq.

    Accepts single image or list of page images (for batch processing).
    Returns (transcribed_markdown, model_used).
    """
    img_list = [images] if isinstance(images, bytes) else images
    candidate_models = models or _get_model_list("VISION_MODELS", DEFAULT_VISION_MODELS)
    errors: list[str] = []

    for model in candidate_models:
        is_gemini = "gemini" in model.lower()
        is_openrouter = _is_openrouter(model)
        try:
            if is_gemini:
                client = _get_gemini_client()
                if not client:
                    continue
                from google.genai import types

                contents: list[Any] = [prompt]
                for img in img_list:
                    contents.append(types.Part.from_bytes(data=img, mime_type="image/png"))

                resp = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(temperature=0),
                )
                return resp.text or "", model

            elif is_openrouter:
                client = _get_openrouter_client()
                if not client:
                    continue

                user_content: list[dict] = [{"type": "text", "text": prompt}]
                for img in img_list:
                    b64 = base64.b64encode(img).decode("utf-8")
                    user_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

                kwargs = {
                    "model": model,
                    "messages": [{"role": "user", "content": user_content}],
                    "temperature": 0,
                }
                try:
                    res = client.chat.send(**kwargs)
                except Exception as or_err:
                    err_text = str(or_err)
                    if "use this slug instead:" in err_text:
                        suggested_slug = err_text.split("use this slug instead:")[-1].strip().rstrip(")")
                        kwargs["model"] = suggested_slug
                        res = client.chat.send(**kwargs)
                    else:
                        raise or_err

                text = res.choices[0].message.content or ""
                used_model = getattr(res, "model", model) or model
                return text, used_model


            else:
                client = _get_groq_client()
                if not client:
                    continue

                user_content: list[dict] = [{"type": "text", "text": prompt}]
                for img in img_list:
                    b64 = base64.b64encode(img).decode("utf-8")
                    user_content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})

                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": user_content}],
                    temperature=0,
                )
                return resp.choices[0].message.content or "", model

        except Exception as e:
            err_msg = f"{model} failed: {e}"
            logger.warning(err_msg)
            errors.append(err_msg)
            continue

    raise RuntimeError(f"All vision models failed in cascade: {'; '.join(errors)}")


def embed(
    texts: list[str] | str,
    model: str = PRIMARY_EMBEDDING_MODEL,
) -> list[list[float]]:
    """Generate text embeddings via OpenRouter (google/gemini-embedding-2:batch by default).

    Accepts a single string or a list of strings.
    Returns a list of float vectors, one per input text.
    Falls back to Gemini native API if OpenRouter is unavailable.
    """
    if isinstance(texts, str):
        texts = [texts]

    # 1. Try OpenRouter
    client = _get_openrouter_client()
    if client:
        try:
            res = client.embeddings.create(model=model, input=texts)
            return [item.embedding for item in res.data]
        except Exception as e:
            logger.warning(f"OpenRouter embed failed ({model}): {e}")

    # 2. Fallback: Gemini native embeddings
    gemini_client = _get_gemini_client()
    if gemini_client:
        try:
            from google.genai import types as gtypes
            results = []
            for text in texts:
                resp = gemini_client.models.embed_content(
                    model="models/text-embedding-004",
                    content=text,
                    config=gtypes.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
                )
                results.append(resp.embeddings[0].values)
            return results
        except Exception as e:
            logger.warning(f"Gemini native embed failed: {e}")

    raise RuntimeError("All embedding providers failed. Set OPENROUTER_API_KEY or GEMINI_API_KEY.")
