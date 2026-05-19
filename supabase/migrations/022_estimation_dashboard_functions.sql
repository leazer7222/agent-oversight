-- Migration 022: Estimation Dashboard — SECURITY DEFINER query functions
--
-- All estimation dashboard reads go through these public-schema functions.
-- Rationale: PostgREST only exposes the public schema; non-public schemas
-- (cost_intelligence, model_intelligence, runtime_governance, telemetry)
-- are not accessible via supabase.schema().from() at runtime.
-- Pattern established in migration 021.
--
-- No CREATE TABLE — linter will pass clean.
-- Depends on: 013-021 (all Phase 1 schemas + public helper functions)
-- Apply to project: hdhovyrlnfojtkqbcegh
-- RFC references: RFC-002, RFC-004, RFC-005, RFC-009

-- ---------------------------------------------------------------------------
-- 1. get_estimation_run_detail(p_run_id UUID)
--
--    Returns all four artifacts for a single run, plus the pricing table
--    version record used at estimate time.
--    Used by: /api/estimation/runs/[id]
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.get_estimation_run_detail(p_run_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_estimate       JSONB;
  v_evaluation     JSONB;
  v_recommendation JSONB;
  v_reservation    JSONB;
  v_settlement     JSONB;
  v_pricing        JSONB;
  v_task_type      JSONB;
  v_run            JSONB;
  v_reservation_id UUID;
BEGIN

  -- Run record (public schema — accessible normally)
  SELECT jsonb_build_object(
    'id',                    r.id,
    'agent_id',              r.agent_id,
    'status',                r.status,
    'started_at',            r.started_at,
    'completed_at',          r.completed_at,
    'cost_usd',              r.cost_usd,
    'tokens_in',             r.tokens_in,
    'tokens_out',            r.tokens_out,
    'error',                 r.error,
    'task_complexity_bucket',r.task_complexity_bucket,
    'task_classifier_version', r.task_classifier_version
  ) INTO v_run
  FROM runs r
  WHERE r.id = p_run_id;

  -- Estimate artifact (cost_intelligence schema)
  SELECT to_jsonb(ea) INTO v_estimate
  FROM cost_intelligence.estimate_artifacts ea
  WHERE ea.run_request_id = p_run_id;

  -- Evaluation artifact
  SELECT to_jsonb(ev) INTO v_evaluation
  FROM cost_intelligence.evaluation_artifacts ev
  WHERE ev.run_id = p_run_id;

  -- Recommendation artifact
  SELECT to_jsonb(ra) INTO v_recommendation
  FROM model_intelligence.recommendation_artifacts ra
  WHERE ra.run_request_id = p_run_id;

  -- Budget reservation
  SELECT to_jsonb(br) INTO v_reservation
  FROM runtime_governance.budget_reservations br
  WHERE br.run_id = p_run_id;

  -- Reservation id for settlement lookup
  SELECT br.id INTO v_reservation_id
  FROM runtime_governance.budget_reservations br
  WHERE br.run_id = p_run_id;

  -- Settlement record (final, non-provisional)
  IF v_reservation_id IS NOT NULL THEN
    SELECT to_jsonb(sr) INTO v_settlement
    FROM runtime_governance.settlement_records sr
    WHERE sr.reservation_id = v_reservation_id
      AND sr.is_provisional = false
    LIMIT 1;
  END IF;

  -- Pricing table version used at estimate time
  IF v_estimate IS NOT NULL THEN
    SELECT jsonb_build_object(
      'id',             ptv.id,
      'version',        ptv.version,
      'status',         ptv.status,
      'effective_from', ptv.effective_from
    ) INTO v_pricing
    FROM cost_intelligence.pricing_table_versions ptv
    WHERE ptv.id = (v_estimate->>'pricing_table_version_id')::uuid;
  END IF;

  -- Task type definition (for complexity thresholds in the UI)
  SELECT jsonb_build_object(
    'code',                  tt.code,
    'label',                 tt.label,
    'complexity_definition', tt.complexity_definition,
    'min_calibration_runs',  tt.min_calibration_runs
  ) INTO v_task_type
  FROM runs r
  JOIN cost_intelligence.task_types tt ON tt.id = r.task_type_id
  WHERE r.id = p_run_id;

  RETURN jsonb_build_object(
    'run',            v_run,
    'estimate',       v_estimate,
    'evaluation',     v_evaluation,
    'recommendation', v_recommendation,
    'reservation',    v_reservation,
    'settlement',     v_settlement,
    'pricing_version',v_pricing,
    'task_type',      v_task_type
  );

EXCEPTION
  WHEN OTHERS THEN
    RETURN jsonb_build_object(
      'error',    SQLERRM,
      'run_id',   p_run_id
    );
END;
$$;

COMMENT ON FUNCTION public.get_estimation_run_detail(UUID) IS
  'Returns all estimation artifacts for a single run. '
  'Called by /api/estimation/runs/[id]. '
  'RFC-002 ART-001, ART-002, ART-005, ART-006, ART-007.';


-- ---------------------------------------------------------------------------
-- 2. get_estimation_accuracy_overview()
--
--    Headline accuracy metrics for the overview page.
--    Excludes rows with telemetry_status != ''complete'' from all accuracy
--    numbers. Completeness counts are tracked separately.
--    Used by: /api/estimation/overview
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.get_estimation_accuracy_overview()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_result JSONB;
BEGIN
  SELECT jsonb_build_object(

    'total_evaluations',
      COUNT(*),

    'complete_evaluations',
      COUNT(*) FILTER (WHERE ev.telemetry_status = 'complete'),

    'incomplete_evaluations',
      COUNT(*) FILTER (WHERE ev.telemetry_status = 'incomplete'),

    'provisional_evaluations',
      COUNT(*) FILTER (WHERE ev.telemetry_status = 'provisional'),

    'completeness_pct',
      ROUND(
        100.0 * COUNT(*) FILTER (WHERE ev.telemetry_status = 'complete')
        / NULLIF(COUNT(*), 0), 1
      ),

    -- MAPE — excludes incomplete telemetry
    -- Note: AVG/PERCENTILE_CONT return float8; ROUND(float8, int) does not exist
    -- in Postgres — must cast to ::numeric first. Same applies everywhere below.
    'mape',
      ROUND(
        (AVG(ABS(ev.percentage_error)) FILTER (
          WHERE ev.telemetry_status = 'complete' AND ev.percentage_error IS NOT NULL
        ))::numeric,
        1
      ),

    -- Median signed error (positive = systematic underestimation)
    'median_signed_error_pct',
      ROUND(
        (PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ev.percentage_error))::numeric,
        1
      ),

    -- Directional bias
    'underestimate_count',
      COUNT(*) FILTER (WHERE ev.underestimated = true),

    'overestimate_count',
      COUNT(*) FILTER (WHERE ev.underestimated = false),

    'underestimate_rate_pct',
      ROUND(
        (100.0 * COUNT(*) FILTER (WHERE ev.underestimated = true)
        / NULLIF(COUNT(*) FILTER (WHERE ev.underestimated IS NOT NULL), 0))::numeric,
        1
      ),

    -- Band containment: did actual fall within the p95 estimate?
    'within_p95_band_count',
      COUNT(*) FILTER (
        WHERE ev.telemetry_status = 'complete' AND ev.actual_cost_usd <= ea.cost_p95_usd
      ),

    'within_p95_band_pct',
      ROUND(
        (100.0 * COUNT(*) FILTER (
          WHERE ev.telemetry_status = 'complete' AND ev.actual_cost_usd <= ea.cost_p95_usd
        ) / NULLIF(COUNT(*) FILTER (WHERE ev.telemetry_status = 'complete'), 0))::numeric,
        1
      ),

    -- Severe misses (>200% error) — manual inspection candidates
    'severe_miss_count',
      COUNT(*) FILTER (
        WHERE ev.telemetry_status = 'complete' AND ABS(ev.percentage_error) > 200
      ),

    -- Unevaluated: has estimate but no evaluation yet (pipeline gap)
    'unevaluated_estimates',
      (
        SELECT COUNT(*)
        FROM cost_intelligence.estimate_artifacts ea2
        LEFT JOIN cost_intelligence.evaluation_artifacts ev2
               ON ev2.run_id = ea2.run_request_id
        WHERE ev2.id IS NULL
          AND ea2.created_at < now() - interval '10 minutes'
      )

  ) INTO v_result
  FROM cost_intelligence.evaluation_artifacts ev
  JOIN cost_intelligence.estimate_artifacts ea ON ea.id = ev.estimate_id;

  RETURN v_result;

