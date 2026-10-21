-- Migration 054: read-only RPCs for the sourcing workspace UI
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 053
-- Status: AUTHORED 2026-10-20 for the pool-acquisition workspace redesign.
--
-- Two narrowly scoped READ functions so the workspace can show a facility's
-- full research record and a conversation's full message history in one
-- request each. No writes, no new tables, no columns. service_role only,
-- like every other swim_* function (PostgREST does not expose swim_sourcing).

BEGIN;

-- All facilities for a company with attributes, confidence, contacts and the
-- latest qualification - the same shape as swim_facility_attributes(), batched.
CREATE OR REPLACE FUNCTION public.swim_facility_details(
  p_company_id UUID,
  p_limit      INT DEFAULT 200
)
RETURNS JSONB
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  SELECT coalesce(jsonb_agg(public.swim_facility_attributes(f.id) ORDER BY f.name), '[]'::jsonb)
  FROM (
    SELECT id, name FROM swim_sourcing.facilities
    WHERE company_id = p_company_id
    ORDER BY name
    LIMIT greatest(1, least(p_limit, 500))
  ) f;
$$;

-- Every message in every thread for a company, oldest first per thread.
CREATE OR REPLACE FUNCTION public.swim_thread_messages(
  p_company_id UUID,
  p_limit      INT DEFAULT 500
)
RETURNS TABLE (
  message_id UUID, thread_id UUID, facility_id UUID, direction TEXT, status TEXT,
  subject TEXT, body TEXT, sent_at TIMESTAMPTZ, received_at TIMESTAMPTZ, created_at TIMESTAMPTZ
)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  SELECT m.id, m.thread_id, t.facility_id, m.direction, m.status, m.subject, m.body,
         m.sent_at, m.received_at, m.created_at
  FROM swim_sourcing.outreach_messages m
  JOIN swim_sourcing.outreach_threads t ON t.id = m.thread_id
  WHERE m.company_id = p_company_id
  ORDER BY m.thread_id, m.created_at
  LIMIT greatest(1, least(p_limit, 2000));
$$;

DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.proname AS fn, pg_get_function_identity_arguments(p.oid) AS args
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname IN ('swim_facility_details', 'swim_thread_messages')
  LOOP
    EXECUTE format('REVOKE ALL ON FUNCTION public.%I(%s) FROM PUBLIC, anon, authenticated', r.fn, r.args);
    EXECUTE format('GRANT EXECUTE ON FUNCTION public.%I(%s) TO service_role', r.fn, r.args);
  END LOOP;
END $$;

COMMIT;
