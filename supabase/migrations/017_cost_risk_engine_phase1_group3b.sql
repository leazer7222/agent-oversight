-- Migration 017: Adaptive Cost Risk Engine — Phase 1 Group 3b
--   cost_intelligence.estimate_artifacts (ART-001, RFC-002 §10)
--
-- Depends on: 016 (recommendation_artifacts must exist)
--             013 (pricing_table_versions must exist)
-- Apply to project: hdhovyrlnfojtkqbcegh
-- RFC references: RFC-002 §10 (ART-001), RFC-009

-- ---------------------------------------------------------------------------
-- estimate_artifacts — ART-001 (RFC-002 §10)
--
--    Records the cost estimate produced at dispatch time (before run execution).
--    Immutable after write. One artifact per run request (INV-ART-003).
--
--    Phase 1 operation:
--      estimation_tier = 'deterministic' (pricing × fixed token estimates)
--      calibration_version_id = NULL (no calibration until Phase 2)
--      confidence = 'low' (no calibration data to improve accuracy)
--
--    The critical field is estimation_features_snapshot (RFC-002 §10.1.1).
--    It must be populated before any other field. If it cannot be populated,
--    the artifact must not be created.
--
--    run_request_id is an app-level reference to runs.id.
--    DB FK to run_requests.id deferred until Phase 3 (table doesn't exist yet).
--    DB FK to calibration_snapshots.id deferred until Phase 2.
-- ---------------------------------------------------------------------------

CREATE TABLE cost_intelligence.estimate_artifacts (
  id                           UUID          NOT NULL  DEFAULT gen_random_uuid(),
  run_request_id               UUID          NOT NULL,
  tenant_id                    UUID          NOT NULL,
  schema_version               TEXT          NOT NULL  DEFAULT '1.0.0',

  model                        TEXT          NOT NULL,
  provider                     TEXT          NOT NULL,
  model_selection_mode         TEXT          NOT NULL
                                 CHECK (model_selection_mode IN (
                                   'user_specified', 'tenant_default', 'policy_enforced',
                                   'router_recommended', 'fallback'
                                 )),
  model_selection_reason       TEXT          NOT NULL,

  pricing_table_version_id     UUID          NOT NULL,
  pricing_snapshot             JSONB         NOT NULL,

  calibration_version_id       UUID,
  calibration_source           TEXT
                                 CHECK (calibration_source IN (
                                   'tenant', 'tenant_segment', 'global', 'deterministic'
                                 )),
  calibration_sample_tier      TEXT
                                 CHECK (calibration_sample_tier IN (
                                   'lt_10', '10_to_100', '100_to_1000', 'gt_1000'
                                 )),

  estimation_features_snapshot JSONB         NOT NULL,
  estimation_tier              TEXT          NOT NULL
                                 CHECK (estimation_tier IN (
                                   'calibrated', 'cached_calibration',
                                   'deterministic', 'embedded_fallback'
                                 )),

  cost_p50_usd                 NUMERIC(10,6) NOT NULL,
  cost_p75_usd                 NUMERIC(10,6) NOT NULL,
  cost_p95_usd                 NUMERIC(10,6) NOT NULL,
  tokens_in_p50                INTEGER,
  tokens_out_p50               INTEGER,
  estimated_latency_ms_p50     INTEGER,
  estimated_quality_p50        NUMERIC(4,3),

  confidence                   TEXT          NOT NULL
                                 CHECK (confidence IN (
                                   'very_low', 'low', 'medium', 'high', 'very_high'
                                 )),
  warnings                     TEXT[]        NOT NULL  DEFAULT '{}',
  created_at                   TIMESTAMPTZ   NOT NULL  DEFAULT now(),

  PRIMARY KEY (id)
);

-- One estimate per run request (INV-ART-003)
CREATE UNIQUE INDEX uq_estimate_per_run_request
  ON cost_intelligence.estimate_artifacts (run_request_id);

-- FK to pricing table (INV-ART: pricing always resolvable)
ALTER TABLE cost_intelligence.estimate_artifacts
  ADD CONSTRAINT fk_estimate_pricing_table
  FOREIGN KEY (pricing_table_version_id)
  REFERENCES cost_intelligence.pricing_table_versions(id)
  ON DELETE RESTRICT;

-- Index for evaluation pipeline (Group 5): find estimates for completed runs
CREATE INDEX idx_estimate_artifacts_run_request
  ON cost_intelligence.estimate_artifacts (run_request_id);

-- Monitoring (RFC-009 §13 Pattern 4): verify n_tup_upd = 0 always
CREATE INDEX idx_estimate_artifacts_tenant_created
  ON cost_intelligence.estimate_artifacts (tenant_id, created_at DESC);

SELECT platform.apply_append_only_rls('cost_intelligence', 'estimate_artifacts');

-- ---------------------------------------------------------------------------
-- Register in schema registry
-- ---------------------------------------------------------------------------

INSERT INTO platform.schema_registry (
  artifact_type, field_name, enum_value, lifecycle_status,
  schema_version, deprecation_reason, rfc_reference
) VALUES (
  'cost_intelligence.estimate_artifacts', NULL, NULL, 'active',
  '1.0.0',
  'Phase 1 Group 3 — deterministic tier only. Calibration wired in Phase 2.',
  'RFC-002'
);

-- ---------------------------------------------------------------------------
-- Verification queries
-- ---------------------------------------------------------------------------
-- SELECT column_name, data_type, is_nullable
--   FROM information_schema.columns
--   WHERE table_schema = 'cost_intelligence' AND table_name = 'estimate_artifacts'
--   ORDER BY ordinal_position;
-- SELECT COUNT(*) FROM cost_intelligence.estimate_artifacts;  -- 0 initially