EXCEPTION
  WHEN OTHERS THEN
    RETURN jsonb_build_object('error', SQLERRM);
END;
$$;

COMMENT ON FUNCTION public.get_estimation_accuracy_overview() IS
  'Headline accuracy metrics for the estimation overview page. '
  'All accuracy figures exclude incomplete telemetry. '
  'RFC-002 ART-001/ART-002.';


-- ---------------------------------------------------------------------------
-- 3. get_biggest_misses(p_limit INT)
--
--    Top-N runs sorted by absolute_error_usd descending.
--    Only rows with telemetry_status = 'complete'.
--    Used by: /api/estimation/biggest-misses
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.get_biggest_misses(p_limit INT DEFAULT 20)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_rows JSONB;
BEGIN
  SELECT COALESCE(jsonb_agg(row ORDER BY row->>'absolute_error_usd' DESC), '[]'::jsonb)
  INTO v_rows
  FROM (
    SELECT jsonb_build_object(
      'run_id',               ea.run_request_id,
      'estimated_at',         ea.created_at,
      'model',                ea.model,
      'provider',             ea.provider,
      'estimation_tier',      ea.estimation_tier,
      'confidence',           ea.confidence,
      'cost_p50_usd',         ea.cost_p50_usd,
      'cost_p95_usd',         ea.cost_p95_usd,
      'warnings',             ea.warnings,
      'actual_cost_usd',      ev.actual_cost_usd,
      'absolute_error_usd',   ev.absolute_error_usd,
      'percentage_error',     ev.percentage_error,
      'underestimated',       ev.underestimated,
      'telemetry_status',     ev.telemetry_status,
      'is_outlier',           ev.is_outlier,
      'tokens_in_p50',        ea.tokens_in_p50,
      'tokens_out_p50',       ea.tokens_out_p50,
      'tokens_in_actual',     ev.tokens_in_actual,
      'tokens_out_actual',    ev.tokens_out_actual,
      'task_type_code',       tt.code,
      'task_type_label',      tt.label,
      'task_complexity_bucket', r.task_complexity_bucket,
      'started_at',           r.started_at
    ) AS row
    FROM cost_intelligence.evaluation_artifacts ev
    JOIN cost_intelligence.estimate_artifacts ea ON ea.id = ev.estimate_id
    JOIN runs r ON r.id = ev.run_id
    JOIN cost_intelligence.task_types tt ON tt.id = r.task_type_id
    WHERE ev.telemetry_status = 'complete'
      AND ev.absolute_error_usd IS NOT NULL
    ORDER BY ev.absolute_error_usd DESC
    LIMIT p_limit
  ) sub;

  RETURN v_rows;

