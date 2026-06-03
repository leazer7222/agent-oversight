-- Migration 033: register PCA intake output types on agent_outputs
--   The Product Clarification Agent (PCA), repurposed as the Agile front-door /
--   intake-normalization agent, writes two artifact types to agent_outputs:
--     - intake_assessment   : the LOGGED classifier decision (coverage / scores / decision /
--                             rationale). Written FIRST on every run, regardless of branch.
--     - clarification_brief : the FINALIZED Clarification Brief + handoff. Written ONLY when
--                             final (proceed_direct, or after Pass B). Never provisional.
--   Same additive pattern as migrations 027 (codebase_context) and 029 (product_graph_scope):
--   superset of the existing CHECK array, so no existing row can be invalidated.
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 002_agent_outputs.sql, 027_codebase_context_output_type.sql,
--             029_product_graph_scope_output_type.sql
-- Relates to: docs/agile-pca-integration-plan.md

ALTER TABLE public.agent_outputs
  DROP CONSTRAINT IF EXISTS agent_outputs_output_type_check;

ALTER TABLE public.agent_outputs
  ADD CONSTRAINT agent_outputs_output_type_check
  CHECK (output_type = ANY (ARRAY[
    'marketing_brief'::text,
    'lp_blueprint'::text,
    'strategy_summary'::text,
    'context_snapshot'::text,
    'ui_components'::text,
    'code_review'::text,
    'codebase_context'::text,
    'product_graph_scope'::text,
    'intake_assessment'::text,
    'clarification_brief'::text,
    'other'::text
  ]));

-- Verification (after applying):
-- SELECT conname FROM pg_constraint WHERE conname = 'agent_outputs_output_type_check';
-- A row with output_type='intake_assessment' or 'clarification_brief' must INSERT;
-- a bogus output_type must be rejected by the CHECK.
