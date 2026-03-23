-- ============================================================
-- 001_initial_schema.sql
-- Agent Oversight System — initial schema
-- ============================================================

-- ── Extensions ──────────────────────────────────────────────
create extension if not exists "pgcrypto";

-- ── Helpers ─────────────────────────────────────────────────
create or replace function updated_at_now()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ============================================================
-- TABLES
-- ============================================================

-- ── companies ───────────────────────────────────────────────
create table companies (
  id                  uuid primary key default gen_random_uuid(),
  name                text        not null,
  slug                text        not null unique,
  description         text,
  cost_limit_usd      numeric(12,4),
  cost_limit_period   text        check (cost_limit_period in ('hourly','daily','weekly','monthly')),
  created_at          timestamptz not null default now()
);

-- Seed data
insert into companies (name, slug, description) values
  ('ReformAI',  'reformai',  'ReformAI platform company'),
  ('AfterGlow', 'afterglow', 'AfterGlow platform company'),
  ('Personal',  'personal',  'Personal projects');

-- ── projects ────────────────────────────────────────────────
create table projects (
  id               uuid primary key default gen_random_uuid(),
  name             text        not null,
  company_id       uuid        not null references companies(id) on delete cascade,
  description      text,
  orchestrator_id  uuid,                          -- fk to agents added below
  status           text        not null default 'active'
                               check (status in ('active','paused','archived')),
  created_at       timestamptz not null default now()
);

create index idx_projects_company_id on projects(company_id);

-- ── agent_definitions ───────────────────────────────────────
create table agent_definitions (
  id              uuid primary key default gen_random_uuid(),
  name            text        not null unique,
  display_name    text        not null,
  description     text,
  capability_tags text[]      not null default '{}',
  instance_type   text        not null default 'stateless'
                              check (instance_type in ('stateless','stateful','long-running')),
  default_model   text,
  input_schema    jsonb       not null default '{}',
  output_schema   jsonb       not null default '{}',
  config_schema   jsonb       not null default '{}',
  version         text        not null default '1.0.0',
  source_path     text,
  created_at      timestamptz not null default now()
);

-- ── agents ──────────────────────────────────────────────────
create table agents (
  id                    uuid primary key default gen_random_uuid(),
  name                  text        not null,
  company_id            uuid        not null references companies(id) on delete cascade,
  project_id            uuid        references projects(id) on delete set null,
  definition_id         uuid        references agent_definitions(id) on delete set null,
  agent_type            text        not null default 'worker'
                                    check (agent_type in ('orchestrator','worker','reviewer','monitor')),
  parent_agent_id       uuid        references agents(id) on delete set null,
  depth                 int         not null default 0,
  platform              text,
  model                 text,
  trigger_type          text        check (trigger_type in ('manual','scheduled','event','webhook','chained')),
  trigger_config        jsonb       not null default '{}',
  status                text        not null default 'active'
                                    check (status in ('active','paused','disabled','error')),
  cost_limit_usd        numeric(12,4),
  cost_limit_period     text        check (cost_limit_period in ('hourly','daily','weekly','monthly')),
  max_errors_per_hour   int         not null default 10,
  priority              int         not null default 5,
  tags                  text[]      not null default '{}',
  can_trigger           text[]      not null default '{}',   -- agent ids / names this agent may trigger
  can_be_triggered_by   text[]      not null default '{}',   -- agent ids / names allowed to trigger this
  config_overrides      jsonb       not null default '{}',
  registered_at         timestamptz not null default now(),
  last_run_at           timestamptz,
  paused_at             timestamptz,
  paused_reason         text,
  metadata              jsonb       not null default '{}'
);

create index idx_agents_company_id    on agents(company_id);
create index idx_agents_project_id    on agents(project_id);
create index idx_agents_definition_id on agents(definition_id);
create index idx_agents_status        on agents(status);

-- Now that agents table exists, wire the orchestrator_id fk on projects
alter table projects
  add constraint fk_projects_orchestrator
  foreign key (orchestrator_id) references agents(id) on delete set null;

