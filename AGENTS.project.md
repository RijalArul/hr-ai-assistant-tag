# AGENTS.project.md
# HR.ai Project-Level Instructions

## Project Snapshot

Project: HR.ai  
Type: Conversational HR support platform with open API  
Runtime shape: Python backend plus Discord bot, with web/admin UI and integrations  
Current stack direction: FastAPI + LangChain Python + discord.py + Supabase PostgreSQL + pgvector + Upstash Redis + Next.js  
Deployment direction: Railway for Python runtime, Netlify for Next.js  

Core product goal:
Employees ask HR questions through chat. The system retrieves trusted HR data, applies company policy, classifies sensitivity and intent, then generates structured actions or delivery outcomes for HR/admin workflows.

Core principle:
Be neutral, factual, and safe.
Do not behave like an advocate for either side.

---

## Repository Reading Order

Before changing code in this project, read in this order:

1. `README.md`
2. root `AGENTS.md`
3. this file
4. feature-specific docs if present
5. nearest working implementation in the same domain
6. touched files and adjacent layers
7. nearby tests if present

Read only enough to implement safely.
Do not over-explore unrelated modules.

---

## Expected High-Level Boundaries

The project should stay aligned with these product areas:

### 1. Conversation AI
Owns:
- intent classification
- sensitivity detection
- message orchestration
- trusted retrieval/tool routing
- final answer synthesis

### 2. Action Engine
Owns:
- action creation from resolved conversations
- action type selection
- action status lifecycle
- execution triggering
- execution result tracking

### 3. API & Integration
Owns:
- public REST endpoints
- webhook registration and delivery
- connector-facing integration logic
- delivery engine contracts
- auth and admin role boundaries

### 4. UI Layer
Owns:
- employee chat UI or Discord UX boundary
- HR Admin dashboard
- rule toggling surfaces
- action review surfaces

Do not mix product areas casually.

---

## Agent Architecture Rules

Preserve the intended orchestration model unless explicitly changed:

### Orchestrator
Responsibilities:
- receive all user messages
- detect intent/sensitivity/path
- choose downstream agents/tools
- synthesize the final response

### hr-data-agent
Responsibilities:
- employee-specific HR data
- payroll
- attendance
- time off
- personal employee context

### company-agent
Responsibilities:
- company structure
- company rules/policy
- company-side HR information not tied to personal records

### file-agent
Responsibilities:
- attachment extraction
- one-shot parsing of PDFs/images
- produce context for downstream agents

Routing expectations:
- personal HR data only -> `hr-data-agent`
- company policy/structure only -> `company-agent`
- both -> parallel read-safe path
- attachment present -> `file-agent` first, then downstream use
- sensitive topic -> conservative flow / redirect / manual handling as designed
- out-of-scope topic -> soft reject, do not fabricate an HR answer

Do not make attachment parsing or company policy lookup behave like unrestricted generic reasoning.

---

## Retrieval Rules

This project is intentionally hybrid, but not evenly hybrid.

### Tool/TAG path should own:
- employees
- personal_infos
- payroll
- attendance
- time_offs
- company_structure
- other structured relational data

### RAG path should mainly own:
- `company_rules`
- long-form policy text
- future FAQ / knowledge-base style content if added later

Rules:
- do not replace structured retrieval with semantic retrieval just because it is easier
- do not expose raw database semantics directly to model output
- prefer deterministic data access for employee-specific records

---

## Trusted Identity and Data Access Rules

Critical rule:
`employee_id` and `company_id` must come from trusted session or application context, not from model-generated text.

Therefore:
- do not accept free-form model-selected identifiers for personal data queries
- do not let the LLM choose whose payroll or attendance is being queried
- do not infer cross-employee access from conversation wording
- do not trust attachment metadata alone for identity resolution

If a feature touches identity or data ownership, check that trust boundaries remain intact.

---

## Admin Boundary Rules

Keep the role boundary explicit.

### IT Admin owns:
- organisation setup
- connectors
- API keys
- webhook configuration
- action templates
- delivery rule plumbing
- rule creation/config structure

### HR Admin owns:
- enabling/disabling rules
- reviewing action tasks
- manual operational follow-up
- escalation management

Do not let HR Admin code paths perform IT Admin setup actions unless explicitly intended.
Do not collapse both roles into a vague “admin” path without a real product decision.

---

## API Contract Areas To Protect

These areas are contract-sensitive and should be treated carefully:

### Conversations
Expected responsibilities:
- create conversation
- retrieve conversation
- send message
- list generated actions
- update conversation status/metadata

Protect:
- conversation status values
- sensitivity level shape
- message payload shape
- conversation response shape

### Actions
Expected responsibilities:
- list actions
- get action details
- update action status
- execute action
- retrieve result

Protect:
- action type enum
- priority/status values
- execution config shape
- result access path

### Rules
Expected responsibilities:
- create/list/get/update/delete rules
- toggle enabled state
- preserve intent-to-action mapping

### Webhooks
Expected responsibilities:
- registration
- secret handling
- event subscription
- delivery logs
- signed payload delivery

### Delivery
Expected responsibilities:
- email
- webhook
- in_app
- manual_review

Sensitive-case rule:
manual review must remain the safe override when the product requires it.

---

## API Documentation Requirements

When adding or changing API routes, documentation is part of the implementation, not a follow-up task.

Required API documentation work:
- update FastAPI route metadata so `/docs` and `/openapi.json` stay useful
- define or update request models, response models, and explicit error response models where practical
- include route `summary`, `description`, and expected status codes
- include example request and response payloads where practical

Required repository docs:
- add or update markdown API docs under `docs/api/`
- document, at minimum: route path, purpose, auth requirement, request body, success response, expected error responses, and status behavior
- if docs locations change, keep `README.md` pointers aligned

