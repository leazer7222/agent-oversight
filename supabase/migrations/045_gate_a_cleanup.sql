-- Migration 045: P2 cleanup (code-review findings)
--
-- #1 Remove the unused 'gate_a_feature_spec' agent_outputs output_type (the Gate A snapshot lives in
--    the dedicated public.gate_a_snapshots table; 0 rows ever used the agent_outputs value).
-- #3 Add the missing tenant_id FK on gate_a_snapshots (0 orphan rows; safe).
--
-- Depends on: 041, 043. Apply to hdhovyrlnfojtkqbcegh.

-- #1: drop the leftover allowed value (restore the pre-041 set + the PCA-era types).
ALTER TABLE public.agent_outputs DROP CONSTRAINT IF EXISTS agent_outputs_output_type_check;
ALTER TABLE public.agent_outputs
  ADD CONSTRAINT agent_outputs_output_type_check
  CHECK (output_type = ANY (ARRAY[
    'marketing_brief'::text, 'lp_blueprint'::text, 'strategy_summary'::text, 'context_snapshot'::text,
    'ui_components'::text, 'code_review'::text, 'codebase_context'::text, 'product_graph_scope'::text,
    'intake_assessment'::text, 'clarification_brief'::text, 'concept_resolution'::text, 'other'::text
  ]));

-- #3: tenant_id FK (company isolation integrity).
ALTER TABLE public.gate_a_snapshots
  ADD CONSTRAINT fk_gate_a_tenant FOREIGN KEY (tenant_id)
  REFERENCES public.companies(id) ON DELETE RESTRICT;