-- ── agent_events ────────────────────────────────────────────
create table agent_events (
  id                    uuid        primary key default gen_random_uuid(),
  agent_id              uuid        not null references agents(id) on delete cascade,
  run_id                text,
  company_id            uuid        not null references companies(id) on delete cascade,
  project_id            uuid        references projects(id) on delete set null,
  event_type            text        not null,
  severity              text        not null default 'info'
                                    check (severity in ('debug','info','warning','error','critical')),
  message               text        not null,
  occurred_at           timestamptz not null default now(),
  cost_usd              numeric(12,6),
  tokens_in             int,
  tokens_out            int,
  duration_ms           int,
  orchestrator_run_id   text,
  triggered_by_agent_id uuid        references agents(id) on delete set null,
  depth                 int         not null default 0,
  payload               jsonb       not null default '{}',
  platform_run_id       text
);

create index idx_agent_events_agent_id    on agent_events(agent_id);
create index idx_agent_events_company_id  on agent_events(company_id);
create index idx_agent_events_run_id      on agent_events(run_id);
create index idx_agent_events_occurred_at on agent_events(occurred_at desc);
create index idx_agent_events_severity    on agent_events(severity);
create index idx_agent_events_project_id  on agent_events(project_id);

-- ── agent_qa_results ────────────────────────────────────────
create table agent_qa_results (
  id                   uuid        primary key default gen_random_uuid(),
  agent_id             uuid        not null references agents(id) on delete cascade,
  run_id               text,
  score                numeric(5,4) check (score between 0 and 1),
  criteria_scores      jsonb       not null default '{}',
  constraints_passed   boolean     not null default true,
  constraints_detail   jsonb       not null default '{}',
  flagged_for_review   boolean     not null default false,
  notes                text,
  evaluated_at         timestamptz not null default now()
);

create index idx_qa_results_agent_id    on agent_qa_results(agent_id);
create index idx_qa_results_run_id      on agent_qa_results(run_id);
create index idx_qa_results_flagged     on agent_qa_results(flagged_for_review) where flagged_for_review = true;

-- ── policies ────────────────────────────────────────────────
create table policies (
  id                        uuid        primary key default gen_random_uuid(),
  name                      text        not null unique,
  enabled                   boolean     not null default true,
  global_cost_cap_usd       numeric(12,4),
  global_cost_cap_period    text        check (global_cost_cap_period in ('hourly','daily','weekly','monthly')),
  auto_pause_on_cap         boolean     not null default true,
  auto_pause_on_error_spike boolean     not null default true,
  error_spike_threshold     int         not null default 10,
  alert_on_latency_ms       int,
  auto_resume               boolean     not null default false,
  alert_email               text,
  alert_slack_webhook       text,
  updated_at                timestamptz not null default now()
);

create trigger trg_policies_updated_at
  before update on policies
  for each row execute function updated_at_now();

-- ── audit_log ───────────────────────────────────────────────
create table audit_log (
  id          uuid        primary key default gen_random_uuid(),
  agent_id    uuid        references agents(id) on delete set null,
  actor       text        not null,
  action      text        not null,
  reason      text,
  detail      jsonb       not null default '{}',
  occurred_at timestamptz not null default now()
);

create index idx_audit_log_agent_id    on audit_log(agent_id);
create index idx_audit_log_occurred_at on audit_log(occurred_at desc);
create index idx_audit_log_actor       on audit_log(actor);

-- ============================================================
-- VIEWS
-- ============================================================

-- ── agent_cost_summary ──────────────────────────────────────
create view agent_cost_summary as
select
  a.id                           as agent_id,
  a.name                         as agent_name,
  a.company_id,
  a.project_id,
  count(e.id)                    as total_runs,
  coalesce(sum(e.cost_usd), 0)   as total_cost_usd,
  coalesce(sum(e.tokens_in), 0)  as total_tokens_in,
  coalesce(sum(e.tokens_out), 0) as total_tokens_out,
  max(e.occurred_at)             as last_event_at
from agents a
left join agent_events e on e.agent_id = a.id
group by a.id, a.name, a.company_id, a.project_id;