EXCEPTION
  WHEN OTHERS THEN
    RETURN jsonb_build_object('error', SQLERRM);
END;
$$;

COMMENT ON FUNCTION public.get_biggest_misses(INT) IS
  'Top-N estimation misses by absolute dollar error. '
  'Only includes complete telemetry. '
  'Called by /api/estimation/biggest-misses.';


-- ---------------------------------------------------------------------------
-- 4. get_bucket_accuracy()
--
--    Per-bucket (task_type × complexity) accuracy summary.
--    Shows all 24 possible buckets (8 types × 3 complexities), including
--    empty ones, so the calibration readiness grid is always complete.
--    Used by: /api/estimation/buckets
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.get_bucket_accuracy()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_rows JSONB;
BEGIN
  SELECT COALESCE(jsonb_agg(row), '[]'::jsonb)
  INTO v_rows
  FROM (
    SELECT jsonb_build_object(
      'bucket_key',          tt.code || '/' || c.bucket,
      'task_type_code',      tt.code,
      'task_type_label',     tt.label,
      'complexity',          c.bucket,
      'n_complete',          COUNT(ev.id) FILTER (WHERE ev.telemetry_status = 'complete'),
      'n_total',             COUNT(ev.id),
      'avg_pct_error',
        ROUND(
          (AVG(ev.percentage_error) FILTER (WHERE ev.telemetry_status = 'complete'))::numeric,
          1
        ),
      'median_pct_error',
        ROUND(
          (PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ev.percentage_error))::numeric,
          1
        ),
      'mape',
        ROUND(
          (AVG(ABS(ev.percentage_error)) FILTER (WHERE ev.telemetry_status = 'complete'))::numeric,
          1
        ),
      'avg_abs_error_usd',
        ROUND(
          (AVG(ev.absolute_error_usd) FILTER (WHERE ev.telemetry_status = 'complete'))::numeric,
          4
        ),
      'underestimate_pct',
        ROUND(
          (100.0 * COUNT(*) FILTER (WHERE ev.underestimated = true)
           / NULLIF(COUNT(*) FILTER (WHERE ev.underestimated IS NOT NULL), 0))::numeric,
          0
        ),
      'outlier_count',
        COUNT(*) FILTER (WHERE ev.is_outlier = true),
      'calibration_threshold', tt.min_calibration_runs,
      'calibration_status',
        CASE
          WHEN COUNT(ev.id) FILTER (WHERE ev.telemetry_status = 'complete') = 0
            THEN 'never_observed'
          WHEN COUNT(ev.id) FILTER (WHERE ev.telemetry_status = 'complete') < 10
            THEN 'sparse'
          WHEN (COUNT(ev.id) FILTER (WHERE ev.is_outlier = true))::float
               / NULLIF(COUNT(ev.id) FILTER (WHERE ev.telemetry_status = 'complete'), 0) >= 0.3
            THEN 'outlier_dominated'
          WHEN COUNT(ev.id) FILTER (WHERE ev.telemetry_status = 'complete')
               >= tt.min_calibration_runs
            THEN 'eligible'
          WHEN COUNT(ev.id) FILTER (WHERE ev.telemetry_status = 'complete')
               >= tt.min_calibration_runs * 0.75
            THEN 'nearly_eligible'
          ELSE 'building'
        END,
      'obs_needed',
        GREATEST(0, tt.min_calibration_runs
          - COUNT(ev.id) FILTER (WHERE ev.telemetry_status = 'complete'))
    ) AS row
    FROM cost_intelligence.task_types tt
    -- CROSS JOIN to all three complexity levels so empty buckets appear
    CROSS JOIN (VALUES ('simple'), ('medium'), ('complex')) AS c(bucket)
    LEFT JOIN runs r
           ON r.task_type_id = tt.id
          AND r.task_complexity_bucket = c.bucket
    LEFT JOIN cost_intelligence.estimate_artifacts ea
           ON ea.run_request_id = r.id
    LEFT JOIN cost_intelligence.evaluation_artifacts ev
           ON ev.run_id = r.id
    WHERE tt.taxonomy_version_id = (
      SELECT id FROM cost_intelligence.task_taxonomy_versions WHERE status = 'active'
    )
    GROUP BY tt.code, tt.label, c.bucket, tt.min_calibration_runs
    ORDER BY
      COUNT(ev.id) FILTER (WHERE ev.telemetry_status = 'complete') DESC,
      tt.code, c.bucket
  ) sub;

  RETURN v_rows;

