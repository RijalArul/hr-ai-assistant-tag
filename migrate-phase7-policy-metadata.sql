-- Phase 7: Policy metadata for company rules
-- Run via: python scripts/migrate.py --file migrate-phase7-policy-metadata.sql

ALTER TABLE company_rules
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
