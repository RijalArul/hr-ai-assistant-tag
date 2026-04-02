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

create index if not exists idx_company_rules_company_id on company_rules(company_id);
create index if not exists idx_company_rules_category on company_rules(category);
create index if not exists idx_company_rules_active on company_rules(is_active);
create index if not exists idx_company_rules_effective_date on company_rules(effective_date desc);

create index if not exists idx_company_rule_chunks_rule_id on company_rule_chunks(company_rule_id);
create index if not exists idx_company_rule_chunks_company_id on company_rule_chunks(company_id);

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

drop trigger if exists trg_company_rules_set_updated_at on company_rules;
create trigger trg_company_rules_set_updated_at
before update on company_rules
for each row execute function set_updated_at();
