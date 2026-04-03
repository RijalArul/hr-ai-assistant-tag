from __future__ import annotations

import asyncio
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from google import genai

from app.core.config import get_settings
from app.models import ConversationIntent, IntentAssessment, SensitivityAssessment
from app.services.provider_health import (
    close_provider_circuit,
    get_open_circuit_reason,
    open_provider_circuit,
)
from shared import SensitivityLevel

settings = get_settings()
GEMINI_FILE_PROVIDER_NAME = "gemini-file-extractor"
GEMINI_CLASSIFIER_PROVIDER_NAME = "gemini-classifier"

INTENT_VALUES = [intent.value for intent in ConversationIntent]
SENSITIVITY_VALUES = [level.value for level in SensitivityLevel]
CLASSIFICATION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "primary_intent": {
            "type": "string",
            "enum": INTENT_VALUES,
        },
        "secondary_intents": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": INTENT_VALUES,
            },
        },
        "confidence": {
            "type": "number",
        },
        "matched_keywords": {
            "type": "array",
            "items": {"type": "string"},
        },
        "sensitivity_level": {
            "type": "string",
            "enum": SENSITIVITY_VALUES,
        },
        "sensitivity_keywords": {
            "type": "array",
            "items": {"type": "string"},
        },
        "sensitivity_rationale": {
            "type": "string",
        },
    },
    "required": [
        "primary_intent",
        "secondary_intents",
        "confidence",
        "matched_keywords",
        "sensitivity_level",
        "sensitivity_keywords",
        "sensitivity_rationale",
    ],
}


@dataclass(slots=True)
class GeminiExtractionResult:
    text: str | None = None
    fallback_reason: str | None = None

    @property
    def is_success(self) -> bool:
        return isinstance(self.text, str) and bool(self.text.strip())


@dataclass(slots=True)
class GeminiClassificationResult:
    intent: IntentAssessment | None = None
    sensitivity: SensitivityAssessment | None = None
    fallback_reason: str | None = None

    @property
    def is_success(self) -> bool:
        return self.intent is not None and self.sensitivity is not None


def _guess_mime_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


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


def _extract_with_gemini(path: Path) -> str:
    client = genai.Client(api_key=settings.gemini_api_key)
    uploaded_file = client.files.upload(
        file=path,
        config={
            "mime_type": _guess_mime_type(path),
            "display_name": path.name,
        },
    )
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=[
            uploaded_file,
            (
                "Extract the HR-relevant text from this file. Return only the "
                "useful extracted content in plain text."
            ),
        ],
    )
    text = getattr(response, "text", None)
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Gemini returned an empty extraction response.")
    return text.strip()


def _classify_with_gemini(message: str) -> dict:
    client = genai.Client(api_key=settings.gemini_api_key)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=[
            (
                "You classify HR support messages. Return JSON only. "
                "Keep employee-specific payroll, attendance, leave, and personal "
                "profile in HR intents. Keep company rules and structure in "
                "company intents. Use employee_wellbeing_concern for harassment, "
                "bullying, violence, self-harm, burnout, or similar wellbeing "
                "risks. Use out_of_scope if not really HR related.\n\n"
                f"Message: {message}"
            ),
        ],
        config={
            "temperature": 0.1,
            "response_mime_type": "application/json",
            "response_json_schema": CLASSIFICATION_JSON_SCHEMA,
        },
    )

    text = getattr(response, "text", None)
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("Gemini returned no classification content.")

    parsed = _extract_json_object(text)
    if parsed is None:
        raise RuntimeError("Gemini returned a response that could not be parsed as JSON.")
    return parsed


async def extract_file_with_gemini(path: Path) -> GeminiExtractionResult:
    if not settings.phase3_use_remote_providers:
        return GeminiExtractionResult(
            fallback_reason="Remote providers are disabled by configuration.",
        )
    if not settings.gemini_api_key:
        return GeminiExtractionResult(
            fallback_reason="Gemini API key is missing from the environment.",
        )

    circuit_reason = get_open_circuit_reason(GEMINI_FILE_PROVIDER_NAME)
    if circuit_reason:
        return GeminiExtractionResult(
            fallback_reason=(
                "Gemini circuit breaker is open because of a recent provider "
                f"failure. {circuit_reason}"
            ),
        )

    try:
        extracted_text = await asyncio.wait_for(
            asyncio.to_thread(_extract_with_gemini, path),
            timeout=settings.gemini_timeout_seconds,
        )
    except TimeoutError:
        reason = f"Gemini timed out after {settings.gemini_timeout_seconds} seconds."
        open_provider_circuit(GEMINI_FILE_PROVIDER_NAME, reason)
        return GeminiExtractionResult(fallback_reason=reason)
    except Exception as exc:
        reason = str(exc).strip() or "Gemini file extraction failed."
        open_provider_circuit(GEMINI_FILE_PROVIDER_NAME, reason)
        return GeminiExtractionResult(fallback_reason=reason)

    close_provider_circuit(GEMINI_FILE_PROVIDER_NAME)
    return GeminiExtractionResult(text=extracted_text)


async def classify_with_gemini(
    message: str,
) -> GeminiClassificationResult:
    if not settings.phase3_use_remote_providers:
        return GeminiClassificationResult(
            fallback_reason="Remote providers are disabled by configuration.",
        )
    if not settings.gemini_api_key:
        return GeminiClassificationResult(
            fallback_reason="Gemini API key is missing from the environment.",
        )

    circuit_reason = get_open_circuit_reason(GEMINI_CLASSIFIER_PROVIDER_NAME)
    if circuit_reason:
        return GeminiClassificationResult(
            fallback_reason=(
                "Gemini circuit breaker is open because of a recent provider "
                f"failure. {circuit_reason}"
            ),
        )

    try:
        parsed = await asyncio.wait_for(
            asyncio.to_thread(_classify_with_gemini, message),
            timeout=settings.gemini_classifier_timeout_seconds,
        )
    except TimeoutError:
        reason = (
            f"Gemini classifier timed out after "
            f"{settings.gemini_classifier_timeout_seconds} seconds."
        )
        open_provider_circuit(GEMINI_CLASSIFIER_PROVIDER_NAME, reason)
        return GeminiClassificationResult(fallback_reason=reason)
    except Exception as exc:
        reason = str(exc).strip() or "Gemini classification failed."
        open_provider_circuit(GEMINI_CLASSIFIER_PROVIDER_NAME, reason)
        return GeminiClassificationResult(fallback_reason=reason)

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
    except (KeyError, ValueError, TypeError):
        reason = "Gemini returned an unexpected classification payload."
        open_provider_circuit(GEMINI_CLASSIFIER_PROVIDER_NAME, reason)
        return GeminiClassificationResult(fallback_reason=reason)

    close_provider_circuit(GEMINI_CLASSIFIER_PROVIDER_NAME)
    return GeminiClassificationResult(intent=intent, sensitivity=sensitivity)
