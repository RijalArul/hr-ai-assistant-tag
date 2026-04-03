from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConversationIntent
from app.services.cache import get_cache
from app.services.embeddings import cosine_similarity, generate_embedding

SEMANTIC_VECTOR_MIN_SIMILARITY = 0.35
SEMANTIC_LEXICAL_MIN_SIMILARITY = 0.18
LEXICAL_STOPWORDS = {
    "dan",
    "atau",
    "yang",
    "untuk",
    "saya",
    "saya",
    "aku",
    "ini",
    "itu",
    "apa",
    "bagaimana",
    "tolong",
    "minta",
    "data",
    "dong",
    "aja",
    "dengan",
    "ke",
    "di",
    "dari",
    "the",
    "this",
    "that",
    "please",
    "help",
}


@dataclass(slots=True)
class SemanticIntentCandidate:
    intent: ConversationIntent
    example_text: str
    similarity: float
    source: str
    weight: int
    company_specific: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.value,
            "example_text": self.example_text,
            "similarity": round(self.similarity, 4),
            "source": self.source,
            "weight": self.weight,
            "company_specific": self.company_specific,
        }


@dataclass(slots=True)
class SemanticIntentResult:
    candidates: list[SemanticIntentCandidate]
    retrieval_mode: str
    fallback_reason: str | None = None

    @property
    def top_candidate(self) -> SemanticIntentCandidate | None:
        if not self.candidates:
            return None
        return self.candidates[0]

    def as_dict(self) -> dict[str, Any]:
        return {
            "retrieval_mode": self.retrieval_mode,
            "fallback_reason": self.fallback_reason,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }


@dataclass(slots=True)
class AgentCapabilityCandidate:
    agent_key: str
    title: str
    description: str
    similarity: float
    source: str
    execution_mode: str
    requires_trusted_employee_context: bool
    can_run_in_parallel: bool
    supported_intents: list[str]
    data_sources: list[str]
    sample_queries: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_key": self.agent_key,
            "title": self.title,
            "description": self.description,
            "similarity": round(self.similarity, 4),
            "source": self.source,
            "execution_mode": self.execution_mode,
            "requires_trusted_employee_context": self.requires_trusted_employee_context,
            "can_run_in_parallel": self.can_run_in_parallel,
            "supported_intents": self.supported_intents,
            "data_sources": self.data_sources,
            "sample_queries": self.sample_queries,
        }


@dataclass(slots=True)
class AgentCapabilityResult:
    candidates: list[AgentCapabilityCandidate]
    retrieval_mode: str
    fallback_reason: str | None = None

    @property
    def top_candidate(self) -> AgentCapabilityCandidate | None:
        if not self.candidates:
            return None
        return self.candidates[0]

    def as_dict(self) -> dict[str, Any]:
        return {
            "retrieval_mode": self.retrieval_mode,
            "fallback_reason": self.fallback_reason,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _tokenize(value: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-zA-Z0-9_]{2,}", _normalize_text(value))
        if token not in LEXICAL_STOPWORDS
    ]


