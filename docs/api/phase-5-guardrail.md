# HR.ai Phase 5 Guardrail API Reference

Phase 5 introduces two new public surfaces for guardrail management:
- guardrail audit log access for IT Admin
- guardrail configuration management for IT Admin

All existing endpoints (auth, conversations, actions, rules, webhooks) continue to work unchanged. The guardrail layer intercepts requests and responses transparently.

## Runtime Docs

- Interactive Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
- Local API base URL: `http://localhost:8000/api/v1`
- Production API base URL: `https://api.hr-ai.io/api/v1`

## Auth and Role Notes

All Phase 5 guardrail endpoints require a bearer token.

Role boundaries:
- `it_admin`: full access to guardrail config and audit logs
- `hr_admin`: read-only access to audit log summaries (no raw logs)
- `employee`: no access to guardrail management surfaces

## How Guardrail Works at Runtime

The guardrail layer is transparent to the caller. No changes are needed to existing API calls.

When a message is blocked by Input Guard, the endpoint returns a structured safe response instead of passing through to the orchestrator:

```json
{
  "id": "conv_...",
  "message": {
    "role": "assistant",
    "content": "Maaf, saya hanya bisa membantu pertanyaan terkait HR. Silakan coba kembali.",
    "created_at": "2026-04-03T10:15:00Z"
  },
  "guardrail_triggered": true,
  "guardrail_event": "input_blocked"
}
```

When Output Guard masks PII, the response content is returned with masked values. No special response field is added, but an audit event is written.

When a rate limit is exceeded, the endpoint returns HTTP 429 with:

```json
{
  "detail": "Terlalu banyak permintaan. Silakan coba lagi dalam beberapa menit.",
  "retry_after_seconds": 300
}
```

## GET /api/v1/guardrails/audit-logs

Purpose:
Lists guardrail audit events for the current company.

Auth:
Bearer token required.

Role requirement:
- `it_admin`: full log access
- `hr_admin`: summary view only (no trigger detail, no raw message context)

Query parameters:

| Parameter | Type | Description |
|---|---|---|
| `event_type` | string | Filter by event type. Options: `input_blocked`, `pii_masked`, `hallucination_flagged`, `rate_limited`, `abuse_warned` |
| `employee_id` | uuid | Filter by employee |
| `from` | datetime | Start of time range (ISO 8601) |
| `to` | datetime | End of time range (ISO 8601) |
| `limit` | int | Max results to return, default 50 |
| `offset` | int | Pagination offset, default 0 |

Expected success response (it_admin):

```json
{
  "items": [
    {
      "id": "70000000-0000-0000-0000-000000000001",
      "company_id": "00000000-0000-0000-0000-000000000001",
      "employee_id": "20000000-0000-0000-0000-000000000004",
      "conversation_id": null,
      "event_type": "rate_limited",
      "trigger": "messages_per_hour limit exceeded: 30/30",
      "action_taken": "blocked",
      "metadata": {
        "limit_type": "messages_per_hour",
        "current_count": 30,
        "limit": 30,
        "window_seconds": 3600
      },
      "created_at": "2026-04-03T10:15:00Z"
    },
    {
      "id": "70000000-0000-0000-0000-000000000002",
      "company_id": "00000000-0000-0000-0000-000000000001",
      "employee_id": "20000000-0000-0000-0000-000000000005",
      "conversation_id": "40000000-0000-0000-0000-000000000002",
      "event_type": "pii_masked",
      "trigger": "nik_pattern detected in output",
      "action_taken": "masked",
      "metadata": {
        "pii_type": "nik",
        "mask_count": 1
      },
      "created_at": "2026-04-03T10:18:00Z"
    }
  ],
  "total": 2
}
```

Expected errors:
- `401 Unauthorized`: token is missing, malformed, expired, or invalid
- `403 Forbidden`: current role is not allowed to access audit logs

## GET /api/v1/guardrails/audit-logs/{id}

Purpose:
Returns detail for one guardrail audit event.

Auth:
Bearer token required.

Role requirement:
- `it_admin`

Expected errors:
- `401 Unauthorized`: token is missing, malformed, expired, or invalid
- `403 Forbidden`: current role is not it_admin
- `404 Not Found`: audit event does not exist in this company

## GET /api/v1/guardrails/config

Purpose:
Returns the current guardrail configuration for the company.

Auth:
Bearer token required.

Role requirement:
- `it_admin`

Expected success response:

```json
{
  "company_id": "00000000-0000-0000-0000-000000000001",
  "rate_limits": {
    "messages_per_hour": 30,
    "conversations_per_day": 10,
    "file_uploads_per_hour": 5
  },
  "pii_patterns": {
    "custom": []
  },
  "blocked_topics": [],
  "sensitivity_overrides": {
    "custom_high": [],
    "custom_medium": []
  },
  "hallucination_check": {
    "enabled": true,
    "numeric_tolerance_pct": 0.01
  },
  "tone_check": {
    "enabled": true,
    "nvc_strict": false
  },
  "audit_level": "standard",
  "updated_at": "2026-04-03T10:00:00Z"
}
```

Expected errors:
- `401 Unauthorized`: token is missing, malformed, expired, or invalid
- `403 Forbidden`: current role is not it_admin

## PATCH /api/v1/guardrails/config

Purpose:
Updates one or more guardrail configuration fields for the company. Partial updates are supported.

Auth:
Bearer token required.

Role requirement:
- `it_admin`

Example request (update rate limits only):

```json
{
  "rate_limits": {
    "messages_per_hour": 60,
    "conversations_per_day": 20
  }
}
```

Example request (add custom PII pattern):

```json
{
  "pii_patterns": {
    "custom": ["\\bEMP-\\d{6}\\b"]
  }
}
```

Example request (add blocked topics):

```json
{
  "blocked_topics": ["cryptocurrency", "trading", "investment"]
}
```

Example request (set audit level):

```json
{
  "audit_level": "verbose"
}
```

Expected success response:
Returns the full updated config object, same format as GET response.

Expected errors:
- `400 Bad Request`: invalid config values (e.g. rate limit below minimum, invalid regex pattern)
- `401 Unauthorized`: token is missing, malformed, expired, or invalid
- `403 Forbidden`: current role is not it_admin

## GET /api/v1/guardrails/rate-status

Purpose:
Returns the current rate limit status for one employee within the current session company. Useful for debugging or building usage indicators in the UI.

Auth:
Bearer token required.

Role requirement:
- `it_admin` or `hr_admin`

Query parameters:

| Parameter | Type | Description |
|---|---|---|
| `employee_id` | uuid | Required. The employee to check. |

Expected success response:

```json
{
  "employee_id": "20000000-0000-0000-0000-000000000004",
  "company_id": "00000000-0000-0000-0000-000000000001",
  "limits": {
    "messages_per_hour": {
      "limit": 30,
      "current": 12,
      "remaining": 18,
      "resets_at": "2026-04-03T11:00:00Z"
    },
    "conversations_per_day": {
      "limit": 10,
      "current": 2,
      "remaining": 8,
      "resets_at": "2026-04-04T00:00:00Z"
    },
    "file_uploads_per_hour": {
      "limit": 5,
      "current": 0,
      "remaining": 5,
      "resets_at": "2026-04-03T11:00:00Z"
    }
  }
}
```

Expected errors:
- `401 Unauthorized`: token is missing, malformed, expired, or invalid
- `403 Forbidden`: current role is not it_admin or hr_admin
- `404 Not Found`: employee_id does not exist in this company
