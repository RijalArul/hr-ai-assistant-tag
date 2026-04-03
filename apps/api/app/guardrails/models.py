"""Pydantic models for guardrail results, config, and audit events."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ─── Guardrail Config ──────────────────────────────────────────────────────────

class RateLimitConfig(BaseModel):
    messages_per_hour: int = 30
    conversations_per_day: int = 10
    file_uploads_per_hour: int = 5


class PiiPatternConfig(BaseModel):
    custom: list[str] = Field(default_factory=list)


class SensitivityOverrideConfig(BaseModel):
    custom_high: list[str] = Field(default_factory=list)
    custom_medium: list[str] = Field(default_factory=list)


class HallucinationCheckConfig(BaseModel):
    enabled: bool = True
    numeric_tolerance_pct: float = 0.01


class ToneCheckConfig(BaseModel):
    enabled: bool = True
    nvc_strict: bool = False


class GuardrailConfig(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "company_id": "00000000-0000-0000-0000-000000000001",
                "rate_limits": {
                    "messages_per_hour": 30,
                    "conversations_per_day": 10,
                    "file_uploads_per_hour": 5,
                },
                "pii_patterns": {"custom": []},
                "blocked_topics": [],
                "sensitivity_overrides": {"custom_high": [], "custom_medium": []},
                "hallucination_check": {"enabled": True, "numeric_tolerance_pct": 0.01},
                "tone_check": {"enabled": True, "nvc_strict": False},
                "audit_level": "standard",
                "updated_at": "2026-04-03T10:00:00Z",
            }
        }
    )

    company_id: str
    rate_limits: RateLimitConfig = Field(default_factory=RateLimitConfig)
    pii_patterns: PiiPatternConfig = Field(default_factory=PiiPatternConfig)
    blocked_topics: list[str] = Field(default_factory=list)
    sensitivity_overrides: SensitivityOverrideConfig = Field(
        default_factory=SensitivityOverrideConfig
    )
    hallucination_check: HallucinationCheckConfig = Field(
        default_factory=HallucinationCheckConfig
    )
    tone_check: ToneCheckConfig = Field(default_factory=ToneCheckConfig)
    audit_level: Literal["minimal", "standard", "verbose"] = "standard"
    updated_at: datetime | None = None


class GuardrailConfigUpdateRequest(BaseModel):
    rate_limits: RateLimitConfig | None = None
    pii_patterns: PiiPatternConfig | None = None
    blocked_topics: list[str] | None = None
    sensitivity_overrides: SensitivityOverrideConfig | None = None
    hallucination_check: HallucinationCheckConfig | None = None
    tone_check: ToneCheckConfig | None = None
    audit_level: Literal["minimal", "standard", "verbose"] | None = None


# ─── Input Guard ──────────────────────────────────────────────────────────────

class InputGuardResult(BaseModel):
    blocked: bool = False
    event_type: str | None = None
    safe_response: str | None = None
    sanitized_message: str | None = None
    audit_metadata: dict[str, Any] = Field(default_factory=dict)


# ─── Output Guard ─────────────────────────────────────────────────────────────

class PiiMaskEvent(BaseModel):
    pii_type: str
    mask_count: int


class HallucinationFlag(BaseModel):
    number: str
    reason: str


class OutputGuardResult(BaseModel):
    response: str
    pii_masked: bool = False
    pii_events: list[PiiMaskEvent] = Field(default_factory=list)
    hallucination_flagged: bool = False
    hallucination_flags: list[HallucinationFlag] = Field(default_factory=list)
    disclaimer_added: bool = False
    tone_warning: bool = False
    audit_metadata: dict[str, Any] = Field(default_factory=dict)


# ─── Rate Limit Status ─────────────────────────────────────────────────────────

class RateLimitEntry(BaseModel):
    limit: int
    current: int
    remaining: int
    resets_at: datetime


class RateStatusResponse(BaseModel):
    employee_id: str
    company_id: str
    limits: dict[str, RateLimitEntry]


# ─── Audit Log ────────────────────────────────────────────────────────────────

GuardrailEventType = Literal[
    "input_blocked",
    "pii_masked",
    "hallucination_flagged",
    "rate_limited",
    "abuse_warned",
]

GuardrailActionTaken = Literal[
    "blocked",
    "masked",
    "disclaimer_added",
    "cooldown_applied",
    "warned",
]


class GuardrailAuditLogResponse(BaseModel):
    id: UUID
    company_id: UUID
    employee_id: UUID
    conversation_id: UUID | None = None
    event_type: str
    trigger: str
    action_taken: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class GuardrailAuditLogListResponse(BaseModel):
    items: list[GuardrailAuditLogResponse]
    total: int
