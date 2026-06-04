-- Migration 036: codebase_context_cache (CCA P1 truth service)
--
-- Commit-scoped, reusable cache of the deterministic inventory + coverage (+ optional
-- semantic context). Keyed by (commit_sha, parser_version) so a parser improvement
-- invalidates the cache even at an unchanged commit. agent_outputs remains the PUBLISHED
-- artifact store; this table is the reusable truth cache (do not conflate - design 11).
--
-- product_key already scopes rows; tenant_id is retained as a nullable annotation column
-- and intentionally kept OUT of the unique key to avoid the NULL-uniqueness trap
-- (NULL <> NULL in Postgres - see LESSONS budget_periods).
-- Apply to project: hdhovyrlnfojtkqbcegh

CREATE TABLE public.codebase_context_cache (
  id                    UUID        NOT NULL DEFAULT gen_random_uuid(),
  tenant_id             UUID,
  product_key           TEXT        NOT NULL,
  repo                  TEXT        NOT NULL,
  branch                TEXT,
  commit_sha            TEXT        NOT NULL,
  parser_version        TEXT        NOT NULL,
  inventory_json        JSONB       NOT NULL,
  coverage_report_json  JSONB       NOT NULL,
  semantic_context_json JSONB,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id),
  UNIQUE (product_key, repo, commit_sha, parser_version)
);

COMMENT ON TABLE public.codebase_context_cache IS
  'CCA commit-scoped deterministic inventory + coverage cache. Key (product_key,repo,commit_sha,parser_version). '
  'Reusable across every feature at the same commit. Not the published-artifact store (that is agent_outputs).';

CREATE INDEX ix_ccc_lookup ON public.codebase_context_cache (product_key, repo, commit_sha, parser_version);
CREATE INDEX ix_ccc_commit ON public.codebase_context_cache (commit_sha);

-- Keep updated_at fresh on UPSERT-as-update.
CREATE OR REPLACE FUNCTION public.touch_codebase_context_cache()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_ccc_touch
  BEFORE UPDATE ON public.codebase_context_cache
  FOR EACH ROW EXECUTE FUNCTION public.touch_codebase_context_cache();
