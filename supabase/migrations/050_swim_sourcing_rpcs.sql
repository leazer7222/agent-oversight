-- Migration 050: public RPC surface for swim_sourcing
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 049
-- Status: AUTHORED, NOT APPLIED.
--
-- PostgREST exposes only the `public` schema, so every cross-schema read/write
-- goes through a SECURITY DEFINER function here. This is the established pattern
-- in this codebase (see get_latest_codebase_context, graph_* in 024).
--
-- Every function below is granted to service_role ONLY. The dashboard reaches
-- them through server routes that have already resolved a verified tenant; the
-- browser never calls them. p_company_id is therefore trusted at this layer
-- because the ONLY caller is a server route that derived it from the session -
-- the authorization decision lives in requireTenant(), not here.

BEGIN;

-- ===========================================================================
-- Job queue: claim with lease, heartbeat, finish, reap
-- ===========================================================================
CREATE OR REPLACE FUNCTION public.swim_claim_job(
  p_worker_id     TEXT,
  p_lease_seconds INT DEFAULT 300,
  p_job_types     TEXT[] DEFAULT NULL
)
RETURNS TABLE (
  job_id UUID, company_id UUID, job_type TEXT, payload JSONB,
  attempts INT, max_attempts INT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE v_id UUID;
BEGIN
  -- FOR UPDATE SKIP LOCKED so concurrent workers never claim the same job.
  SELECT j.id INTO v_id
  FROM swim_sourcing.jobs j
  WHERE j.status = 'queued'
    AND j.next_attempt_at <= now()
    AND NOT j.cancel_requested
    AND (p_job_types IS NULL OR j.job_type = ANY(p_job_types))
  ORDER BY j.priority, j.next_attempt_at
  LIMIT 1
  FOR UPDATE SKIP LOCKED;

  IF v_id IS NULL THEN RETURN; END IF;

  RETURN QUERY
  UPDATE swim_sourcing.jobs j
     SET status = 'running',
         attempts = j.attempts + 1,
         worker_id = p_worker_id,
         started_at = coalesce(j.started_at, now()),
         heartbeat_at = now(),
         lease_expires_at = now() + make_interval(secs => p_lease_seconds),
         updated_at = now()
   WHERE j.id = v_id
  RETURNING j.id, j.company_id, j.job_type, j.payload, j.attempts, j.max_attempts;
END $$;

-- Extends the lease. A worker calls this periodically during long work; if it
-- stops calling, the reaper takes the job back. Returns false when the job has
-- been cancelled, which is how cooperative cancellation reaches the worker.
CREATE OR REPLACE FUNCTION public.swim_heartbeat_job(
  p_job_id        UUID,
  p_worker_id     TEXT,
  p_lease_seconds INT DEFAULT 300
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE v_cancelled BOOLEAN;
BEGIN
  UPDATE swim_sourcing.jobs
     SET heartbeat_at = now(),
         lease_expires_at = now() + make_interval(secs => p_lease_seconds),
         updated_at = now()
   WHERE id = p_job_id AND worker_id = p_worker_id AND status = 'running'
  RETURNING cancel_requested INTO v_cancelled;

  IF NOT FOUND THEN RETURN false; END IF;   -- lease lost or job reaped
  RETURN NOT v_cancelled;
END $$;

CREATE OR REPLACE FUNCTION public.swim_finish_job(
  p_job_id    UUID,
  p_worker_id TEXT,
  p_status    TEXT,
  p_result    JSONB DEFAULT NULL,
  p_error     TEXT  DEFAULT NULL
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE v_attempts INT; v_max INT;
BEGIN
  IF p_status NOT IN ('done','failed','blocked','cancelled') THEN
    RAISE EXCEPTION 'invalid terminal status: %', p_status;
  END IF;

  SELECT attempts, max_attempts INTO v_attempts, v_max
  FROM swim_sourcing.jobs WHERE id = p_job_id;
  IF NOT FOUND THEN RETURN false; END IF;

  -- A retryable failure with attempts left goes back to queued with exponential
  -- backoff (2^attempts minutes, capped at 60). 'blocked' is deliberately NOT
  -- retried: it means a precondition failed (missing credential, budget
  -- exceeded) and retrying would just burn the same wall.
  IF p_status = 'failed' AND v_attempts < v_max THEN
    UPDATE swim_sourcing.jobs
       SET status = 'queued',
           error = p_error,
           lease_expires_at = NULL,
           worker_id = NULL,
           next_attempt_at = now() + make_interval(mins => least(power(2, v_attempts)::int, 60)),
           updated_at = now()
     WHERE id = p_job_id;
  ELSE
    UPDATE swim_sourcing.jobs
       SET status = p_status,
           result = coalesce(p_result, result),
           error = p_error,
           lease_expires_at = NULL,
           finished_at = now(),
           updated_at = now()
     WHERE id = p_job_id;
  END IF;
  RETURN true;
END $$;

-- Returns jobs whose lease expired - a crashed worker's work - to the queue.
-- This is the capability public.claim_intake_job lacks entirely.
CREATE OR REPLACE FUNCTION public.swim_reap_expired_jobs()
RETURNS TABLE (reaped_job_id UUID, reaped_attempts INT, outcome TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
BEGIN
  RETURN QUERY
  WITH expired AS (
    SELECT id, attempts, max_attempts FROM swim_sourcing.jobs
    WHERE status = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at < now()
    FOR UPDATE SKIP LOCKED
  ), requeued AS (
    UPDATE swim_sourcing.jobs j
       SET status = CASE WHEN e.attempts < e.max_attempts THEN 'queued' ELSE 'failed' END,
           error = 'lease expired - worker presumed dead',
           worker_id = NULL,
           lease_expires_at = NULL,
           next_attempt_at = now(),
           finished_at = CASE WHEN e.attempts >= e.max_attempts THEN now() ELSE NULL END,
           updated_at = now()
      FROM expired e
     WHERE j.id = e.id
    RETURNING j.id, j.attempts, j.status
  )
  SELECT id, attempts, status FROM requeued;
END $$;

CREATE OR REPLACE FUNCTION public.swim_enqueue_job(
  p_company_id UUID,
  p_job_type   TEXT,
  p_payload    JSONB DEFAULT '{}'::jsonb,
  p_priority   INT DEFAULT 100
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE v_id UUID;
BEGIN
  INSERT INTO swim_sourcing.jobs (company_id, job_type, payload, priority)
  VALUES (p_company_id, p_job_type, coalesce(p_payload, '{}'::jsonb), p_priority)
  RETURNING id INTO v_id;
  RETURN v_id;
END $$;

CREATE OR REPLACE FUNCTION public.swim_cancel_job(p_job_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
BEGIN
  UPDATE swim_sourcing.jobs
     SET cancel_requested = true,
         status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE status END,
         updated_at = now()
   WHERE id = p_job_id AND status IN ('queued','running');
  RETURN FOUND;
END $$;

-- ===========================================================================
-- Facilities: idempotent upsert
-- ===========================================================================
-- Returns whether the row was inserted or matched, so the discovery agent can
-- report "20 found, 3 new" and so a duplicate run provably creates nothing.
CREATE OR REPLACE FUNCTION public.swim_upsert_facility(
  p_company_id UUID,
  p_facility   JSONB
)
RETURNS TABLE (facility_id UUID, was_inserted BOOLEAN)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE v_id UUID; v_inserted BOOLEAN := false;
BEGIN
  IF coalesce(p_facility->>'name', '') = '' THEN
    RAISE EXCEPTION 'facility name is required';
  END IF;
  IF coalesce(p_facility->>'source', '') = '' THEN
    RAISE EXCEPTION 'facility source is required (provenance is mandatory)';
  END IF;

  -- Match on the strong external key first.
  IF p_facility->>'source_ref' IS NOT NULL THEN
    SELECT id INTO v_id FROM swim_sourcing.facilities
    WHERE company_id = p_company_id AND source_ref = p_facility->>'source_ref';
  END IF;

  -- Fall back to name+address, which catches the same place from another source.
  IF v_id IS NULL THEN
    SELECT id INTO v_id FROM swim_sourcing.facilities
    WHERE company_id = p_company_id
      AND lower(name) = lower(p_facility->>'name')
      AND lower(coalesce(address, '')) = lower(coalesce(p_facility->>'address', ''));
  END IF;

  IF v_id IS NULL THEN
    INSERT INTO swim_sourcing.facilities (
      company_id, name, facility_type, address, city, state, postal_code,
      latitude, longitude, distance_miles, phone, website,
      source, source_ref, source_url, attributes, attributes_confidence, unknown_fields)
    VALUES (
      p_company_id,
      p_facility->>'name',
      coalesce(p_facility->>'facility_type', 'unknown'),
      p_facility->>'address', p_facility->>'city', p_facility->>'state',
      p_facility->>'postal_code',
      (p_facility->>'latitude')::double precision,
      (p_facility->>'longitude')::double precision,
      (p_facility->>'distance_miles')::numeric,
      p_facility->>'phone', p_facility->>'website',
      p_facility->>'source', p_facility->>'source_ref', p_facility->>'source_url',
      coalesce(p_facility->'attributes', '{}'::jsonb),
      coalesce(p_facility->'attributes_confidence', '{}'::jsonb),
      coalesce((SELECT array_agg(x) FROM jsonb_array_elements_text(
                 coalesce(p_facility->'unknown_fields', '[]'::jsonb)) x), ARRAY[]::text[]))
    RETURNING id INTO v_id;
    v_inserted := true;
  ELSE
    -- Refresh volatile contact details and the provenance timestamp; never
    -- downgrade a populated column back to NULL on a thinner later result.
    UPDATE swim_sourcing.facilities f
       SET website = coalesce(p_facility->>'website', f.website),
           phone   = coalesce(p_facility->>'phone', f.phone),
           address = coalesce(p_facility->>'address', f.address),
           source_fetched_at = now(),
           updated_at = now()
     WHERE f.id = v_id;
  END IF;

  RETURN QUERY SELECT v_id, v_inserted;
END $$;

CREATE OR REPLACE FUNCTION public.swim_record_qualification(
  p_company_id UUID,
  p_payload    JSONB
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, swim_sourcing, public
AS $$
DECLARE v_id UUID; v_facility UUID; v_status TEXT;
BEGIN
  v_facility := (p_payload->>'facility_id')::uuid;
  v_status   := p_payload->>'status';

  INSERT INTO swim_sourcing.qualifications (
    company_id, facility_id, run_id, model_version, score, status, completeness,
    score_breakdown, verified_fields, inferred_fields, unknown_fields,
    open_questions, disqualifiers)
  VALUES (
    p_company_id, v_facility, (p_payload->>'run_id')::uuid,
    p_payload->>'model_version', (p_payload->>'score')::numeric, v_status,
    (p_payload->>'completeness')::numeric,
    coalesce(p_payload->'score_breakdown', '{}'::jsonb),
    coalesce((SELECT array_agg(x) FROM jsonb_array_elements_text(coalesce(p_payload->'verified_fields','[]'::jsonb)) x), ARRAY[]::text[]),
    coalesce((SELECT array_agg(x) FROM jsonb_array_elements_text(coalesce(p_payload->'inferred_fields','[]'::jsonb)) x), ARRAY[]::text[]),
    coalesce((SELECT array_agg(x) FROM jsonb_array_elements_text(coalesce(p_payload->'unknown_fields','[]'::jsonb)) x), ARRAY[]::text[]),
    coalesce(p_payload->'open_questions', '[]'::jsonb),
    coalesce((SELECT array_agg(x) FROM jsonb_array_elements_text(coalesce(p_payload->'disqualifiers','[]'::jsonb)) x), ARRAY[]::text[]))
  RETURNING id INTO v_id;

  -- Advance the pipeline stage to match the verdict. needs_info is a distinct
  -- stage, not a soft 'qualified': a facility we know too little about must not
  -- enter outreach.
  UPDATE swim_sourcing.facilities
     SET pipeline_stage = CASE v_status
                            WHEN 'qualified'    THEN 'qualified'
                            WHEN 'disqualified' THEN 'disqualified'
                            ELSE 'needs_info' END,
         updated_at = now()
   WHERE id = v_facility AND pipeline_stage IN ('discovered','qualified','needs_info','disqualified');

  RETURN v_id;
END $$;

-- Attributes for one facility, for the qualification agent. Separate from
-- swim_list_facilities because that is a lean projection for the table view and
-- attributes are a jsonb payload the list does not need.
CREATE OR REPLACE FUNCTION public.swim_facility_attributes(p_facility_id UUID)
RETURNS JSONB
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  SELECT jsonb_build_object(
    'facility_id', id,
    'company_id', company_id,
    'distance_miles', distance_miles,
    'attributes', attributes,
    'attributes_confidence', attributes_confidence,
    'unknown_fields', to_jsonb(unknown_fields))
  FROM swim_sourcing.facilities WHERE id = p_facility_id;
$$;

-- ===========================================================================
-- Dashboard reads
-- ===========================================================================
CREATE OR REPLACE FUNCTION public.swim_pipeline_summary(p_company_id UUID)
RETURNS TABLE (stage TEXT, facility_count BIGINT)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  SELECT pipeline_stage, count(*)
  FROM swim_sourcing.facilities WHERE company_id = p_company_id
  GROUP BY pipeline_stage ORDER BY 1;
$$;

CREATE OR REPLACE FUNCTION public.swim_list_facilities(
  p_company_id UUID,
  p_stage      TEXT DEFAULT NULL,
  p_limit      INT  DEFAULT 100
)
RETURNS TABLE (
  facility_id UUID, name TEXT, facility_type TEXT, city TEXT, website TEXT,
  distance_miles NUMERIC, pipeline_stage TEXT, source TEXT, source_url TEXT,
  score NUMERIC, qualification_status TEXT, unknown_count INT, created_at TIMESTAMPTZ
)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  SELECT f.id, f.name, f.facility_type, f.city, f.website, f.distance_miles,
         f.pipeline_stage, f.source, f.source_url,
         q.score, q.status, coalesce(array_length(f.unknown_fields, 1), 0), f.created_at
  FROM swim_sourcing.facilities f
  LEFT JOIN LATERAL (
    SELECT score, status FROM swim_sourcing.qualifications
    WHERE facility_id = f.id ORDER BY created_at DESC LIMIT 1
  ) q ON true
  WHERE f.company_id = p_company_id
    AND (p_stage IS NULL OR f.pipeline_stage = p_stage)
  ORDER BY q.score DESC NULLS LAST, f.created_at DESC
  LIMIT greatest(1, least(p_limit, 500));
$$;

CREATE OR REPLACE FUNCTION public.swim_operations_summary(p_company_id UUID)
RETURNS JSONB
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  SELECT jsonb_build_object(
    'facilities_discovered', (SELECT count(*) FROM swim_sourcing.facilities WHERE company_id = p_company_id),
    'qualified',             (SELECT count(*) FROM swim_sourcing.facilities WHERE company_id = p_company_id AND pipeline_stage = 'qualified'),
    'needs_info',            (SELECT count(*) FROM swim_sourcing.facilities WHERE company_id = p_company_id AND pipeline_stage = 'needs_info'),
    'drafts',                (SELECT count(*) FROM swim_sourcing.outreach_messages WHERE company_id = p_company_id AND status = 'draft'),
    'pending_approvals',     (SELECT count(*) FROM swim_sourcing.outreach_messages WHERE company_id = p_company_id AND status = 'draft'),
    'emails_sent',           (SELECT count(*) FROM swim_sourcing.outreach_messages WHERE company_id = p_company_id AND status = 'sent'),
    'replies_received',      (SELECT count(*) FROM swim_sourcing.outreach_messages WHERE company_id = p_company_id AND direction = 'inbound'),
    'meetings_scheduled',    (SELECT count(*) FROM swim_sourcing.meetings WHERE company_id = p_company_id AND status = 'scheduled'),
    'jobs_queued',           (SELECT count(*) FROM swim_sourcing.jobs WHERE company_id = p_company_id AND status = 'queued'),
    'jobs_running',          (SELECT count(*) FROM swim_sourcing.jobs WHERE company_id = p_company_id AND status = 'running'),
    'jobs_failed',           (SELECT count(*) FROM swim_sourcing.jobs WHERE company_id = p_company_id AND status = 'failed'),
    'suppressed',            (SELECT count(*) FROM swim_sourcing.suppression_list WHERE company_id = p_company_id)
  );
$$;

-- service_role only, for every function in this migration.
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.proname AS fn, pg_get_function_identity_arguments(p.oid) AS args
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname LIKE 'swim\_%'
  LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I(%s) FROM PUBLIC, anon, authenticated', r.fn, r.args);
    EXECUTE format('GRANT EXECUTE ON FUNCTION public.%I(%s) TO service_role', r.fn, r.args);
  END LOOP;
END $$;

COMMIT;
