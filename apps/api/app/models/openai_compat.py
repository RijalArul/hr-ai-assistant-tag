"""Phase 6 — Pydantic models for OpenAI-compatible request/response format."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class OpenAIMessage(BaseModel):
    role: str  # "system" | "user" | "assistant"
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "hr-ai"
    messages: list[OpenAIMessage]
    stream: bool = False
    # Ignored fields — accepted to avoid 422 from strict UIs
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    n: int | None = None
    tools: list[Any] | None = None
    functions: list[Any] | None = None


# ---------------------------------------------------------------------------
# Response (non-streaming)
# ---------------------------------------------------------------------------


class OpenAIResponseMessage(BaseModel):
    role: str = "assistant"
    content: str


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: OpenAIResponseMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str = "hr-ai"
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage = Field(default_factory=ChatCompletionUsage)


# ---------------------------------------------------------------------------
# Streaming chunk
# ---------------------------------------------------------------------------


class DeltaMessage(BaseModel):
    role: str | None = None
    content: str | None = None


class ChatCompletionChunkChoice(BaseModel):
    index: int = 0
    delta: DeltaMessage
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str = "hr-ai"
    choices: list[ChatCompletionChunkChoice]


# ---------------------------------------------------------------------------
# /v1/models response
# ---------------------------------------------------------------------------


class ModelObject(BaseModel):
    id: str = "hr-ai"
    object: str = "model"
    created: int
    owned_by: str = "hr-ai"


class ModelListResponse(BaseModel):
    object: str = "list"
    data: list[ModelObject]


# ---------------------------------------------------------------------------
# Error format (OpenAI-style)
# ---------------------------------------------------------------------------


class OpenAIErrorDetail(BaseModel):
    message: str
    type: str
    code: str


class OpenAIErrorResponse(BaseModel):
    error: OpenAIErrorDetail
    retry_after_seconds: int | None = None
