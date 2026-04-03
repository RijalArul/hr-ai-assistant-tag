# HR.ai Phase 2 API Reference

Current Phase 2 endpoints cover the action engine surface:
- action review and execution
- rule configuration
- webhook registration

## Runtime Docs

- Interactive Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
- Local API base URL: `http://localhost:8000/api/v1`
- Production API base URL: `https://api.hr-ai.io/api/v1`

## Auth and Role Notes

All Phase 2 endpoints require a bearer token.

Current role boundaries:
- `employee`: can list and read only their own actions
- `hr_admin`: can review actions, update actions, execute actions, read rules, and toggle `rules.is_enabled`
- `it_admin`: can manage full rule configuration and webhook registrations

Sensitive action safeguard:
- if `sensitivity != low`, the action delivery path is normalized to `manual_review` only

Delivery queue behavior:
- action execution now creates delivery queue records for each requested channel
- webhook delivery uses registered company webhooks that subscribe to `action.delivery_requested`

## GET /api/v1/actions

Purpose:
Lists actions visible to the current session.

Auth:
Bearer token required.

Scope behavior:
- employees only see their own actions
- `hr_admin` can review actions across the same company

Expected success response:

```json
{
  "items": [
    {
      "id": "50000000-0000-0000-0000-000000000001",
      "company_id": "00000000-0000-0000-0000-000000000001",
      "employee_id": "20000000-0000-0000-0000-000000000004",
      "conversation_id": "40000000-0000-0000-0000-000000000001",
      "type": "document_generation",
      "title": "Generate salary slip for March 2026",
      "summary": "Prepare a payroll document and deliver it to the employee.",
      "status": "pending",
      "priority": "medium",
      "sensitivity": "low",
      "delivery_channels": ["email", "in_app"],
      "payload": {
        "type": "document_generation",
        "document_type": "salary_slip",
        "template_key": "payroll_salary_slip_v1",
        "parameters": {
          "month": 3,
          "year": 2026
        }
      },
      "execution_result": null,
      "metadata": {},
      "last_executed_at": null,
      "created_at": "2026-04-03T10:15:00Z",
      "updated_at": "2026-04-03T10:15:00Z"
    }
  ],
  "total": 1
}
```

Expected errors:
- `401 Unauthorized`: token is missing, malformed, expired, or invalid
- `403 Forbidden`: current role is not allowed to read actions

## GET /api/v1/actions/{id}

Purpose:
Returns one action inside the current session scope.

Auth:
Bearer token required.

Expected errors:
- `401 Unauthorized`: token is missing, malformed, expired, or invalid
- `403 Forbidden`: current role is not allowed to read actions
- `404 Not Found`: action does not exist in the current company/session scope

## PATCH /api/v1/actions/{id}

Purpose:
Updates action metadata or status.

Auth:
Bearer token required.

Role requirement:
- `hr_admin`

Example request:

```json
{
  "status": "ready",
  "priority": "high",
  "delivery_channels": ["manual_review"]
}
```

Expected errors:
- `401 Unauthorized`: token is missing, malformed, expired, or invalid
- `403 Forbidden`: current role is not allowed to update actions
- `409 Conflict`: action is already terminal and cannot be updated manually
- `404 Not Found`: action does not exist in the current company scope

## POST /api/v1/actions/{id}/execute

Purpose:
Executes an action and stores execution metadata.

Auth:
Bearer token required.

Role requirement:
- `hr_admin`

Example request:

```json
{
  "delivery_channels": ["manual_review"],
  "trigger_delivery": true,
  "executor_note": "Escalated for HR review before outbound delivery."
}
```

Expected success response:

```json
{
  "action": {
    "id": "50000000-0000-0000-0000-000000000001",
    "company_id": "00000000-0000-0000-0000-000000000001",
    "employee_id": "20000000-0000-0000-0000-000000000004",
    "conversation_id": "40000000-0000-0000-0000-000000000001",
    "type": "document_generation",
    "title": "Generate salary slip for March 2026",
    "summary": "Prepare a payroll document and deliver it to the employee.",
    "status": "completed",
    "priority": "medium",
    "sensitivity": "high",
    "delivery_channels": ["manual_review"],
    "payload": {
      "type": "document_generation",
      "document_type": "salary_slip",
      "template_key": "payroll_salary_slip_v1",
      "parameters": {
        "month": 3,
        "year": 2026
      }
    },
    "execution_result": {
      "executed_at": "2026-04-03T10:20:00Z",
      "delivery_channels": ["manual_review"],
      "delivery_requested": true,
      "executor_note": "Escalated for HR review before outbound delivery.",
      "delivery_mode": "manual_review_only"
    },
    "metadata": {},
    "last_executed_at": "2026-04-03T10:20:00Z",
    "created_at": "2026-04-03T10:15:00Z",
    "updated_at": "2026-04-03T10:20:00Z"
  },
  "delivery_channels": ["manual_review"],
  "delivery_requested": true,
  "execution_log": {
    "id": "51000000-0000-0000-0000-000000000001",
    "action_id": "50000000-0000-0000-0000-000000000001",
    "event_name": "action.executed",
    "status": "completed",
    "message": "Action executed.",
    "metadata": {
      "delivery_mode": "manual_review_only"
    },
    "created_at": "2026-04-03T10:20:00Z"
  },
  "delivery_requests": [
    {
      "id": "52000000-0000-0000-0000-000000000001",
      "action_id": "50000000-0000-0000-0000-000000000001",
      "channel": "manual_review",
      "delivery_status": "queued",
      "target_reference": "hr_admin_review_queue",
      "payload": {
        "action_id": "50000000-0000-0000-0000-000000000001",
        "action_type": "document_generation",
        "status": "completed",
        "title": "Generate salary slip for March 2026"
      },
      "created_at": "2026-04-03T10:20:00Z"
    }
  ],
  "webhook_deliveries_queued": 0
}
```

