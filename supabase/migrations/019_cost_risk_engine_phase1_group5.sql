-- Migration 019: Adaptive Cost Risk Engine — Phase 1 Group 5
--   cost_intelligence.evaluation_artifacts (ART-002, RFC-002 §10)
--
-- Depends on: 017 (estimate_artifacts), 018 (budget_reservations)
-- Apply to project: hdhovyrlnfojtkqbcegh
-- RFC references: RFC-002 §10 (ART-002), RFC-009

-- ---------------------------------------------------------------------------
-- evaluation_artifacts — ART-002 (RFC-002 §10)
--
--    Records the post-run comparison between estimate and actuals.
--    Created asynchronously after every run reaching terminal state.
--    Immutable after write. Idempotent creation (UNIQUE on run_id).
--
--    Phase 1 operating mode:
--      eval_algorithm_version  = 'eval-v1-deterministic'
--      calibration_bucket_id   = NULL (Phase 2)
--      is_outlier              = false (Phase 2 outlier detection deferred)
--      is_recomputable         = true  (all Phase 1 estimates are recomputable)
--
--    RFC-002 §10 ART-002 incomplete telemetry handling:
--      If actual_cost_usd = NULL at evaluation time:
--        telemetry_status = 'incomplete', actual_cost_usd = 0.0
--        Error metrics set to NULL (do not use estimate as surrogate)
--        Excluded from calibration until reconciled
--
--    derivation_manifest JSONB is required and documents input sources.
-- ---------------------------------------------------------------------------

CREATE TABLE cost_intelligence.evaluation_artifacts (
  id                        UUID          NOT NULL  DEFAULT gen_random_uuid(),
  estimate_id               UUID          NOT NULL,
  run_id                    UUID          NOT NULL,
  tenant_id                 UUID          NOT NULL,
  schema_version            TEXT          NOT NULL  DEFAULT '1.0.0',
  eval_algorithm_version    TEXT          NOT NULL,

  telemetry_status          TEXT          NOT NULL
                              CHECK (telemetry_status IN (
                                'complete', 'incomplete', 'provisional', 'reconciled'
                              )),

  actual_cost_usd           NUMERIC(10,6) NOT NULL,
  actual_cost_input_usd     NUMERIC(10,6),
  actual_cost_output_usd    NUMERIC(10,6),
  actual_cost_cached_usd    NUMERIC(10,6),
  actual_cost_tools_usd     NUMERIC(10,6),
  actual_cost_reasoning_usd NUMERIC(10,6),

  tokens_in_actual          INTEGER,
  tokens_out_actual         INTEGER,
  tokens_cached_actual      INTEGER,
  tokens_reasoning_actual   INTEGER,

  wall_clock_ms             INTEGER,
  time_to_first_token_ms    INTEGER,
  retry_count               INTEGER       NOT NULL  DEFAULT 0,
  failure_mode              TEXT
                              CHECK (failure_mode IN (
                                'rate_limit', 'context_overflow', 'content_filter',
                                'api_error', 'timeout', 'user_cancelled',
                                'cost_limit_abort', 'force_killed', 'provider_unreachable'
                              )),
  actual_tool_calls         INTEGER,
  actual_child_runs         INTEGER,
  context_window_used_pct   NUMERIC(5,2),

  absolute_error_usd        NUMERIC(10,6),
  percentage_error          NUMERIC(8,4),
  underestimated            BOOLEAN,

  calibration_bucket_id     UUID,
  calibration_bucket_key    TEXT,
  is_outlier                BOOLEAN       NOT NULL  DEFAULT false,
  outlier_reason            TEXT,

  is_recomputable           BOOLEAN       NOT NULL  DEFAULT true,
  derivation_manifest       JSONB         NOT NULL,

  created_at                TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);

-- One evaluation per run (INV-ART-004) — idempotent creation gate
CREATE UNIQUE INDEX uq_evaluation_per_run
  ON cost_intelligence.evaluation_artifacts (run_id);

ALTER TABLE cost_intelligence.evaluation_artifacts
  ADD CONSTRAINT fk_evaluation_estimate
  FOREIGN KEY (estimate_id)
  REFERENCES cost_intelligence.estimate_artifacts(id)
  ON DELETE RESTRICT;

-- Index for monitoring (RFC-003 §14: runs awaiting evaluation)
CREATE INDEX idx_evaluation_tenant_created
  ON cost_intelligence.evaluation_artifacts (tenant_id, created_at DESC);

SELECT platform.apply_append_only_rls('cost_intelligence', 'evaluation_artifacts');

-- ---------------------------------------------------------------------------
-- Register in schema registry
-- ---------------------------------------------------------------------------

INSERT INTO platform.schema_registry (
  artifact_type, field_name, enum_value, lifecycle_status,
  schema_version, deprecation_reason, rfc_reference
) VALUES (
  'cost_intelligence.evaluation_artifacts', NULL, NULL, 'active',
  '1.0.0',
  'Phase 1 Group 5 — eval-v1-deterministic algorithm. Calibration wired Phase 2.',
  'RFC-002'
);

-- ---------------------------------------------------------------------------
-- Verification queries
-- ---------------------------------------------------------------------------
-- SELECT column_name, data_type, is_nullable
--   FROM information_schema.columns
--   WHERE table_schema = 'cost_intelligence' AND table_name = 'evaluation_artifacts'
--   ORDER BY ordinal_position;
-- SELECT COUNT(*) FROM cost_intelligence.evaluation_artifacts;  -- 0 initially
