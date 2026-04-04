from __future__ import annotations

import math
import re
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

# Heading patterns recognised by section-aware chunker.
_HEADING_RE = re.compile(r"^#{1,6}\s+.+", re.MULTILINE)


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
    ignore_provider_flag: bool = False,
) -> list[float] | None:
    """Generate an embedding vector for *text*.

    When ``ignore_provider_flag=True`` the ``phase3_use_remote_providers``
    setting is bypassed, which allows semantic routing to function even when
    the broader provider integrations are disabled.  The API key and circuit
    breaker are still respected.
    """
    normalized = text.strip()
    if not normalized:
        return None

    if not ignore_provider_flag and not settings.phase3_use_remote_providers:
        return None
    if not settings.gemini_api_key:
        return None

    circuit_reason = get_open_circuit_reason(GEMINI_EMBEDDING_PROVIDER_NAME)
    if circuit_reason:
        return None

    try:
        embed_config = types.EmbedContentConfig(
            task_type=task_type,
            title=title,
            output_dimensionality=settings.gemini_embedding_output_dimensionality,
        )
        response = _get_embedding_client().models.embed_content(
            model=settings.gemini_embedding_model,
            contents=normalized,
            config=embed_config,
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


def _split_into_sections(text: str) -> list[str]:
    """Split *text* on Markdown headings and blank-line boundaries.

    This produces coarser, semantically meaningful sections before the
    character-limit slicer is applied, so each chunk stays inside one
    coherent topic rather than being cut arbitrarily mid-sentence.
    """
    # Normalise line endings first.
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")

    # Insert a sentinel before every heading so we can split on it.
    with_sentinels = _HEADING_RE.sub(lambda m: f"\x00{m.group(0)}", normalised)
    raw_sections = with_sentinels.split("\x00")

    sections: list[str] = []
    for raw in raw_sections:
        # Further split on blank lines (paragraph boundaries).
        for paragraph in re.split(r"\n{2,}", raw):
            cleaned = " ".join(paragraph.split())
            if cleaned:
                sections.append(cleaned)

    return sections


def chunk_text(
    text: str,
    *,
    max_chars: int = 500,
    overlap: int = 80,
) -> list[str]:
    """Chunk *text* into segments suitable for embedding.

    The algorithm first splits the text on Markdown headings and paragraph
    boundaries so each chunk stays within a coherent section.  Only when a
    section is longer than *max_chars* is it sliced further, with an
    *overlap* character window to preserve cross-boundary context.
    """
    sections = _split_into_sections(text)
    if not sections:
        return []

    chunks: list[str] = []
    for section in sections:
        if len(section) <= max_chars:
            chunks.append(section)
            continue

        # Slice long sections with overlap.
        start = 0
        length = len(section)
        while start < length:
            end = min(start + max_chars, length)
            chunk = section[start:end].strip()
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
