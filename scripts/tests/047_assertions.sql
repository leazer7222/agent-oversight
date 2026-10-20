-- Post-apply CATALOG assertions for migration 047 (P0-0 hardening).
--
-- STRICTLY READ-ONLY. Every statement inspects system catalogs; nothing is
-- written, so this is safe to run against production immediately after 047 is
-- applied. Raises on the first violated invariant, so a non-zero exit means the
-- migration did not produce the intended end state.
--
-- Companion: 047_behaviour_probes.sql proves the same conclusions behaviourally
-- by impersonating anon/authenticated (wrapped in a transaction that rolls back).

DO $$
DECLARE
  n int;
  t text;
  v text;
BEGIN
  -- A1. No function in the three schemas may remain EXECUTE-able by anon.
  SELECT count(*) INTO n
  FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
  WHERE ns.nspname IN ('public','platform','product_graph') AND p.prokind = 'f'
    AND has_function_privilege('anon', p.oid, 'EXECUTE');
  IF n > 0 THEN RAISE EXCEPTION 'A1 FAILED: % function(s) still anon-executable', n; END IF;

  -- A2. Same for authenticated.
  SELECT count(*) INTO n
  FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
  WHERE ns.nspname IN ('public','platform','product_graph') AND p.prokind = 'f'
    AND has_function_privilege('authenticated', p.oid, 'EXECUTE');
  IF n > 0 THEN RAISE EXCEPTION 'A2 FAILED: % function(s) still authenticated-executable', n; END IF;

  -- A1b. No function may carry a PUBLIC grant, and none may have a NULL acl.
  -- This is the specific defect that made the first draft of 047 ineffective:
  -- EXECUTE was granted to PUBLIC (ACL entry `=X/postgres`), so revoking the
  -- explicit anon entry changed nothing. A1/A2 above would also catch it via
  -- has_function_privilege, but this names the cause rather than the symptom.
  SELECT count(*) INTO n
  FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
  WHERE ns.nspname IN ('public','platform','product_graph') AND p.prokind = 'f'
    AND (p.proacl IS NULL
         OR EXISTS (SELECT 1 FROM unnest(p.proacl) a WHERE a::text LIKE '=%'));
  IF n > 0 THEN
    RAISE EXCEPTION 'A1b FAILED: % function(s) still grant EXECUTE to PUBLIC (or have a NULL acl)', n;
  END IF;

  -- A3. service_role must RETAIN execute on every one of them (no-regression).
  SELECT count(*) INTO n
  FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
  WHERE ns.nspname IN ('public','platform','product_graph') AND p.prokind = 'f'
    AND NOT has_function_privilege('service_role', p.oid, 'EXECUTE');
  IF n > 0 THEN RAISE EXCEPTION 'A3 FAILED: service_role lost EXECUTE on % function(s)', n; END IF;

  -- B1. RLS must be ON for all 8 previously-unprotected tables.
  FOREACH t IN ARRAY ARRAY['event_type_registry','output_type_registry','pipeline_config',
                           'contractor_rows','contractor_evidence','contractor_approval_queue',
                           'contractor_sync_log','codebase_context_cache']
  LOOP
    SELECT count(*) INTO n FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace
      WHERE ns.nspname='public' AND c.relname=t AND c.relrowsecurity;
    IF n <> 1 THEN RAISE EXCEPTION 'B1 FAILED: RLS not enabled on public.%', t; END IF;
  END LOOP;

  -- C1. No authenticated_* policy may survive anywhere in public.
  SELECT count(*) INTO n FROM pg_policies
  WHERE schemaname='public' AND policyname LIKE 'authenticated_%';
  IF n > 0 THEN RAISE EXCEPTION 'C1 FAILED: % authenticated_* policy(ies) remain', n; END IF;

  -- C2. No table in public may still grant anything to anon or authenticated.
  SELECT count(*) INTO n FROM information_schema.role_table_grants
  WHERE table_schema='public' AND grantee IN ('anon','authenticated');
  IF n > 0 THEN RAISE EXCEPTION 'C2 FAILED: % table grant(s) to anon/authenticated remain', n; END IF;

  -- C3. service_role must retain table access (no-regression).
  SELECT count(*) INTO n FROM information_schema.role_table_grants
  WHERE table_schema='public' AND grantee='service_role' AND privilege_type='SELECT';
  IF n = 0 THEN RAISE EXCEPTION 'C3 FAILED: service_role lost SELECT on public tables'; END IF;

  -- D1. The permissive roles=public policies must be gone from the job queue.
  SELECT count(*) INTO n FROM pg_policies
  WHERE tablename IN ('agile_intake_jobs','cbc_identity_registry')
    AND policyname IN ('read_all','insert_all','update_all');
  IF n > 0 THEN RAISE EXCEPTION 'D1 FAILED: % permissive public policy(ies) remain on the queue', n; END IF;

  -- D2. The restrictive no_delete protection must be PRESERVED, not dropped.
  SELECT count(*) INTO n FROM pg_policies
  WHERE tablename IN ('agile_intake_jobs','cbc_identity_registry') AND policyname='no_delete';
  IF n <> 2 THEN RAISE EXCEPTION 'D2 FAILED: no_delete policy count is % (expected 2)', n; END IF;

  -- D3. service_role replacements must exist on the queue.
  SELECT count(*) INTO n FROM pg_policies
  WHERE tablename='agile_intake_jobs' AND policyname LIKE 'service_role_%';
  IF n <> 3 THEN RAISE EXCEPTION 'D3 FAILED: expected 3 service_role policies on the queue, found %', n; END IF;

  -- F1. All 7 previously-mutable functions must have search_path pinned.
  SELECT count(*) INTO n
  FROM pg_proc p JOIN pg_namespace ns ON ns.oid=p.pronamespace
  WHERE ((ns.nspname='public' AND p.proname IN ('updated_at_now','touch_codebase_context_cache',
                                                'graph_node_epistemic_status','claim_intake_job'))
      OR (ns.nspname='platform' AND p.proname IN ('apply_append_only_rls','enforce_cbc_frozen_fields'))
      OR (ns.nspname='product_graph' AND p.proname='enforce_node_immutability'))
    AND (p.proconfig IS NULL OR NOT EXISTS (
          SELECT 1 FROM unnest(p.proconfig) cfg WHERE cfg LIKE 'search_path=%'));
  IF n > 0 THEN RAISE EXCEPTION 'F1 FAILED: % function(s) still have a mutable search_path', n; END IF;

  -- F1b. Default privileges must deny EXECUTE to PUBLIC/anon for FUTURE functions,
  -- including in schemas that do not exist yet (the global postgres entry).
  -- Without this, creating swim_sourcing (or any new schema) silently reopens
  -- the exposure 047 closes the first time a function lands there.
  SELECT count(*) INTO n
  FROM pg_default_acl d
  WHERE d.defaclobjtype = 'f'
    AND pg_get_userbyid(d.defaclrole) = 'postgres'
    AND d.defaclnamespace = 0            -- 0 = global (no IN SCHEMA)
    AND NOT EXISTS (
      SELECT 1 FROM unnest(d.defaclacl) a
      WHERE a::text LIKE '=%' OR a::text LIKE 'anon=%' OR a::text LIKE 'authenticated=%');
  IF n <> 1 THEN
    RAISE EXCEPTION 'F1b FAILED: global postgres default privileges for functions do not deny PUBLIC/anon (matched % rows, expected 1)', n;
  END IF;

  -- F2. All 3 cost views must be security_invoker.
  FOREACH v IN ARRAY ARRAY['agent_cost_summary','project_cost_summary','company_cost_summary']
  LOOP
    -- Postgres stores the literal spelling used in ALTER VIEW, so
    -- `SET (security_invoker = on)` persists as 'security_invoker=on', NOT
    -- '...=true'. An earlier version of this assertion matched only 'true' and
    -- reported a correctly-applied migration as failed. Parse the option and
    -- accept any spelling Postgres treats as boolean true.
    SELECT count(*) INTO n FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace
      WHERE ns.nspname='public' AND c.relname=v AND c.relkind='v'
        AND lower(coalesce((SELECT option_value FROM pg_options_to_table(c.reloptions)
                             WHERE option_name='security_invoker'), 'off'))
            IN ('on','true','yes','1');
    IF n <> 1 THEN RAISE EXCEPTION 'F2 FAILED: view public.% is not security_invoker', v; END IF;
  END LOOP;

  RAISE NOTICE 'ALL 047 ASSERTIONS PASSED (A1-A3, B1, C1-C3, D1-D3, F1-F2)';
END $$;
