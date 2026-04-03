-- HR.ai MVP PostgreSQL / Supabase schema
-- Derived from the uploaded project decision summary and simple ERD.
-- Assumptions:
-- 1) MVP keeps one employee = one role.
-- 2) company_structure is implemented as departments + self-reference.
-- 3) company_rules stays relational-first, with optional pgvector chunk table for RAG.

create extension if not exists pgcrypto;
create extension if not exists vector;

-- Optional enums for stronger data consistency
DO $$ BEGIN
    create type employment_status_enum as enum ('active', 'inactive', 'probation', 'resigned', 'terminated', 'contract_end');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    create type employment_type_enum as enum ('permanent', 'contract', 'intern', 'freelance');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    create type leave_record_type_enum as enum ('balance', 'request');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    create type leave_status_enum as enum ('draft', 'pending', 'approved', 'rejected', 'cancelled');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    create type attendance_status_enum as enum ('present', 'absent', 'late', 'wfh', 'leave', 'holiday');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    create type payroll_payment_status_enum as enum ('draft', 'processed', 'paid', 'failed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    create type action_type_enum as enum ('document_generation', 'counseling_task', 'followup_chat', 'escalation', 'custom_webhook');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    create type action_status_enum as enum ('pending', 'ready', 'in_progress', 'completed', 'failed', 'cancelled');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    create type action_priority_enum as enum ('low', 'medium', 'high', 'urgent');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    create type conversation_status_enum as enum ('active', 'resolved', 'escalated', 'closed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    create type conversation_message_role_enum as enum ('user', 'assistant', 'system');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    create type sensitivity_level_enum as enum ('low', 'medium', 'high');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    create type delivery_channel_enum as enum ('email', 'webhook', 'in_app', 'manual_review');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    create type rule_trigger_enum as enum ('conversation_resolved', 'sensitivity_detected', 'action_execution_completed');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    create type webhook_event_enum as enum ('action.created', 'action.updated', 'action.executed', 'action.delivery_requested');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

create table if not exists companies (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    industry text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists departments (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references companies(id) on delete cascade,
    parent_id uuid null references departments(id) on delete set null,
    head_employee_id uuid null,
    name text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_departments_company_name unique (company_id, name)
);

create table if not exists employees (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references companies(id) on delete cascade,
    department_id uuid null references departments(id) on delete set null,
    manager_id uuid null references employees(id) on delete set null,
    name text not null,
    email text not null,
    position text,
    employment_type employment_type_enum,
    employment_status employment_status_enum not null default 'active',
    role text not null,
    discord_user_id text,
    join_date date,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_employees_company_email unique (company_id, email),
    constraint uq_employees_company_discord unique (company_id, discord_user_id),
    constraint chk_employee_email_format check (position('@' in email) > 1),
    constraint chk_employee_manager_not_self check (manager_id is null or manager_id <> id)
);

create table if not exists personal_infos (
    id uuid primary key default gen_random_uuid(),
    employee_id uuid not null unique references employees(id) on delete cascade,
    phone text,
    address text,
    national_id text,
    tax_id text,
    bank_account text,
    emergency_contact text,
    emergency_phone text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists time_offs (
    id uuid primary key default gen_random_uuid(),
    employee_id uuid not null references employees(id) on delete cascade,
    leave_type text not null,
    record_type leave_record_type_enum not null,
    total_days numeric(6,2),
    used_days numeric(6,2),
    remaining_days numeric(6,2),
    start_date date,
    end_date date,
    status leave_status_enum,
    reason text,
    year int not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint chk_time_off_year check (year between 2000 and 2100),
    constraint chk_time_off_date_range check (
        start_date is null
        or end_date is null
        or end_date >= start_date
    ),
    constraint chk_time_off_record_type_balance_fields check (
        (record_type = 'balance' and start_date is null and end_date is null)
        or (record_type = 'request')
    ),
    constraint chk_time_off_days_non_negative check (
        coalesce(total_days, 0) >= 0
        and coalesce(used_days, 0) >= 0
        and coalesce(remaining_days, 0) >= 0
    )
);

create table if not exists attendance (
    id uuid primary key default gen_random_uuid(),
    employee_id uuid not null references employees(id) on delete cascade,
    attendance_date date not null,
    check_in time,
    check_out time,
    status attendance_status_enum not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_attendance_employee_date unique (employee_id, attendance_date),
    constraint chk_attendance_time_order check (
        check_in is null
        or check_out is null
        or check_out >= check_in
    )
);

create table if not exists payroll (
    id uuid primary key default gen_random_uuid(),
    employee_id uuid not null references employees(id) on delete cascade,
    month int not null,
    year int not null,
    basic_salary numeric(14,2) not null default 0,
    allowances numeric(14,2) not null default 0,
    gross_salary numeric(14,2) not null default 0,
    deductions numeric(14,2) not null default 0,
    bpjs_kesehatan numeric(14,2) not null default 0,
    bpjs_ketenagakerjaan numeric(14,2) not null default 0,
    pph21 numeric(14,2) not null default 0,
    net_pay numeric(14,2) not null default 0,
    payment_status payroll_payment_status_enum not null default 'draft',
    payment_date date,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_payroll_employee_period unique (employee_id, year, month),
    constraint chk_payroll_month check (month between 1 and 12),
    constraint chk_payroll_year check (year between 2000 and 2100),
    constraint chk_payroll_non_negative check (
        basic_salary >= 0 and allowances >= 0 and gross_salary >= 0 and deductions >= 0
        and bpjs_kesehatan >= 0 and bpjs_ketenagakerjaan >= 0 and pph21 >= 0 and net_pay >= 0
    )
);

create table if not exists rules (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references companies(id) on delete cascade,
    name text not null,
    description text,
    trigger rule_trigger_enum not null default 'conversation_resolved',
    intent_key text not null,
    sensitivity_threshold sensitivity_level_enum,
    is_enabled boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_rules_company_name unique (company_id, name)
);

create table if not exists rule_actions (
    id uuid primary key default gen_random_uuid(),
    rule_id uuid not null references rules(id) on delete cascade,
    action_type action_type_enum not null,
    title_template text not null,
    summary_template text,
    priority action_priority_enum not null default 'medium',
    delivery_channels delivery_channel_enum[] not null default ARRAY['in_app']::delivery_channel_enum[],
    payload_template jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists conversations (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references companies(id) on delete cascade,
    employee_id uuid not null references employees(id) on delete cascade,
    title text,
    status conversation_status_enum not null default 'active',
    metadata jsonb not null default '{}'::jsonb,
    last_message_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists conversation_messages (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null references conversations(id) on delete cascade,
    company_id uuid not null references companies(id) on delete cascade,
    employee_id uuid not null references employees(id) on delete cascade,
    role conversation_message_role_enum not null,
    content text not null,
    attachments jsonb not null default '[]'::jsonb,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists actions (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references companies(id) on delete cascade,
    employee_id uuid not null references employees(id) on delete cascade,
    conversation_id uuid references conversations(id) on delete set null,
    rule_id uuid references rules(id) on delete set null,
    type action_type_enum not null,
    title text not null,
    summary text,
    status action_status_enum not null default 'pending',
    priority action_priority_enum not null default 'medium',
    sensitivity sensitivity_level_enum not null default 'low',
    delivery_channels delivery_channel_enum[] not null default ARRAY['in_app']::delivery_channel_enum[],
    payload jsonb not null default '{}'::jsonb,
    execution_result jsonb,
    metadata jsonb not null default '{}'::jsonb,
    last_executed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_actions_conversation_id'
    ) THEN
        ALTER TABLE actions
        ADD CONSTRAINT fk_actions_conversation_id
        FOREIGN KEY (conversation_id)
        REFERENCES conversations(id)
        ON DELETE SET NULL
        NOT VALID;
    END IF;
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

create table if not exists action_logs (
    id uuid primary key default gen_random_uuid(),
    action_id uuid not null references actions(id) on delete cascade,
    company_id uuid not null references companies(id) on delete cascade,
    event_name text not null,
    status action_status_enum not null,
    message text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists action_deliveries (
    id uuid primary key default gen_random_uuid(),
    action_id uuid not null references actions(id) on delete cascade,
    company_id uuid not null references companies(id) on delete cascade,
    channel delivery_channel_enum not null,
    delivery_status text not null default 'queued',
    target_reference text,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists webhooks (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references companies(id) on delete cascade,
    name text not null,
    target_url text not null,
    subscribed_events webhook_event_enum[] not null,
    secret text not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_webhooks_company_name unique (company_id, name)
);

create table if not exists webhook_deliveries (
    id uuid primary key default gen_random_uuid(),
    webhook_id uuid not null references webhooks(id) on delete cascade,
    action_id uuid references actions(id) on delete set null,
    event_name webhook_event_enum not null,
    delivery_status text not null default 'queued',
    response_status int,
    response_body text,
    attempted_at timestamptz not null default now()
);

create table if not exists company_rules (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references companies(id) on delete cascade,
    title text not null,
    category text not null,
    content text not null,
    effective_date date,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Optional RAG support for company_rules via pgvector.
-- One rule can be chunked into multiple embeddings.
create table if not exists company_rule_chunks (
    id uuid primary key default gen_random_uuid(),
    company_rule_id uuid not null references company_rules(id) on delete cascade,
    company_id uuid not null references companies(id) on delete cascade,
    chunk_index int not null,
    content_chunk text not null,
    embedding vector(1024),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    constraint uq_company_rule_chunks unique (company_rule_id, chunk_index)
);

create table if not exists intent_examples (
    id uuid primary key default gen_random_uuid(),
    company_id uuid null references companies(id) on delete cascade,
    intent_key text not null,
    example_text text not null,
    language text not null default 'id',
    weight int not null default 1,
    embedding vector(1024),
    metadata jsonb not null default '{}'::jsonb,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint chk_intent_examples_weight check (
        weight between 1 and 10
    ),
    constraint uq_intent_examples unique (
        company_id,
        intent_key,
        example_text
    )
);

create table if not exists agent_capabilities (
    id uuid primary key default gen_random_uuid(),
    company_id uuid null references companies(id) on delete cascade,
    agent_key text not null,
    title text not null,
    description text not null,
    supported_intents jsonb not null default '[]'::jsonb,
    data_sources jsonb not null default '[]'::jsonb,
    execution_mode text not null default 'structured_lookup',
    requires_trusted_employee_context boolean not null default false,
    can_run_in_parallel boolean not null default true,
    sample_queries jsonb not null default '[]'::jsonb,
    embedding vector(1024),
    metadata jsonb not null default '{}'::jsonb,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint chk_agent_capabilities_execution_mode check (
        execution_mode in (
            'structured_lookup',
            'policy_lookup',
            'file_extraction'
        )
    ),
    constraint uq_agent_capabilities unique (
        company_id,
        agent_key
    )
);

create table if not exists classifier_keyword_overrides (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references companies(id) on delete cascade,
    classifier_type text not null,
    target_key text not null,
    keyword text not null,
    weight int not null default 1,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint chk_classifier_keyword_override_type check (
        classifier_type in ('intent', 'sensitivity')
    ),
    constraint chk_classifier_keyword_override_weight check (
        weight between 1 and 10
    ),
    constraint uq_classifier_keyword_overrides unique (
        company_id,
        classifier_type,
        target_key,
        keyword
    )
);

-- Add FK after employees exists to avoid circular creation issue.
alter table departments
    drop constraint if exists fk_departments_head_employee;

alter table departments
    add constraint fk_departments_head_employee
    foreign key (head_employee_id) references employees(id) on delete set null;

-- Helpful indexes
create index if not exists idx_departments_company_id on departments(company_id);
create index if not exists idx_departments_parent_id on departments(parent_id);

create index if not exists idx_employees_company_id on employees(company_id);
create index if not exists idx_employees_department_id on employees(department_id);
create index if not exists idx_employees_manager_id on employees(manager_id);
create index if not exists idx_employees_role on employees(role);
create index if not exists idx_employees_join_date on employees(join_date);

create index if not exists idx_personal_infos_employee_id on personal_infos(employee_id);

create index if not exists idx_time_offs_employee_id on time_offs(employee_id);
create index if not exists idx_time_offs_employee_year on time_offs(employee_id, year);
create index if not exists idx_time_offs_record_type on time_offs(record_type);
create index if not exists idx_time_offs_status on time_offs(status);
create index if not exists idx_time_offs_leave_type on time_offs(leave_type);

create index if not exists idx_attendance_employee_id on attendance(employee_id);
create index if not exists idx_attendance_employee_date on attendance(employee_id, attendance_date desc);
create index if not exists idx_attendance_status on attendance(status);

create index if not exists idx_payroll_employee_id on payroll(employee_id);
create index if not exists idx_payroll_employee_period on payroll(employee_id, year desc, month desc);
create index if not exists idx_payroll_payment_status on payroll(payment_status);

create index if not exists idx_rules_company_id on rules(company_id);
create index if not exists idx_rules_trigger on rules(trigger);
create index if not exists idx_rules_intent_key on rules(intent_key);
create index if not exists idx_rules_enabled on rules(is_enabled);

create index if not exists idx_rule_actions_rule_id on rule_actions(rule_id);
create index if not exists idx_rule_actions_action_type on rule_actions(action_type);

create index if not exists idx_conversations_company_id on conversations(company_id);
create index if not exists idx_conversations_employee_id on conversations(employee_id);
create index if not exists idx_conversations_status on conversations(status);
create index if not exists idx_conversations_last_message_at on conversations(last_message_at desc);
create index if not exists idx_conversation_messages_conversation_id on conversation_messages(conversation_id);
create index if not exists idx_conversation_messages_company_id on conversation_messages(company_id);
create index if not exists idx_conversation_messages_created_at on conversation_messages(created_at asc);

create index if not exists idx_actions_company_id on actions(company_id);
create index if not exists idx_actions_employee_id on actions(employee_id);
create index if not exists idx_actions_conversation_id on actions(conversation_id);
create index if not exists idx_actions_rule_id on actions(rule_id);
create index if not exists idx_actions_type on actions(type);
create index if not exists idx_actions_status on actions(status);
create index if not exists idx_actions_sensitivity on actions(sensitivity);
create index if not exists idx_actions_created_at on actions(created_at desc);

create index if not exists idx_action_logs_action_id on action_logs(action_id);
create index if not exists idx_action_logs_company_id on action_logs(company_id);
create index if not exists idx_action_logs_created_at on action_logs(created_at desc);

create index if not exists idx_action_deliveries_action_id on action_deliveries(action_id);
create index if not exists idx_action_deliveries_company_id on action_deliveries(company_id);
create index if not exists idx_action_deliveries_channel on action_deliveries(channel);
create index if not exists idx_action_deliveries_created_at on action_deliveries(created_at desc);

create index if not exists idx_webhooks_company_id on webhooks(company_id);
create index if not exists idx_webhooks_active on webhooks(is_active);

create index if not exists idx_webhook_deliveries_webhook_id on webhook_deliveries(webhook_id);
create index if not exists idx_webhook_deliveries_action_id on webhook_deliveries(action_id);
create index if not exists idx_webhook_deliveries_attempted_at on webhook_deliveries(attempted_at desc);

create index if not exists idx_company_rules_company_id on company_rules(company_id);
create index if not exists idx_company_rules_category on company_rules(category);
create index if not exists idx_company_rules_active on company_rules(is_active);
create index if not exists idx_company_rules_effective_date on company_rules(effective_date desc);

create index if not exists idx_company_rule_chunks_rule_id on company_rule_chunks(company_rule_id);
create index if not exists idx_company_rule_chunks_company_id on company_rule_chunks(company_id);
create index if not exists idx_intent_examples_company_id on intent_examples(company_id);
create index if not exists idx_intent_examples_intent_key on intent_examples(intent_key);
create index if not exists idx_intent_examples_active on intent_examples(is_active);
create index if not exists idx_agent_capabilities_company_id on agent_capabilities(company_id);
create index if not exists idx_agent_capabilities_agent_key on agent_capabilities(agent_key);
create index if not exists idx_agent_capabilities_active on agent_capabilities(is_active);
create index if not exists idx_classifier_keyword_overrides_company_id on classifier_keyword_overrides(company_id);
create index if not exists idx_classifier_keyword_overrides_type on classifier_keyword_overrides(classifier_type, target_key);
create index if not exists idx_classifier_keyword_overrides_active on classifier_keyword_overrides(is_active);

-- Optional vector index (recommended only after data volume grows)
-- create index if not exists idx_company_rule_chunks_embedding
--     on company_rule_chunks
--     using ivfflat (embedding vector_cosine_ops)
--     with (lists = 100);

-- Generic updated_at trigger
create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_companies_set_updated_at on companies;
create trigger trg_companies_set_updated_at
before update on companies
for each row execute function set_updated_at();

drop trigger if exists trg_departments_set_updated_at on departments;
create trigger trg_departments_set_updated_at
before update on departments
for each row execute function set_updated_at();

drop trigger if exists trg_employees_set_updated_at on employees;
create trigger trg_employees_set_updated_at
before update on employees
for each row execute function set_updated_at();

drop trigger if exists trg_personal_infos_set_updated_at on personal_infos;
create trigger trg_personal_infos_set_updated_at
before update on personal_infos
for each row execute function set_updated_at();

drop trigger if exists trg_time_offs_set_updated_at on time_offs;
create trigger trg_time_offs_set_updated_at
before update on time_offs
for each row execute function set_updated_at();

drop trigger if exists trg_attendance_set_updated_at on attendance;
create trigger trg_attendance_set_updated_at
before update on attendance
for each row execute function set_updated_at();

drop trigger if exists trg_payroll_set_updated_at on payroll;
create trigger trg_payroll_set_updated_at
before update on payroll
for each row execute function set_updated_at();

drop trigger if exists trg_rules_set_updated_at on rules;
create trigger trg_rules_set_updated_at
before update on rules
for each row execute function set_updated_at();

drop trigger if exists trg_actions_set_updated_at on actions;
create trigger trg_actions_set_updated_at
before update on actions
for each row execute function set_updated_at();

drop trigger if exists trg_webhooks_set_updated_at on webhooks;
create trigger trg_webhooks_set_updated_at
before update on webhooks
for each row execute function set_updated_at();

drop trigger if exists trg_company_rules_set_updated_at on company_rules;
create trigger trg_company_rules_set_updated_at
before update on company_rules
for each row execute function set_updated_at();

drop trigger if exists trg_intent_examples_set_updated_at on intent_examples;
create trigger trg_intent_examples_set_updated_at
before update on intent_examples
for each row execute function set_updated_at();

drop trigger if exists trg_agent_capabilities_set_updated_at on agent_capabilities;
create trigger trg_agent_capabilities_set_updated_at
before update on agent_capabilities
for each row execute function set_updated_at();

drop trigger if exists trg_classifier_keyword_overrides_set_updated_at on classifier_keyword_overrides;
create trigger trg_classifier_keyword_overrides_set_updated_at
before update on classifier_keyword_overrides
for each row execute function set_updated_at();