def _parse_embedding(value: Any) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, tuple):
        return [float(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, list):
            return [float(item) for item in parsed]
    return None


def _ensure_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        value = parsed
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _score_lexical_similarity(message: str, example_text: str) -> float:
    message_tokens = set(_tokenize(message))
    example_tokens = set(_tokenize(example_text))
    if not message_tokens or not example_tokens:
        return 0.0

    overlap = message_tokens & example_tokens
    if not overlap:
        return 0.0

    overlap_ratio = len(overlap) / max(len(example_tokens), 1)
    coverage_ratio = len(overlap) / max(len(message_tokens), 1)
    score = (overlap_ratio * 0.65) + (coverage_ratio * 0.35)

    normalized_message = _normalize_text(message)
    normalized_example = _normalize_text(example_text)
    if normalized_example in normalized_message or normalized_message in normalized_example:
        score += 0.12

    return min(score, 0.99)


async def _load_intent_examples(
    db: AsyncSession,
    company_id: str,
) -> list[dict[str, Any]]:
    cache = get_cache("intent_examples")
    cache_key = f"intent_examples:{company_id}"
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return cached

    try:
        result = await db.execute(
            text(
                """
                SELECT
                    id::text AS id,
                    company_id::text AS company_id,
                    intent_key,
                    example_text,
                    language,
                    weight,
                    CAST(embedding AS text) AS embedding,
                    is_active
                FROM intent_examples
                WHERE is_active = true
                  AND (company_id IS NULL OR company_id = CAST(:company_id AS uuid))
                ORDER BY
                    CASE
                        WHEN company_id = CAST(:company_id AS uuid) THEN 0
                        ELSE 1
                    END,
                    weight DESC,
                    created_at ASC
                """
            ),
            {"company_id": company_id},
        )
    except Exception:
        cache.set(cache_key, [], ttl_seconds=60)
        return []

    items: list[dict[str, Any]] = []
    for row in result.mappings().all():
        data = dict(row)
        intent_key = str(data.get("intent_key", "")).strip()
        example_text = str(data.get("example_text", "")).strip()
        if not intent_key or not example_text:
            continue

        try:
            intent = ConversationIntent(intent_key)
        except ValueError:
            continue

        company_scope = str(data.get("company_id") or "").strip()
        items.append(
            {
                "id": data.get("id"),
                "intent": intent,
                "example_text": example_text,
                "language": str(data.get("language") or "id"),
                "weight": max(int(data.get("weight") or 1), 1),
                "embedding": _parse_embedding(data.get("embedding")),
                "company_specific": company_scope == company_id,
            }
        )

    cache.set(cache_key, items, ttl_seconds=300)
    return items


async def _load_agent_capabilities(
    db: AsyncSession,
    company_id: str,
) -> list[dict[str, Any]]:
    cache = get_cache("agent_capabilities")
    cache_key = f"agent_capabilities:{company_id}"
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return cached

    try:
        result = await db.execute(
            text(
                """
                SELECT
                    id::text AS id,
                    company_id::text AS company_id,
                    agent_key,
                    title,
                    description,
                    supported_intents,
                    data_sources,
                    execution_mode,
                    requires_trusted_employee_context,
                    can_run_in_parallel,
                    sample_queries,
                    CAST(embedding AS text) AS embedding,
                    is_active
                FROM agent_capabilities
                WHERE is_active = true
                  AND (company_id IS NULL OR company_id = CAST(:company_id AS uuid))
                ORDER BY
                    CASE
                        WHEN company_id = CAST(:company_id AS uuid) THEN 0
                        ELSE 1
                    END,
                    created_at ASC
                """
            ),
            {"company_id": company_id},
        )
    except Exception:
        cache.set(cache_key, [], ttl_seconds=60)
        return []

    items: list[dict[str, Any]] = []
    for row in result.mappings().all():
        data = dict(row)
        agent_key = str(data.get("agent_key", "")).strip()
        title = str(data.get("title", "")).strip()
        description = str(data.get("description", "")).strip()
        if not agent_key or not title or not description:
            continue

        sample_queries = _ensure_string_list(data.get("sample_queries"))
        supported_intents = _ensure_string_list(data.get("supported_intents"))
        data_sources = _ensure_string_list(data.get("data_sources"))
        combined_text = " ".join(
            [
                title,
                description,
                " ".join(sample_queries),
                " ".join(supported_intents),
                " ".join(data_sources),
            ]
        ).strip()
        company_scope = str(data.get("company_id") or "").strip()
        items.append(
            {
                "id": data.get("id"),
                "agent_key": agent_key,
                "title": title,
                "description": description,
                "supported_intents": supported_intents,
                "data_sources": data_sources,
                "execution_mode": str(data.get("execution_mode") or "structured_lookup"),
                "requires_trusted_employee_context": bool(
                    data.get("requires_trusted_employee_context")
                ),
                "can_run_in_parallel": bool(data.get("can_run_in_parallel", True)),
                "sample_queries": sample_queries,
                "embedding": _parse_embedding(data.get("embedding")),
                "combined_text": combined_text,
                "company_specific": company_scope == company_id,
            }
        )

    cache.set(cache_key, items, ttl_seconds=300)
    return items


def _rank_vector_candidates(
    message: str,
    examples: list[dict[str, Any]],
) -> list[SemanticIntentCandidate]:
    query_embedding = generate_embedding(message)
    if query_embedding is None:
        return []

    ranked_by_intent: dict[ConversationIntent, SemanticIntentCandidate] = {}
    for example in examples:
        example_embedding = example.get("embedding")
        if example_embedding is None:
            continue

        base_similarity = cosine_similarity(query_embedding, example_embedding)
        adjusted_similarity = min(
            base_similarity
            + ((example["weight"] - 1) * 0.03)
            + (0.02 if example["company_specific"] else 0.0),
            0.99,
        )
        if adjusted_similarity < SEMANTIC_VECTOR_MIN_SIMILARITY:
            continue

        candidate = SemanticIntentCandidate(
            intent=example["intent"],
            example_text=example["example_text"],
            similarity=adjusted_similarity,
            source="vector",
            weight=example["weight"],
            company_specific=example["company_specific"],
        )
        current = ranked_by_intent.get(candidate.intent)
        if current is None or candidate.similarity > current.similarity:
            ranked_by_intent[candidate.intent] = candidate

    return sorted(
        ranked_by_intent.values(),
        key=lambda item: item.similarity,
        reverse=True,
    )


def _rank_lexical_candidates(
    message: str,
    examples: list[dict[str, Any]],
) -> list[SemanticIntentCandidate]:
    ranked_by_intent: dict[ConversationIntent, SemanticIntentCandidate] = {}
    for example in examples:
        base_similarity = _score_lexical_similarity(message, example["example_text"])
        adjusted_similarity = min(
            base_similarity
            + ((example["weight"] - 1) * 0.02)
            + (0.02 if example["company_specific"] else 0.0),
            0.99,
        )
        if adjusted_similarity < SEMANTIC_LEXICAL_MIN_SIMILARITY:
            continue

        candidate = SemanticIntentCandidate(
            intent=example["intent"],
            example_text=example["example_text"],
            similarity=adjusted_similarity,
            source="lexical",
            weight=example["weight"],
            company_specific=example["company_specific"],
        )
        current = ranked_by_intent.get(candidate.intent)
        if current is None or candidate.similarity > current.similarity:
            ranked_by_intent[candidate.intent] = candidate

    return sorted(
        ranked_by_intent.values(),
        key=lambda item: item.similarity,
        reverse=True,
    )


async def retrieve_intent_candidates(
    db: AsyncSession,
    company_id: str,
    message: str,
    *,
    top_k: int = 4,
) -> SemanticIntentResult:
    normalized_message = _normalize_text(message)
    if not normalized_message:
        return SemanticIntentResult(
            candidates=[],
            retrieval_mode="empty",
            fallback_reason="Message was empty after normalization.",
        )

    examples = await _load_intent_examples(db, company_id)
    if not examples:
        return SemanticIntentResult(
            candidates=[],
            retrieval_mode="empty",
            fallback_reason="No active intent examples were available.",
        )

    vector_candidates = _rank_vector_candidates(normalized_message, examples)
    if vector_candidates:
        return SemanticIntentResult(
            candidates=vector_candidates[:top_k],
            retrieval_mode="vector",
        )

    lexical_candidates = _rank_lexical_candidates(normalized_message, examples)
    if lexical_candidates:
        return SemanticIntentResult(
            candidates=lexical_candidates[:top_k],
            retrieval_mode="lexical",
            fallback_reason="Embedding model was unavailable, so lexical retrieval was used.",
        )

    return SemanticIntentResult(
        candidates=[],
        retrieval_mode="empty",
        fallback_reason="No sufficiently similar intent examples matched the message.",
    )


def _rank_agent_vector_candidates(
    message: str,
    capabilities: list[dict[str, Any]],
) -> list[AgentCapabilityCandidate]:
    query_embedding = generate_embedding(message)
    if query_embedding is None:
        return []

    ranked: list[AgentCapabilityCandidate] = []
    for capability in capabilities:
        capability_embedding = capability.get("embedding")
        if capability_embedding is None:
            continue

        similarity = min(
            cosine_similarity(query_embedding, capability_embedding)
            + (0.02 if capability["company_specific"] else 0.0),
            0.99,
        )
        if similarity < SEMANTIC_VECTOR_MIN_SIMILARITY:
            continue

        ranked.append(
            AgentCapabilityCandidate(
                agent_key=capability["agent_key"],
                title=capability["title"],
                description=capability["description"],
                similarity=similarity,
                source="vector",
                execution_mode=capability["execution_mode"],
                requires_trusted_employee_context=capability[
                    "requires_trusted_employee_context"
                ],
                can_run_in_parallel=capability["can_run_in_parallel"],
                supported_intents=capability["supported_intents"],
                data_sources=capability["data_sources"],
                sample_queries=capability["sample_queries"],
            )
        )

    ranked.sort(key=lambda item: item.similarity, reverse=True)
    return ranked


def _rank_agent_lexical_candidates(
    message: str,
    capabilities: list[dict[str, Any]],
) -> list[AgentCapabilityCandidate]:
    ranked: list[AgentCapabilityCandidate] = []
    for capability in capabilities:
        similarity = min(
            _score_lexical_similarity(message, capability["combined_text"])
            + (0.02 if capability["company_specific"] else 0.0),
            0.99,
        )
        if similarity < SEMANTIC_LEXICAL_MIN_SIMILARITY:
            continue

        ranked.append(
            AgentCapabilityCandidate(
                agent_key=capability["agent_key"],
                title=capability["title"],
                description=capability["description"],
                similarity=similarity,
                source="lexical",
                execution_mode=capability["execution_mode"],
                requires_trusted_employee_context=capability[
                    "requires_trusted_employee_context"
                ],
                can_run_in_parallel=capability["can_run_in_parallel"],
                supported_intents=capability["supported_intents"],
                data_sources=capability["data_sources"],
                sample_queries=capability["sample_queries"],
            )
        )

    ranked.sort(key=lambda item: item.similarity, reverse=True)
    return ranked


async def retrieve_agent_capabilities(
    db: AsyncSession,
    company_id: str,
    message: str,
    *,
    top_k: int = 4,
) -> AgentCapabilityResult:
    normalized_message = _normalize_text(message)
    if not normalized_message:
        return AgentCapabilityResult(
            candidates=[],
            retrieval_mode="empty",
            fallback_reason="Message was empty after normalization.",
        )

    capabilities = await _load_agent_capabilities(db, company_id)
    if not capabilities:
        return AgentCapabilityResult(
            candidates=[],
            retrieval_mode="empty",
            fallback_reason="No active agent capabilities were available.",
        )

    vector_candidates = _rank_agent_vector_candidates(normalized_message, capabilities)
    if vector_candidates:
        return AgentCapabilityResult(
            candidates=vector_candidates[:top_k],
            retrieval_mode="vector",
        )

    lexical_candidates = _rank_agent_lexical_candidates(
        normalized_message,
        capabilities,
    )
    if lexical_candidates:
        return AgentCapabilityResult(
            candidates=lexical_candidates[:top_k],
            retrieval_mode="lexical",
            fallback_reason="Embedding model was unavailable, so lexical retrieval was used.",
        )

    return AgentCapabilityResult(
        candidates=[],
        retrieval_mode="empty",
        fallback_reason="No sufficiently similar agent capability matched the message.",
    )
