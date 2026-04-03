# HR.ai Phase 6 OpenAI-Compatible API Reference

Phase 6 introduces a single OpenAI-compatible endpoint that allows any open source chatbot UI to connect to HR.ai without modification.

This endpoint translates between the OpenAI Chat Completions format and the HR.ai conversations API internally.

## Endpoint Base URL

```text
https://api.hr-ai.io/v1
```

Note: this prefix is `/v1/`, separate from the internal API at `/api/v1/`. This matches the expected base URL format used by open source chat UIs.

## Authentication

Same JWT bearer token as all other HR.ai endpoints:

```text
Authorization: Bearer <hr-ai-jwt-token>
```

Obtain a token by calling `POST /api/v1/auth/login` with an employee email. The returned `access_token` is used as the API Key in open source UI settings.

## POST /v1/chat/completions

Purpose:
Receives a chat request in OpenAI format, processes it through the HR.ai orchestration pipeline, and returns a response in OpenAI format.

Auth:
Bearer token required.

### Request Body

```json
{
  "model": "hr-ai",
  "messages": [
    {
      "role": "user",
      "content": "Berapa sisa cuti saya?"
    }
  ],
  "stream": false
}
```

Field behavior:

| Field | Behavior |
|---|---|
| `model` | Ignored. Always uses HR.ai internal orchestrator. |
| `messages` | The last message with `role: user` is sent to the orchestrator. Prior messages are used for context. |
| `messages[].role` | `user` and `assistant` are mapped to HR.ai roles. `system` messages are ignored. |
| `stream` | `false` for standard response. `true` for SSE streaming (see Streaming section). |
| `temperature`, `top_p`, `max_tokens` | Ignored. HR.ai manages these parameters internally. |
| `tools`, `functions` | Not supported. HR.ai uses internal agent routing. |

### Request Headers

| Header | Required | Description |
|---|---|---|
| `Authorization` | Yes | `Bearer <hr-ai-jwt-token>` |
| `X-HR-Conversation-Id` | No | If provided, continues an existing HR.ai conversation. If not provided, a new conversation is created. |

### Expected Success Response (stream: false)

HTTP 200:

```json
{
  "id": "chatcmpl-conv-40000000-0000-0000-0000-000000000001",
  "object": "chat.completion",
  "created": 1714723200,
  "model": "hr-ai",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Sisa cuti kamu saat ini adalah 8 hari dari total 12 hari untuk tahun 2026."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": null,
    "completion_tokens": null,
    "total_tokens": null
  }
}
```

Response headers include:

```text
X-HR-Conversation-Id: 40000000-0000-0000-0000-000000000001
```

Store this value and send it back in `X-HR-Conversation-Id` on subsequent requests to continue the same conversation.

### Streaming Response (stream: true)

When `stream: true`, the response is sent as Server-Sent Events (SSE):

