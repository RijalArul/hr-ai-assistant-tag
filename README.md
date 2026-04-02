# HR.ai

**Conversational HR support platform with structured follow-up actions.**

HR.ai helps employees get instant HR answers through a chat interface while automatically turning resolved conversations into structured follow-up actions for HR teams. The platform is designed as an open API that can integrate with an existing HRIS through REST APIs and webhooks.

> Core principle: **neutral, factual, and bridge-oriented** — HR.ai is not meant to side with either the employee or the company.

---

## Overview

HR.ai is built for HR support scenarios where employees need fast answers, but organisations still need governance, auditability, and controlled follow-up.

At a high level, HR.ai:
- answers employee HR questions through a conversational interface
- retrieves structured HR data when needed
- classifies intent and sensitivity
- generates follow-up actions for HR teams
- delivers execution results through configurable channels such as email, webhook, in-app notification, or manual review

The product direction supports:
- **Hosted SaaS UI** for ready-to-use chat and admin workflows
- **Headless API** for companies that want to build their own frontend
- **Hybrid embedding** via widget / component

---

## Why HR.ai

Traditional HR support is often fragmented across chat messages, policy documents, HRIS screens, and manual follow-up. HR.ai is designed to close that gap by combining:

- **conversational access** for employees
- **structured action handling** for HR teams
- **API-first integration** for IT teams
- **sensitive-case guardrails** for higher-risk workflows

This makes HR.ai more than a chatbot. It is intended to be an operational layer between employees, HR teams, and HRIS data.

---

## Core Product Model

HR.ai separates responsibilities clearly between two admin roles:

### IT Admin
Responsible for technical setup:
- organisation registration
- API key management
- HRIS connector setup
- webhook registration
- action template configuration
- post-execution delivery rules

### HR Admin
Responsible for operational control:
- enabling and disabling rules
- reviewing action task lists
- handling escalations
- managing day-to-day business logic without engineering involvement

---

## Functional Layers

HR.ai is designed around four functional layers:

1. **Conversation AI**
   - natural-language dialogue
   - intent classification
   - sensitivity detection
   - employee-specific HR data retrieval

2. **Action Engine**
   - converts resolved conversations into structured follow-up actions
   - supports document generation, counseling tasks, follow-up chat, escalation, and custom webhook triggers

3. **API & Integration**
   - open REST API
   - webhook event bus
   - HRIS connectors
   - post-execution delivery engine

4. **UI Layer**
   - employee chat interface
   - HR admin dashboard
   - optional embedded/widget mode

---

## Current Product Direction

The current MVP direction is intentionally pragmatic:

- employee interaction starts from a **chat-based interface**, with the early decision summary centering on a **Discord bot** approach for employee-initiated conversations
- the broader product direction also supports **open API**, **hosted UI**, and **headless integration**
- the system avoids unnecessary platform complexity during MVP while keeping the architecture expandable later

---

## Core Domains

HR.ai works primarily with these domains:

- `employees`
- `personal_infos`
- `time_offs`
- `attendance`
- `payroll`
- `company_structure`
- `company_rules`

### Structured data vs knowledge retrieval
HR.ai does **not** treat all HR data the same way.

- **TAG (Tool-Augmented Generation)** is used for structured employee/company data such as payroll, attendance, leave, and profile records.
- **RAG (Retrieval-Augmented Generation)** is used only for `company_rules` content, where semantic search over longer policy text is useful.

Current retrieval philosophy:
- **90% TAG (Tools Augmented Generation)** 
- **10% RAG (Retrieval Augmented Generation)**

This keeps personal HR data precise, queryable, and safer than forcing everything through a generic RAG pipeline.

---

## Agent Architecture

HR.ai uses a focused 4-agent design with one orchestrator:

### 1. Orchestrator
- primary entry point for all user messages
- analyzes intent
- routes requests
- synthesizes final response

### 2. hr-data-agent
- handles employee-specific HR data
- used for personal payroll, attendance, leave, profile, and related HR topics

### 3. company-agent
- handles company structure and company rule retrieval
- used for organisational and policy-level questions

### 4. file-agent
- handles file extraction from PDFs and images
- runs first when file attachments are present

### Routing strategy
- **HR data only** -> `hr-data-agent`
- **Company data only** -> `company-agent`
- **Both needed** -> parallel execution where safe
- **File attached** -> `file-agent` first, then downstream agents
- **Sensitive topic** -> hard redirect to HR contact / protected path
- **Out of context** -> soft empathetic reject

---

## Action Engine

A conversation in HR.ai can generate one or more structured actions.

Supported action types include:
- `document_generation`
- `counseling_task`
- `followup_chat`
- `escalation`
- `custom_webhook`

Rules determine which actions are created for which intents. The intended operating model is:
- **IT Admin** configures rule templates
- **HR Admin** toggles the active rules

---

## Security and Trust Boundaries

