from __future__ import annotations

import math
from functools import lru_cache
from typing import Sequence

from google import genai
from google.genai import types

from app.core.config import get_settings
from app.services.provider_health import (
    close_provider_circuit,
    get_open_circuit_reason,
    open_provider_circuit,
)

settings = get_settings()
GEMINI_EMBEDDING_PROVIDER_NAME = "gemini-embeddings"


@lru_cache
def _get_embedding_client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


def _extract_embedding_values(result: object) -> list[float] | None:
    embeddings = getattr(result, "embeddings", None)
    if not isinstance(embeddings, Sequence) or isinstance(embeddings, (str, bytes)) or not embeddings:
        return None

    values = getattr(embeddings[0], "values", None)
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
        return None

    return [float(value) for value in values]


def generate_embedding(
    text: str,
    *,
    task_type: str = "RETRIEVAL_QUERY",
    title: str | None = None,
) -> list[float] | None:
    normalized = text.strip()
    if not normalized:
        return None

    if not settings.phase3_use_remote_providers:
        return None
    if not settings.gemini_api_key:
        return None

    circuit_reason = get_open_circuit_reason(GEMINI_EMBEDDING_PROVIDER_NAME)
    if circuit_reason:
        return None

    config_kwargs: dict[str, object] = {
        "task_type": task_type,
        "output_dimensionality": settings.gemini_embedding_output_dimensionality,
    }
    if title:
        config_kwargs["title"] = title

    try:
        response = _get_embedding_client().models.embed_content(
            model=settings.gemini_embedding_model,
            contents=normalized,
            config=types.EmbedContentConfig(**config_kwargs),
        )
        vector = _extract_embedding_values(response)
    except Exception as exc:
        open_provider_circuit(
            GEMINI_EMBEDDING_PROVIDER_NAME,
            str(exc).strip() or "Gemini embedding request failed.",
        )
        return None

    if vector is None:
        open_provider_circuit(
            GEMINI_EMBEDDING_PROVIDER_NAME,
            "Gemini returned no embedding values.",
        )
        return None

    close_provider_circuit(GEMINI_EMBEDDING_PROVIDER_NAME)
    return vector


def to_pgvector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def chunk_text(
    text: str,
    *,
    max_chars: int = 500,
    overlap: int = 80,
) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    length = len(normalized)

    while start < length:
        end = min(start + max_chars, length)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = max(end - overlap, start + 1)

    return chunks


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)
