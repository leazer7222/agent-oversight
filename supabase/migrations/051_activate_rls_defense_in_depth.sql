-- Migration 051: make the tenant RLS policies actually reachable
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- Depends on: 047 (grant revocation), 048 (company_members), 049 (swim_sourcing)
--
-- DEFECT THIS FIXES, found by scripts/tests/test_tenant_isolation_live.py
-- --------------------------------------------------------------------------
-- The live isolation test showed an authenticated user receiving HTTP 403 when
-- reading public.company_members, where the design expects 200 with exactly
-- their own row.
--
-- Cause: migration 047 correctly revoked ALL table privileges from
-- `authenticated` across schema public. Migration 048 then created
-- company_members with an RLS policy FOR SELECT TO authenticated - but never
-- granted SELECT on the table. **RLS filters rows for roles that already hold
-- the table privilege; it does not confer it.** With no GRANT, the policy can
-- never be evaluated, so it is dead code. The nine tenant_member_select
-- policies on swim_sourcing tables are inert for exactly the same reason, and
-- additionally because `authenticated` has no USAGE on that schema.
--
-- Nothing was exposed by this - the failure mode is over-restriction, and all
-- application access goes through the service role, which is unaffected. But
-- the documented defense-in-depth layer did not exist: tenant isolation rested
-- entirely on requireTenant() in the application. That is a single layer, and
-- the whole point of the RLS policies was to survive an application bug.
--
-- WHAT THIS GRANTS, AND WHAT IT DELIBERATELY DOES NOT
-- --------------------------------------------------------------------------
-- SELECT only. No INSERT, UPDATE or DELETE is granted to `authenticated` on any
-- table here. A signed-in browser can therefore read only rows its RLS policy
-- admits, and can write nothing directly - every mutation still goes through a
-- server route holding the service-role key.
--
-- The swim_* RPCs stay service_role-only. This migration does not widen them.

BEGIN;

-- ---------------------------------------------------------------------------
-- public.company_members: a user may read their own membership rows
-- ---------------------------------------------------------------------------
-- Policy own_membership_select (from 048) restricts this to user_id = auth.uid().
GRANT SELECT ON public.company_members TO authenticated;

-- ---------------------------------------------------------------------------
-- swim_sourcing: tenant-scoped read access
-- ---------------------------------------------------------------------------
-- USAGE first - without it the grants below are unreachable regardless of RLS.
GRANT USAGE ON SCHEMA swim_sourcing TO authenticated;

-- Policy tenant_member_select (from 049) restricts every one of these to
--   company_id IN (SELECT company_id FROM company_members WHERE user_id = auth.uid())
-- so a signed-in user sees only their own company's rows, enforced by the
-- database rather than by the application remembering to filter.
GRANT SELECT ON swim_sourcing.facilities         TO authenticated;
GRANT SELECT ON swim_sourcing.facility_contacts  TO authenticated;
GRANT SELECT ON swim_sourcing.qualifications     TO authenticated;
GRANT SELECT ON swim_sourcing.outreach_threads   TO authenticated;
GRANT SELECT ON swim_sourcing.outreach_messages  TO authenticated;
GRANT SELECT ON swim_sourcing.approvals          TO authenticated;
GRANT SELECT ON swim_sourcing.meetings           TO authenticated;
GRANT SELECT ON swim_sourcing.suppression_list   TO authenticated;
GRANT SELECT ON swim_sourcing.jobs               TO authenticated;

-- Future tables in this schema should inherit the same read-only posture, so a
-- new table is covered by RLS rather than silently unreadable (which would
-- recreate exactly the dead-policy problem this migration fixes).
ALTER DEFAULT PRIVILEGES IN SCHEMA swim_sourcing GRANT SELECT ON TABLES TO authenticated;

-- ---------------------------------------------------------------------------
-- Explicitly NOT granted, recorded so the omissions read as decisions
-- ---------------------------------------------------------------------------
--   * anon            - no grant anywhere; it holds no USAGE on swim_sourcing
--   * INSERT/UPDATE/DELETE to authenticated - writes go through server routes
--   * public.agents, runs, agent_events, agent_outputs and the rest of the
--     control plane - these are platform-oversight data, served to admins by
--     /api/* behind requireAdminOrDeny, not read directly by a browser
--   * the swim_* RPCs - still service_role only

COMMIT;