Required Postman docs:
- add or update a module-level collection under `docs/postman/modules/`
- group requests by module, for example `auth`, `health`, `conversations`, `actions`, `rules`, `webhooks`
- for each request, include example request payloads plus saved example responses for success and relevant error cases
- keep shared variables or environments usable for local development
- if a combined collection exists, keep it aligned with the module collections

Rule:
- do not consider an API task complete if the route exists but the docs and Postman examples were not updated with it

---

## Security and Privacy Guardrails

Treat these as repository-level expectations:

- HTTPS-only external communication assumptions
- API key for server-to-server integrations
- JWT/Bearer for employee and HR user sessions
- scope-aware route protection
- HMAC-SHA256 signature verification for webhook requests
- encrypted-at-rest treatment for sensitive case content where applicable
- PII masking defaults where applicable
- request-time HRIS fetch behavior for personal HR data when product expects it

Do not weaken security boundaries for convenience.

If a change affects auth, delivery, webhook, or PII behavior, treat it as a deep-reflection change.

---

## Cache Rules

Expected cache behavior:

- `employee_profile` -> LRU + Redis
- `personal_info` -> LRU + Redis
- `payroll` -> Redis only, period-specific
- `attendance` -> Redis only, period-specific
- `time_off` -> Redis only, yearly/approval-sensitive
- `company_rules` -> LRU + Redis
- `chat_history` -> Redis only, session-oriented

Guardrails:
- do not cache personal data with weak or ambiguous keys
- do not use model-provided identifiers in cache keys
- do not tie static cache invalidation to chat session expiry without need
- do not prefetch everything at session start unless product direction changes

---

## Monorepo / Runtime Expectations

Current direction suggests:
- one Python runtime containing FastAPI + discord.py behaviors where practical
- one Next.js app for hosted/admin UI
- Makefile or similarly simple orchestration instead of heavy monorepo tooling

Therefore:
- keep cross-runtime boundaries explicit
- do not introduce heavy build orchestration unless the repo actually needs it
- prefer simple local commands and explicit entrypoints
- avoid architecture changes that fight the Python + JS mixed-runtime reality

---

## What The Agent Should Avoid In HR.ai

Avoid these project-specific anti-patterns:

- turning HR.ai into a generic chat framework
- pushing structured personal data access into pure RAG
- letting the model select trusted IDs
- bypassing service/orchestration layers for sensitive flows
- silently changing webhook payload contracts
- bypassing manual review safeguards for sensitive cases
- introducing LangGraph for well-defined flows without real need
- adding MCP as default runtime complexity for MVP needs
- prefetching all user data at session start
- adding new abstractions before repeated use proves they are needed
- overbuilding for scale that the current MVP has explicitly rejected

---

## Default Layer Ownership Pattern

Use this as the preferred implementation shape unless the repo already uses a clearer one:

`route or transport -> schema/validation -> orchestrator or service -> repository/connector/tool -> mapper/response`

Guidance:
- transport layer should stay thin
- orchestration and business decisions should stay visible
- repositories/connectors should not contain UI-level response shaping
- mapping should not hide product rules
- sensitive-case overrides should be obvious in code

If the repo has a more specific local pattern, follow the local pattern.

---

## Multi-File Consistency Checklist For HR.ai

Before finalizing non-trivial changes, verify:

- route/handler input shape <-> schema shape
- schema <-> DTO/type parity
- service/orchestrator input-output shape
- service <-> repository/connector contract
- action/rule enums and status values remain aligned
- webhook event name and payload shape remain aligned
- auth/session context assumptions remain aligned
- cache keys and read/write paths remain aligned
- response models still match actual outputs
- API docs, OpenAPI metadata, and Postman examples remain aligned with actual route behavior
- any sensitive-case overrides still fire in the right path

If the change touches conversation, action, rule, webhook, delivery, auth, identity, or cache, do deep reflection.

---

## Ask-First Conditions Specific To HR.ai

Pause and ask if:
- it is unclear whether logic belongs in conversation flow or action engine
- it is unclear whether data should come from TAG or RAG
- a personal-data request could cross employee boundaries
- it is unclear whether a case should be sensitive/manual-review only
- a route contract may change for external integrators
- webhook payload changes would affect downstream systems
- a new abstraction is being considered for orchestration
- a feature seems to require product behavior not yet defined in docs

When asking:
- explain the ambiguity briefly
- give 2-3 options
- recommend the safest product-aligned option

---

## Validation Guidance For HR.ai

Keep validation practical and flow-based.

Preferred validations:
- employee asks payroll question -> correct data path -> correct action/output
- company policy question -> correct company_rules retrieval path
- mixed question -> correct parallel-safe orchestration path if implemented
- attachment present -> file extraction path feeds downstream flow correctly
- sensitive topic -> redirect/manual-review behavior is preserved
- webhook event emitted -> payload signed and shape preserved
- rule disabled -> no action generated
- rule enabled -> action generated as expected
- session-bound request -> no cross-employee leakage

Tests are useful when branching or product rules become non-trivial.
For smaller edits, manual contract verification is acceptable.

---

## Final Project Gate

Before saying the task is done, confirm:

- I read the relevant docs and local code first.
- I preserved HR.ai’s neutral and factual product behavior.
- I kept structured HR data on the correct retrieval path.
- I did not allow model-generated trusted identity values.
- I preserved IT Admin vs HR Admin boundaries.
- I checked affected contracts across files/layers.
- If I changed API routes, I updated OpenAPI metadata, markdown docs, and Postman collections/examples.
- I avoided unnecessary abstraction and MVP inflation.
- I reflected before finalizing.
- The result is readable for a human maintainer.

If any answer is no, the work is not complete.
