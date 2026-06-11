-- Fix total_runs in the cost-summary views.
--
-- BUG: agent_cost_summary.total_runs and project_cost_summary.total_runs were
-- defined as count(agent_events.id) -- i.e. a TELEMETRY EVENT count, not a run
-- count. Each run emits multiple events (run_started, step, run_completed,
-- errors...), so the dashboard "Runs" column was inflated several-fold and
-- never reconciled with the "Total Runs" KPI (which is COUNT(*) on runs).
-- Conversely, runs that emitted no events were undercounted.
--
-- FIX: source total_runs from the authoritative `runs` table while keeping
-- cost/token aggregates from agent_events. The per-agent run subquery returns
-- one row per agent, so it does not multiply the event-level cost/token sums.
--
-- Verified against live DB on 2026-06-10: per-agent totals now match the runs
-- table, and the sum of agent_cost_summary.total_runs equals COUNT(*) FROM runs.

CREATE OR REPLACE VIEW agent_cost_summary AS
  SELECT
    a.id          AS agent_id,
    a.name        AS agent_name,
    a.company_id,
    a.project_id,
    COALESCE(r.run_count, 0)                   AS total_runs,
    COALESCE(sum(e.cost_usd),   0::numeric)    AS total_cost_usd,
    COALESCE(sum(e.tokens_in),  0::bigint)     AS total_tokens_in,
    COALESCE(sum(e.tokens_out), 0::bigint)     AS total_tokens_out,
    max(e.occurred_at)                         AS last_event_at
  FROM agents a
  LEFT JOIN agent_events e ON e.agent_id = a.id
  LEFT JOIN (
    SELECT agent_id, count(*) AS run_count
    FROM runs
    GROUP BY agent_id
  ) r ON r.agent_id = a.id
  GROUP BY a.id, a.name, a.company_id, a.project_id, r.run_count;

CREATE OR REPLACE VIEW project_cost_summary AS
  SELECT
    p.id          AS project_id,
    p.name        AS project_name,
    p.company_id,
    count(DISTINCT e.agent_id)                 AS active_agents,
    COALESCE(r.run_count, 0)                    AS total_runs,
    COALESCE(sum(e.cost_usd),   0::numeric)    AS total_cost_usd,
    COALESCE(sum(e.tokens_in),  0::bigint)     AS total_tokens_in,
    COALESCE(sum(e.tokens_out), 0::bigint)     AS total_tokens_out,
    max(e.occurred_at)                         AS last_event_at
  FROM projects p
  LEFT JOIN agent_events e ON e.project_id = p.id
  LEFT JOIN (
    -- runs has no project_id; resolve project via the owning agent
    SELECT a.project_id, count(*) AS run_count
    FROM runs rr
    JOIN agents a ON a.id = rr.agent_id
    GROUP BY a.project_id
  ) r ON r.project_id = p.id
  GROUP BY p.id, p.name, p.company_id, r.run_count;
