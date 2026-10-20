-- Fixture for the local validation of migration 047 (P0-0 hardening).
--
-- Replicates the EXACT preconditions measured from production
-- (hdhovyrlnfojtkqbcegh) on 2026-10-20 for every object 047 touches:
--   - the Supabase roles anon / authenticated / service_role
--   - the 19 tables 047 alters, with their real RLS state
--   - the permissive policies 047 drops, with their real names, commands and roles
--   - Supabase's stock blanket grants to anon/authenticated on schema public
--   - function stubs with identity signatures matching production, including the
--     write_run_started_artifacts OVERLOAD pair and the 7 SECURITY INVOKER
--     functions whose search_path 047 pins
--   - the 3 cost views, created SECURITY DEFINER (the PG default)
--
-- This is NOT a replay of migrations 001-046. It is a faithful stand-in for the
-- starting state of the objects under test, which is what 047 must transform.

CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN BYPASSRLS;

CREATE SCHEMA platform;
CREATE SCHEMA product_graph;

-- Supabase's auth helper shims (referenced by pre-existing policies we keep).
CREATE SCHEMA auth;
CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS $$ SELECT 'anon'::text $$;
CREATE FUNCTION auth.uid()  RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;

-- ---------------------------------------------------------------------------
-- Section C targets: ledger + registry tables (RLS ON, authenticated_* policies)
-- ---------------------------------------------------------------------------
CREATE TABLE public.companies        (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text, cost_limit_usd numeric, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.projects         (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.agent_definitions(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.agents           (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid, status text, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.runs             (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), agent_id uuid, cost_usd numeric, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.agent_events     (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), run_id uuid, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.agent_outputs    (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), run_id uuid, output_type text, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.agent_qa_results (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), run_id uuid, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.policies         (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.audit_log        (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), action text, created_at timestamptz NOT NULL DEFAULT now());

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['agent_outputs','agent_events','audit_log','agents','companies',
                           'projects','agent_definitions','agent_qa_results','policies']
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY authenticated_select ON public.%I FOR SELECT TO authenticated USING (true)', t);
    EXECUTE format('CREATE POLICY authenticated_insert ON public.%I FOR INSERT TO authenticated WITH CHECK (true)', t);
    EXECUTE format('CREATE POLICY authenticated_update ON public.%I FOR UPDATE TO authenticated USING (true)', t);
    EXECUTE format('CREATE POLICY authenticated_delete ON public.%I FOR DELETE TO authenticated USING (true)', t);
  END LOOP;
END $$;

-- runs/project_state already follow the service_role_all convention in prod.
ALTER TABLE public.runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY service_role_all ON public.runs FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- Section B targets: the 8 tables with RLS OFF
-- ---------------------------------------------------------------------------
CREATE TABLE public.event_type_registry       (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), event_type text, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.output_type_registry      (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), output_type text, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.pipeline_config           (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), key text, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.contractor_rows           (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.contractor_evidence       (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), row_id uuid, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.contractor_approval_queue (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), row_id uuid, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.contractor_sync_log       (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), detail text, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE public.codebase_context_cache    (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), target_key text, created_at timestamptz NOT NULL DEFAULT now());
-- RLS intentionally left OFF on all 8, matching production.

-- ---------------------------------------------------------------------------
-- Section D targets: permissive roles=public policies
-- ---------------------------------------------------------------------------
CREATE TABLE public.agile_intake_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id uuid, product_key text, intake jsonb, status text DEFAULT 'queued',
  created_by text DEFAULT 'dashboard', started_at timestamptz, updated_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.agile_intake_jobs ENABLE ROW LEVEL SECURITY;
CREATE POLICY read_all   ON public.agile_intake_jobs FOR SELECT USING (true);
CREATE POLICY insert_all ON public.agile_intake_jobs FOR INSERT WITH CHECK (true);
CREATE POLICY update_all ON public.agile_intake_jobs FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY no_delete  ON public.agile_intake_jobs AS RESTRICTIVE FOR DELETE USING (false);

CREATE TABLE platform.cbc_identity_registry (
  cbc_id text PRIMARY KEY, cbc_type text, name text,
  created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE platform.cbc_identity_registry ENABLE ROW LEVEL SECURITY;
CREATE POLICY read_all   ON platform.cbc_identity_registry FOR SELECT USING (true);
CREATE POLICY insert_all ON platform.cbc_identity_registry FOR INSERT WITH CHECK (true);
CREATE POLICY update_all ON platform.cbc_identity_registry FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY no_delete  ON platform.cbc_identity_registry AS RESTRICTIVE FOR DELETE USING (false);

-- ---------------------------------------------------------------------------
-- Section F targets: the 3 cost views, created SECURITY DEFINER (PG default)
-- ---------------------------------------------------------------------------
CREATE VIEW public.agent_cost_summary   AS SELECT agent_id, sum(cost_usd) AS total FROM public.runs GROUP BY agent_id;
CREATE VIEW public.project_cost_summary AS SELECT id AS project_id, 0::numeric AS total FROM public.projects;
CREATE VIEW public.company_cost_summary AS SELECT id AS company_id, 0::numeric AS total FROM public.companies;

-- ---------------------------------------------------------------------------
-- Section A + F targets: function stubs with production identity signatures
-- ---------------------------------------------------------------------------
-- The 7 SECURITY INVOKER functions whose search_path 047 pins. Signatures must
-- match exactly or the ALTER FUNCTION statements in 047 will fail.
CREATE FUNCTION public.updated_at_now() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$;
CREATE FUNCTION public.touch_codebase_context_cache() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$;
CREATE FUNCTION public.graph_node_epistemic_status(p_node_type text, p_status text)
  RETURNS text LANGUAGE sql AS $$ SELECT 'stub'::text $$;
CREATE FUNCTION public.claim_intake_job(p_worker text DEFAULT 'worker')
  RETURNS SETOF public.agile_intake_jobs LANGUAGE sql AS $$ SELECT * FROM public.agile_intake_jobs LIMIT 0 $$;
CREATE FUNCTION platform.apply_append_only_rls(p_schema text, p_table text)
  RETURNS void LANGUAGE plpgsql AS $$ BEGIN RETURN; END $$;
CREATE FUNCTION platform.enforce_cbc_frozen_fields() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$;
CREATE FUNCTION product_graph.enforce_node_immutability() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$;

-- SECURITY DEFINER RPCs. Includes the write_run_started_artifacts OVERLOAD pair,
-- which is the case most likely to break a hand-written REVOKE list, plus the
-- awkward argument types (text[], jsonb, timestamptz) that the DO-block loop in
-- Section A must format correctly.
CREATE FUNCTION public.get_calibration_readiness() RETURNS jsonb
  LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$ SELECT '{}'::jsonb $$;
CREATE FUNCTION public.invariant_report() RETURNS jsonb
  LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$ SELECT '{}'::jsonb $$;
CREATE FUNCTION public.get_task_type_id(p_code text) RETURNS uuid
  LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$ SELECT gen_random_uuid() $$;
CREATE FUNCTION public.cbc_resolve(p_noun text) RETURNS text
  LANGUAGE sql SECURITY DEFINER SET search_path = platform, public AS $$ SELECT 'stub'::text $$;
CREATE FUNCTION public.graph_ratify_node(p_tenant uuid, p_product text, p_node_key text,
    p_new_status text, p_ratified_by text) RETURNS jsonb
  LANGUAGE sql SECURITY DEFINER SET search_path = product_graph, public AS $$ SELECT '{}'::jsonb $$;
CREATE FUNCTION public.graph_set_maps_to_codebase(p_tenant uuid, p_product text,
    p_node_key text, p_cbc_ids text[]) RETURNS jsonb
  LANGUAGE sql SECURITY DEFINER SET search_path = product_graph, public AS $$ SELECT '{}'::jsonb $$;
CREATE FUNCTION public.graph_upsert_node(p_tenant uuid, p_product text, p_node_type text,
    p_node_key text, p_title text, p_status text, p_created_by text, p_kind text,
    p_blocking boolean, p_divergence text, p_maps_to_codebase text[], p_aliases text[],
    p_node_attributes jsonb) RETURNS jsonb
  LANGUAGE sql SECURITY DEFINER SET search_path = product_graph, public AS $$ SELECT '{}'::jsonb $$;
CREATE FUNCTION public.ingest_telemetry_event(p_id uuid, p_event_type text, p_schema_version text,
    p_emitted_at timestamptz, p_sequence_number integer, p_trace_id uuid, p_run_id uuid,
    p_parent_run_id uuid, p_campaign_id uuid, p_tenant_id uuid, p_is_replay boolean,
    p_replay_id uuid, p_payload jsonb) RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$ BEGIN RETURN; END $$;
CREATE FUNCTION public.write_run_started_artifacts(p_run_id uuid, p_tenant_id uuid, p_model text,
    p_provider text, p_task_type_code text, p_task_complexity_bucket text) RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$ BEGIN RETURN; END $$;
CREATE FUNCTION public.write_run_started_artifacts(p_run_id uuid, p_tenant_id uuid, p_model text,
    p_provider text, p_task_type_code text, p_task_complexity_bucket text,
    p_tokens_in_hint integer, p_declared_max_steps integer) RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$ BEGIN RETURN; END $$;
CREATE FUNCTION public.write_run_completed_artifacts(p_run_id uuid, p_tenant_id uuid,
    p_actual_cost_usd numeric, p_tokens_in integer, p_tokens_out integer,
    p_started_at timestamptz, p_completed_at timestamptz, p_error_text text) RETURNS void
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$ BEGIN RETURN; END $$;

-- ---------------------------------------------------------------------------
-- Supabase's stock bootstrap grants - the root cause of the exposure
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES    IN SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO anon, authenticated, service_role;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA platform      TO anon, authenticated, service_role;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA product_graph TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO anon, authenticated;

-- Seed one row per table so "reachable and returns data" is distinguishable
-- from "reachable but empty" in the assertions.
INSERT INTO public.contractor_rows (name) VALUES ('fixture');
INSERT INTO public.pipeline_config (key)  VALUES ('fixture');
INSERT INTO public.agent_outputs (output_type) VALUES ('code_review');
INSERT INTO public.audit_log (action) VALUES ('fixture');
INSERT INTO public.agile_intake_jobs (product_key, intake) VALUES ('fixture', '[]'::jsonb);
