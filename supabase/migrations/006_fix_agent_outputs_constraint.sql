-- Fix agent_outputs output_type CHECK constraint to include ui_components.
-- The live constraint (agent_outputs_output_type_check) rejects ui_components,
-- causing orchestrator writes to fail silently. This drops and recreates it.

ALTER TABLE agent_outputs DROP CONSTRAINT IF EXISTS agent_outputs_output_type_check;

ALTER TABLE agent_outputs ADD CONSTRAINT agent_outputs_output_type_check
  CHECK (output_type = ANY (ARRAY[
    'marketing_brief'::text,
    'lp_blueprint'::text,
    'strategy_summary'::text,
    'context_snapshot'::text,
    'ui_components'::text,
    'other'::text
  ]));
