-- Migration 037: allow output_type='concept_resolution' on agent_outputs (CCA P1)
--
-- The CCA publishes feature-scoped concept_resolution artifacts (PCA/BA handoff concepts
-- resolved against the deterministic inventory). For P1 it is a typed agent_output, not a
-- dedicated table (design Q3) - promote to codebase_concept_resolutions in P2.
-- Preserves every existing allowed value (last set in migration 033) and adds concept_resolution.
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
    'product_graph_scope'::text,
    'intake_assessment'::text,
    'clarification_brief'::text,
    'concept_resolution'::text,
    'other'::text
  ]));
