from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.models import (
    ConversationIntent,
    IntentAssessment,
    SensitivityAssessment,
)
from app.core.config import get_settings
from app.services.provider_health import (
    close_provider_circuit,
    get_open_circuit_reason,
    open_provider_circuit,
)
from shared import SensitivityLevel

settings = get_settings()
MINIMAX_PROVIDER_NAME = "minimax-classifier"

INTENT_VALUES = [intent.value for intent in ConversationIntent]
SENSITIVITY_VALUES = [level.value for level in SensitivityLevel]


@dataclass(slots=True)
class ProviderClassificationResult:
    intent: IntentAssessment | None = None
    sensitivity: SensitivityAssessment | None = None
    chosen_agents: list[str] | None = None
    fallback_reason: str | None = None

    @property
    def is_success(self) -> bool:
        return self.intent is not None and self.sensitivity is not None


def _resolve_chat_completion_url() -> str:
    base = settings.minimax_api_base.rstrip("/")
    if base.endswith("/text/chatcompletion_v2"):
        return base
    return f"{base}/text/chatcompletion_v2"


def _extract_json_object(raw_text: str) -> dict | None:
    candidate = raw_text.strip()
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        parsed = json.loads(candidate[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _extract_message_content(payload: dict) -> str | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None

    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None

    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return "\n".join(parts)
    return None


def _call_minimax(system_prompt: str, user_prompt: str) -> dict:
    body = {
        "model": settings.minimax_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 600,
    }

    request = Request(
        _resolve_chat_completion_url(),
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.minimax_api_key}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=settings.minimax_timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="ignore").strip()
        detail = f"MiniMax returned HTTP {exc.code}."
        if response_body:
            detail = f"{detail} {response_body[:240]}"
        raise RuntimeError(detail) from exc
    except URLError as exc:
        raise RuntimeError(f"MiniMax network error: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError(
            f"MiniMax timed out after {settings.minimax_timeout_seconds} seconds."
        ) from exc


async def classify_with_minimax(
    message: str,
    *,
    candidate_intents: list[dict[str, Any]] | None = None,
    candidate_agents: list[dict[str, Any]] | None = None,
    local_assessment: IntentAssessment | None = None,
) -> ProviderClassificationResult:
    if not settings.phase3_use_remote_providers:
        return ProviderClassificationResult(
            fallback_reason="Remote providers are disabled by configuration.",
        )
    if not settings.minimax_api_key:
        return ProviderClassificationResult(
            fallback_reason="MiniMax API key is missing from the environment.",
        )

    circuit_reason = get_open_circuit_reason(MINIMAX_PROVIDER_NAME)
    if circuit_reason:
        return ProviderClassificationResult(
            fallback_reason=(
                "MiniMax circuit breaker is open because of a recent provider "
                f"failure. {circuit_reason}"
            ),
        )

    system_prompt = f"""
You classify HR support messages.
Return JSON only.
The JSON must contain:
- primary_intent: one of {INTENT_VALUES}
- secondary_intents: array of values from {INTENT_VALUES}
- confidence: number between 0 and 1
- matched_keywords: array of short strings
- sensitivity_level: one of {SENSITIVITY_VALUES}
- sensitivity_keywords: array of short strings
- sensitivity_rationale: short string
- chosen_agents: array of values from ['hr-data-agent', 'company-agent', 'file-agent']
Rules:
- Keep employee-specific payroll, attendance, leave, and personal profile in HR intents.
- Keep company rules and structure in company intents.
- Prefer hr-data-agent for employee-specific structured HR data.
- Prefer company-agent for company policy and company structure.
- Prefer file-agent only when attachment handling is clearly relevant.
- Use employee_wellbeing_concern for harassment, bullying, violence, self-harm, burnout, or similar wellbeing risks.
- Use out_of_scope if not really HR related.
- If semantic routing candidates are provided and they fit the message, prefer them over inventing a new intent.
""".strip()

    user_prompt_parts = [f"Message: {message}"]
    if local_assessment is not None:
        user_prompt_parts.append(
            "\n".join(
                [
                    "Local heuristic assessment:",
                    f"- primary_intent: {local_assessment.primary_intent.value}",
                    f"- confidence: {local_assessment.confidence:.2f}",
                    (
                        "- secondary_intents: "
                        + ", ".join(intent.value for intent in local_assessment.secondary_intents)
                    )
                    if local_assessment.secondary_intents
                    else "- secondary_intents: none",
                    (
                        "- matched_keywords: "
                        + ", ".join(local_assessment.matched_keywords)
                    )
                    if local_assessment.matched_keywords
                    else "- matched_keywords: none",
                ]
            )
        )
    if candidate_intents:
        candidate_lines = ["Semantic routing candidates:"]
        for candidate in candidate_intents[:5]:
            candidate_lines.append(
                "- "
                + ", ".join(
                    [
                        f"intent={candidate.get('intent', '-')}",
                        f"similarity={float(candidate.get('similarity', 0.0)):.2f}",
                        f"source={candidate.get('source', '-')}",
                        f"example={str(candidate.get('example_text', ''))[:180]}",
                    ]
                )
            )
        user_prompt_parts.append("\n".join(candidate_lines))
    if candidate_agents:
        candidate_lines = ["Agent capability candidates:"]
        for candidate in candidate_agents[:5]:
            candidate_lines.append(
                "- "
                + ", ".join(
                    [
                        f"agent_key={candidate.get('agent_key', '-')}",
                        f"similarity={float(candidate.get('similarity', 0.0)):.2f}",
                        f"execution_mode={candidate.get('execution_mode', '-')}",
                        f"title={str(candidate.get('title', ''))[:120]}",
                    ]
                )
            )
        user_prompt_parts.append("\n".join(candidate_lines))

    user_prompt = "\n\n".join(part for part in user_prompt_parts if part)

    try:
        response_payload = await asyncio.wait_for(
            asyncio.to_thread(
                _call_minimax,
                system_prompt,
                user_prompt,
            ),
            timeout=settings.minimax_timeout_seconds + 1,
        )
    except RuntimeError as exc:
        reason = str(exc).strip() or "MiniMax request failed."
        open_provider_circuit(MINIMAX_PROVIDER_NAME, reason)
        return ProviderClassificationResult(fallback_reason=reason)
    except TimeoutError:
        reason = f"MiniMax timed out after {settings.minimax_timeout_seconds + 1} seconds."
        open_provider_circuit(MINIMAX_PROVIDER_NAME, reason)
        return ProviderClassificationResult(fallback_reason=reason)

    content = _extract_message_content(response_payload)
    if not content:
        reason = "MiniMax returned no message content."
        open_provider_circuit(MINIMAX_PROVIDER_NAME, reason)
        return ProviderClassificationResult(fallback_reason=reason)

    parsed = _extract_json_object(content)
    if parsed is None:
        reason = "MiniMax returned a response that could not be parsed as JSON."
        open_provider_circuit(MINIMAX_PROVIDER_NAME, reason)
        return ProviderClassificationResult(fallback_reason=reason)

    try:
        intent = IntentAssessment(
            primary_intent=ConversationIntent(parsed["primary_intent"]),
            secondary_intents=[
                ConversationIntent(value)
                for value in parsed.get("secondary_intents", [])
                if value in INTENT_VALUES and value != parsed["primary_intent"]
            ],
            confidence=float(parsed.get("confidence", 0.5)),
            matched_keywords=[
                str(value) for value in parsed.get("matched_keywords", [])[:8]
            ],
        )
        sensitivity = SensitivityAssessment(
            level=SensitivityLevel(parsed["sensitivity_level"]),
            matched_keywords=[
                str(value) for value in parsed.get("sensitivity_keywords", [])[:8]
            ],
            rationale=str(parsed.get("sensitivity_rationale", "Provider classification."))[
                :500
            ],
        )
        chosen_agents = [
            str(value)
            for value in parsed.get("chosen_agents", [])
            if str(value) in {"hr-data-agent", "company-agent", "file-agent"}
        ]
    except (KeyError, ValueError, TypeError):
        reason = "MiniMax returned an unexpected classification payload."
        open_provider_circuit(MINIMAX_PROVIDER_NAME, reason)
        return ProviderClassificationResult(fallback_reason=reason)

    close_provider_circuit(MINIMAX_PROVIDER_NAME)
    return ProviderClassificationResult(
        intent=intent,
        sensitivity=sensitivity,
        chosen_agents=chosen_agents,
    )
