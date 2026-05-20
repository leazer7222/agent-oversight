-- Migration 023: Estimation accuracy improvements
--
-- Addresses three compounding estimation errors identified from live data:
--
-- 1. Add missing Anthropic Opus models to active pricing table
--    (claude-opus-4-5, claude-opus-4-6 were absent; runs on these models
--    fell back to embedded Sonnet rates, a 5x pricing error)
--
-- 2. Replace write_run_started_artifacts() with improved version:
--    - Accepts p_tokens_in_hint INT (optional) — caller's pre-call token estimate
--    - Uses hint for v_tokens_in when provided; falls back to complexity heuristic
--    - Sets prompt_chars = hint*4 in features snapshot (schema-v1 compatible)
--    - p95 band = 15x p50 when no hint (context size unknown)
--    - p95 band = 2.10x p50 when hint provided (normal tail scenario)
--    - Accepts p_declared_max_steps INT (optional, default 5)
--
-- Root cause of Phase 1 estimation errors (from 4 complete evaluations):
--   All estimates produced $0.033 p50 because:
--   - tokens_in hardcoded to 2000 regardless of actual context size
--   - model hardcoded to claude-sonnet-4-6 in ingest route (Opus runs: 5x error)
--   - p95 = 2.1x provided no useful budget protection
--
-- Expected post-fix accuracy for code-review-agent (back-of-envelope):
--   87K token Opus run:   estimated $1.65 vs actual $1.658 (<1% error)
--   217K token Sonnet run: estimated $0.77 vs actual $0.775 (<1% error)
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- RFC references: RFC-002 §5 (estimation tier ladder), RFC-002 §10.1.1 (features)

-- ---------------------------------------------------------------------------
-- 1. Add missing Opus models to active pricing table
--
--    Opus 4.5 and 4.6 share the same per-token rates as Opus 4.7:
--      input:  $15.00 / M tokens
--      output: $75.00 / M tokens
--    (Anthropic pricing as of 2026-05)
-- ---------------------------------------------------------------------------

UPDATE cost_intelligence.pricing_table_versions
SET entries = entries || '[
  {
    "provider": "anthropic",
    "model": "claude-opus-4-5",
    "rates": {
      "input_per_1k_tokens_usd":        0.015,
      "output_per_1k_tokens_usd":       0.075,
      "cached_input_per_1k_tokens_usd": 0.0015,
      "reasoning_per_1k_tokens_usd":    0.075,
      "tool_call_per_invocation_usd":   0.0
    }
  },
  {
    "provider": "anthropic",
    "model": "claude-opus-4-6",
    "rates": {
      "input_per_1k_tokens_usd":        0.015,
      "output_per_1k_tokens_usd":       0.075,
      "cached_input_per_1k_tokens_usd": 0.0015,
      "reasoning_per_1k_tokens_usd":    0.075,
      "tool_call_per_invocation_usd":   0.0
    }
  }
]'::jsonb
WHERE status = 'active';

