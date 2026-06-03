-- Migration 027: allow output_type='codebase_context' on agent_outputs
--
-- The Codebase Context Agent (reformai.codebase-context-agent) writes its
-- codebase-context.json artifact to agent_outputs with output_type='codebase_context'.
-- The live CHECK constraint (last set in migration 011) does not include it, so the
-- insert fails with constraint violation agent_outputs_output_type_check.
--
-- This preserves every existing allowed value and adds 'codebase_context'.
-- Apply to project: hdhovyrlnfojtkqbcegh

ALTER TABLE agent_outputs DROP CONSTRAINT IF EXISTS agent_outputs_output_type_check;

ALTER TABLE agent_outputs ADD CONSTRAINT agent_outputs_output_type_check
  CHECK (output_type = ANY (ARRAY[
    'marketing_brief'::text,
    'lp_blueprint'::text,
    'strategy_summary'::text,
    'context_snapshot'::text,
    'ui_components'::text,
    'code_review'::text,
    'codebase_context'::text,
    'other'::text
  ]));
