-- ============================================================
-- 002_agent_outputs.sql
-- Agent Outputs table — stores structured output from agents
-- Both queryable (for UI Design Agent etc.) and links to GDrive doc
-- ============================================================

create table agent_outputs (
  id              uuid        primary key default gen_random_uuid(),
  agent_id        uuid        not null references agents(id) on delete cascade,
  run_id          uuid        not null references runs(id) on delete cascade,
  company_id      uuid        not null references companies(id) on delete cascade,
  output_type     text        not null
                              check (output_type in (
                                'marketing_brief',
                                'lp_blueprint',
                                'strategy_summary',
                                'context_snapshot',
                                'other'
                              )),
  content         jsonb       not null default '{}',
  gdrive_file_id  text,                          -- GDrive doc ID if written back to Drive
  gdrive_url      text,                          -- Human-readable link to the Drive doc
  version         int         not null default 1,
  created_at      timestamptz not null default now()
);

create index idx_agent_outputs_agent_id    on agent_outputs(agent_id);
create index idx_agent_outputs_run_id      on agent_outputs(run_id);
create index idx_agent_outputs_company_id  on agent_outputs(company_id);
create index idx_agent_outputs_output_type on agent_outputs(output_type);
create index idx_agent_outputs_created_at  on agent_outputs(created_at desc);

-- RLS
alter table agent_outputs enable row level security;

create policy "authenticated_select" on agent_outputs
  for select to authenticated using (true);
create policy "authenticated_insert" on agent_outputs
  for insert to authenticated with check (true);
create policy "authenticated_update" on agent_outputs
  for update to authenticated using (true);
create policy "authenticated_delete" on agent_outputs
  for delete to authenticated using (true);
