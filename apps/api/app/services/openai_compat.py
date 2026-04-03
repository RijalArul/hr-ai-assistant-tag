"""Phase 6 — mapping logic between OpenAI format and HR.ai conversations API."""

from __future__ import annotations

import json
import time
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import SessionContext
from app.models import (
    ConversationCreateRequest,
    ConversationMessageCreateRequest,
)
from app.models.openai_compat import (
    ChatCompletionChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    DeltaMessage,
    OpenAIMessage,
    OpenAIResponseMessage,
)
from app.services.conversations import (
    create_conversation,
    create_conversation_message,
)

BLOCKED_SAFE_CONTENT = (
    "Maaf, saya hanya bisa membantu pertanyaan terkait HR. Silakan coba kembali."
)


def _extract_last_user_message(messages: list[OpenAIMessage]) -> str:
    """Return content of the last user message."""
    for msg in reversed(messages):
        if msg.role == "user":
            return msg.content
    return ""


def _make_completion_id(conversation_id: str) -> str:
    return f"chatcmpl-conv-{conversation_id}"


async def process_chat_completion(
    db: AsyncSession,
    session: SessionContext,
    request: ChatCompletionRequest,
    conversation_id: str | None,
) -> tuple[ChatCompletionResponse, str]:
    """
    Process a ChatCompletionRequest and return (response, conversation_id).

    conversation_id is resolved or created here. The caller should attach
    it to the response headers as X-HR-Conversation-Id.
    """
    user_message = _extract_last_user_message(request.messages)

    # Resolve or create conversation
    if conversation_id:
        conv_id = UUID(conversation_id)
    else:
        conv = await create_conversation(
            db,
            session,
            ConversationCreateRequest(title="OpenAI Compat Session"),
        )
        conv_id = conv.id

    # Send through the full HR.ai pipeline (including guardrails)
    exchange = await create_conversation_message(
        db,
        conv_id,
        ConversationMessageCreateRequest(message=user_message),
        session,
    )

    answer = exchange.orchestration.answer or BLOCKED_SAFE_CONTENT
    created_ts = int(time.time())
    comp_id = _make_completion_id(str(conv_id))

    response = ChatCompletionResponse(
        id=comp_id,
        created=created_ts,
        choices=[
            ChatCompletionChoice(
                message=OpenAIResponseMessage(content=answer),
            )
        ],
        usage=ChatCompletionUsage(),
    )
    return response, str(conv_id)


async def stream_chat_completion(
    db: AsyncSession,
    session: SessionContext,
    request: ChatCompletionRequest,
    conversation_id: str | None,
):
    """
    Async generator that yields SSE-formatted strings for streaming.

    Because the HR.ai orchestrator is non-streaming today, the full response
    is obtained first and then flushed word-by-word to emulate streaming.
    """
    response, conv_id = await process_chat_completion(
        db, session, request, conversation_id
    )

    comp_id = response.id
    created_ts = response.created
    full_content = response.choices[0].message.content

    # First chunk: role announcement
    first_chunk = ChatCompletionChunk(
        id=comp_id,
        created=created_ts,
        choices=[
            ChatCompletionChunkChoice(
                delta=DeltaMessage(role="assistant", content=""),
            )
        ],
    )
    yield f"data: {first_chunk.model_dump_json()}\n\n"

    # Stream content word-by-word
    words = full_content.split(" ")
    for i, word in enumerate(words):
        token = word if i == len(words) - 1 else word + " "
        chunk = ChatCompletionChunk(
            id=comp_id,
            created=created_ts,
            choices=[
                ChatCompletionChunkChoice(
                    delta=DeltaMessage(content=token),
                )
            ],
        )
        yield f"data: {chunk.model_dump_json()}\n\n"

    # Final chunk
    final_chunk = ChatCompletionChunk(
        id=comp_id,
        created=created_ts,
        choices=[
            ChatCompletionChunkChoice(
                delta=DeltaMessage(),
                finish_reason="stop",
            )
        ],
    )
    yield f"data: {final_chunk.model_dump_json()}\n\n"
    yield "data: [DONE]\n\n"
