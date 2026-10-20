-- Pre-image capture for migration 047 (P0-0 database hardening).
--
-- THIS IS THE RECOVERY MECHANISM FOR 047. This Supabase project is on the Free
-- plan, which has NO automated backups and NO point-in-time recovery (verified:
-- branching refused as "Pro plan or above"; Supabase's backup docs limit daily
-- backups to Pro/Team/Enterprise).
--
-- 047 changes only privileges, policies, function search_path settings and view
-- options - no rows, no DDL on tables, no dropped objects. The recovery surface
-- is therefore fully expressible as SQL, and for this change a precise pre-image
-- beats a daily backup: no downtime, no data-loss window, surgical.
--
-- STRICTLY READ-ONLY. This script SELECTs text; it changes nothing.
--
-- HOW TO USE (runbook step 1, immediately before applying 047):
--   1. Run this file. It returns one SQL statement per row, in apply order.
--   2. Save the `stmt` column, in order, to
--        supabase/migrations/047_preimage_<YYYYMMDDHHMM>.sql
--   3. Commit that file BEFORE applying 047.
--   4. To reverse a committed 047, run that captured file. Prefer it over
--      047_rollback.sql: the pre-image is derived from the live catalog, the
--      rollback script is hand-written.
--
-- IDEMPOTENCY (fixed 2026-10-20): the generated script is re-runnable.
--   * Every CREATE POLICY is preceded by DROP POLICY IF EXISTS, so restoring
--     cannot fail with duplicate_object (42710) if a policy of that name exists.
--   * A preamble drops the policies 047 ITSELF creates (service_role_all and the
--     service_role_select/insert/update trio). Without this, restoring would
--     leave 047's permissive service_role policies in place ALONGSIDE the
--     restored originals, which is not the pre-047 state.
--   * Grants, RLS toggles, search_path and view options are naturally idempotent.
--
-- KNOWN FIDELITY LIMITS:
--   * Three functions currently have a NULL proacl (no ACL row, relying on the
--     built-in EXECUTE-to-PUBLIC default). Once 047 materialises an ACL, "NULL"
--     cannot be recreated; the emitted GRANT ... TO PUBLIC is functionally
--     equivalent but catalog-visibly different.
--   * 047 adds an explicit service_role EXECUTE grant. Restoring does not remove
--     it, so service_role keeps a direct grant rather than inheriting via PUBLIC.
--     Harmless (service_role is the trusted path) but not byte-identical.
--   * Default privileges owned by supabase_admin are neither captured nor
--     modified by 047 (postgres is not a member of supabase_admin).

WITH fn AS (
  SELECT n.nspname AS s, p.proname AS f,
         pg_get_function_identity_arguments(p.oid) AS args, p.proacl, p.proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname IN ('public','platform','product_graph') AND p.prokind = 'f'
),
-- Tables whose policies 047 alters. Used to emit the drop-preamble for the
-- policies 047 creates, so a restore returns to the true pre-047 state.
touched(sch, tbl) AS (
  VALUES ('public','agent_outputs'), ('public','agent_events'), ('public','audit_log'),
         ('public','agents'), ('public','companies'), ('public','projects'),
         ('public','agent_definitions'), ('public','agent_qa_results'), ('public','policies'),
         ('public','event_type_registry'), ('public','output_type_registry'),
         ('public','pipeline_config'), ('public','contractor_rows'),
         ('public','contractor_evidence'), ('public','contractor_approval_queue'),
         ('public','contractor_sync_log'), ('public','codebase_context_cache'),
         ('public','agile_intake_jobs'), ('platform','cbc_identity_registry')
)
SELECT 0 AS ord, '-- RESTORE SCRIPT: pre-047 state, captured from the live catalog.' AS stmt
UNION ALL
SELECT 0, '-- Re-runnable. Drops 047-created policies first, then restores originals.'
UNION ALL
SELECT 0, 'BEGIN;'
UNION ALL
SELECT 1, '-- [PRE] remove policies created BY 047 so the restore is not additive'
UNION ALL
SELECT 1, format('DROP POLICY IF EXISTS %I ON %I.%I;', pol, sch, tbl)
FROM touched,
     unnest(ARRAY['service_role_all','service_role_select','service_role_insert','service_role_update']) AS pol
