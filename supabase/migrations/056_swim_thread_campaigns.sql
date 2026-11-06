-- Migration 056: thread -> campaign lookup for redrafting
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 049, 053
-- Status: AUTHORED 2026-11-06.
--
-- Threads are unique on (facility_id, campaign_id). When the business profile
-- changes, the worker re-composes every UNSENT draft; to append the new draft to
-- the existing thread (instead of opening a duplicate conversation) it needs
-- each thread's campaign_id, which swim_list_threads does not return. This is a
-- read-only, service_role-only helper in `public` (PostgREST does not expose
-- swim_sourcing). No tables or constraints change.

BEGIN;

CREATE OR REPLACE FUNCTION public.swim_list_thread_campaigns(
  p_company_id UUID
)
RETURNS TABLE (
  thread_id UUID, facility_id UUID, facility_name TEXT, campaign_id UUID, state TEXT,
  inbound_count INT, latest_outbound_status TEXT
)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, swim_sourcing, public STABLE
AS $$
  SELECT t.id, f.id, f.name, t.campaign_id, t.state,
         (SELECT count(*)::int FROM swim_sourcing.outreach_messages m
           WHERE m.thread_id = t.id AND m.direction = 'inbound'),
         (SELECT m.status FROM swim_sourcing.outreach_messages m
           WHERE m.thread_id = t.id AND m.direction = 'outbound'
           ORDER BY m.created_at DESC LIMIT 1)
  FROM swim_sourcing.outreach_threads t
  JOIN swim_sourcing.facilities f ON f.id = t.facility_id
  WHERE t.company_id = p_company_id
  ORDER BY t.updated_at DESC;
$$;

REVOKE ALL ON FUNCTION public.swim_list_thread_campaigns(UUID) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.swim_list_thread_campaigns(UUID) TO service_role;

COMMIT;
