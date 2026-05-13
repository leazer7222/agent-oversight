-- Initial schema — reverse-engineered from live Supabase DB (hdhovyrlnfojtkqbcegh) on 2026-05-13.
-- This file has NEVER been applied to the live database.
-- Purpose: governance documentation + fresh-deploy reproducibility only.
-- DO NOT apply to the live project — it already has these tables.

-- Companies: top-level tenant entity with cost controls
CREATE TABLE companies (
  id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name              text        NOT NULL,
  slug              text        NOT NULL,
  description       text,
  cost_limit_usd    numeric,
  cost_limit_period text,
  created_at        timestamptz NOT NULL DEFAULT now()
);

-- Projects: grouped workstreams within a company
CREATE TABLE projects (
  id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name             text        NOT NULL,
  company_id       uuid        NOT NULL REFERENCES companies(id),
  description      text,
  orchestrator_id  uuid,       -- FK to agents(id) added after agents table exists
  status           text        NOT NULL DEFAULT 'active',
  created_at       timestamptz NOT NULL DEFAULT now()
);

-- Agent definitions: shared library of agent types (no company ownership)
CREATE TABLE agent_definitions (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name            text        NOT NULL,
  display_name    text,
  description     text,
  capability_tags text[],
  instance_type   text,
  default_model   text,
  input_schema    jsonb,
  output_schema   jsonb,
  config_schema   jsonb,
  version         text,
  source_path     text,
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- Agents: deployed instances of agent definitions within a company
CREATE TABLE agents (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name                text        NOT NULL,
  company_id          uuid        REFERENCES companies(id),
  project_id          uuid        REFERENCES projects(id),
  definition_id       uuid        REFERENCES agent_definitions(id),
  agent_type          text,
  parent_agent_id     uuid        REFERENCES agents(id),
  depth               int,
  platform            text,
  model               text,
  trigger_type        text,
  trigger_config      jsonb,
  status              text,
  cost_limit_usd      numeric,
  cost_limit_period   text,
  max_errors_per_hour int,
  priority            int,
  tags                text[],
  can_trigger         uuid[],
  can_be_triggered_by uuid[],
  config_overrides    jsonb,
  registered_at       timestamptz,
  last_run_at         timestamptz,
  paused_at           timestamptz,
  paused_reason       text,
  metadata            jsonb
);

-- Add deferred FK now that agents table exists
ALTER TABLE projects
  ADD CONSTRAINT projects_orchestrator_id_fkey
  FOREIGN KEY (orchestrator_id) REFERENCES agents(id);

-- Runs: execution lifecycle summary rows (one per agent invocation)
CREATE TABLE runs (
  id           uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id     uuid        NOT NULL REFERENCES agents(id),
  status       text        NOT NULL DEFAULT 'started',
  started_at   timestamptz NOT NULL DEFAULT now(),
  created_at   timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  tokens_in    int,
  tokens_out   int,
  cost_usd     numeric,
  error        text,
  metadata     jsonb
);

-- Agent events: append-only observability trace (one row per event per run)
CREATE TABLE agent_events (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id              uuid        NOT NULL REFERENCES agents(id),
  company_id            uuid        NOT NULL REFERENCES companies(id),
  project_id            uuid        REFERENCES projects(id),
  run_id                uuid,       -- nullable: events can occur outside a run context
  event_type            text        NOT NULL,
  occurred_at           timestamptz NOT NULL DEFAULT now(),
  message               text        NOT NULL,
  payload               jsonb       NOT NULL DEFAULT '{}',
  severity              text        NOT NULL,
  depth                 int         NOT NULL,
  duration_ms           int,
  cost_usd              numeric,
  tokens_in             int,
  tokens_out            int,
  orchestrator_run_id   text,
  platform_run_id       text,
  triggered_by_agent_id uuid        REFERENCES agents(id)
);

-- Agent outputs: persisted artifacts produced by agents
CREATE TABLE agent_outputs (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id    uuid        NOT NULL REFERENCES agents(id),
  run_id      uuid        REFERENCES runs(id),
  output_type text        NOT NULL CHECK (output_type = ANY (ARRAY[
                'marketing_brief', 'lp_blueprint', 'strategy_summary',
                'context_snapshot', 'ui_components', 'other'
              ])),
  content     jsonb       NOT NULL DEFAULT '{}',
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- Policies: governance engine — cost caps, error spike thresholds, alerting
CREATE TABLE policies (
  id                       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  name                     text        NOT NULL,
  enabled                  boolean     NOT NULL DEFAULT true,
  global_cost_cap_usd      numeric,
  global_cost_cap_period   text,
  auto_pause_on_cap        boolean     NOT NULL DEFAULT true,
  auto_pause_on_error_spike boolean    NOT NULL DEFAULT true,
  error_spike_threshold    int         NOT NULL DEFAULT 10,
  alert_on_latency_ms      int,
  auto_resume              boolean     NOT NULL DEFAULT false,
  alert_email              text,
  alert_slack_webhook      text,
  updated_at               timestamptz NOT NULL DEFAULT now()
);

-- Budgets: cost budget tracking (schema TBD — table exists live as empty shell)
CREATE TABLE budgets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid()
);

-- Project state: typed key-value store for agent session continuity
CREATE TABLE project_state (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  project_tag   text        NOT NULL UNIQUE,
  current_state text,
  todo          text,
  lessons       text,
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- Cost summary views (aggregate from agent_events, not runs)
CREATE VIEW agent_cost_summary AS
  SELECT
    a.id          AS agent_id,
    a.name        AS agent_name,
    a.company_id,
    a.project_id,
    count(e.id)                                  AS total_runs,
    COALESCE(sum(e.cost_usd),    0::numeric)     AS total_cost_usd,
    COALESCE(sum(e.tokens_in),   0::bigint)      AS total_tokens_in,
    COALESCE(sum(e.tokens_out),  0::bigint)      AS total_tokens_out,
    max(e.occurred_at)                           AS last_event_at
  FROM agents a
  LEFT JOIN agent_events e ON e.agent_id = a.id
  GROUP BY a.id, a.name, a.company_id, a.project_id;

CREATE VIEW project_cost_summary AS
  SELECT
    p.id          AS project_id,
    p.name        AS project_name,
    p.company_id,
    count(DISTINCT e.agent_id)                   AS active_agents,
    count(e.id)                                  AS total_runs,
    COALESCE(sum(e.cost_usd),    0::numeric)     AS total_cost_usd,
    COALESCE(sum(e.tokens_in),   0::bigint)      AS total_tokens_in,
    COALESCE(sum(e.tokens_out),  0::bigint)      AS total_tokens_out,
    max(e.occurred_at)                           AS last_event_at
  FROM projects p
  LEFT JOIN agent_events e ON e.project_id = p.id
  GROUP BY p.id, p.name, p.company_id;

-- RLS policies (matching live DB pattern: authenticated full access, service_role on runs)
ALTER TABLE agents        ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_events  ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_outputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs          ENABLE ROW LEVEL SECURITY;

CREATE POLICY authenticated_select ON agents        FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_insert ON agents        FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY authenticated_update ON agents        FOR UPDATE TO authenticated USING (true);
CREATE POLICY authenticated_delete ON agents        FOR DELETE TO authenticated USING (true);

CREATE POLICY authenticated_select ON agent_events  FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_insert ON agent_events  FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY authenticated_update ON agent_events  FOR UPDATE TO authenticated USING (true);
CREATE POLICY authenticated_delete ON agent_events  FOR DELETE TO authenticated USING (true);

CREATE POLICY authenticated_select ON agent_outputs FOR SELECT TO authenticated USING (true);
CREATE POLICY authenticated_insert ON agent_outputs FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY authenticated_update ON agent_outputs FOR UPDATE TO authenticated USING (true);
CREATE POLICY authenticated_delete ON agent_outputs FOR DELETE TO authenticated USING (true);

CREATE POLICY service_role_all ON runs FOR ALL TO service_role USING (true) WITH CHECK (true);