-- ---------------------------------------------------------------------------
-- 2. Replace write_run_started_artifacts() with improved version
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.write_run_started_artifacts(
  p_run_id                 UUID,
  p_tenant_id              UUID,
  p_model                  TEXT,
  p_provider               TEXT,
  p_task_type_code         TEXT,
  p_task_complexity_bucket TEXT,
  p_tokens_in_hint         INT  DEFAULT NULL,
  p_declared_max_steps     INT  DEFAULT 5
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
DECLARE
  v_task_type_id    UUID;
  v_pricing_id      UUID;
  v_pricing_entries JSONB;
  v_model_entry     JSONB;
  v_pricing_snap    JSONB;
  v_input_rate      NUMERIC := 0.003;
  v_output_rate     NUMERIC := 0.015;
  v_tokens_in       INT;
  v_tokens_out      INT;
  v_cost_p50        NUMERIC(10,6);
  v_cost_p75        NUMERIC(10,6);
  v_cost_p95        NUMERIC(10,6);
  v_rec_id          UUID;
  v_est_id          UUID;
  v_period_key      TEXT;
  v_period_id       UUID;
  v_budget_avail    NUMERIC(12,4);
  v_features        JSONB;
  v_tier            TEXT;
  v_warnings        TEXT[];
BEGIN
  -- Task type lookup; fall back to code_gen if unknown code supplied
  SELECT id INTO v_task_type_id
  FROM cost_intelligence.task_types WHERE code = p_task_type_code LIMIT 1;
  IF v_task_type_id IS NULL THEN
    SELECT id INTO v_task_type_id
    FROM cost_intelligence.task_types WHERE code = 'code_gen' LIMIT 1;
  END IF;

  -- Active pricing table lookup
  SELECT id, entries INTO v_pricing_id, v_pricing_entries
  FROM cost_intelligence.pricing_table_versions WHERE status = 'active' LIMIT 1;

  IF v_pricing_id IS NOT NULL THEN
    SELECT elem INTO v_model_entry
    FROM jsonb_array_elements(v_pricing_entries) elem
    WHERE elem->>'provider' = p_provider AND elem->>'model' = p_model
    LIMIT 1;
  END IF;

  IF v_model_entry IS NOT NULL THEN
    v_input_rate  := (v_model_entry->'rates'->>'input_per_1k_tokens_usd')::NUMERIC;
    v_output_rate := (v_model_entry->'rates'->>'output_per_1k_tokens_usd')::NUMERIC;
    v_pricing_snap := jsonb_build_object(
      'provider', p_provider, 'model', p_model,
      'rates', v_model_entry->'rates', 'captured_at', now()
    );
    v_tier := 'deterministic';
  ELSE
    -- Model not in pricing table — use conservative Sonnet-class fallback
    v_pricing_snap := jsonb_build_object(
      'provider', p_provider, 'model', p_model,
      'rates', jsonb_build_object(
        'input_per_1k_tokens_usd',        0.003,
        'output_per_1k_tokens_usd',       0.015,
        'cached_input_per_1k_tokens_usd', 0.0003,
        'reasoning_per_1k_tokens_usd',    0.015,
        'tool_call_per_invocation_usd',   0.0
      ),
      'captured_at', now()
    );
    v_tier := 'embedded_fallback';
    IF v_pricing_id IS NULL THEN v_pricing_id := gen_random_uuid(); END IF;
    v_warnings := array_append(
      v_warnings,
      format('model ''%s/%s'' not in pricing table — using embedded fallback rates', p_provider, p_model)
    );
  END IF;

  -- Input token estimate:
  --   Use caller-provided hint when available (agent knows its own context size).
  --   Fall back to complexity heuristic only when hint is absent.
  v_tokens_in := CASE
    WHEN p_tokens_in_hint IS NOT NULL THEN p_tokens_in_hint
    WHEN p_task_complexity_bucket = 'simple'  THEN 500
    WHEN p_task_complexity_bucket = 'complex' THEN 8000
    ELSE 2000
  END;

  -- Output token estimate: engineering heuristic by task type + complexity
  v_tokens_out := CASE p_task_type_code || '_' || p_task_complexity_bucket
    WHEN 'info_retrieval_simple'  THEN 250   WHEN 'info_retrieval_medium'  THEN 700   WHEN 'info_retrieval_complex'  THEN 1800
    WHEN 'content_gen_simple'     THEN 600   WHEN 'content_gen_medium'     THEN 2200  WHEN 'content_gen_complex'     THEN 5500
    WHEN 'code_gen_simple'        THEN 450   WHEN 'code_gen_medium'        THEN 1800  WHEN 'code_gen_complex'        THEN 4500
    WHEN 'data_analysis_simple'   THEN 350   WHEN 'data_analysis_medium'   THEN 1100  WHEN 'data_analysis_complex'   THEN 3200
    WHEN 'orchestration_simple'   THEN 250   WHEN 'orchestration_medium'   THEN 900   WHEN 'orchestration_complex'   THEN 3000
    WHEN 'classification_simple'  THEN 80    WHEN 'classification_medium'  THEN 250   WHEN 'classification_complex'  THEN 600
    WHEN 'conversation_simple'    THEN 200   WHEN 'conversation_medium'    THEN 600   WHEN 'conversation_complex'    THEN 1600
    WHEN 'evaluation_simple'      THEN 350   WHEN 'evaluation_medium'      THEN 1000  WHEN 'evaluation_complex'      THEN 2500
    ELSE 1000
  END;

  -- Cost bands
  v_cost_p50 := GREATEST(
    round(((v_tokens_in * v_input_rate + v_tokens_out * v_output_rate) / 1000)::numeric, 6),
    0.000001
  );
  v_cost_p75 := round(v_cost_p50 * 1.35, 6);
  -- p95: wide (15x) when context size unknown, normal (2.1x) when hint was provided
  v_cost_p95 := CASE
    WHEN p_tokens_in_hint IS NULL THEN round(v_cost_p50 * 15.0, 6)
    ELSE                               round(v_cost_p50 * 2.10, 6)
  END;

  -- Build warnings array
  IF p_tokens_in_hint IS NULL THEN
    v_warnings := array_append(
      v_warnings,
      'prompt_chars=0: context size unknown at ingest time; p95 band widened to 15x'
    );
  END IF;
  v_warnings := array_append(v_warnings, 'feature_snapshot_partial: hashes unavailable at ingest');

  -- Feature snapshot (features-v1 schema — frozen)
  -- prompt_chars: back-calculated from hint (* 4 chars/token) when hint is available
  v_features := jsonb_build_object(
    'feature_schema_version',       'features-v1',
    'captured_at',                  now(),
    'prompt_chars',                 COALESCE(p_tokens_in_hint * 4, 0),
    'context_ref_count',            0,
    'artifact_ref_count',           0,
    'tools_enabled',                '[]'::jsonb,
    'tools_definition_hash',        'unknown',
    'system_prompt_hash',           'unknown',
    'declared_max_steps',           COALESCE(p_declared_max_steps, 5),
    'declared_child_runs',          0,
    'task_type_code',               p_task_type_code,
    'task_complexity_bucket',       p_task_complexity_bucket,
    'context_window_requested_pct', 0
  );

  -- Recommendation artifact (passthrough stub)
  INSERT INTO model_intelligence.recommendation_artifacts (
    run_request_id, tenant_id, schema_version, routing_mode, model_selection_mode,
    selected_model, selected_provider, selection_reason, task_type_id, task_complexity_bucket,
    budget_eligible_models, budget_available_at_routing, cold_start_model_selected,
    routing_confidence, candidates_evaluated
  ) VALUES (
    p_run_id, p_tenant_id, '1.0.0', 'passthrough', 'user_specified',
    p_model, p_provider, 'passthrough: routing engine not active in Phase 1',
    v_task_type_id, p_task_complexity_bucket, ARRAY[p_model], 9999.9999, false,
    'not_applicable', '[]'
  ) ON CONFLICT (run_request_id) DO NOTHING;
  SELECT id INTO v_rec_id
  FROM model_intelligence.recommendation_artifacts WHERE run_request_id = p_run_id;

  -- Estimate artifact
  INSERT INTO cost_intelligence.estimate_artifacts (
    run_request_id, tenant_id, schema_version, model, provider, model_selection_mode,
    model_selection_reason, pricing_table_version_id, pricing_snapshot, calibration_source,
    estimation_features_snapshot, estimation_tier,
    cost_p50_usd, cost_p75_usd, cost_p95_usd,
    tokens_in_p50, tokens_out_p50, confidence, warnings
  ) VALUES (
    p_run_id, p_tenant_id, '1.0.0', p_model, p_provider, 'user_specified',
    'passthrough via recommendation ' || COALESCE(v_rec_id::TEXT, 'unknown'),
    v_pricing_id, v_pricing_snap, 'deterministic',
    v_features, v_tier,
    v_cost_p50, v_cost_p75, v_cost_p95,
    v_tokens_in, v_tokens_out, 'low', v_warnings
  ) ON CONFLICT (run_request_id) DO NOTHING;
  SELECT id INTO v_est_id
  FROM cost_intelligence.estimate_artifacts WHERE run_request_id = p_run_id;

  -- Budget period (upsert — one row per tenant per month)
  v_period_key := to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM');

  INSERT INTO runtime_governance.budget_periods (tenant_id, period_key, period_type, budget_usd)
  VALUES (p_tenant_id, v_period_key, 'monthly', 9999.0000)
  ON CONFLICT (tenant_id, period_key) WHERE cost_center_id IS NULL DO NOTHING;

  SELECT id, budget_usd - reserved_usd - consumed_usd INTO v_period_id, v_budget_avail
  FROM runtime_governance.budget_periods
  WHERE tenant_id = p_tenant_id AND period_key = v_period_key AND cost_center_id IS NULL;

  -- Budget reservation at p95 tier
  IF v_est_id IS NOT NULL AND v_period_id IS NOT NULL THEN
    INSERT INTO runtime_governance.budget_reservations (
      run_id, tenant_id, estimate_id, recommendation_id, trace_id,
      period_key, reserved_usd, reservation_tier, budget_available_at_dispatch, expires_at
    ) VALUES (
      p_run_id, p_tenant_id, v_est_id, v_rec_id, p_run_id,
      v_period_key, v_cost_p95, 'p95', COALESCE(v_budget_avail, 9999), now() + interval '2 hours'
    ) ON CONFLICT (run_id) DO NOTHING;

    UPDATE runtime_governance.budget_periods
    SET reserved_usd = reserved_usd + v_cost_p95,
        updated_at   = now(),
        version      = version + 1
    WHERE id = v_period_id
      AND reserved_usd + consumed_usd + v_cost_p95 <= budget_usd;
  END IF;

  RETURN jsonb_build_object(
    'rec_id',   v_rec_id,
    'est_id',   v_est_id,
    'cost_p50', v_cost_p50,
    'cost_p95', v_cost_p95
  );
EXCEPTION WHEN OTHERS THEN
  RETURN jsonb_build_object('error', SQLERRM);
END;
$$;
