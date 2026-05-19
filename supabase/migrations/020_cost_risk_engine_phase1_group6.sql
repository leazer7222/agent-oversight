-- Migration 020: Adaptive Cost Risk Engine — Phase 1 Group 6
--   Class C monitoring invariants — Postgres reporting function
--
-- Creates public.invariant_report() — callable via supabase.rpc('invariant_report').
-- Returns a JSONB blob consumed by the /api/monitoring/invariants route and
-- the /dashboard/invariants page.
--
-- All queries are read-only. SECURITY DEFINER so the function can access
-- pg_stat_user_tables (system catalog) even from a restricted role.
--
-- Depends on: 013-019 (all Phase 1 Group 1-5 schemas)
-- RFC references: RFC-002 §11 (INV-ART-009 to 014), RFC-003 §14, RFC-004 §15,
--                RFC-005 §9, RFC-009 §13, RFC-010 §6

CREATE OR REPLACE FUNCTION public.invariant_report()
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_result JSONB;
BEGIN

  SELECT jsonb_build_object(
    'checked_at', now(),

    -- -----------------------------------------------------------------------
    -- RFC-003 §14 — Telemetry pipeline health
    -- -----------------------------------------------------------------------
    'telemetry_events_5min', (
      SELECT COUNT(*) FROM telemetry.raw_events
      WHERE received_at > now() - interval '5 minutes'
    ),
    'telemetry_events_1h', (
      SELECT COUNT(*) FROM telemetry.raw_events
      WHERE received_at > now() - interval '1 hour'
    ),

    -- -----------------------------------------------------------------------
    -- RFC-002 INV-ART-009 — runs awaiting evaluation
    -- Count: estimate_artifacts older than 10 min with no evaluation_artifact.
    -- (Only estimates are tracked; pre-Group-3 runs have no estimate so are excluded.)
    -- -----------------------------------------------------------------------
    'runs_awaiting_evaluation', (
      SELECT COUNT(*)
      FROM cost_intelligence.estimate_artifacts ea
      LEFT JOIN cost_intelligence.evaluation_artifacts ev ON ev.run_id = ea.run_request_id
      WHERE ea.created_at < now() - interval '10 minutes'
        AND ev.id IS NULL
    ),

    -- -----------------------------------------------------------------------
    -- INV-ART-013 — runs missing recommendation_artifact (last 24h)
    -- -----------------------------------------------------------------------
    'runs_without_recommendation_24h', (
      SELECT COUNT(*)
      FROM runs r
      LEFT JOIN model_intelligence.recommendation_artifacts ra ON ra.run_request_id = r.id
      WHERE r.created_at > now() - interval '24 hours'
        AND ra.id IS NULL
    ),

    -- -----------------------------------------------------------------------
    -- Estimate coverage (last 24h) — every run should have an estimate_artifact
    -- -----------------------------------------------------------------------
    'runs_without_estimate_24h', (
      SELECT COUNT(*)
      FROM runs r
      LEFT JOIN cost_intelligence.estimate_artifacts ea ON ea.run_request_id = r.id
      WHERE r.created_at > now() - interval '24 hours'
        AND ea.id IS NULL
    ),

    -- -----------------------------------------------------------------------
    -- RFC-004 INV-RG-007 — active reservations for completed runs > 15 min
    -- -----------------------------------------------------------------------
    'unsettled_reservations', (
      SELECT COUNT(*)
      FROM runtime_governance.budget_reservations br
      JOIN runs r ON r.id = br.run_id
      WHERE br.status = 'active'
        AND r.completed_at IS NOT NULL
        AND r.completed_at < now() - interval '15 minutes'
    ),

    -- -----------------------------------------------------------------------
    -- RFC-002 INV-ART-001 — estimate_artifacts with NULL features snapshot
    -- Always must be 0 (Class A constraint enforced at write time)
    -- -----------------------------------------------------------------------
    'estimates_missing_features', (
      SELECT COUNT(*) FROM cost_intelligence.estimate_artifacts
      WHERE estimation_features_snapshot IS NULL
    ),

    -- -----------------------------------------------------------------------
    -- RFC-009 §13 Pattern 4 — immutability: n_tup_upd on Class I tables
    -- Non-zero means an UPDATE was issued on an artifact table — invariant violation.
    -- Values reset on Postgres restart; 0 is always safe (conservative pass).
    -- -----------------------------------------------------------------------
    'n_tup_upd_estimate_artifacts', (
      SELECT COALESCE(n_tup_upd, 0) FROM pg_stat_user_tables
      WHERE schemaname = 'cost_intelligence' AND relname = 'estimate_artifacts'
    ),
    'n_tup_upd_evaluation_artifacts', (
      SELECT COALESCE(n_tup_upd, 0) FROM pg_stat_user_tables
      WHERE schemaname = 'cost_intelligence' AND relname = 'evaluation_artifacts'
    ),
    'n_tup_upd_recommendation_artifacts', (
      SELECT COALESCE(n_tup_upd, 0) FROM pg_stat_user_tables
      WHERE schemaname = 'model_intelligence' AND relname = 'recommendation_artifacts'
    ),
    'n_tup_upd_pricing_table_versions', (
      SELECT COALESCE(n_tup_upd, 0) FROM pg_stat_user_tables
      WHERE schemaname = 'cost_intelligence' AND relname = 'pricing_table_versions'
    ),
    'n_tup_upd_task_types', (
      SELECT COALESCE(n_tup_upd, 0) FROM pg_stat_user_tables
      WHERE schemaname = 'cost_intelligence' AND relname = 'task_types'
    ),
    'n_tup_upd_raw_events', (
      SELECT COALESCE(n_tup_upd, 0) FROM pg_stat_user_tables
      WHERE schemaname = 'telemetry' AND relname = 'raw_events'
    ),

    -- -----------------------------------------------------------------------
    -- RFC-005 §9 — task type distribution (last 7 days)
    -- -----------------------------------------------------------------------
    'task_distribution_7d', (
      SELECT COALESCE(jsonb_agg(row ORDER BY row->>'count' DESC), '[]'::jsonb)
      FROM (
        SELECT jsonb_build_object(
          'code',  tt.code,
          'label', tt.label,
          'count', COUNT(r.id)
        ) AS row
        FROM runs r
        JOIN cost_intelligence.task_types tt ON tt.id = r.task_type_id
        WHERE r.created_at > now() - interval '7 days'
        GROUP BY tt.code, tt.label
      ) sub
    ),

    -- -----------------------------------------------------------------------
    -- Complexity distribution (last 7 days)
    -- -----------------------------------------------------------------------
    'complexity_distribution_7d', (
      SELECT COALESCE(jsonb_agg(row ORDER BY row->>'count' DESC), '[]'::jsonb)
      FROM (
        SELECT jsonb_build_object(
          'bucket', task_complexity_bucket,
          'count',  COUNT(id)
        ) AS row
        FROM runs
        WHERE created_at > now() - interval '7 days'
        GROUP BY task_complexity_bucket
      ) sub
    ),

    -- -----------------------------------------------------------------------
    -- Estimation tier breakdown (all time) — calibrated vs deterministic vs fallback
    -- -----------------------------------------------------------------------
    'estimation_tier_breakdown', (
      SELECT COALESCE(jsonb_agg(row ORDER BY row->>'count' DESC), '[]'::jsonb)
      FROM (
        SELECT jsonb_build_object(
          'tier',  estimation_tier,
          'count', COUNT(id)
        ) AS row
        FROM cost_intelligence.estimate_artifacts
        GROUP BY estimation_tier
      ) sub
    ),

    -- -----------------------------------------------------------------------
    -- Accuracy overview (all complete evaluations)
    -- -----------------------------------------------------------------------
    'accuracy_overview', (
      SELECT jsonb_build_object(
        'total_evaluations',     COUNT(*),
        'complete_evaluations',  COUNT(*) FILTER (WHERE telemetry_status = 'complete'),
        'incomplete_evaluations',COUNT(*) FILTER (WHERE telemetry_status = 'incomplete'),
        'avg_pct_error',         ROUND(AVG(percentage_error) FILTER (WHERE percentage_error IS NOT NULL)::numeric, 2),
        'underestimated_pct',    ROUND(
          (100.0 * COUNT(*) FILTER (WHERE underestimated = true) /
           NULLIF(COUNT(*) FILTER (WHERE underestimated IS NOT NULL), 0))::numeric, 1
        )
      )
      FROM cost_intelligence.evaluation_artifacts
    ),

    -- -----------------------------------------------------------------------
    -- Totals
    -- -----------------------------------------------------------------------
    'totals', jsonb_build_object(
      'runs_24h',              (SELECT COUNT(*) FROM runs WHERE created_at > now() - interval '24 hours'),
      'runs_7d',               (SELECT COUNT(*) FROM runs WHERE created_at > now() - interval '7 days'),
      'estimate_artifacts',    (SELECT COUNT(*) FROM cost_intelligence.estimate_artifacts),
      'evaluation_artifacts',  (SELECT COUNT(*) FROM cost_intelligence.evaluation_artifacts),
      'recommendation_artifacts', (SELECT COUNT(*) FROM model_intelligence.recommendation_artifacts),
      'budget_reservations',   (SELECT COUNT(*) FROM runtime_governance.budget_reservations),
      'raw_events_total',      (SELECT COUNT(*) FROM telemetry.raw_events)
    )

  ) INTO v_result;

  RETURN v_result;

EXCEPTION
  WHEN OTHERS THEN
    -- Return a partial result rather than failing the whole page
    RETURN jsonb_build_object(
      'error',      SQLERRM,
      'checked_at', now()
    );
END;
$$;

COMMENT ON FUNCTION public.invariant_report() IS
  'Phase 1 Group 6 — Class C monitoring invariants. '
  'Called by /api/monitoring/invariants. '
  'RFC references: RFC-002 §11, RFC-003 §14, RFC-004 §15, RFC-005 §9, RFC-009 §13.';

-- ---------------------------------------------------------------------------
-- Verification
-- ---------------------------------------------------------------------------
-- SELECT public.invariant_report();
