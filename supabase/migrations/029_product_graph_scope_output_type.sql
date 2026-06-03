-- Migration 029: allow agent_outputs.output_type = 'product_graph_scope'
--   The BA Scoping Agent writes its product_graph_scope artifact to agent_outputs
--   (the on-disk mirror of the graph_nodes/edges it produced). Same pattern as
--   migration 027 (codebase_context).
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 002_agent_outputs.sql, 027_codebase_context_output_type.sql

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
    'other'::text
  ]));
