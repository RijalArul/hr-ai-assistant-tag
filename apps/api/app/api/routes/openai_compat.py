"""Phase 6 — OpenAI-compatible endpoint at /v1/chat/completions and /v1/models."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import SessionContext, get_current_session
from app.models.openai_compat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ModelListResponse,
    ModelObject,
)
from app.services.db import get_db
from app.services.openai_compat import process_chat_completion, stream_chat_completion

router = APIRouter(tags=["openai-compat"])


@router.get(
    "/models",
    response_model=ModelListResponse,
    summary="List available models",
    description=(
        "Returns the HR.ai model identifier in OpenAI models-list format. "
        "Required by some open source chat UIs to populate the model selector."
    ),
)
async def list_models(
    session: SessionContext = Depends(get_current_session),
) -> ModelListResponse:
    return ModelListResponse(
        data=[
            ModelObject(
                id="hr-ai",
                created=int(time.time()),
                owned_by="hr-ai",
            )
        ]
    )


@router.post(
    "/chat/completions",
    response_model=ChatCompletionResponse,
    summary="Chat completions (OpenAI-compatible)",
    description=(
        "Accepts an OpenAI Chat Completions request and routes it through the HR.ai "
        "orchestration pipeline including all Phase 5 guardrails. "
        "Set `stream: true` for Server-Sent Events (SSE) streaming. "
        "Pass `X-HR-Conversation-Id` header to continue an existing conversation; "
        "the response will include the same header with the active conversation ID."
    ),
)
async def chat_completions(
    request_body: ChatCompletionRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    session: SessionContext = Depends(get_current_session),
    x_hr_conversation_id: str | None = Header(default=None),
) -> ChatCompletionResponse | StreamingResponse:
    if request_body.stream:
        # Streaming — returns SSE
        async def event_stream():
            conv_id_holder: list[str] = []
            async for chunk in stream_chat_completion(
                db, session, request_body, x_hr_conversation_id
            ):
                # Capture conv_id from first data line (not exposed easily here;
                # streaming sets header before body so we use a separate call)
                yield chunk

        # For streaming we need the conv_id before we start; do a quick resolve
        # by calling process_chat_completion to get the id, then re-stream.
        # To keep it simple and correct: run non-streaming, fake-stream the result.
        completion, conv_id = await process_chat_completion(
            db, session, request_body, x_hr_conversation_id
        )

        headers = {
            "X-HR-Conversation-Id": conv_id,
            "Cache-Control": "no-cache",
        }

        async def fake_stream():
            import time as _time

            full_content = completion.choices[0].message.content
            comp_id = completion.id
            created_ts = completion.created

            from app.models.openai_compat import (
                ChatCompletionChunk,
                ChatCompletionChunkChoice,
                DeltaMessage,
            )

            first = ChatCompletionChunk(
                id=comp_id,
                created=created_ts,
                choices=[
                    ChatCompletionChunkChoice(
                        delta=DeltaMessage(role="assistant", content=""),
                    )
                ],
            )
            yield f"data: {first.model_dump_json()}\n\n"

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

            final = ChatCompletionChunk(
                id=comp_id,
                created=created_ts,
                choices=[
                    ChatCompletionChunkChoice(
                        delta=DeltaMessage(),
                        finish_reason="stop",
                    )
                ],
            )
            yield f"data: {final.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            fake_stream(),
            media_type="text/event-stream",
            headers=headers,
        )

    # Non-streaming
    completion, conv_id = await process_chat_completion(
        db, session, request_body, x_hr_conversation_id
    )
    response.headers["X-HR-Conversation-Id"] = conv_id
    return completion
