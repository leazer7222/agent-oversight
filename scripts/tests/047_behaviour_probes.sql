-- Post-apply BEHAVIOURAL probes for migration 047 (P0-0 hardening).
--
-- Proves the hardening by actually impersonating anon and authenticated and
-- confirming the previously-open paths now raise insufficient_privilege, rather
-- than only inspecting catalogs (047_assertions.sql does that).
--
-- SAFETY: the whole file runs inside a single transaction that ends in ROLLBACK.
-- Some probes are deliberately WRITE attempts (job injection, audit_log delete,
-- artifact mutation) - they are expected to be REJECTED, and the ROLLBACK means
-- that even if one unexpectedly succeeds, nothing is persisted. Safe to run
-- against production after 047 is applied.

BEGIN;

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

ROLLBACK;
