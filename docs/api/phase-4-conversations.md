# HR.ai Phase 4 Conversations API Reference

Current Phase 4 endpoints cover the public conversation surface:
- conversation creation
- conversation detail lookup
- message posting that invokes the Phase 3 orchestrator
- linked action lookup per conversation
- conversation metadata/status updates

## Runtime Docs

- Interactive Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
- Local API base URL: `http://localhost:8000/api/v1`
- Production API base URL: `https://api.hr-ai.io/api/v1`
- Postman module collection: `docs/postman/modules/conversations.postman_collection.json`
- Suggested environment: `docs/postman/hr-ai-local.postman_environment.json`

## Auth and Scope Notes

All conversation endpoints require a bearer token.

Current role boundaries:
- `employee`: can create conversations, post messages to their own conversations, read their own conversations, and read actions linked to their own conversations
- `hr_admin`: can read and patch conversations in the same company scope, but cannot create or post employee chat messages

Trust boundary note:
- personal HR retrieval still depends on trusted `employee_id` and `company_id` from the authenticated session
- the `POST /messages` route delegates downstream routing to the Phase 3 orchestrator

## POST /api/v1/conversations

Purpose:
Creates one conversation in the current employee scope.

Auth:
Bearer token required.

Role requirement:
- `employee`

Example request:

```json
{
  "title": "Payroll self-service chat",
  "metadata": {
    "source": "api"
  }
}
```

Expected success response:
- `201 Created`

## GET /api/v1/conversations/{id}

Purpose:
Returns one conversation and its stored messages.

Auth:
Bearer token required.

Role requirement:
- `employee`
- `hr_admin`

Expected errors:
- `401 Unauthorized`: token is missing, malformed, expired, or invalid
- `403 Forbidden`: current role is not allowed to read conversations
- `404 Not Found`: conversation does not exist in the current scope

## PATCH /api/v1/conversations/{id}

Purpose:
Updates one conversation title, status, or metadata.

Auth:
Bearer token required.

Role requirement:
- `employee`
- `hr_admin`

Expected errors:
- `401 Unauthorized`: token is missing, malformed, expired, or invalid
- `403 Forbidden`: current role is not allowed to update conversations
- `404 Not Found`: conversation does not exist in the current scope

## POST /api/v1/conversations/{id}/messages

Purpose:
Stores one user message, invokes the Phase 3 orchestrator, stores the assistant response, and returns the orchestration payload.

Auth:
Bearer token required.

Role requirement:
- `employee`

Example request:

```json
{
  "message": "Berapa sisa cuti saya tahun ini dan apa aturan carry over?",
  "attachments": []
}
```

Expected success response:
- `200 OK`

Important response fields:
- `conversation`
- `user_message`
- `assistant_message`
- `orchestration`
- `triggered_actions`
- `orchestration.context.query_policy`
- `orchestration.context.retrieval_assessment`
- `orchestration.context.conversation_grounding`
- `orchestration.context.fallback_ladder`

Testing note:
- this route is the main Phase 4 surface for end-to-end testing of Phase 3 intent, sensitivity, file handling, and routing behavior
- for `payroll_document_request`, Phase 4 now also checks enabled Phase 2 rules and can create linked `document_generation` actions automatically
- document actions are now gated by explicit execution intent, so exploratory questions about payslips should not auto-create actions
- exploratory phrasings such as `bagaimana download payslip saya` or `apakah payslip bisa di-email` are intentionally treated as non-executable until the user asks explicitly
- low-risk payslip requests are auto-executed internally, so the returned `triggered_actions` entry can already contain a generated PDF reference inside `execution_result.document`
- if the requested payroll period is unavailable, the conversation should still return `200 OK`; the action can remain pending with an explanatory note instead of breaking the whole exchange
- short referential follow-ups such as "yang tadi" can now be grounded using recent conversation history before routing
- short standalone questions such as `berapa sisa cuti saya?` stay ungrounded even inside an existing conversation because they already contain enough explicit intent on their own
- policy lookups now expose freshness-aware and sufficiency-aware metadata through the orchestration context
- when S3-compatible storage is configured, `execution_result.document` stores object metadata and a signed `download_url`; otherwise it falls back to inline base64 content

Expected errors:
- `401 Unauthorized`: token is missing, malformed, expired, or invalid
- `403 Forbidden`: current role is not allowed to write conversations
- `404 Not Found`: conversation does not exist in the current scope
- `409 Conflict`: conversation is closed and can no longer accept new messages

## GET /api/v1/conversations/{id}/actions

Purpose:
Lists actions whose `conversation_id` matches the requested conversation.

Auth:
Bearer token required.

Role requirement:
- `employee`
- `hr_admin`

Expected errors:
- `401 Unauthorized`: token is missing, malformed, expired, or invalid
- `403 Forbidden`: current role is not allowed to read conversations
- `404 Not Found`: conversation does not exist in the current scope
