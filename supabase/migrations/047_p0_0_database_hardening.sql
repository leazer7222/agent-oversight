-- Migration 047: P0-0 database security hardening
--
-- Closes the database attack surface that is reachable WITHOUT going through the
-- Next.js application, discovered during the 2026-10-20 audit
-- (docs/swim-school-facility-sourcing-plan.md, "Addendum: Live Database Verification").
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 001..046 (all applied)
-- Authorization: P0-0 only. Prepared in-repo; NOT applied to production by this commit.
--
-- ---------------------------------------------------------------------------
-- WHY THIS IS SAFE (verified before authoring, not assumed)
-- ---------------------------------------------------------------------------
-- 1. No application code uses the anon/publishable key. src/lib/supabase/client.ts
--    (createBrowserClient) has ZERO imports anywhere in src/. No "use client"
--    component references supabase. Verified by grep.
-- 2. All 28 API routes use createServiceRoleClient() (src/lib/supabase/server.ts:30).
--    Every one of the 30 .rpc() call sites is inside a server route.
-- 3. All Python agents authenticate with SUPABASE_SERVICE_ROLE_KEY.
-- 4. service_role holds BYPASSRLS, so enabling RLS and revoking anon/authenticated
--    privileges does not affect any current server-side code path.
-- Therefore every revoke below is expected to be behaviour-neutral for the app
-- while removing anonymous reachability. The post-apply verification script
-- (scripts/verify_p0_0_security.py) proves both halves of that claim.
--
-- ---------------------------------------------------------------------------
-- ROLLBACK
-- ---------------------------------------------------------------------------
-- This migration only removes privileges and tightens policies; it creates no
-- objects and alters no data. To revert, run supabase/migrations/047_rollback.sql
-- (authored alongside this file). Rolling back restores the vulnerable state and
-- should only be used if an unforeseen break is traced to this migration.
--
-- ---------------------------------------------------------------------------
-- OPERATIONAL IMPACT
-- ---------------------------------------------------------------------------
-- Expected: none on the dashboard, ingest, agents, or the agile worker.
-- Breaks (by design): any direct PostgREST access using the anon or an end-user
-- JWT. There is no such caller today. If one is added later it must go through a
-- server route, which is the intended architecture.

BEGIN;

