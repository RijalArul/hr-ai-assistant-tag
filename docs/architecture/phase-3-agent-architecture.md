# HR.ai Phase 3 Agent Architecture

Phase 3 in this repository is implemented as an internal orchestration layer on top of the existing Phase 1 and Phase 2 foundations.

Product alignment note:
- Phase 3 currently powers the **Employee Support Layer** and **Reasoning Layer**
- the **HR Operations Layer** stays owned by the Phase 2 action engine plus the Phase 4 conversation/action surface
- see `docs/architecture/phase-7-product-capability-blueprint-id.md` for the concise capability and boundary map

Bahasa Indonesia workflow guide:
- `docs/architecture/phase-1-workflow-id.md`
- `docs/architecture/phase-2-workflow-id.md`
- `docs/architecture/phase-3-workflow-id.md`
- `docs/architecture/phase-3-semantic-routing-id.md`

Current scope:
- `orchestrator` accepts trusted session context plus one user message
- `hr-data-agent` reads structured employee data using `session.employee_id`
- `company-agent` reads company rules and company structure using `session.company_id`
- `file-agent` parses local attachments before downstream routing when attachments are supplied
- the response contract now also distinguishes `request_category`, `response_mode`, and `recommended_next_steps`

Semantic routing status:
- Stage 1 is already active for semantic intent retrieval and semantic fallback
- Stage 2 MVP is already active for `agent_capabilities` and capability-aware agent selection
- Current Stage 2 scope still stays limited to `hr-data-agent`, `company-agent`, and `file-agent`
- See `docs/architecture/phase-3-semantic-routing-id.md` for the detailed plan

## Why Phase 3 Sits Here

The current repository already has:
- Phase 1 trust boundaries for authenticated session context
- Phase 2 action engine contracts and persistence

Phase 3 now fills the AI routing layer between those two foundations and any later `conversations` API.

This means:
- no public conversation endpoint is required yet
- the orchestration flow can already be exercised safely at service level
- future Phase 4 routes can call the same orchestrator instead of re-implementing routing logic

## Internal Flow

Current execution order:

```text
trusted session
  -> optional file-agent
  -> intent classification
  -> sensitivity assessment
  -> route selection
  -> hr-data-agent and/or company-agent
  -> request category + response mode resolution
  -> final synthesized answer
```

Routing rules:
- personal HR data -> `hr-data-agent`
- company policy / structure -> `company-agent`
- both -> `mixed`
- sensitive topic -> `sensitive_redirect`
- unclear / out of domain -> `out_of_scope`

## Current Response Contract

The current orchestrator response is not only about route selection. It also carries:
- `request_category` so callers can distinguish informational, guidance, policy reasoning, workflow, sensitive, and decision-support conversations
- `response_mode` so the answer shape can be tuned as `informational`, `guidance`, `policy_reasoning`, `workflow_intake`, `sensitive_guarded`, or `hr_ops_summary`
- `recommended_next_steps` so employee-facing channels or future dashboards can render follow-up hints consistently

## Trust Boundary

Personal HR retrieval remains bound to trusted session context:
- `employee_id` comes from JWT-backed session context
- `company_id` comes from JWT-backed session context
- the orchestrator does not accept model-selected identifiers for employee data access

## Current Fallback Strategy

The repository now includes a deterministic local fallback flow:
- intent classification uses keyword heuristics
- sensitivity detection uses keyword heuristics
- PDF extraction works locally through `pypdf`
- image attachments currently expose metadata locally and can be upgraded later with a provider-backed extractor
- company policy retrieval currently uses relational rule lookup and ranking; the schema is already compatible with a later vector-backed retrieval upgrade

This keeps Phase 3 usable now without overcommitting to provider-specific runtime behavior.

Current provider-ready upgrades:
- `orchestrator` will try MiniMax classification first, then fall back to local heuristics if the provider is unavailable
- `file-agent` will try Gemini extraction for PDFs and images first, then fall back to local extraction/metadata
- `company-agent` will try vector search over `company_rule_chunks` when Gemini embeddings are available, then fall back to keyword ranking
- semantic routing will try vector retrieval for `intent_examples` and `agent_capabilities` when Gemini embeddings are synced, then fall back to lexical retrieval
- deterministic HR queries now carry an internal `query_policy` and retrieval sufficiency metadata so semantic routing does not widen exact employee-data lookups carelessly
- HR attendance and payroll retrieval now include temporal fallback behavior for incomplete early-period requests and expose sufficiency as `enough`, `partial`, or `weak`
- short referential follow-ups can now be grounded with recent conversation history before routing
- short standalone queries that already mention a clear HR/company target stay ungrounded, so previous context does not override a fresh explicit lookup
- company policy retrieval now considers freshness/version priority so older policy versions do not outrank newer ones too easily
- orchestrator now exposes a formal `fallback_ladder` in response context for easier audit/debug of classifier, semantic, and retrieval decisions

Remote provider calls are opt-in in local development:
- set `PHASE3_USE_REMOTE_PROVIDERS=true` if you intentionally want MiniMax and Gemini to be called
- otherwise Phase 3 stays on deterministic local fallback paths

To populate vector chunks from `company_rules`, run:

```bash
python scripts/sync_company_rule_chunks.py
```

To populate vector embeddings for semantic routing tables, run:

```bash
python scripts/sync_semantic_routing_embeddings.py
```

## Local Preview Harness

Use the preview script to run the internal orchestrator without adding a public API route:

```bash
python scripts/phase3_preview.py \
  --email fakhrul.rijal@majubersama.id \
  --message "Berapa sisa cuti saya dan apa aturan carry-over?"
```

Optional attachments:

```bash
python scripts/phase3_preview.py \
  --email fakhrul.rijal@majubersama.id \
  --message "Tolong cek lampiran ini" \
  --attachment C:/path/to/document.pdf
```