Expected errors:
- `401 Unauthorized`: token is missing, malformed, expired, or invalid
- `403 Forbidden`: current role is not allowed to execute actions
- `409 Conflict`: action is already completed or cancelled
- `404 Not Found`: action does not exist in the current company scope

## GET /api/v1/actions/{id}/result

Purpose:
Returns the latest stored execution result for one action.

Auth:
Bearer token required.

Expected success response:

```json
{
  "action_id": "50000000-0000-0000-0000-000000000001",
  "status": "completed",
  "execution_result": {
    "executed_at": "2026-04-03T10:20:00Z",
    "delivery_channels": ["manual_review"],
    "delivery_requested": true,
    "executor_note": "Escalated for HR review before outbound delivery.",
    "delivery_mode": "manual_review_only"
  },
  "last_executed_at": "2026-04-03T10:20:00Z"
}
```

Expected errors:
- `401 Unauthorized`: token is missing, malformed, expired, or invalid
- `403 Forbidden`: current role is not allowed to read actions
- `404 Not Found`: action does not exist in the current company/session scope

## GET /api/v1/rules

Purpose:
Lists action-generation rules for the current company.

Auth:
Bearer token required.

Role requirement:
- `hr_admin` or `it_admin`

## GET /api/v1/rules/{id}

Purpose:
Returns one rule plus its mapped action templates.

Auth:
Bearer token required.

Role requirement:
- `hr_admin` or `it_admin`

## POST /api/v1/rules

Purpose:
Creates one rule and its action template mappings.

Auth:
Bearer token required.

Role requirement:
- `it_admin`

Example request:

```json
{
  "name": "Payroll document follow-up",
  "description": "Generate a salary slip when the payroll request intent is resolved.",
  "trigger": "conversation_resolved",
  "intent_key": "payroll_document_request",
  "sensitivity_threshold": "medium",
  "is_enabled": true,
  "actions": [
    {
      "action_type": "document_generation",
      "title_template": "Generate salary slip",
      "summary_template": "Prepare payroll document for delivery.",
      "priority": "medium",
      "delivery_channels": ["email", "in_app"],
      "payload_template": {
        "document_type": "salary_slip",
        "template_key": "payroll_salary_slip_v1"
      }
    }
  ]
}
```

## PATCH /api/v1/rules/{id}

Purpose:
Updates one rule.

Role behavior:
- `hr_admin` can only toggle `is_enabled`
- `it_admin` can change the full rule configuration

Example request for `hr_admin`:

```json
{
  "is_enabled": false
}
```

## DELETE /api/v1/rules/{id}

Purpose:
Deletes one rule and its mapped action templates.

Auth:
Bearer token required.

Role requirement:
- `it_admin`

## GET /api/v1/webhooks

Purpose:
Lists webhook registrations for the current company.

Auth:
Bearer token required.

Role requirement:
- `it_admin`

## GET /api/v1/webhooks/{id}

Purpose:
Returns one webhook registration.

Auth:
Bearer token required.

Role requirement:
- `it_admin`

## POST /api/v1/webhooks

Purpose:
Registers one outbound webhook endpoint and stores the signing secret.

Auth:
Bearer token required.

Role requirement:
- `it_admin`

Example request:

```json
{
  "name": "Primary HRIS webhook",
  "target_url": "https://example.com/webhooks/hr-ai",
  "subscribed_events": [
    "action.created",
    "action.delivery_requested"
  ],
  "secret": "super-secret-signing-key",
  "is_active": true
}
```

Expected success response:

```json
{
  "id": "60000000-0000-0000-0000-000000000001",
  "company_id": "00000000-0000-0000-0000-000000000001",
  "name": "Primary HRIS webhook",
  "target_url": "https://example.com/webhooks/hr-ai",
  "subscribed_events": [
    "action.created",
    "action.executed"
  ],
  "secret_preview": "supe...-key",
  "is_active": true,
  "created_at": "2026-04-03T10:30:00Z",
  "updated_at": "2026-04-03T10:30:00Z"
}
```

## PATCH /api/v1/webhooks/{id}

Purpose:
Updates a webhook registration and optional secret rotation.

Auth:
Bearer token required.

Role requirement:
- `it_admin`

## DELETE /api/v1/webhooks/{id}

Purpose:
Deletes one webhook registration.

Auth:
Bearer token required.

Role requirement:
- `it_admin`