EXCEPTION
  WHEN OTHERS THEN
    RETURN jsonb_build_object('error', SQLERRM);
END;
$$;

COMMENT ON FUNCTION public.get_bucket_accuracy() IS
  'Per-bucket estimation accuracy + calibration readiness. '
  'Returns all 24 buckets (8 task types × 3 complexities), including empty. '
  'Bucket status logic is canonical here — do not duplicate in TS. '
  'Called by /api/estimation/buckets.';


-- ---------------------------------------------------------------------------
-- 5. get_calibration_readiness()
--
--    Schema freeze gate + bucket eligibility summary.
--    Used by: /api/estimation/calibration
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.get_calibration_readiness()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_total_evals         BIGINT;
  v_complete_evals      BIGINT;
  v_incomplete_evals    BIGINT;
  v_missing_features    BIGINT;
  v_non_recomputable    BIGINT;
  v_unevaluated         BIGINT;
  v_eligible_buckets    BIGINT;
  v_schema_freeze_safe  BOOLEAN;
  v_bucket_rows         JSONB;
BEGIN

  SELECT
    COUNT(*),
    COUNT(*) FILTER (WHERE telemetry_status = 'complete'),
    COUNT(*) FILTER (WHERE telemetry_status = 'incomplete'),
    COUNT(*) FILTER (WHERE estimation_features_snapshot IS NULL),
    COUNT(*) FILTER (WHERE is_recomputable = false)
  INTO v_total_evals, v_complete_evals, v_incomplete_evals,
       v_missing_features, v_non_recomputable
  FROM cost_intelligence.evaluation_artifacts;

  SELECT COUNT(*)
  INTO v_unevaluated
  FROM cost_intelligence.estimate_artifacts ea
  LEFT JOIN cost_intelligence.evaluation_artifacts ev ON ev.run_id = ea.run_request_id
  WHERE ev.id IS NULL AND ea.created_at < now() - interval '10 minutes';

  -- Re-use get_bucket_accuracy for the grid
  v_bucket_rows := public.get_bucket_accuracy();

  -- Count eligible buckets from the result
  SELECT COUNT(*)
  INTO v_eligible_buckets
  FROM jsonb_array_elements(v_bucket_rows) AS b
  WHERE b->>'calibration_status' = 'eligible';

  -- Schema freeze gate: all conditions must pass
  v_schema_freeze_safe := (
    v_missing_features = 0
    AND v_non_recomputable = 0
    AND (v_incomplete_evals::float / NULLIF(v_total_evals, 0)) < 0.10
    AND v_unevaluated = 0
    AND v_eligible_buckets >= 1
  );

  RETURN jsonb_build_object(
    'schema_freeze_safe',   v_schema_freeze_safe,
    'gate_checks', jsonb_build_object(
      'missing_features_zero',     v_missing_features = 0,
      'all_recomputable',          v_non_recomputable = 0,
      'incomplete_pct_below_10',   (v_incomplete_evals::float / NULLIF(v_total_evals, 0)) < 0.10,
      'no_unevaluated_estimates',  v_unevaluated = 0,
      'has_eligible_bucket',       v_eligible_buckets >= 1
    ),
    'totals', jsonb_build_object(
      'total_evaluations',    v_total_evals,
      'complete_evaluations', v_complete_evals,
      'incomplete_evaluations', v_incomplete_evals,
      'missing_features',     v_missing_features,
      'non_recomputable',     v_non_recomputable,
      'unevaluated_estimates',v_unevaluated,
      'eligible_buckets',     v_eligible_buckets
    ),
    'buckets', v_bucket_rows
  );

EXCEPTION
  WHEN OTHERS THEN
    RETURN jsonb_build_object('error', SQLERRM);
END;
$$;

COMMENT ON FUNCTION public.get_calibration_readiness() IS
  'Phase 2 gate: schema freeze checklist + per-bucket calibration status. '
  'Bucket status logic is owned by get_bucket_accuracy() — not duplicated here. '
  'Called by /api/estimation/calibration.';


-- ---------------------------------------------------------------------------
-- Verification queries (run after applying)
-- ---------------------------------------------------------------------------
-- SELECT public.get_estimation_run_detail('00000000-0000-0000-0000-000000000000');
-- SELECT public.get_estimation_accuracy_overview();
-- SELECT public.get_biggest_misses(5);
-- SELECT jsonb_array_length(public.get_bucket_accuracy());  -- should return 24
-- SELECT public.get_calibration_readiness()->'schema_freeze_safe';