-- ===========================================================================
-- SECTION A (P0-0A) - Revoke EXECUTE on all RPC functions from anon/authenticated
-- ===========================================================================
-- 35 SECURITY DEFINER functions were executable by anon via /rest/v1/rpc/*,
-- including ledger writers (ingest_telemetry_event, write_run_started_artifacts,
-- write_run_completed_artifacts) and approval mutators (graph_ratify_node).
-- 7 additional SECURITY INVOKER functions were likewise exposed, including
-- public.claim_intake_job - an anonymous caller could claim agent work.
--
-- A loop is used rather than 42 hand-written signatures so that function
-- OVERLOADS are handled exactly (write_run_started_artifacts has two) and so the
-- statement cannot silently miss one because a signature was transcribed wrong.
--
-- Scope note, measured not assumed: only `public` is actually reachable by anon.
-- anon/authenticated hold NO USAGE on platform, product_graph, telemetry,
-- cost_intelligence, runtime_governance or model_intelligence, so the 35 exploitable
-- functions are all in public. The loop also covers platform and product_graph as
-- defence in depth, so that granting schema USAGE later cannot silently re-open them.
--
-- Verified safe to run: zero functions in these schemas are extension-owned
-- (checked via pg_depend deptype='e'), and all 42 are owned by postgres, so no
-- REVOKE here can fail on ownership and abort the migration.
-- RAISE NOTICE records the count for the apply log.

-- MUST REVOKE FROM **PUBLIC**, NOT JUST anon/authenticated.
-- The live ACL on these functions is:
--     =X/postgres  postgres=X/postgres  anon=X/postgres  authenticated=X/postgres  service_role=X/postgres
-- The leading `=X/postgres` is a grant of EXECUTE to PUBLIC, and PUBLIC includes
-- every role - anon among them. Revoking only the explicit anon/authenticated
-- entries would leave the PUBLIC grant intact and anon would KEEP execute access:
-- the migration would appear to succeed and close nothing. Verified against the
-- live catalog: all 42 functions carry a PUBLIC grant (39 in public, 2 in
-- platform, 1 in product_graph; 3 of them via a NULL proacl, whose built-in
-- default for functions is also EXECUTE to PUBLIC).
--
-- Tables are NOT affected by this: their relacl carries no PUBLIC entry
-- (postgres=.../anon=.../authenticated=.../service_role=... only), so Section E's
-- revoke is sufficient there. PUBLIC is included there anyway as a no-op guard.
--
-- Because revoking PUBLIC also strips the 3 NULL-ACL functions' only grant,
-- service_role is re-granted EXECUTE explicitly afterwards. service_role is the
-- sole legitimate caller, and assertion A3 checks this did not regress.

DO $$
DECLARE
  r        record;
  n_count  int := 0;
BEGIN
  FOR r IN
    SELECT n.nspname AS schema_name,
           p.proname AS fn_name,
           pg_get_function_identity_arguments(p.oid) AS args
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname IN ('public', 'platform', 'product_graph')
      AND p.prokind = 'f'
  LOOP
    EXECUTE format(
      'REVOKE ALL ON FUNCTION %I.%I(%s) FROM PUBLIC, anon, authenticated',
      r.schema_name, r.fn_name, r.args
    );
    EXECUTE format(
      'GRANT EXECUTE ON FUNCTION %I.%I(%s) TO service_role',
      r.schema_name, r.fn_name, r.args
    );
    n_count := n_count + 1;
  END LOOP;
  RAISE NOTICE '[047A] Revoked PUBLIC/anon/authenticated and re-granted service_role on % function(s)', n_count;
END $$;

-- Stop recurrence: functions created later must not inherit EXECUTE for anon.
-- Supabase's stock defaults grant it, which is how all 42 above became exposed.
--
-- PARTIAL COVERAGE, stated honestly: ALTER DEFAULT PRIVILEGES only affects the
-- default-ACL entry of the role running it. Schema public has TWO such entries -
-- one owned by `postgres` and one by `supabase_admin`. This migration runs as
-- `postgres`, which is NOT a member of `supabase_admin` (verified:
-- pg_has_role -> false) and therefore cannot amend that second entry. Objects
-- created by `supabase_admin` would still inherit anon grants. In practice every
-- object in this project is created by migrations running as postgres, so the gap
-- is theoretical - but it is a gap, not a guarantee, and closing it would need
-- Supabase support or a dashboard-level change.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA platform
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA product_graph
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public        GRANT EXECUTE ON FUNCTIONS TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA platform      GRANT EXECUTE ON FUNCTIONS TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA product_graph GRANT EXECUTE ON FUNCTIONS TO service_role;

-- GLOBAL guard, covering schemas that do not exist yet.
-- The three per-schema statements above only protect schemas named today. Any
-- NEW schema - swim_sourcing being the immediate case - would otherwise fall
-- back to PostgreSQL's built-in default, which grants EXECUTE on new functions
-- to PUBLIC, and the exposure this migration closes would silently reappear the
-- first time a function is created there.
--
-- A default-privilege entry with no IN SCHEMA clause applies to every schema for
-- objects created by this role. Scoped to `postgres` because that is the role
-- migrations run as (verified: current_user = session_user = postgres); it does
-- not touch supabase_admin-owned entries for storage/realtime/auth internals,
-- which postgres does not create and is not a member of.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres
  GRANT EXECUTE ON FUNCTIONS TO service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres
  REVOKE ALL ON TABLES FROM anon, authenticated;

-- ===========================================================================
-- SECTION B (P0-0B) - Enable RLS on the 8 unprotected public tables
-- ===========================================================================
-- These tables had RLS OFF *and* full DML+TRUNCATE granted to anon, so an
-- anonymous caller could read, modify, or TRUNCATE them. Verified exploitable:
--   GET /rest/v1/contractor_rows?select=id&limit=1  (anon key) -> HTTP 200
-- service_role bypasses RLS, so the contractor pipeline, the CCA cache writer,
-- and the registries continue to work unchanged.

ALTER TABLE public.event_type_registry       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.output_type_registry      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pipeline_config           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contractor_rows           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contractor_evidence       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contractor_approval_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contractor_sync_log       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.codebase_context_cache    ENABLE ROW LEVEL SECURITY;

-- Explicit service_role policies, mirroring the existing convention on
-- public.runs and public.project_state. Not strictly required (BYPASSRLS covers
-- it) but it documents the intended sole caller for the next reader.
CREATE POLICY service_role_all ON public.event_type_registry
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all ON public.output_type_registry
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all ON public.pipeline_config
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all ON public.contractor_rows
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all ON public.contractor_evidence
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all ON public.contractor_approval_queue
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all ON public.contractor_sync_log
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all ON public.codebase_context_cache
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ===========================================================================
-- SECTION C (P0-0C) - Remove authenticated write access to the ledger
-- ===========================================================================
-- Every one of these tables carried authenticated_insert/update/delete policies
-- with USING (true) - so any signed-in user could rewrite or empty them.
-- public.agent_outputs is documented as immutable artifact storage and
-- public.audit_log is the record of record; both were live-updatable.
--
-- Dropped rather than narrowed because there are ZERO authenticated users today
-- (no auth UI exists), so dropping is behaviour-neutral AND maximally safe.
-- P0-1 reintroduces tenant-scoped SELECT policies bound to a verified identity.
--
-- NOTE (deliberate limit, see "Remaining Risks" in the plan): RLS does not bind
-- service_role. These policies stop *authenticated* mutation; they cannot stop a
-- holder of the service-role key. True append-only enforcement against
-- service_role requires BEFORE UPDATE/DELETE triggers and is out of P0-0 scope.

DROP POLICY IF EXISTS authenticated_select ON public.agent_outputs;
DROP POLICY IF EXISTS authenticated_insert ON public.agent_outputs;
DROP POLICY IF EXISTS authenticated_update ON public.agent_outputs;
DROP POLICY IF EXISTS authenticated_delete ON public.agent_outputs;

DROP POLICY IF EXISTS authenticated_select ON public.agent_events;
DROP POLICY IF EXISTS authenticated_insert ON public.agent_events;
DROP POLICY IF EXISTS authenticated_update ON public.agent_events;
DROP POLICY IF EXISTS authenticated_delete ON public.agent_events;

DROP POLICY IF EXISTS authenticated_select ON public.audit_log;
DROP POLICY IF EXISTS authenticated_insert ON public.audit_log;
DROP POLICY IF EXISTS authenticated_update ON public.audit_log;
DROP POLICY IF EXISTS authenticated_delete ON public.audit_log;

DROP POLICY IF EXISTS authenticated_select ON public.agents;
DROP POLICY IF EXISTS authenticated_insert ON public.agents;
DROP POLICY IF EXISTS authenticated_update ON public.agents;
DROP POLICY IF EXISTS authenticated_delete ON public.agents;

DROP POLICY IF EXISTS authenticated_select ON public.companies;
DROP POLICY IF EXISTS authenticated_insert ON public.companies;
DROP POLICY IF EXISTS authenticated_update ON public.companies;
DROP POLICY IF EXISTS authenticated_delete ON public.companies;

DROP POLICY IF EXISTS authenticated_select ON public.projects;
DROP POLICY IF EXISTS authenticated_insert ON public.projects;
DROP POLICY IF EXISTS authenticated_update ON public.projects;
DROP POLICY IF EXISTS authenticated_delete ON public.projects;

DROP POLICY IF EXISTS authenticated_select ON public.agent_definitions;
DROP POLICY IF EXISTS authenticated_insert ON public.agent_definitions;
DROP POLICY IF EXISTS authenticated_update ON public.agent_definitions;
DROP POLICY IF EXISTS authenticated_delete ON public.agent_definitions;

DROP POLICY IF EXISTS authenticated_select ON public.agent_qa_results;
DROP POLICY IF EXISTS authenticated_insert ON public.agent_qa_results;
DROP POLICY IF EXISTS authenticated_update ON public.agent_qa_results;
DROP POLICY IF EXISTS authenticated_delete ON public.agent_qa_results;

DROP POLICY IF EXISTS authenticated_select ON public.policies;
DROP POLICY IF EXISTS authenticated_insert ON public.policies;
DROP POLICY IF EXISTS authenticated_update ON public.policies;
DROP POLICY IF EXISTS authenticated_delete ON public.policies;

CREATE POLICY service_role_all ON public.agent_outputs
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all ON public.agent_events
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all ON public.audit_log
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all ON public.agents
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all ON public.companies
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all ON public.projects
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all ON public.agent_definitions
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all ON public.agent_qa_results
  FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY service_role_all ON public.policies
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ===========================================================================
-- SECTION D (P0-0D/F) - Close anonymous job injection into the agent queue
-- ===========================================================================
-- public.agile_intake_jobs carried insert_all / read_all / update_all policies
-- scoped to roles=public (which INCLUDES anon), on top of a full anon DML grant.
-- An anonymous caller could therefore enqueue work that the agile worker would
-- pick up and execute against a real LLM key - anonymous spend, under the
-- platform's own credentials. This is beyond the original audit's findings and
-- is the most directly abusable item in P0-0.
--
-- Replaced with service_role-only access. The dashboard enqueues via
-- /api/agile/intake (service role) and worker.py claims via the service-role
-- key, so both current callers are unaffected.

DROP POLICY IF EXISTS read_all   ON public.agile_intake_jobs;
DROP POLICY IF EXISTS insert_all ON public.agile_intake_jobs;
DROP POLICY IF EXISTS update_all ON public.agile_intake_jobs;
-- no_delete (restrictive, qual=false) is retained: it is a correct protection.

CREATE POLICY service_role_select ON public.agile_intake_jobs
  FOR SELECT TO service_role USING (true);
CREATE POLICY service_role_insert ON public.agile_intake_jobs
  FOR INSERT TO service_role WITH CHECK (true);
CREATE POLICY service_role_update ON public.agile_intake_jobs
  FOR UPDATE TO service_role USING (true) WITH CHECK (true);

-- platform.cbc_identity_registry carries the same permissive roles=public policy
-- shape (read_all / insert_all / update_all PERMISSIVE; no_delete RESTRICTIVE).
-- Stated precisely: this one was NOT remotely exploitable, because anon holds no
-- USAGE on the platform schema and PostgREST does not expose it. This is hygiene,
-- so that a future GRANT USAGE cannot silently turn it into the agile_intake_jobs
-- problem above. Its RPC path (cbc_* functions in public) is closed by Section A.
DROP POLICY IF EXISTS read_all   ON platform.cbc_identity_registry;
DROP POLICY IF EXISTS insert_all ON platform.cbc_identity_registry;
DROP POLICY IF EXISTS update_all ON platform.cbc_identity_registry;

CREATE POLICY service_role_select ON platform.cbc_identity_registry
  FOR SELECT TO service_role USING (true);
CREATE POLICY service_role_insert ON platform.cbc_identity_registry
  FOR INSERT TO service_role WITH CHECK (true);
CREATE POLICY service_role_update ON platform.cbc_identity_registry
  FOR UPDATE TO service_role USING (true) WITH CHECK (true);

-- ===========================================================================
-- SECTION E (P0-0B/C continued) - Revoke the blanket table grants
-- ===========================================================================
-- Supabase's stock bootstrap runs GRANT ALL ON ALL TABLES IN SCHEMA public TO
-- anon, authenticated. That was never tightened, so EVERY public table carried
-- DELETE, INSERT, SELECT, UPDATE and TRUNCATE for anon. RLS was the only thing
-- standing in front of most of them - defence in depth of exactly one layer.
-- Removing the grant means a future table that forgets ENABLE ROW LEVEL SECURITY
-- is not instantly world-writable, which is the failure mode that produced
-- Section B's eight tables.

-- PUBLIC is included as a no-op guard: the live relacl on these tables carries no
-- PUBLIC entry (verified), unlike the function ACLs in Section A.
REVOKE ALL ON ALL TABLES    IN SCHEMA public        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES    IN SCHEMA platform      FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES    IN SCHEMA product_graph FROM PUBLIC, anon, authenticated;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA platform
  REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA product_graph
  REVOKE ALL ON TABLES FROM anon, authenticated;

-- ===========================================================================
-- SECTION F (P0-0E) - Harden function search_path and the cost views
-- ===========================================================================
-- Seven functions had no search_path pinned. All seven are SECURITY INVOKER, so
-- the severity is lower than the SECURITY DEFINER set (which already pin theirs),
-- but four are trigger functions that run during writes and claim_intake_job
-- mutates the job queue - a mutable search_path lets a caller with CREATE on a
-- searched schema shadow an unqualified object.
--
-- search_path is set to the schemas each function actually references (verified
-- against each body), NOT to the empty string: these bodies use unqualified names
-- and '' would break them. pg_catalog is implicitly searched first regardless.

ALTER FUNCTION public.updated_at_now()                                  SET search_path = pg_catalog, public;
ALTER FUNCTION public.touch_codebase_context_cache()                    SET search_path = pg_catalog, public;
ALTER FUNCTION public.graph_node_epistemic_status(text, text)            SET search_path = pg_catalog, public;
ALTER FUNCTION public.claim_intake_job(text)                             SET search_path = pg_catalog, public;
ALTER FUNCTION platform.apply_append_only_rls(text, text)                SET search_path = pg_catalog, platform, public;
ALTER FUNCTION platform.enforce_cbc_frozen_fields()                      SET search_path = pg_catalog, platform, public;
ALTER FUNCTION product_graph.enforce_node_immutability()                 SET search_path = pg_catalog, product_graph, public;

-- The three cost-summary views were SECURITY DEFINER (the PG default), so they
-- evaluated with the view owner's rights and bypassed RLS on runs/agents. Their
-- only caller is /api/cost via the service-role client, which bypasses RLS
-- anyway, so flipping to security_invoker is behaviour-neutral for the dashboard
-- and removes the bypass for everyone else.

ALTER VIEW public.agent_cost_summary   SET (security_invoker = on);
ALTER VIEW public.project_cost_summary SET (security_invoker = on);
ALTER VIEW public.company_cost_summary SET (security_invoker = on);

COMMIT;

-- ===========================================================================
-- POST-APPLY VERIFICATION (must be run; none of it has been run yet)
-- ===========================================================================
-- This migration has NOT been applied. Nothing below has been executed, and a
-- prepared migration is not an applied security fix.
--
-- 1. Catalog assertions (strictly read-only, safe immediately after apply):
--      scripts/tests/047_assertions.sql        -> 12 invariants, raises on first failure
-- 2. Behavioural probes (impersonates anon/authenticated; wrapped BEGIN..ROLLBACK
--    so nothing persists even if a probe unexpectedly succeeds):
--      scripts/tests/047_behaviour_probes.sql
-- 3. External HTTP probes with the public anon key, which is the actual threat
--    model (the key ships in any browser bundle):
--      python scripts/verify_p0_0_security.py --expect-hardened --include-write-probes
--    -> every anon probe must be denied; every service_role probe must succeed.
-- 4. No-regression checks against the live app:
--      a. Load /dashboard, /dashboard/runs, /dashboard/costs, /dashboard/scoping.
--      b. Run one agent end to end; confirm run_started + run_completed persist.
--      c. Run agents/teams/agile/worker.py --once against a queued job.
--      d. Confirm /api/cost still returns data (the 3 cost views changed).
-- 5. Re-run the Supabase security advisors; expect zero ERROR-level lints.
--
-- If a break appears, prefer a narrow forward GRANT for the one object that
-- broke over running 047_rollback.sql, which restores the whole vulnerable state.
