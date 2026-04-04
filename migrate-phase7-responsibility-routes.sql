-- Phase 7: Company navigation functional-owner routing
-- Run via: python scripts/migrate.py --file migrate-phase7-responsibility-routes.sql

CREATE TABLE IF NOT EXISTS responsibility_routes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    topic_key TEXT NOT NULL,
    department_id UUID NULL REFERENCES departments(id) ON DELETE SET NULL,
    primary_employee_id UUID NULL REFERENCES employees(id) ON DELETE SET NULL,
    alternate_employee_id UUID NULL REFERENCES employees(id) ON DELETE SET NULL,
    recommended_channel TEXT,
    preparation_checklist JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_responsibility_routes_company_topic UNIQUE (company_id, topic_key),
    CONSTRAINT chk_responsibility_route_contacts_present CHECK (
        primary_employee_id IS NOT NULL
        OR alternate_employee_id IS NOT NULL
        OR department_id IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_responsibility_routes_company_id
    ON responsibility_routes(company_id);

CREATE INDEX IF NOT EXISTS idx_responsibility_routes_topic_key
    ON responsibility_routes(topic_key);

CREATE INDEX IF NOT EXISTS idx_responsibility_routes_active
    ON responsibility_routes(is_active);

DROP TRIGGER IF EXISTS trg_responsibility_routes_set_updated_at ON responsibility_routes;
CREATE TRIGGER trg_responsibility_routes_set_updated_at
BEFORE UPDATE ON responsibility_routes
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
