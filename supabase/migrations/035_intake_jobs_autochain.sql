-- Migration 035: extend agile_intake_jobs for the PCA -> BA auto-chain
--   After a proceed_direct PCA brief, the worker continues to BA (reusing the latest
--   codebase_context) and parks the job at scope_review (Gate A). These columns track the
--   scoping stage + result so the dashboard can show the progression and link to the feature.
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 034_agile_intake_jobs.sql

ALTER TABLE public.agile_intake_jobs ADD COLUMN IF NOT EXISTS stage             TEXT;
ALTER TABLE public.agile_intake_jobs ADD COLUMN IF NOT EXISTS feature_key       TEXT;
ALTER TABLE public.agile_intake_jobs ADD COLUMN IF NOT EXISTS scope_artifact_id UUID;
ALTER TABLE public.agile_intake_jobs ADD COLUMN IF NOT EXISTS scope_ready       BOOLEAN;

-- Extend the status set: 'scoping' (BA running), 'scoped' (BA done, awaiting Gate A).
ALTER TABLE public.agile_intake_jobs DROP CONSTRAINT IF EXISTS agile_intake_jobs_status_check;
ALTER TABLE public.agile_intake_jobs ADD CONSTRAINT agile_intake_jobs_status_check
  CHECK (status IN ('queued', 'running', 'clarify', 'done', 'blocked', 'error', 'scoping', 'scoped'));

COMMENT ON COLUMN public.agile_intake_jobs.stage IS
  'Current lifecycle stage of the job: clarifying | scoping | scope_review (Gate A).';
COMMENT ON COLUMN public.agile_intake_jobs.feature_key IS
  'product_graph FEAT-* key produced by BA in the auto-chain.';

-- Recreate claim_intake_job so its RETURNS SETOF rowtype picks up the new columns above.
-- (A SETOF <table> function caches the table's rowtype; after ALTER TABLE ADD COLUMN it must
-- be re-created or it returns an empty/mismatched result while still claiming the row.)
CREATE OR REPLACE FUNCTION public.claim_intake_job(p_worker TEXT DEFAULT 'worker')
RETURNS SETOF public.agile_intake_jobs
LANGUAGE plpgsql
AS $$
DECLARE v_id UUID;
BEGIN
  SELECT id INTO v_id FROM public.agile_intake_jobs
    WHERE status = 'queued' ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED;
  IF v_id IS NULL THEN
    RETURN;
  END IF;
  RETURN QUERY
    UPDATE public.agile_intake_jobs
       SET status = 'running', started_at = now(), updated_at = now()
     WHERE id = v_id
    RETURNING *;
END;
$$;

-- Verification:
-- SELECT column_name FROM information_schema.columns WHERE table_name='agile_intake_jobs'
--   AND column_name IN ('stage','feature_key','scope_artifact_id','scope_ready');
