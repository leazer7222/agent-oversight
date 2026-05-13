-- Governance lookup tables for output and event type taxonomies.
-- Prevents silent constraint violations (like the ui_components incident)
-- by maintaining a sanctioned list of valid values in the DB.

CREATE TABLE IF NOT EXISTS output_type_registry (
  output_type  text        PRIMARY KEY,
  description  text,
  added_at     timestamptz NOT NULL DEFAULT now()
);

INSERT INTO output_type_registry (output_type, description) VALUES
  ('marketing_brief',  'Full marketing brief artifact'),
  ('lp_blueprint',     'Landing page blueprint'),
  ('strategy_summary', 'Strategic planning summary'),
  ('context_snapshot', 'Agent context snapshot'),
  ('ui_components',    'Generated UI component code'),
  ('other',            'Uncategorized output')
ON CONFLICT (output_type) DO NOTHING;

CREATE TABLE IF NOT EXISTS event_type_registry (
  event_type   text        PRIMARY KEY,
  description  text,
  added_at     timestamptz NOT NULL DEFAULT now()
);

INSERT INTO event_type_registry (event_type, description) VALUES
  ('run_started',    'Agent run initiated'),
  ('run_completed',  'Agent run completed successfully'),
  ('run_failed',     'Agent run terminated with error'),
  ('step_completed', 'Intermediate step completed'),
  ('tool_called',    'External tool or MCP invoked'),
  ('cost_reported',  'Cost/token usage reported mid-run')
ON CONFLICT (event_type) DO NOTHING;
