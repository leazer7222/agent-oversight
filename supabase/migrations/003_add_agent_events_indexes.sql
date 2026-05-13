-- Add indexes and confirm RLS on agent_events.
-- The table already exists in the live DB but has no indexes — this migration
-- adds them for query performance without touching the table structure.

CREATE INDEX IF NOT EXISTS agent_events_run_id_idx
  ON agent_events(run_id)
  WHERE run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS agent_events_agent_id_idx
  ON agent_events(agent_id);

CREATE INDEX IF NOT EXISTS agent_events_occurred_at_idx
  ON agent_events(occurred_at DESC);

CREATE INDEX IF NOT EXISTS agent_events_company_id_idx
  ON agent_events(company_id);