HR.ai is designed with explicit trust and privacy controls.

### Authentication
- **API Key** for server-to-server integration
- **Bearer Token (JWT)** for employee and HR user sessions

For the current Phase 1 MVP, employee login is intentionally simple:
- existing employee email -> JWT bearer session
- `employee_id` and `company_id` are injected from the authenticated session, not user prompts

### OAuth scopes
Examples include:
- `conversation:read`
- `conversation:write`
- `action:read`
- `action:write`
- `webhook:manage`
- `rule:manage`
- `org:admin`

### Data security principles
- all API traffic over HTTPS
- sensitive case content encrypted at rest
- webhook payloads signed with HMAC-SHA256
- PII masked by default in webhook payloads
- sensitive cases default to **manual review** before delivery

### Critical identity rule
`employee_id` and `company_id` must come from trusted session context, **never from the LLM**.

This is one of the most important safety boundaries in the system.

---

## Caching Strategy

HR.ai uses a two-tier cache strategy:

### In-memory LRU cache
Used for static or semi-static data where local access speed matters.
Examples:
- employee profile
- personal info
- company rules

### Redis cache
Used for dynamic or TTL-based data.
Examples:
- payroll
- attendance
- time off
- chat history

Current cache philosophy:
- static data and dynamic data are treated differently
- chat history follows shorter session-style expiration
- static data does not need to expire with every session

---

## Tech Stack

### Backend
- **FastAPI**
- **LangChain Python (LCEL)**
- **discord.py** for the early employee chat interface path

### Models
- **MiniMax M2.7** as primary conversational/orchestration model
- **Gemini Flash 2.5** for file extraction
- **multilingual-e5-large** for policy embeddings

### Data
- **Supabase PostgreSQL**
- **pgvector** for vector search on policy content

### Cache
- **LRU in-memory cache**
- **Upstash Redis**

### Frontend / Delivery
- **Next.js**
- **Netlify**

### Deployment
- **Railway** for Python services
- **Netlify** for frontend
- **GitHub Actions** for CI/CD
- **Makefile** as the unified entry point for a mixed Python + JS monorepo

---

## API Overview

Base URL:

```text
https://api.hr-ai.io/api/v1
```

### Auth
- `POST /auth/login`
- `GET /auth/me`

### Conversations
- `POST /conversations`
- `GET /conversations/{id}`
- `POST /conversations/{id}/messages`
- `GET /conversations/{id}/actions`
- `PATCH /conversations/{id}`

### Actions
- `GET /actions`
- `GET /actions/{id}`
- `PATCH /actions/{id}`
- `POST /actions/{id}/execute`
- `GET /actions/{id}/result`

### Rules
- `GET /rules`
- `GET /rules/{id}`
- `PATCH /rules/{id}`
- `POST /rules`
- `DELETE /rules/{id}`

### Webhooks
- `POST /webhooks`
- `GET /webhooks`
- `GET /webhooks/{id}`
- `PATCH /webhooks/{id}`
- `DELETE /webhooks/{id}`

Current docs for implemented endpoints:
- Interactive docs: `/docs`
- OpenAPI JSON: `/openapi.json`
- Markdown reference: `docs/api/phase-1-auth-health.md`
- Postman combined collection: `docs/postman/hr-ai-phase-1.postman_collection.json`
- Postman module collection - auth: `docs/postman/modules/auth.postman_collection.json`
- Postman module collection - health: `docs/postman/modules/health.postman_collection.json`
- Postman environment: `docs/postman/hr-ai-local.postman_environment.json`

---

## Delivery Model

After an action is executed, HR.ai can deliver the result through one or more channels:
- `email`
- `webhook`
- `in_app`
- `manual_review`

For sensitive cases, the default behavior is **manual review only**, even if other delivery methods are configured.

Webhook receivers should:
- verify `X-HRai-Signature`
- respond quickly
- process asynchronously when needed

---

## Quick Integration Flow

A minimal integration flow is expected to look like this:

1. Register the organisation and obtain API credentials
2. Connect the company HRIS
3. Register webhook endpoints
4. Configure action rules
5. Deploy hosted UI or use headless API

At runtime, the intended flow is roughly:

```text
Employee -> Chat Interface -> Conversation AI -> Tool / Connector Access
        -> Intent + Sensitivity Classification -> Action Engine
        -> Delivery Layer / HR Admin Review / External Webhook
```

---

## Local Development Status

This repository is currently aligned to a **build-stage / MVP-stage architecture**, not a fully production-proven platform yet.

Some design decisions are locked, but a few assumptions still need validation, especially around:
- Indonesian conversation quality for the primary LLM
- tool-calling compatibility through the selected wrapper/orchestration path
- embedding API limits over time
- free-tier database sizing for realistic company data

---

## Deliberate MVP Constraints

To keep the build focused, HR.ai explicitly avoids several things for now:

- no full-RAG approach for all data
- no MCP layer for MVP
- no LangGraph unless orchestration becomes much more complex
- no staging-heavy setup for a small MVP
- no Turborepo/Nx requirement for the mixed Python + JS monorepo
- no broad prefetch of all employee data at session start

The current direction favors:
- simpler build velocity
- lower cost
- lower operational overhead
- stronger control over trust boundaries

---

## Non-Goals for the Current MVP

The current MVP is **not** trying to become:
- a generic enterprise chatbot platform
- a fully autonomous HR decision-maker
- a policy engine that replaces HR review on sensitive cases
- a framework-heavy orchestration playground

HR.ai is meant to be useful, safe, and operationally realistic first.

---

## Planned / Post-MVP Areas

Likely next areas after the initial build:
- final FastAPI route design
- HR Admin dashboard refinement
- demo and seed data strategy
- notification system for pending actions
- optional MCP support for admin-side natural language query use cases
- broader RAG coverage if the knowledge base expands

---

## Suggested Repository Direction

If this repository evolves as a monorepo, a practical layout would be:

```text
apps/
  api/          # FastAPI + LangChain
  bot/          # discord.py
  web/          # Next.js
packages/
  shared/       # shared contracts, schemas, utilities
infra/
  deployment/   # Railway / Netlify / CI config
```

This section is a suggested direction, not a locked contract.

---

## Principles for Contributors

When contributing to HR.ai:
- keep implementations factual and traceable
- preserve trust boundaries between session identity and model reasoning
- do not move structured HR data into a vague RAG flow
- keep sensitive-case handling conservative
- prefer explicit, human-readable code over clever abstractions
- treat HR.ai as an operational system, not just a chat app

---

## TODO List (Implementation Tasks)

### Phase 1: Setup & Trust Boundaries (Priority)
- [ ] **Monorepo Init:** Scaffold `apps/api` (FastAPI), `apps/bot` (discord.py), and `packages/shared`.
- [ ] **Database Setup:** Initialize Supabase PostgreSQL and configure `pgvector` extension.
- [ ] **Auth & Security:** Implement JWT/Bearer token middleware in FastAPI.
- [ ] **Trust Boundary Enforcement:** Ensure `employee_id` and `company_id` are strictly injected from the authenticated session context, not the LLM.
- [ ] **Caching Layer:** Setup LRU in-memory cache (for static data like rules) and Upstash Redis (for dynamic data like sessions/payroll).

### Phase 2: Action Engine
- [ ] **Schemas:** Define Pydantic models for actions (`document_generation`, `counseling_task`, `followup_chat`, `escalation`, `custom_webhook`).
- [ ] **Database Schema:** Create tables for actions, logs, and rules mapping.
- [ ] **Delivery Logic:** Implement delivery routing (email, webhook, in_app, manual_review).
- [ ] **Sensitive Guardrail:** Enforce `manual_review` default for any action classified as sensitive.

### Phase 3: Agent Architecture (AI Layer)
- [ ] **Orchestrator:** Implement intent classification and sensitivity detection (using MiniMax M2.7).
- [ ] **hr-data-agent (TAG):** Build LangChain tools to retrieve structured data (payroll, attendance, time_offs) safely using the session's `employee_id`.
- [ ] **company-agent (RAG):** Implement vector search using `multilingual-e5-large` embeddings for querying `company_rules`.
- [ ] **file-agent:** Integrate Gemini Flash 2.5 for image/PDF extraction at the start of the conversation flow.

### Phase 4: API & Integration (FastAPI)
- [ ] **Conversations API:** Implement `/api/v1/conversations` endpoints (POST, GET, PATCH).
- [ ] **Actions API:** Implement `/api/v1/actions` endpoints.
- [ ] **Rules API:** Implement `/api/v1/rules` endpoints for HR Admin configurations.
- [ ] **Webhooks API:** Implement `/api/v1/webhooks` endpoints with `X-HRai-Signature` HMAC-SHA256 generation/validation.

### Phase 5: MVP UI & Delivery
- [ ] **Discord Bot:** Setup `discord.py` bot as the primary employee chat interface.
- [ ] **Bot to API Connection:** Wire the Discord bot to send messages to the `/api/v1/conversations` endpoint.
- [ ] **Testing:** End-to-end test of the chat -> intent -> agent -> action -> delivery flow.

### Phase 6: Post-MVP / Backlog
- [ ] **HR Admin Dashboard:** Build Next.js UI for reviewing actions and managing rules.
- [ ] **Seed Data:** Create dummy HRIS data for testing/demo purposes.
- [ ] **Notification System:** Implement scheduled alerts for pending manual reviews.

---

## Status

**Project phase:** MVP / Hackathon architecture defined, implementation in progress.

If you are building inside this repository, start from the architecture, trust boundaries, and action workflow first. Those are the real backbone of HR.ai.
