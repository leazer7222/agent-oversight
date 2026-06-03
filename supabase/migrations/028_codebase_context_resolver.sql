-- Migration 028: codebase-context handoff resolver
--
-- The stable consumption seam between the Codebase Context Agent (producer) and the
-- BA Scoping Agent (consumer). The BA never hand-queries agent_outputs; it calls this
-- function with a target_key and gets the latest COMPLETE codebase_context artifact.
--
-- "Complete" = a non-empty concept_resolution (the loop-closer). This deterministically
-- skips truncated/partial artifacts (e.g. a run that hit max_tokens before emitting
-- concept_resolution) without needing to mutate the immutable agent_outputs ledger.
--
-- Mirrors the public.cbc_resolve / public.graph_* RPC pattern (PostgREST-callable).
-- Apply to project: hdhovyrlnfojtkqbcegh

CREATE OR REPLACE FUNCTION public.get_latest_codebase_context(p_target_key TEXT)
RETURNS TABLE (
  artifact_id    UUID,
  run_id         UUID,
  agent_id       UUID,
  company_id     UUID,
  repo           TEXT,
  commit_sha     TEXT,
  feature_intent TEXT,
  generated_at   TIMESTAMPTZ,
  created_at     TIMESTAMPTZ,
  content        JSONB
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT ao.id, ao.run_id, ao.agent_id, ao.company_id,
         ao.content->>'repo'           AS repo,
         ao.content->>'commit_sha'     AS commit_sha,
         ao.content->>'feature_intent' AS feature_intent,
         (ao.content->>'generated_at')::timestamptz AS generated_at,
         ao.created_at,
         ao.content
  FROM agent_outputs ao
  WHERE ao.output_type = 'codebase_context'
    AND ao.content->>'repo' = p_target_key
    AND jsonb_array_length(COALESCE(ao.content->'concept_resolution', '[]'::jsonb)) > 0
  ORDER BY ao.created_at DESC
  LIMIT 1;
$$;

COMMENT ON FUNCTION public.get_latest_codebase_context(TEXT) IS
  'BA-facing handoff resolver: returns the latest COMPLETE codebase_context artifact for a target_key '
  '(non-empty concept_resolution). The canonical consumption entry point; the BA never reads agent_outputs directly.';

-- Convenience: just the staleness-relevant header (no full content payload) for quick checks.
CREATE OR REPLACE FUNCTION public.get_latest_codebase_context_meta(p_target_key TEXT)
RETURNS TABLE (
  artifact_id  UUID,
  commit_sha   TEXT,
  generated_at TIMESTAMPTZ,
  n_entities   INT,
  n_signals    INT,
  n_resolved   INT
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT ao.id,
         ao.content->>'commit_sha' AS commit_sha,
         (ao.content->>'generated_at')::timestamptz AS generated_at,
         jsonb_array_length(COALESCE(ao.content->'entities', '[]'::jsonb)),
         jsonb_array_length(COALESCE(ao.content->'domain_signals', '[]'::jsonb)),
         jsonb_array_length(COALESCE(ao.content->'concept_resolution', '[]'::jsonb))
  FROM agent_outputs ao
  WHERE ao.output_type = 'codebase_context'
    AND ao.content->>'repo' = p_target_key
    AND jsonb_array_length(COALESCE(ao.content->'concept_resolution', '[]'::jsonb)) > 0
  ORDER BY ao.created_at DESC
  LIMIT 1;
$$;
