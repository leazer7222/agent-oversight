-- Migration 016: Adaptive Cost Risk Engine — Phase 1 Group 3a
--   model_intelligence schema
--   model_intelligence.recommendation_artifacts (passthrough stub, RFC-002 ART-007)
--
-- Depends on: 015 (runs.task_type_id FK must exist)
-- Apply to project: hdhovyrlnfojtkqbcegh
-- RFC references: RFC-002 §10 (ART-007), RFC-009

-- ---------------------------------------------------------------------------
-- 1. model_intelligence schema
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS model_intelligence;

-- ---------------------------------------------------------------------------
-- 2. recommendation_artifacts — ART-007 (RFC-002 §10)
--
--    Phase 1 operating mode: passthrough.
--      routing_mode        = 'passthrough' on every row
--      candidates_evaluated = '[]'  (empty array is valid in passthrough — RFC-002 §10)
--      budget_available_at_routing = 9999.9999 (no budget governance until Phase 3)
--
--    One recommendation_artifact per run_request (INV-ART-006).
--    run_request_id is an app-level reference to runs.id.
--    The DB FK to run_requests.id is deferred until Phase 3 when that table exists.
--
--    INV-ART-013: every run_request has a recommendation_artifact including passthrough.
-- ---------------------------------------------------------------------------

CREATE TABLE model_intelligence.recommendation_artifacts (
  id                          UUID          NOT NULL  DEFAULT gen_random_uuid(),
  run_request_id              UUID          NOT NULL,
  tenant_id                   UUID          NOT NULL,
  schema_version              TEXT          NOT NULL  DEFAULT '1.0.0',
  routing_mode                TEXT          NOT NULL  DEFAULT 'passthrough'
                                CHECK (routing_mode IN (
                                  'passthrough', 'cheapest_acceptable', 'balanced',
                                  'highest_quality', 'fastest', 'regulated', 'experimental'
                                )),
  model_selection_mode        TEXT          NOT NULL
                                CHECK (model_selection_mode IN (
                                  'user_specified', 'tenant_default', 'policy_enforced',
                                  'router_recommended', 'fallback'
                                )),
  selected_model              TEXT          NOT NULL,
  selected_provider           TEXT          NOT NULL,
  selection_reason            TEXT          NOT NULL,
  routing_policy_version      TEXT,
  scoring_function_version    TEXT,
  profile_snapshot_version    TEXT,
  task_type_id                UUID,
  task_complexity_bucket      TEXT,
  budget_eligible_models      TEXT[]        NOT NULL  DEFAULT '{}',
  quality_floor_applied       NUMERIC(4,3),
  budget_available_at_routing NUMERIC(12,4) NOT NULL,
  cold_start_model_selected   BOOLEAN       NOT NULL  DEFAULT false,
  routing_confidence          TEXT
                                CHECK (routing_confidence IN (
                                  'very_low', 'low', 'medium', 'high',
                                  'very_high', 'not_applicable'
                                )),
  candidates_evaluated        JSONB         NOT NULL  DEFAULT '[]',
  created_at                  TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);

-- One recommendation per run request (INV-ART-006)
CREATE UNIQUE INDEX uq_recommendation_per_run_request
  ON model_intelligence.recommendation_artifacts (run_request_id);

-- task_type_id FK to cost_intelligence.task_types
ALTER TABLE model_intelligence.recommendation_artifacts
  ADD CONSTRAINT fk_recommendation_task_type
  FOREIGN KEY (task_type_id)
  REFERENCES cost_intelligence.task_types(id)
  ON DELETE RESTRICT;

-- Index for monitoring (INV-ART-013: daily query for runs with no recommendation)
CREATE INDEX idx_recommendation_created
  ON model_intelligence.recommendation_artifacts (created_at DESC);

SELECT platform.apply_append_only_rls('model_intelligence', 'recommendation_artifacts');

-- ---------------------------------------------------------------------------
-- 3. Register in schema registry
-- ---------------------------------------------------------------------------

INSERT INTO platform.schema_registry (
  artifact_type, field_name, enum_value, lifecycle_status,
  schema_version, deprecation_reason, rfc_reference
) VALUES (
  'model_intelligence.recommendation_artifacts', NULL, NULL, 'active',
  '1.0.0',
  'Phase 1 Group 3 — passthrough stub. Routing engine wired in Phase 4.',
  'RFC-002'
);

-- ---------------------------------------------------------------------------
-- Verification queries
-- ---------------------------------------------------------------------------
-- SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'model_intelligence';
-- SELECT indexname FROM pg_indexes WHERE schemaname = 'model_intelligence';
