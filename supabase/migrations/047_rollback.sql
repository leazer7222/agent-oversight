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

-- ---------------------------------------------------------------------------
-- FIDELITY NOTES (what this script can and cannot restore exactly)
-- ---------------------------------------------------------------------------
-- Post-deployment rollback is NOT the same thing as a transaction rollback. If
-- 047 fails before COMMIT, Postgres reverts everything automatically and this
-- file is irrelevant. This file is for deliberately reversing an ALREADY
-- COMMITTED 047, and it cannot be byte-identical:
--
--  1. Three functions originally had a NULL proacl (no ACL row at all, relying on
--     the built-in default of EXECUTE to PUBLIC). Once 047 materialises an ACL,
--     "NULL" cannot be recreated. Granting EXECUTE to PUBLIC below is
--     FUNCTIONALLY equivalent but catalog-visibly different.
--  2. Default privileges: schemas platform and product_graph had NO default-ACL
--     entry before 047. This script restores the built-in behaviour (EXECUTE to
--     PUBLIC) rather than the absence of an entry.
--  3. Views: the three cost views had no reloptions at all. RESET removes the
--     option rather than setting it to false, which is the closest restoration.
--  4. Default privileges owned by supabase_admin were never touched by 047 and
--     are not touched here.
--
-- Prefer a NARROW FORWARD GRANT for an isolated regression over running this
-- whole file, which re-opens every hole P0-0 closed.

-- Section F reverse: cost views back to the PG default (no explicit option).
ALTER VIEW public.agent_cost_summary   RESET (security_invoker);
ALTER VIEW public.project_cost_summary RESET (security_invoker);
ALTER VIEW public.company_cost_summary RESET (security_invoker);

-- Section F reverse: unpin search_path on the 7 SECURITY INVOKER functions.
ALTER FUNCTION public.updated_at_now()                        RESET search_path;
ALTER FUNCTION public.touch_codebase_context_cache()          RESET search_path;
ALTER FUNCTION public.graph_node_epistemic_status(text, text)  RESET search_path;
ALTER FUNCTION public.claim_intake_job(text)                   RESET search_path;
ALTER FUNCTION platform.apply_append_only_rls(text, text)      RESET search_path;
ALTER FUNCTION platform.enforce_cbc_frozen_fields()            RESET search_path;
ALTER FUNCTION product_graph.enforce_node_immutability()       RESET search_path;

-- Section E reverse: restore Supabase's stock blanket grants on public ONLY.
--
-- DEFECT FIXED 2026-10-20: earlier versions of this file also granted ALL on
-- platform and product_graph tables to anon/authenticated. Those grants NEVER
-- EXISTED - verified against the live catalog, which returned "(none)" for
-- anon/authenticated table grants outside schema public, and anon holds no USAGE
-- on either schema. Restoring them would have granted MORE than the original
-- state, i.e. a rollback that quietly escalated privilege. Removed.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT ALL ON SEQUENCES TO anon, authenticated;

GRANT ALL ON ALL TABLES    IN SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;

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

-- Section A reverse: restore EXECUTE on all functions.
--
-- DEFECT FIXED 2026-10-20: this must restore the grant to **PUBLIC** as well as
-- to anon/authenticated. The original ACL was
--   =X/postgres  postgres=X/postgres  anon=X/postgres  authenticated=X/postgres  service_role=X/postgres
-- and the leading `=X/postgres` is the PUBLIC grant. An earlier version restored
-- only anon/authenticated, which would have left a rollback that did not actually
-- return the database to its prior state.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO PUBLIC, anon, authenticated;
-- platform / product_graph had no default-ACL entry originally; PUBLIC is the
-- built-in default for functions, so this restores equivalent behaviour.
ALTER DEFAULT PRIVILEGES IN SCHEMA platform      GRANT EXECUTE ON FUNCTIONS TO PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA product_graph GRANT EXECUTE ON FUNCTIONS TO PUBLIC;

DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT n.nspname AS schema_name, p.proname AS fn_name,
           pg_get_function_identity_arguments(p.oid) AS args
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname IN ('public','platform','product_graph') AND p.prokind = 'f'
  LOOP
    EXECUTE format('GRANT EXECUTE ON FUNCTION %I.%I(%s) TO PUBLIC, anon, authenticated',
                   r.schema_name, r.fn_name, r.args);
  END LOOP;
END $$;

COMMIT;
