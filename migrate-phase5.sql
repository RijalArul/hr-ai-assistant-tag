-- Phase 5: Guardrail Layer — new tables
-- Run via: python scripts/migrate.py --file migrate-phase5.sql
-- Or append to migrate-schema.sql and re-run

-- ─── Guardrail Config per company ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS guardrail_configs (
    company_id  UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
    config_json JSONB NOT NULL DEFAULT '{}',
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Guardrail Audit Logs ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS guardrail_audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id      UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    employee_id     UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    event_type      TEXT NOT NULL,
    trigger         TEXT NOT NULL,
    action_taken    TEXT NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_guardrail_audit_company_time
    ON guardrail_audit_logs(company_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_guardrail_audit_employee
    ON guardrail_audit_logs(employee_id);

CREATE INDEX IF NOT EXISTS idx_guardrail_audit_event_type
    ON guardrail_audit_logs(event_type);
