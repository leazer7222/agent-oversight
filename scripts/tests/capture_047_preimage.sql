-- Pre-image capture for migration 047 (P0-0 database hardening).
--
-- THIS IS THE RECOVERY MECHANISM FOR 047, and it exists because this Supabase
-- project is on the Free plan, which has NO automated backups and NO
-- point-in-time recovery (verified: branching was refused with "supported only
-- on the Pro plan or above", and Supabase's backup docs state daily backups
-- cover "Pro, Team, and Enterprise Plan projects" only).
--
-- That matters less than it sounds for THIS migration. 047 changes only
-- privileges, policies, function search_path settings and view options. It
-- touches no rows, creates no objects, drops no objects and alters no column.
-- The entire recovery surface is therefore expressible as SQL - and a precise
-- pre-image is strictly BETTER than a daily backup here: no downtime, no data
-- loss window, and surgical rather than whole-project restoration.
--
-- STRICTLY READ-ONLY. This script SELECTs text; it changes nothing.
--
-- HOW TO USE (runbook step 1, immediately before applying 047):
--   1. Run this file. It returns one SQL statement per row, in apply order.
--   2. Save the `stmt` column, in order, to
--        supabase/migrations/047_preimage_<YYYYMMDDHHMM>.sql
--   3. Commit that file BEFORE applying 047.
--   4. If 047 needs reversing after commit, that captured file restores the
--      exact prior state. Prefer it over 047_rollback.sql, which is a
--      hand-written approximation; this is derived from the live catalog.
--
-- Verified 2026-10-20: produces ~150 statements covering all 42 functions
-- (grants + search_path), the uniform public table/sequence grants, RLS state
-- for every affected table, every policy in public/platform/product_graph with
-- its exact definition, the 3 cost views, and the postgres-owned default
-- privileges for schema public.
--
-- KNOWN FIDELITY LIMITS (also noted in 047_rollback.sql):
--   - Three functions currently have a NULL proacl (no ACL row, relying on the
--     built-in EXECUTE-to-PUBLIC default). Once 047 materialises an ACL, "NULL"
--     cannot be recreated; the emitted GRANT ... TO PUBLIC is functionally
--     equivalent but catalog-visibly different.
--   - Default privileges owned by supabase_admin are NOT captured and are NOT
--     modified by 047 (postgres is not a member of supabase_admin).

WITH fn AS (
  SELECT n.nspname AS s, p.proname AS f,
         pg_get_function_identity_arguments(p.oid) AS args, p.proacl, p.proconfig
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE n.nspname IN ('public','platform','product_graph') AND p.prokind = 'f'
)
SELECT 1 AS ord, '-- [A] function EXECUTE grants' AS stmt
UNION ALL
SELECT 2, format('GRANT EXECUTE ON FUNCTION %I.%I(%s) TO %s;', s, f, args,
         CASE WHEN proacl IS NULL THEN 'PUBLIC'
              ELSE (SELECT string_agg(DISTINCT g, ', ' ORDER BY g) FROM (
                      SELECT CASE WHEN a::text LIKE '=%' THEN 'PUBLIC'
                                  ELSE split_part(a::text, '=', 1) END AS g
                      FROM unnest(proacl) a
                      WHERE split_part(a::text, '=', 1) <> 'postgres') x) END)
FROM fn
UNION ALL
SELECT 3, '-- [A] function search_path settings'
UNION ALL
SELECT 4, CASE WHEN proconfig IS NULL
       THEN format('ALTER FUNCTION %I.%I(%s) RESET search_path;', s, f, args)
       ELSE format('ALTER FUNCTION %I.%I(%s) SET %s;', s, f, args,
              (SELECT c FROM unnest(proconfig) c WHERE c LIKE 'search_path=%')) END
FROM fn
WHERE proconfig IS NULL OR EXISTS (SELECT 1 FROM unnest(proconfig) c WHERE c LIKE 'search_path=%')
UNION ALL
SELECT 5, '-- [E] table/sequence grants (verified uniform across all public relations)'
UNION ALL
SELECT 6, 'GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;'
UNION ALL
SELECT 7, 'GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;'
UNION ALL
SELECT 8, '-- [B] RLS enablement state'
UNION ALL
SELECT 9, format('ALTER TABLE %I.%I %s ROW LEVEL SECURITY;', n.nspname, c.relname,
                 CASE WHEN c.relrowsecurity THEN 'ENABLE' ELSE 'DISABLE' END)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r' AND n.nspname IN ('public','platform','product_graph')
  AND (c.relname IN ('event_type_registry','output_type_registry','pipeline_config','contractor_rows',
       'contractor_evidence','contractor_approval_queue','contractor_sync_log','codebase_context_cache')
    OR EXISTS (SELECT 1 FROM pg_policies pp WHERE pp.schemaname = n.nspname AND pp.tablename = c.relname))
UNION ALL
SELECT 10, '-- [C/D] policies (exact current definitions)'
UNION ALL
SELECT 11, format('CREATE POLICY %I ON %I.%I%s FOR %s TO %s%s%s;',
         policyname, schemaname, tablename,
         CASE WHEN permissive = 'RESTRICTIVE' THEN ' AS RESTRICTIVE' ELSE '' END,
         cmd, array_to_string(roles, ', '),
         CASE WHEN qual IS NOT NULL THEN ' USING (' || qual || ')' ELSE '' END,
         CASE WHEN with_check IS NOT NULL THEN ' WITH CHECK (' || with_check || ')' ELSE '' END)
FROM pg_policies
WHERE schemaname IN ('public','platform','product_graph')
UNION ALL
SELECT 12, '-- [F] view options'
UNION ALL
SELECT 13, format('ALTER VIEW %I.%I RESET (security_invoker);', n.nspname, c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'v' AND c.relname LIKE '%cost_summary'
UNION ALL
SELECT 14, '-- [A/E] default privileges (postgres-owned entries, schema public)'
UNION ALL
SELECT 15, 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;'
UNION ALL
SELECT 16, 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated;'
UNION ALL
SELECT 17, 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO PUBLIC, anon, authenticated;'
ORDER BY 1, 2;
