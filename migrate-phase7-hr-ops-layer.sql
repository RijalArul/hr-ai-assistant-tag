-- Phase 7: HR Operations Layer (Session G)
-- Run via: python scripts/migrate.py --file migrate-phase7-hr-ops-layer.sql

ALTER TABLE actions
    ADD COLUMN IF NOT EXISTS suggested_pic VARCHAR(100),
    ADD COLUMN IF NOT EXISTS suggested_next_action VARCHAR(500),
    ADD COLUMN IF NOT EXISTS sla_hours INTEGER,
    ADD COLUMN IF NOT EXISTS escalation_rule VARCHAR(500);

ALTER TABLE rule_actions
    ADD COLUMN IF NOT EXISTS suggested_pic_template VARCHAR(100),
    ADD COLUMN IF NOT EXISTS suggested_next_action_template VARCHAR(500),
    ADD COLUMN IF NOT EXISTS sla_hours INTEGER,
    ADD COLUMN IF NOT EXISTS escalation_rule_template VARCHAR(500);
