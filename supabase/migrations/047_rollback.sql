-- Rollback for migration 047 (P0-0 database security hardening)
--
-- WARNING: running this RESTORES THE VULNERABLE STATE documented in
-- docs/swim-school-facility-sourcing-plan.md ("Addendum: Live Database
-- Verification"). It re-opens anonymous RPC execution, anonymous table access,
-- and authenticated write access to the ledger and audit log.
--
-- Use only if a production break is positively traced to 047 and the fix cannot
-- wait. Prefer a narrow forward fix: re-GRANT the single object that broke, and
-- record why, rather than reverting the whole migration.
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Reverts: 047_p0_0_database_hardening.sql

BEGIN;

-- Section F reverse: cost views back to SECURITY DEFINER (the PG default).
ALTER VIEW public.agent_cost_summary   SET (security_invoker = off);
ALTER VIEW public.project_cost_summary SET (security_invoker = off);
ALTER VIEW public.company_cost_summary SET (security_invoker = off);

-- Section F reverse: unpin search_path on the 7 SECURITY INVOKER functions.
ALTER FUNCTION public.updated_at_now()                        RESET search_path;
ALTER FUNCTION public.touch_codebase_context_cache()          RESET search_path;
ALTER FUNCTION public.graph_node_epistemic_status(text, text)  RESET search_path;
ALTER FUNCTION public.claim_intake_job(text)                   RESET search_path;
ALTER FUNCTION platform.apply_append_only_rls(text, text)      RESET search_path;
ALTER FUNCTION platform.enforce_cbc_frozen_fields()            RESET search_path;
ALTER FUNCTION product_graph.enforce_node_immutability()       RESET search_path;

-- Section E reverse: restore Supabase's stock blanket grants on public.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON SEQUENCES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA platform      GRANT ALL ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA product_graph GRANT ALL ON TABLES TO anon, authenticated;

GRANT ALL ON ALL TABLES    IN SCHEMA public        TO anon, authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public        TO anon, authenticated;
GRANT ALL ON ALL TABLES    IN SCHEMA platform      TO anon, authenticated;
GRANT ALL ON ALL TABLES    IN SCHEMA product_graph TO anon, authenticated;

-- Section D reverse: permissive roles=public policies on the job queue.
DROP POLICY IF EXISTS service_role_select ON public.agile_intake_jobs;
DROP POLICY IF EXISTS service_role_insert ON public.agile_intake_jobs;
DROP POLICY IF EXISTS service_role_update ON public.agile_intake_jobs;
CREATE POLICY read_all   ON public.agile_intake_jobs FOR SELECT USING (true);
CREATE POLICY insert_all ON public.agile_intake_jobs FOR INSERT WITH CHECK (true);
CREATE POLICY update_all ON public.agile_intake_jobs FOR UPDATE USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_role_select ON platform.cbc_identity_registry;
DROP POLICY IF EXISTS service_role_insert ON platform.cbc_identity_registry;
DROP POLICY IF EXISTS service_role_update ON platform.cbc_identity_registry;
CREATE POLICY read_all   ON platform.cbc_identity_registry FOR SELECT USING (true);
CREATE POLICY insert_all ON platform.cbc_identity_registry FOR INSERT WITH CHECK (true);
CREATE POLICY update_all ON platform.cbc_identity_registry FOR UPDATE USING (true) WITH CHECK (true);

-- Section C reverse: authenticated full access to the ledger and registry tables.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['agent_outputs','agent_events','audit_log','agents','companies',
                           'projects','agent_definitions','agent_qa_results','policies']
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS service_role_all ON public.%I', t);
    EXECUTE format('CREATE POLICY authenticated_select ON public.%I FOR SELECT TO authenticated USING (true)', t);
    EXECUTE format('CREATE POLICY authenticated_insert ON public.%I FOR INSERT TO authenticated WITH CHECK (true)', t);
    EXECUTE format('CREATE POLICY authenticated_update ON public.%I FOR UPDATE TO authenticated USING (true)', t);
    EXECUTE format('CREATE POLICY authenticated_delete ON public.%I FOR DELETE TO authenticated USING (true)', t);
  END LOOP;
END $$;

-- Section B reverse: RLS back off on the 8 tables.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['event_type_registry','output_type_registry','pipeline_config',
                           'contractor_rows','contractor_evidence','contractor_approval_queue',
                           'contractor_sync_log','codebase_context_cache']
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS service_role_all ON public.%I', t);
    EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;

-- Section A reverse: restore EXECUTE to anon/authenticated on all functions.
ALTER DEFAULT PRIVILEGES IN SCHEMA public        GRANT EXECUTE ON FUNCTIONS TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA platform      GRANT EXECUTE ON FUNCTIONS TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA product_graph GRANT EXECUTE ON FUNCTIONS TO anon, authenticated;

DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT n.nspname AS schema_name, p.proname AS fn_name,
           pg_get_function_identity_arguments(p.oid) AS args
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname IN ('public','platform','product_graph') AND p.prokind = 'f'
  LOOP
    EXECUTE format('GRANT EXECUTE ON FUNCTION %I.%I(%s) TO anon, authenticated',
                   r.schema_name, r.fn_name, r.args);
  END LOOP;
END $$;

COMMIT;