UNION ALL
SELECT 2, '-- [A] function EXECUTE grants'
UNION ALL
SELECT 3, format('GRANT EXECUTE ON FUNCTION %I.%I(%s) TO %s;', s, f, args,
         CASE WHEN proacl IS NULL THEN 'PUBLIC'
              ELSE (SELECT string_agg(DISTINCT g, ', ' ORDER BY g) FROM (
                      SELECT CASE WHEN a::text LIKE '=%' THEN 'PUBLIC'
                                  ELSE split_part(a::text, '=', 1) END AS g
                      FROM unnest(proacl) a
                      WHERE split_part(a::text, '=', 1) <> 'postgres') x) END)
FROM fn
UNION ALL
SELECT 4, '-- [A] function search_path settings'
UNION ALL
SELECT 5, CASE WHEN proconfig IS NULL
       THEN format('ALTER FUNCTION %I.%I(%s) RESET search_path;', s, f, args)
       ELSE format('ALTER FUNCTION %I.%I(%s) SET %s;', s, f, args,
              (SELECT c FROM unnest(proconfig) c WHERE c LIKE 'search_path=%')) END
FROM fn
WHERE proconfig IS NULL OR EXISTS (SELECT 1 FROM unnest(proconfig) c WHERE c LIKE 'search_path=%')
UNION ALL
SELECT 6, '-- [E] table/sequence grants (verified uniform across all public relations)'
UNION ALL
SELECT 7, 'GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;'
UNION ALL
SELECT 8, 'GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;'
UNION ALL
SELECT 9, '-- [B] RLS enablement state'
UNION ALL
SELECT 10, format('ALTER TABLE %I.%I %s ROW LEVEL SECURITY;', n.nspname, c.relname,
                  CASE WHEN c.relrowsecurity THEN 'ENABLE' ELSE 'DISABLE' END)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r' AND n.nspname IN ('public','platform','product_graph')
  AND (c.relname IN ('event_type_registry','output_type_registry','pipeline_config','contractor_rows',
       'contractor_evidence','contractor_approval_queue','contractor_sync_log','codebase_context_cache')
    OR EXISTS (SELECT 1 FROM pg_policies pp WHERE pp.schemaname = n.nspname AND pp.tablename = c.relname))
UNION ALL
SELECT 11, '-- [C/D] policies: drop-then-create so the restore is idempotent'
UNION ALL
SELECT 12, format('DROP POLICY IF EXISTS %I ON %I.%I;', policyname, schemaname, tablename)
FROM pg_policies WHERE schemaname IN ('public','platform','product_graph')
UNION ALL
SELECT 13, format('CREATE POLICY %I ON %I.%I%s FOR %s TO %s%s%s;',
         policyname, schemaname, tablename,
         CASE WHEN permissive = 'RESTRICTIVE' THEN ' AS RESTRICTIVE' ELSE '' END,
         cmd, array_to_string(roles, ', '),
         CASE WHEN qual IS NOT NULL THEN ' USING (' || qual || ')' ELSE '' END,
         CASE WHEN with_check IS NOT NULL THEN ' WITH CHECK (' || with_check || ')' ELSE '' END)
FROM pg_policies
WHERE schemaname IN ('public','platform','product_graph')
UNION ALL
SELECT 14, '-- [F] view options'
UNION ALL
SELECT 15, format('ALTER VIEW %I.%I RESET (security_invoker);', n.nspname, c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'v' AND c.relname LIKE '%cost_summary'
UNION ALL
SELECT 16, '-- [A/E] default privileges (postgres-owned entries, schema public)'
UNION ALL
SELECT 17, 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;'
UNION ALL
SELECT 18, 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated;'
UNION ALL
SELECT 19, 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO PUBLIC, anon, authenticated;'
UNION ALL
SELECT 20, 'ALTER DEFAULT PRIVILEGES IN SCHEMA platform REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;'
UNION ALL
SELECT 21, 'ALTER DEFAULT PRIVILEGES IN SCHEMA product_graph REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated;'
UNION ALL
SELECT 22, '-- NOTE: the two REVOKEs above are intentional. platform/product_graph had NO'
UNION ALL
SELECT 22, '-- default-ACL entry pre-047; removing 047''s entry is not expressible, so these'
UNION ALL
SELECT 22, '-- leave them hardened. Functionally safer than the original absence.'
UNION ALL
SELECT 23, 'COMMIT;'
ORDER BY 1, 2;