```text
HTTP/1.1 200 OK
Content-Type: text/event-stream
X-HR-Conversation-Id: 40000000-0000-0000-0000-000000000001

data: {"id":"chatcmpl-conv-40000000-0000-0000-0000-000000000001","object":"chat.completion.chunk","created":1714723200,"model":"hr-ai","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}

data: {"id":"chatcmpl-conv-40000000-0000-0000-0000-000000000001","object":"chat.completion.chunk","created":1714723200,"model":"hr-ai","choices":[{"index":0,"delta":{"content":"Sisa"},"finish_reason":null}]}

data: {"id":"chatcmpl-conv-40000000-0000-0000-0000-000000000001","object":"chat.completion.chunk","created":1714723200,"model":"hr-ai","choices":[{"index":0,"delta":{"content":" cuti"},"finish_reason":null}]}

data: {"id":"chatcmpl-conv-40000000-0000-0000-0000-000000000001","object":"chat.completion.chunk","created":1714723200,"model":"hr-ai","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

### Response When Input Guard Blocks

If the Input Guard blocks the message (injection detected, rate limited, abuse detected), the endpoint still returns HTTP 200 with a safe response instead of an error:

```json
{
  "id": "chatcmpl-blocked-...",
  "object": "chat.completion",
  "created": 1714723200,
  "model": "hr-ai",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Maaf, saya hanya bisa membantu pertanyaan terkait HR. Silakan coba kembali."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": null,
    "completion_tokens": null,
    "total_tokens": null
  }
}
```

### Expected Errors

| Status | Condition |
|---|---|
| `401 Unauthorized` | Token is missing, malformed, expired, or invalid |
| `429 Too Many Requests` | Rate limit exceeded. Body includes `retry_after_seconds`. |
| `503 Service Unavailable` | Orchestrator or required providers are temporarily unavailable |

HTTP 429 body:

```json
{
  "error": {
    "message": "Terlalu banyak permintaan. Silakan coba lagi dalam beberapa menit.",
    "type": "rate_limit_error",
    "code": "rate_limit_exceeded"
  },
  "retry_after_seconds": 300
}
```

## GET /v1/models

Purpose:
Returns a list of available models. Required by some open source UIs to populate the model selector.

Auth:
Bearer token required.

Expected success response:

```json
{
  "object": "list",
  "data": [
    {
      "id": "hr-ai",
      "object": "model",
      "created": 1714723200,
      "owned_by": "hr-ai"
    }
  ]
}
```

## Limitations

The following OpenAI API features are intentionally not supported:

| Feature | Status | Reason |
|---|---|---|
| `tools` / `function_calling` | Not supported | HR.ai uses internal agent routing |
| `logprobs` | Not supported | Not applicable |
| `temperature`, `top_p` | Ignored | HR.ai manages internally |
| `max_tokens` | Ignored | HR.ai manages internally |
| `n` (multiple completions) | Not supported | Always returns one choice |
| Base64 images in `content` | Not supported | Use Phase 4 attachment flow instead |
| Embeddings endpoint | Not supported | Not applicable for chat UI integration |
| Fine-tuning endpoints | Not supported | Not applicable |

## Session Continuity

Open source UIs often send the full conversation history in every request. HR.ai handles this via conversation_id tracking:

```text
First request (no X-HR-Conversation-Id header):
  -> wrapper creates a new conversation
  -> processes the last user message
  -> returns response with X-HR-Conversation-Id: {id} in response header

Subsequent requests (with X-HR-Conversation-Id header):
  -> wrapper continues the existing conversation
  -> processes the last user message only
  -> prior messages in the request body are used for context, not re-sent to orchestrator
```

If the UI does not support sending custom headers, each request creates a new conversation. The chat history will still appear in the UI (rendered from `messages[]`) but the orchestrator will not have memory of prior turns.

## Configuration Guide Per UI

### LibreChat

`librechat.yaml`:

```yaml
endpoints:
  custom:
    - name: "HR.ai"
      apiKey: "${HR_AI_JWT_TOKEN}"
      baseURL: "https://api.hr-ai.io/v1"
      models:
        default: ["hr-ai"]
        fetch: false
      titleConvo: true
      titleModel: "hr-ai"
      dropParams:
        - "temperature"
        - "top_p"
        - "frequency_penalty"
        - "presence_penalty"
```

### Open WebUI

Environment variables:

```bash
OPENAI_API_BASE_URL=https://api.hr-ai.io/v1
OPENAI_API_KEY=<hr-ai-jwt-token>
```

### AnythingLLM

In LLM Provider settings:
- Provider: `Generic OpenAI`
- Base URL: `https://api.hr-ai.io/v1`
- API Key: JWT token from HR.ai login
- Model ID: `hr-ai`

### LobeChat

In model provider settings:
- Provider: `Custom`
- Base URL: `https://api.hr-ai.io/v1`
- API Key: JWT token
- Model: `hr-ai`

## Docker Compose Quick Start

Reference template for running LibreChat alongside HR.ai:

Location in repo: `infra/examples/librechat-compose/docker-compose.yml`

This template provisions:
- HR.ai FastAPI backend
- LibreChat frontend
- Shared PostgreSQL
- Shared Redis

Start with:

```bash
cp infra/examples/librechat-compose/.env.example .env
# fill in HR_AI_JWT_TOKEN and other variables
docker compose up
```

Employee access point after startup: `http://localhost:3080`
