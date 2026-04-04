from __future__ import annotations

import hashlib
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

# Hybrid merge weights: how much each signal contributes to the final score.
_HYBRID_VECTOR_WEIGHT = 0.70
_HYBRID_LEXICAL_WEIGHT = 0.30
# When a candidate appears in only one signal, apply a discount so pure-vector
# and pure-lexical candidates don't outrank confirmed hybrid matches.
_HYBRID_VECTOR_ONLY_DISCOUNT = 0.85
_HYBRID_LEXICAL_ONLY_DISCOUNT = 0.60

# TTL values for per-request retrieval caches.
_EMBEDDING_CACHE_TTL = 600   # 10 min â€“ query vectors change only when text changes
_RETRIEVAL_CACHE_TTL = 120   # 2 min  â€“ short enough to stay fresh but avoids re-ranking

LEXICAL_STOPWORDS = {
    "dan",
    "atau",
    "yang",
    "untuk",
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


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _tokenize(value: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-zA-Z0-9_]{2,}", _normalize_text(value))
        if token not in LEXICAL_STOPWORDS
    ]


def _message_hash(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()  # noqa: S324  # not security-critical


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


# ---------------------------------------------------------------------------
# Query-embedding cache (I.5)
# Caches the embedding vector for a given text string so repeated calls
# within a request window avoid paying the Gemini API round-trip cost.
# ---------------------------------------------------------------------------

def _generate_embedding_cached(message: str) -> list[float] | None:
    """Return a cached query embedding or call the provider.

    Uses ``ignore_provider_flag=True`` (I.6) so semantic routing can still
    produce vector matches even when ``phase3_use_remote_providers`` is
    disabled â€“ as long as the API key and circuit breaker are healthy.
    """
    cache = get_cache("query_embeddings")
    cache_key = _message_hash(message)
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return cached  # type: ignore[return-value]

    vector = generate_embedding(message, ignore_provider_flag=True)
    if vector is not None:
        cache.set(cache_key, vector, ttl_seconds=_EMBEDDING_CACHE_TTL)
    return vector


# ---------------------------------------------------------------------------
# DB loaders
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Per-signal rankers
# ---------------------------------------------------------------------------

def _rank_vector_candidates(
    message: str,
    examples: list[dict[str, Any]],
    *,
    metadata_boost_intents: set[str] | None = None,
) -> list[SemanticIntentCandidate]:
    """Return per-intent best-vector-score candidates.

    ``metadata_boost_intents`` (I.2): when the calling context has a strong
    signal about the likely domain (e.g. policy reasoning â†’ boost
    ``company_policy``), passing those intent keys here adds a small
    similarity bonus so the correct route rises above noise.
    """
    query_embedding = _generate_embedding_cached(message)
    if query_embedding is None:
        return []

    ranked_by_intent: dict[ConversationIntent, SemanticIntentCandidate] = {}
    for example in examples:
        example_embedding = example.get("embedding")
        if example_embedding is None:
            continue

        base_similarity = cosine_similarity(query_embedding, example_embedding)
        metadata_boost = (
            0.04
            if (
                metadata_boost_intents
                and example["intent"].value in metadata_boost_intents
            )
            else 0.0
        )
        adjusted_similarity = min(
            base_similarity
            + ((example["weight"] - 1) * 0.03)
            + (0.02 if example["company_specific"] else 0.0)
            + metadata_boost,
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
    *,
    metadata_boost_intents: set[str] | None = None,
) -> list[SemanticIntentCandidate]:
    """Return per-intent best-lexical-score candidates.

    See ``_rank_vector_candidates`` for ``metadata_boost_intents`` semantics.
    """
    ranked_by_intent: dict[ConversationIntent, SemanticIntentCandidate] = {}
    for example in examples:
        base_similarity = _score_lexical_similarity(message, example["example_text"])
        metadata_boost = (
            0.03
            if (
                metadata_boost_intents
                and example["intent"].value in metadata_boost_intents
            )
            else 0.0
        )
        adjusted_similarity = min(
            base_similarity
            + ((example["weight"] - 1) * 0.02)
            + (0.02 if example["company_specific"] else 0.0)
            + metadata_boost,
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


# ---------------------------------------------------------------------------
# Hybrid merge + reranking (I.1 + I.4)
# ---------------------------------------------------------------------------

def _merge_hybrid_intent_candidates(
    vector_candidates: list[SemanticIntentCandidate],
    lexical_candidates: list[SemanticIntentCandidate],
) -> list[SemanticIntentCandidate]:
    """Merge vector and lexical rankings into a single hybrid-scored list.

    Scoring rules:
    - Intent present in **both** signals:
      ``hybrid = vector * 0.70 + lexical * 0.30``  (source = "hybrid")
    - Intent present **only in vector**:
      ``score = vector * 0.85``  (source = "vector")
    - Intent present **only in lexical**:
      ``score = lexical * 0.60``  (source = "lexical")

    Discounts for single-signal candidates ensure that a confirmed hybrid
    match always ranks above a lone lexical hit with the same raw score.
    The merged list is then sorted by the blended score (reranking step I.4).
    """
    vector_map: dict[ConversationIntent, SemanticIntentCandidate] = {
        c.intent: c for c in vector_candidates
    }
    lexical_map: dict[ConversationIntent, SemanticIntentCandidate] = {
        c.intent: c for c in lexical_candidates
    }

    merged: list[SemanticIntentCandidate] = []
    seen: set[ConversationIntent] = set()

    all_intents = list(vector_map.keys()) + [
        intent for intent in lexical_map if intent not in vector_map
    ]
    for intent in all_intents:
        if intent in seen:
            continue
        seen.add(intent)

        v_candidate = vector_map.get(intent)
        l_candidate = lexical_map.get(intent)

        if v_candidate is not None and l_candidate is not None:
            blended_score = min(
                v_candidate.similarity * _HYBRID_VECTOR_WEIGHT
                + l_candidate.similarity * _HYBRID_LEXICAL_WEIGHT,
                0.99,
            )
            best_example = (
                v_candidate.example_text
                if v_candidate.similarity >= l_candidate.similarity
                else l_candidate.example_text
            )
            merged.append(
                SemanticIntentCandidate(
                    intent=intent,
                    example_text=best_example,
                    similarity=blended_score,
                    source="hybrid",
                    weight=max(v_candidate.weight, l_candidate.weight),
                    company_specific=v_candidate.company_specific or l_candidate.company_specific,
                )
            )
        elif v_candidate is not None:
            merged.append(
                SemanticIntentCandidate(
                    intent=intent,
                    example_text=v_candidate.example_text,
                    similarity=min(
                        v_candidate.similarity * _HYBRID_VECTOR_ONLY_DISCOUNT, 0.99
                    ),
                    source="vector",
                    weight=v_candidate.weight,
                    company_specific=v_candidate.company_specific,
                )
            )
        elif l_candidate is not None:
            merged.append(
                SemanticIntentCandidate(
                    intent=intent,
                    example_text=l_candidate.example_text,
                    similarity=min(
                        l_candidate.similarity * _HYBRID_LEXICAL_ONLY_DISCOUNT, 0.99
                    ),
                    source="lexical",
                    weight=l_candidate.weight,
                    company_specific=l_candidate.company_specific,
                )
            )

    # Final reranking pass: sort by blended similarity descending (I.4).
    merged.sort(key=lambda c: c.similarity, reverse=True)
    return merged


def _merge_hybrid_capability_candidates(
    vector_candidates: list[AgentCapabilityCandidate],
    lexical_candidates: list[AgentCapabilityCandidate],
) -> list[AgentCapabilityCandidate]:
    """Same merge logic as intent candidates, applied to agent capabilities."""
    vector_map: dict[str, AgentCapabilityCandidate] = {
        c.agent_key: c for c in vector_candidates
    }
    lexical_map: dict[str, AgentCapabilityCandidate] = {
        c.agent_key: c for c in lexical_candidates
    }

    merged: list[AgentCapabilityCandidate] = []
    seen: set[str] = set()

    all_keys = list(vector_map.keys()) + [
        k for k in lexical_map if k not in vector_map
    ]
    for key in all_keys:
        if key in seen:
            continue
        seen.add(key)

        v = vector_map.get(key)
        lx = lexical_map.get(key)

        if v is not None and lx is not None:
            blended = min(
                v.similarity * _HYBRID_VECTOR_WEIGHT
                + lx.similarity * _HYBRID_LEXICAL_WEIGHT,
                0.99,
            )
            merged.append(
                AgentCapabilityCandidate(
                    agent_key=key,
                    title=v.title,
                    description=v.description,
                    similarity=blended,
                    source="hybrid",
                    execution_mode=v.execution_mode,
                    requires_trusted_employee_context=v.requires_trusted_employee_context,
                    can_run_in_parallel=v.can_run_in_parallel,
                    supported_intents=v.supported_intents,
                    data_sources=v.data_sources,
                    sample_queries=v.sample_queries,
                )
            )
        elif v is not None:
            merged.append(
                AgentCapabilityCandidate(
                    agent_key=key,
                    title=v.title,
                    description=v.description,
                    similarity=min(v.similarity * _HYBRID_VECTOR_ONLY_DISCOUNT, 0.99),
                    source="vector",
                    execution_mode=v.execution_mode,
                    requires_trusted_employee_context=v.requires_trusted_employee_context,
                    can_run_in_parallel=v.can_run_in_parallel,
                    supported_intents=v.supported_intents,
                    data_sources=v.data_sources,
                    sample_queries=v.sample_queries,
                )
            )
        elif lx is not None:
            merged.append(
                AgentCapabilityCandidate(
                    agent_key=key,
                    title=lx.title,
                    description=lx.description,
                    similarity=min(lx.similarity * _HYBRID_LEXICAL_ONLY_DISCOUNT, 0.99),
                    source="lexical",
                    execution_mode=lx.execution_mode,
                    requires_trusted_employee_context=lx.requires_trusted_employee_context,
                    can_run_in_parallel=lx.can_run_in_parallel,
                    supported_intents=lx.supported_intents,
                    data_sources=lx.data_sources,
                    sample_queries=lx.sample_queries,
                )
            )

    merged.sort(key=lambda c: c.similarity, reverse=True)
    return merged


# ---------------------------------------------------------------------------
# Per-signal agent-capability rankers
# ---------------------------------------------------------------------------

def _rank_agent_vector_candidates(
    message: str,
    capabilities: list[dict[str, Any]],
) -> list[AgentCapabilityCandidate]:
    query_embedding = _generate_embedding_cached(message)
    if query_embedding is None:
        return []

    # Keep only the best-scored candidate per agent_key so duplicate rows
    # (e.g. global + company-specific registration) don't confuse the merge.
    ranked_by_key: dict[str, AgentCapabilityCandidate] = {}
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

        candidate = AgentCapabilityCandidate(
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
        current = ranked_by_key.get(candidate.agent_key)
        if current is None or candidate.similarity > current.similarity:
            ranked_by_key[candidate.agent_key] = candidate

    ranked = sorted(ranked_by_key.values(), key=lambda item: item.similarity, reverse=True)
    return ranked


def _rank_agent_lexical_candidates(
    message: str,
    capabilities: list[dict[str, Any]],
) -> list[AgentCapabilityCandidate]:
    # Keep only the best-scored candidate per agent_key (same rationale as vector variant).
    ranked_by_key: dict[str, AgentCapabilityCandidate] = {}
    for capability in capabilities:
        similarity = min(
            _score_lexical_similarity(message, capability["combined_text"])
            + (0.02 if capability["company_specific"] else 0.0),
            0.99,
        )
        if similarity < SEMANTIC_LEXICAL_MIN_SIMILARITY:
            continue

        candidate = AgentCapabilityCandidate(
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
        current = ranked_by_key.get(candidate.agent_key)
        if current is None or candidate.similarity > current.similarity:
            ranked_by_key[candidate.agent_key] = candidate

    ranked = sorted(ranked_by_key.values(), key=lambda item: item.similarity, reverse=True)
    return ranked


# ---------------------------------------------------------------------------
# Public retrieval functions
# ---------------------------------------------------------------------------

async def retrieve_intent_candidates(
    db: AsyncSession,
    company_id: str,
    message: str,
    *,
    top_k: int = 4,
    context_hint: str | None = None,
) -> SemanticIntentResult:
    """Retrieve the top-k most relevant intent candidates for *message*.

    ``context_hint`` (I.2): a short label such as ``"policy_reasoning"`` or
    ``"guidance"`` that hints at the expected domain.  When supplied, intents
    associated with that domain receive a small similarity boost so the
    correct route rises above noise without hard-wiring the outcome.

    Results are cached per ``(company_id, message)`` pair for
    ``_RETRIEVAL_CACHE_TTL`` seconds (I.5).
    """
    normalized_message = _normalize_text(message)
    if not normalized_message:
        return SemanticIntentResult(
            candidates=[],
            retrieval_mode="empty",
            fallback_reason="Message was empty after normalization.",
        )

    # Retrieval-result cache (I.5).
    # context_hint is included in the key so the same message called with
    # different hints produces separate cache entries with the correct boosts
    # applied (otherwise I.2 metadata boost is silently lost on cache hits).
    result_cache = get_cache("retrieval_results_intent")
    result_cache_key = f"{company_id}:{context_hint or ''}:{_message_hash(normalized_message)}"
    cached_result = result_cache.get(result_cache_key)
    if isinstance(cached_result, SemanticIntentResult):
        return cached_result

    examples = await _load_intent_examples(db, company_id)
    if not examples:
        return SemanticIntentResult(
            candidates=[],
            retrieval_mode="empty",
            fallback_reason="No active intent examples were available.",
        )

    # Metadata boost hints (I.2).
    metadata_boost_intents: set[str] | None = None
    if context_hint == "policy_reasoning":
        metadata_boost_intents = {"company_policy"}
    elif context_hint == "guidance":
        metadata_boost_intents = {"company_structure"}
    elif context_hint == "hr_data":
        metadata_boost_intents = {
            "payroll_info",
            "payroll_document_request",
            "attendance_review",
            "time_off_balance",
            "time_off_request_status",
            "personal_profile",
        }

    vector_candidates = _rank_vector_candidates(
        normalized_message,
        examples,
        metadata_boost_intents=metadata_boost_intents,
    )
    lexical_candidates = _rank_lexical_candidates(
        normalized_message,
        examples,
        metadata_boost_intents=metadata_boost_intents,
    )

    has_vector = bool(vector_candidates)
    has_lexical = bool(lexical_candidates)

    if not has_vector and not has_lexical:
        return SemanticIntentResult(
            candidates=[],
            retrieval_mode="empty",
            fallback_reason="No sufficiently similar intent examples matched the message.",
        )

    if has_vector and has_lexical:
        merged = _merge_hybrid_intent_candidates(vector_candidates, lexical_candidates)
        retrieval_mode = "hybrid"
        fallback_reason = None
    elif has_vector:
        # Vector-only: apply single-signal discount via a pass through the merger.
        merged = _merge_hybrid_intent_candidates(vector_candidates, [])
        retrieval_mode = "vector"
        fallback_reason = None
    else:
        # Lexical-only: embedding was unavailable.
        merged = _merge_hybrid_intent_candidates([], lexical_candidates)
        retrieval_mode = "lexical"
        fallback_reason = "Embedding model was unavailable, so lexical retrieval was used."

    result = SemanticIntentResult(
        candidates=merged[:top_k],
        retrieval_mode=retrieval_mode,
        fallback_reason=fallback_reason,
    )
    result_cache.set(result_cache_key, result, ttl_seconds=_RETRIEVAL_CACHE_TTL)
    return result


async def retrieve_agent_capabilities(
    db: AsyncSession,
    company_id: str,
    message: str,
    *,
    top_k: int = 4,
) -> AgentCapabilityResult:
    """Retrieve the top-k most relevant agent capability candidates.

    Uses hybrid scoring (I.1 + I.4) and caches results (I.5).
    """
    normalized_message = _normalize_text(message)
    if not normalized_message:
        return AgentCapabilityResult(
            candidates=[],
            retrieval_mode="empty",
            fallback_reason="Message was empty after normalization.",
        )

    # Retrieval-result cache (I.5).
    result_cache = get_cache("retrieval_results_capability")
    result_cache_key = f"{company_id}:{_message_hash(normalized_message)}"
    cached_result = result_cache.get(result_cache_key)
    if isinstance(cached_result, AgentCapabilityResult):
        return cached_result

    capabilities = await _load_agent_capabilities(db, company_id)
    if not capabilities:
        return AgentCapabilityResult(
            candidates=[],
            retrieval_mode="empty",
            fallback_reason="No active agent capabilities were available.",
        )

    vector_candidates = _rank_agent_vector_candidates(normalized_message, capabilities)
    lexical_candidates = _rank_agent_lexical_candidates(normalized_message, capabilities)

    has_vector = bool(vector_candidates)
    has_lexical = bool(lexical_candidates)

    if not has_vector and not has_lexical:
        return AgentCapabilityResult(
            candidates=[],
            retrieval_mode="empty",
            fallback_reason="No sufficiently similar agent capability matched the message.",
        )

    if has_vector and has_lexical:
        merged = _merge_hybrid_capability_candidates(vector_candidates, lexical_candidates)
        retrieval_mode = "hybrid"
        fallback_reason = None
    elif has_vector:
        merged = _merge_hybrid_capability_candidates(vector_candidates, [])
        retrieval_mode = "vector"
        fallback_reason = None
    else:
        merged = _merge_hybrid_capability_candidates([], lexical_candidates)
        retrieval_mode = "lexical"
        fallback_reason = "Embedding model was unavailable, so lexical retrieval was used."

    result = AgentCapabilityResult(
        candidates=merged[:top_k],
        retrieval_mode=retrieval_mode,
        fallback_reason=fallback_reason,
    )
    result_cache.set(result_cache_key, result, ttl_seconds=_RETRIEVAL_CACHE_TTL)
    return result

