-- Migration 034: Agile intake job queue (Phase 1b in-app trigger)
--   public.agile_intake_jobs: the dashboard ENQUEUES an intake job; a worker
--   (agents/teams/agile/worker.py, local or hosted) CLAIMS and executes PCA
--   run_intake, then writes the result pointers back.
--
-- The trigger model (dashboard vs CLI) is decoupled from execution: both write the
-- same intake_assessment / clarification_brief artifacts. This table holds queue STATE
-- and pointers only - artifact bodies stay in agent_outputs.
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 001_companies (public.companies), 033_pca_intake_output_types.sql
-- Relates to: docs/agile-pca-integration-plan.md (Interaction surface & execution model)

CREATE TABLE public.agile_intake_jobs (
  id            UUID        NOT NULL DEFAULT gen_random_uuid(),
  company_id    UUID        NOT NULL,
  product_key   TEXT        NOT NULL,
  workspace_id  TEXT        NOT NULL DEFAULT 'reformai-product',
  pass          TEXT        NOT NULL DEFAULT 'a' CHECK (pass IN ('a', 'b')),
  intake        JSONB       NOT NULL,                 -- [{source_type, text}]
  answers       JSONB,                                -- pass b: [{question, answer}]
  parent_job_id UUID,                                 -- pass b -> the original job
  status        TEXT        NOT NULL DEFAULT 'queued'
                  CHECK (status IN ('queued', 'running', 'clarify', 'done', 'blocked', 'error')),
  decision      TEXT        CHECK (decision IN ('proceed_direct', 'clarify', 'block')),
  assessment_id UUID,                                 -- agent_outputs id
  brief_id      UUID,                                 -- agent_outputs id
  pca_run_id    UUID,
  error         TEXT,
  created_by    TEXT        NOT NULL DEFAULT 'dashboard',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at    TIMESTAMPTZ,
  finished_at   TIMESTAMPTZ,
  PRIMARY KEY (id)
);

ALTER TABLE public.agile_intake_jobs
  ADD CONSTRAINT fk_intake_company FOREIGN KEY (company_id)
  REFERENCES public.companies(id) ON DELETE RESTRICT;
ALTER TABLE public.agile_intake_jobs
  ADD CONSTRAINT fk_intake_parent FOREIGN KEY (parent_job_id)
  REFERENCES public.agile_intake_jobs(id) ON DELETE RESTRICT;

CREATE INDEX ix_intake_jobs_status  ON public.agile_intake_jobs (status, created_at);
CREATE INDEX ix_intake_jobs_company ON public.agile_intake_jobs (company_id, created_at DESC);

COMMENT ON TABLE public.agile_intake_jobs IS
  'Agile front-door intake job queue. Dashboard enqueues; worker.py executes PCA run_intake. '
  'Queue state + result pointers only; artifact bodies live in agent_outputs.';

-- Atomic claim for the worker. Marks the oldest queued job running and returns it (SKIP LOCKED
-- so concurrent workers never grab the same job).
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
       SET status = 'running', started_at = now(), updated_at = now(), created_by = created_by
     WHERE id = v_id
    RETURNING *;
END;
$$;

-- RLS: service-role (API routes + worker) bypasses RLS. Enable + permissive read/insert/update,
-- block delete. No tenant-isolation policy in Phase 1b (access is server-side service role only).
ALTER TABLE public.agile_intake_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "no_delete"  ON public.agile_intake_jobs AS RESTRICTIVE FOR DELETE USING (false);
CREATE POLICY "read_all"   ON public.agile_intake_jobs FOR SELECT USING (true);
CREATE POLICY "insert_all" ON public.agile_intake_jobs FOR INSERT WITH CHECK (true);
CREATE POLICY "update_all" ON public.agile_intake_jobs FOR UPDATE USING (true);

-- Verification (after applying):
-- SELECT tablename FROM pg_tables WHERE tablename = 'agile_intake_jobs';
-- SELECT proname FROM pg_proc WHERE proname = 'claim_intake_job';
