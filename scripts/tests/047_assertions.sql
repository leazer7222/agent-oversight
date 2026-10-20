-- Post-apply assertions for migration 047 (P0-0 hardening).
-- Run against the local fixture database AFTER applying 047.
-- Raises an exception on the first violated invariant, so a non-zero psql exit
-- means the migration did not produce the intended end state.

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

  -- F2. All 3 cost views must be security_invoker.
  FOREACH v IN ARRAY ARRAY['agent_cost_summary','project_cost_summary','company_cost_summary']
  LOOP
    SELECT count(*) INTO n FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace
      WHERE ns.nspname='public' AND c.relname=v AND c.relkind='v'
        AND c.reloptions @> ARRAY['security_invoker=true'];
    IF n <> 1 THEN RAISE EXCEPTION 'F2 FAILED: view public.% is not security_invoker', v; END IF;
  END LOOP;

  RAISE NOTICE 'ALL 047 ASSERTIONS PASSED (A1-A3, B1, C1-C3, D1-D3, F1-F2)';
END $$;

-- Behavioural proof, not just catalog inspection: impersonate anon and confirm
-- the previously-open paths now raise insufficient_privilege.
DO $$
DECLARE ok boolean;
BEGIN
  SET LOCAL ROLE anon;
  BEGIN
    PERFORM public.get_calibration_readiness();
    RESET ROLE;
    RAISE EXCEPTION 'BEHAVIOUR FAILED: anon could still execute get_calibration_readiness()';
  EXCEPTION WHEN insufficient_privilege THEN
    ok := true;
  END;
  RESET ROLE;
  RAISE NOTICE 'BEHAVIOUR: anon RPC execution correctly denied';
END $$;

DO $$
DECLARE ok boolean; c int;
BEGIN
  SET LOCAL ROLE anon;
  BEGIN
    SELECT count(*) INTO c FROM public.contractor_rows;
    RESET ROLE;
    RAISE EXCEPTION 'BEHAVIOUR FAILED: anon could still read contractor_rows';
  EXCEPTION WHEN insufficient_privilege THEN
    ok := true;
  END;
  RESET ROLE;
  RAISE NOTICE 'BEHAVIOUR: anon table read correctly denied';
END $$;

DO $$
DECLARE ok boolean;
BEGIN
  SET LOCAL ROLE anon;
  BEGIN
    INSERT INTO public.agile_intake_jobs (product_key, intake) VALUES ('injected', '[]'::jsonb);
    RESET ROLE;
    RAISE EXCEPTION 'BEHAVIOUR FAILED: anon could still inject a job into the agent queue';
  EXCEPTION WHEN insufficient_privilege THEN
    ok := true;
  END;
  RESET ROLE;
  RAISE NOTICE 'BEHAVIOUR: anon job injection correctly denied';
END $$;

DO $$
DECLARE ok boolean;
BEGIN
  SET LOCAL ROLE authenticated;
  BEGIN
    DELETE FROM public.audit_log;
    RESET ROLE;
    RAISE EXCEPTION 'BEHAVIOUR FAILED: authenticated could still delete the audit log';
  EXCEPTION WHEN insufficient_privilege THEN
    ok := true;
  END;
  RESET ROLE;
  RAISE NOTICE 'BEHAVIOUR: authenticated audit_log deletion correctly denied';
END $$;

DO $$
DECLARE ok boolean;
BEGIN
  SET LOCAL ROLE authenticated;
  BEGIN
    UPDATE public.agent_outputs SET output_type = 'tampered';
    RESET ROLE;
    RAISE EXCEPTION 'BEHAVIOUR FAILED: authenticated could still mutate agent_outputs';
  EXCEPTION WHEN insufficient_privilege THEN
    ok := true;
  END;
  RESET ROLE;
  RAISE NOTICE 'BEHAVIOUR: authenticated artifact mutation correctly denied';
END $$;

-- No-regression proof: service_role must still do real work.
DO $$
DECLARE c int;
BEGIN
  SET LOCAL ROLE service_role;
  PERFORM public.get_calibration_readiness();
  SELECT count(*) INTO c FROM public.contractor_rows;
  SELECT count(*) INTO c FROM public.agent_outputs;
  SELECT count(*) INTO c FROM public.agent_cost_summary;
  INSERT INTO public.agile_intake_jobs (product_key, intake) VALUES ('svc-ok', '[]'::jsonb);
  UPDATE public.agile_intake_jobs SET status = 'running' WHERE product_key = 'svc-ok';
  PERFORM public.claim_intake_job('test-worker');
  RESET ROLE;
  RAISE NOTICE 'NO-REGRESSION: service_role RPC, reads, views, queue insert/update/claim all OK';
END $$;