-- ── project_cost_summary ────────────────────────────────────
create view project_cost_summary as
select
  p.id                            as project_id,
  p.name                          as project_name,
  p.company_id,
  count(distinct e.agent_id)      as active_agents,
  count(e.id)                     as total_runs,
  coalesce(sum(e.cost_usd), 0)    as total_cost_usd,
  coalesce(sum(e.tokens_in), 0)   as total_tokens_in,
  coalesce(sum(e.tokens_out), 0)  as total_tokens_out,
  max(e.occurred_at)              as last_event_at
from projects p
left join agent_events e on e.project_id = p.id
group by p.id, p.name, p.company_id;

-- ── company_cost_summary ────────────────────────────────────
create view company_cost_summary as
select
  c.id                            as company_id,
  c.name                          as company_name,
  c.cost_limit_usd,
  c.cost_limit_period,
  count(distinct e.agent_id)      as active_agents,
  count(e.id)                     as total_runs,
  coalesce(sum(e.cost_usd), 0)    as total_cost_usd,
  coalesce(sum(e.tokens_in), 0)   as total_tokens_in,
  coalesce(sum(e.tokens_out), 0)  as total_tokens_out,
  max(e.occurred_at)              as last_event_at
from companies c
left join agent_events e on e.company_id = c.id
group by c.id, c.name, c.cost_limit_usd, c.cost_limit_period;

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================

alter table companies         enable row level security;
alter table projects          enable row level security;
alter table agent_definitions enable row level security;
alter table agents            enable row level security;
alter table agent_events      enable row level security;
alter table agent_qa_results  enable row level security;
alter table policies          enable row level security;
alter table audit_log         enable row level security;

-- Authenticated users can read/write all rows.
-- Tighten these policies per-tenant once auth claims are in place.

create policy "authenticated_select" on companies
  for select to authenticated using (true);
create policy "authenticated_insert" on companies
  for insert to authenticated with check (true);
create policy "authenticated_update" on companies
  for update to authenticated using (true);
create policy "authenticated_delete" on companies
  for delete to authenticated using (true);

create policy "authenticated_select" on projects
  for select to authenticated using (true);
create policy "authenticated_insert" on projects
  for insert to authenticated with check (true);
create policy "authenticated_update" on projects
  for update to authenticated using (true);
create policy "authenticated_delete" on projects
  for delete to authenticated using (true);

create policy "authenticated_select" on agent_definitions
  for select to authenticated using (true);
create policy "authenticated_insert" on agent_definitions
  for insert to authenticated with check (true);
create policy "authenticated_update" on agent_definitions
  for update to authenticated using (true);
create policy "authenticated_delete" on agent_definitions
  for delete to authenticated using (true);

create policy "authenticated_select" on agents
  for select to authenticated using (true);
create policy "authenticated_insert" on agents
  for insert to authenticated with check (true);
create policy "authenticated_update" on agents
  for update to authenticated using (true);
create policy "authenticated_delete" on agents
  for delete to authenticated using (true);

create policy "authenticated_select" on agent_events
  for select to authenticated using (true);
create policy "authenticated_insert" on agent_events
  for insert to authenticated with check (true);
create policy "authenticated_update" on agent_events
  for update to authenticated using (true);
create policy "authenticated_delete" on agent_events
  for delete to authenticated using (true);

create policy "authenticated_select" on agent_qa_results
  for select to authenticated using (true);
create policy "authenticated_insert" on agent_qa_results
  for insert to authenticated with check (true);
create policy "authenticated_update" on agent_qa_results
  for update to authenticated using (true);
create policy "authenticated_delete" on agent_qa_results
  for delete to authenticated using (true);

create policy "authenticated_select" on policies
  for select to authenticated using (true);
create policy "authenticated_insert" on policies
  for insert to authenticated with check (true);
create policy "authenticated_update" on policies
  for update to authenticated using (true);
create policy "authenticated_delete" on policies
  for delete to authenticated using (true);

create policy "authenticated_select" on audit_log
  for select to authenticated using (true);
create policy "authenticated_insert" on audit_log
  for insert to authenticated with check (true);
create policy "authenticated_update" on audit_log
  for update to authenticated using (true);
create policy "authenticated_delete" on audit_log
  for delete to authenticated using (true);
