from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.agent_architecture import AttachmentInput, OrchestratorResponse
from app.models.action_engine import ActionResponse
from shared import ConversationStatus


class ConversationMessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ConversationCreateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Payroll self-service chat",
                "metadata": {
                    "source": "discord_bot",
                },
            }
        }
    )

    title: str | None = Field(default=None, min_length=2, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=160)
    status: ConversationStatus | None = None
    metadata: dict[str, Any] | None = None


class ConversationMessageCreateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Berapa sisa cuti saya tahun ini?",
                "attachments": [],
                "metadata": {
                    "channel": "api",
                },
            }
        }
    )

    message: str = Field(min_length=1, max_length=4000)
    attachments: list[AttachmentInput] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationMessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: ConversationMessageRole
    content: str
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ConversationResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "40000000-0000-0000-0000-000000000101",
                "company_id": "00000000-0000-0000-0000-000000000001",
                "employee_id": "20000000-0000-0000-0000-000000000004",
                "title": "Payroll self-service chat",
                "status": "active",
                "metadata": {
                    "source": "discord_bot",
                },
                "last_message_at": "2026-04-03T10:05:00Z",
                "created_at": "2026-04-03T10:00:00Z",
                "updated_at": "2026-04-03T10:05:00Z",
                "messages": [],
            }
        }
    )

    id: UUID
    company_id: UUID
    employee_id: UUID
    title: str | None = None
    status: ConversationStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[ConversationMessageResponse] = Field(default_factory=list)


class ConversationMessageExchangeResponse(BaseModel):
    conversation: ConversationResponse
    user_message: ConversationMessageResponse
    assistant_message: ConversationMessageResponse
    orchestration: OrchestratorResponse
    triggered_actions: list[ActionResponse] = Field(default_factory=list)
