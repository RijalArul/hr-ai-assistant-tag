# HR.ai Phase 1 API Reference

Current Phase 1 endpoints cover trust-boundary foundations:
- health check
- employee email login
- current authenticated session lookup

## Runtime Docs

- Interactive Swagger UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`
- Local API base URL: `http://localhost:8000/api/v1`
- Production API base URL: `https://api.hr-ai.io/api/v1`

`/openapi.json` can be imported directly into Postman when the API is running.

## GET /api/v1/health

Purpose:
Checks API dependency readiness for Phase 1.

Auth:
No authentication required.

Request body:
None.

Expected success response:

```json
{
  "status": "ok",
  "database": "ok",
  "redis": "ok"
}
```

Possible degraded response:

```json
{
  "status": "degraded",
  "database": "ok",
  "redis": "error: Redis client is not initialized. Call init_redis() first."
}
```

Status behavior:
- `200 OK`: endpoint is reachable. Read the `status` field to determine whether dependencies are healthy or degraded.

Expected errors:
- No dedicated error contract at route level right now. Dependency failures are reported inside the response body as `status = degraded`.

## POST /api/v1/auth/login

Purpose:
Creates a simple Phase 1 employee session using email only.

Auth:
No authentication required.

Request body:

```json
{
  "email": "fakhrul.rijal@majubersama.id"
}
```

Expected success response:

```json
{
  "access_token": "<jwt-access-token>",
  "token_type": "bearer",
  "session": {
    "employee_id": "20000000-0000-0000-0000-000000000004",
    "company_id": "00000000-0000-0000-0000-000000000001",
    "email": "fakhrul.rijal@majubersama.id",
    "role": "employee"
  }
}
```

Status behavior:
- `200 OK`: email found and JWT session created.
- `401 Unauthorized`: email not found.
- `409 Conflict`: same email appears in more than one company, so the API refuses to create an ambiguous session.
- `422 Unprocessable Entity`: request body is invalid, usually because `email` is missing or malformed.

Expected error responses:

`401 Unauthorized`

```json
{
  "detail": "Invalid email."
}
```

`409 Conflict`

```json
{
  "detail": "Email matches multiple companies. Phase 1 login expects a globally unique company email."
}
```

`422 Unprocessable Entity`

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "email"],
      "msg": "Value error, email must be a valid email address",
      "input": "not-an-email"
    }
  ]
}
```

Trust-boundary note:
After login, downstream routes must use the returned session context as the trusted source for `employee_id` and `company_id`.

## GET /api/v1/auth/me

Purpose:
Returns the current trusted session context from the bearer token.

Auth:
Bearer token required.

Headers:

```text
Authorization: Bearer <jwt-access-token>
```

Expected success response:

```json
{
  "employee_id": "20000000-0000-0000-0000-000000000004",
  "company_id": "00000000-0000-0000-0000-000000000001",
  "email": "fakhrul.rijal@majubersama.id",
  "role": "employee"
}
```

Status behavior:
- `200 OK`: bearer token is valid.
- `401 Unauthorized`: token is missing, malformed, expired, or invalid.

Expected error response:

```json
{
  "detail": "Could not validate credentials."
}
```
