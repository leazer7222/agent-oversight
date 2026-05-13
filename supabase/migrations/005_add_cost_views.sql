-- Cost summary views — verified SQL retrieved from live DB on 2026-05-13.
-- Both views aggregate from agent_events (not runs).
-- They will show zero until the agent_events write path is active in /api/ingest.
--
-- NOTE: runs_with_agents does NOT exist in the live DB (confirmed 2026-05-13).

CREATE OR REPLACE VIEW agent_cost_summary AS
  SELECT
    a.id          AS agent_id,
    a.name        AS agent_name,
    a.company_id,
    a.project_id,
    count(e.id)                               AS total_runs,
    COALESCE(sum(e.cost_usd),   0::numeric)   AS total_cost_usd,
    COALESCE(sum(e.tokens_in),  0::bigint)    AS total_tokens_in,
    COALESCE(sum(e.tokens_out), 0::bigint)    AS total_tokens_out,
    max(e.occurred_at)                        AS last_event_at
  FROM agents a
  LEFT JOIN agent_events e ON e.agent_id = a.id
  GROUP BY a.id, a.name, a.company_id, a.project_id;

CREATE OR REPLACE VIEW project_cost_summary AS
  SELECT
    p.id          AS project_id,
    p.name        AS project_name,
    p.company_id,
    count(DISTINCT e.agent_id)                AS active_agents,
    count(e.id)                               AS total_runs,
    COALESCE(sum(e.cost_usd),   0::numeric)   AS total_cost_usd,
    COALESCE(sum(e.tokens_in),  0::bigint)    AS total_tokens_in,
    COALESCE(sum(e.tokens_out), 0::bigint)    AS total_tokens_out,
    max(e.occurred_at)                        AS last_event_at
  FROM projects p
  LEFT JOIN agent_events e ON e.project_id = p.id
  GROUP BY p.id, p.name, p.company_id;
