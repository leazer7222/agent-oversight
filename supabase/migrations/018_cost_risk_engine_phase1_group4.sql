-- Migration 018: Adaptive Cost Risk Engine — Phase 1 Group 4
--   runtime_governance schema
--   runtime_governance.budget_periods     (Class II — mutable operational state)
--   runtime_governance.budget_reservations (ART-005 hybrid: financial immutable, status mutable)
--   runtime_governance.settlement_records  (ART-006 — immutable append-only)
--
-- Phase 1 operating mode (no enforcement):
--   Reservations are created and settled to accumulate data for Phase 3.
--   budget_periods.reserved_usd and consumed_usd ARE updated (accurate data,
--   no enforcement). Initial budget seeded at $9999 per company in ingest handler.
--   Hard/soft limits are NULL. create_reservation SERIALIZABLE function deferred Phase 3.
--
-- Depends on: 017 (estimate_artifacts must exist)
-- Apply to project: hdhovyrlnfojtkqbcegh
-- RFC references: RFC-002 (ART-005, ART-006), RFC-004, RFC-009

-- ---------------------------------------------------------------------------
-- 1. runtime_governance schema
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS runtime_governance;

-- ---------------------------------------------------------------------------
-- 2. budget_periods — RFC-004 §4
--    One row per tenant × cost_center × period_key.
--    Class II (mutable): reserved_usd and consumed_usd updated on reservation/settlement.
--    INV-RG-001: reserved_usd + consumed_usd <= budget_usd at all times.
--
--    NULL cost_center_id is the default (no cost center). Two partial unique indexes
--    handle the NULL-inequality quirk in PostgreSQL UNIQUE constraints.
-- ---------------------------------------------------------------------------

CREATE TABLE runtime_governance.budget_periods (
  id              UUID          NOT NULL  DEFAULT gen_random_uuid(),
  tenant_id       UUID          NOT NULL,
  cost_center_id  UUID,
  period_key      TEXT          NOT NULL,
  period_type     TEXT          NOT NULL
                    CHECK (period_type IN ('monthly', 'quarterly', 'annual', 'custom')),
  budget_usd      NUMERIC(12,4) NOT NULL  CHECK (budget_usd > 0),
  reserved_usd    NUMERIC(12,4) NOT NULL  DEFAULT 0  CHECK (reserved_usd >= 0),
  consumed_usd    NUMERIC(12,4) NOT NULL  DEFAULT 0  CHECK (consumed_usd >= 0),
  version         INTEGER       NOT NULL  DEFAULT 0,
  created_at      TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  updated_at      TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id),
  CONSTRAINT chk_budget_not_exceeded
    CHECK (reserved_usd + consumed_usd <= budget_usd)
);

-- Unique period per tenant with no cost center (default case)
CREATE UNIQUE INDEX uq_budget_period_default
  ON runtime_governance.budget_periods (tenant_id, period_key)
  WHERE cost_center_id IS NULL;

-- Unique period per tenant + cost center
CREATE UNIQUE INDEX uq_budget_period_cost_center
  ON runtime_governance.budget_periods (tenant_id, cost_center_id, period_key)
  WHERE cost_center_id IS NOT NULL;

-- RLS: block DELETE, allow INSERT and UPDATE (mutable operational state), tenant isolation
ALTER TABLE runtime_governance.budget_periods ENABLE ROW LEVEL SECURITY;

CREATE POLICY "no_delete" ON runtime_governance.budget_periods
  AS RESTRICTIVE FOR DELETE USING (false);

CREATE POLICY "tenant_isolation" ON runtime_governance.budget_periods
  FOR SELECT
  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

-- ---------------------------------------------------------------------------
-- 3. budget_reservations — ART-005 (RFC-002 §10)
--    Financial fields are immutable after creation (see RFC-002 §10 ART-005).
--    status is the only mutable field (operational lifecycle).
--    Uses custom RLS — NOT apply_append_only_rls — because status updates are required.
--
--    Phase 1: hard_limit_usd and soft_limit_usd are NULL (enforcement deferred Phase 3).
--    Phase 1: trace_id = run_id (no cross-run trace propagation yet).
-- ---------------------------------------------------------------------------

CREATE TABLE runtime_governance.budget_reservations (
  id                            UUID          NOT NULL  DEFAULT gen_random_uuid(),
  run_id                        UUID          NOT NULL,
  tenant_id                     UUID          NOT NULL,
  estimate_id                   UUID          NOT NULL,
  recommendation_id             UUID,
  trace_id                      UUID          NOT NULL,
  parent_reservation_id         UUID,
  period_key                    TEXT          NOT NULL,
  reserved_usd                  NUMERIC(10,6) NOT NULL,
  reservation_tier              TEXT          NOT NULL
                                  CHECK (reservation_tier IN ('p50', 'p75', 'p95')),
  hard_limit_usd                NUMERIC(10,6),
  soft_limit_usd                NUMERIC(10,6),
  max_run_time_ms               INTEGER,
  budget_available_at_dispatch  NUMERIC(12,4) NOT NULL,
  status                        TEXT          NOT NULL  DEFAULT 'active'
                                  CHECK (status IN (
                                    'active', 'soft_timeout', 'hard_timeout',
                                    'provisional_settlement', 'settled',
                                    'overrun', 'expired', 'cancelled'
                                  )),
  expires_at                    TIMESTAMPTZ   NOT NULL,
  created_at                    TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  updated_at                    TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);

-- One reservation per run (INV-ART from RFC-002)
CREATE UNIQUE INDEX uq_reservation_per_run
  ON runtime_governance.budget_reservations (run_id);

ALTER TABLE runtime_governance.budget_reservations
  ADD CONSTRAINT fk_reservation_estimate
  FOREIGN KEY (estimate_id)
  REFERENCES cost_intelligence.estimate_artifacts(id)
  ON DELETE RESTRICT;

ALTER TABLE runtime_governance.budget_reservations
  ADD CONSTRAINT fk_reservation_recommendation
  FOREIGN KEY (recommendation_id)
  REFERENCES model_intelligence.recommendation_artifacts(id)
  ON DELETE RESTRICT;

ALTER TABLE runtime_governance.budget_reservations
  ADD CONSTRAINT fk_reservation_parent
  FOREIGN KEY (parent_reservation_id)
  REFERENCES runtime_governance.budget_reservations(id)
  ON DELETE RESTRICT;

-- RLS: block DELETE, allow INSERT and status UPDATE, tenant isolation
ALTER TABLE runtime_governance.budget_reservations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "no_delete" ON runtime_governance.budget_reservations
  AS RESTRICTIVE FOR DELETE USING (false);

CREATE POLICY "tenant_isolation" ON runtime_governance.budget_reservations
  FOR SELECT
  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

-- Index for cleanup job (INV-RG-007: find active reservations for completed runs)
CREATE INDEX idx_reservations_status_run
  ON runtime_governance.budget_reservations (status, run_id)
  WHERE status = 'active';

-- ---------------------------------------------------------------------------
-- 4. settlement_records — ART-006 (RFC-002 §10)
--    Immutable after write. One non-provisional settlement per reservation (INV-RG-002).
-- ---------------------------------------------------------------------------

CREATE TABLE runtime_governance.settlement_records (
  id                UUID          NOT NULL  DEFAULT gen_random_uuid(),
  reservation_id    UUID          NOT NULL,
  tenant_id         UUID          NOT NULL,
  settlement_type   TEXT          NOT NULL
                      CHECK (settlement_type IN (
                        'normal', 'overrun', 'provisional', 'force_kill', 'timeout'
                      )),
  actual_cost_usd   NUMERIC(10,6) NOT NULL,
  settlement_source TEXT          NOT NULL
                      CHECK (settlement_source IN (
                        'telemetry', 'estimated', 'manual', 'reconciled'
                      )),
  is_provisional    BOOLEAN       NOT NULL  DEFAULT false,
  reconciled_at     TIMESTAMPTZ,
  created_at        TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);

-- One final (non-provisional) settlement per reservation (INV-RG-002)
CREATE UNIQUE INDEX uq_final_settlement_per_reservation
  ON runtime_governance.settlement_records (reservation_id)
  WHERE is_provisional = false;

ALTER TABLE runtime_governance.settlement_records
  ADD CONSTRAINT fk_settlement_reservation
  FOREIGN KEY (reservation_id)
  REFERENCES runtime_governance.budget_reservations(id)
  ON DELETE RESTRICT;

SELECT platform.apply_append_only_rls('runtime_governance', 'settlement_records');

-- ---------------------------------------------------------------------------
-- 5. Register in schema registry
-- ---------------------------------------------------------------------------

INSERT INTO platform.schema_registry (
  artifact_type, field_name, enum_value, lifecycle_status,
  schema_version, deprecation_reason, rfc_reference
) VALUES
  ('runtime_governance.budget_periods',      NULL, NULL, 'active', '1.0.0',
   'Phase 1 Group 4 — data capture mode. Enforcement wired in Phase 3.', 'RFC-004'),
  ('runtime_governance.budget_reservations', NULL, NULL, 'active', '1.0.0',
   'Phase 1 Group 4 — reservations created per run. Hard limits deferred Phase 3.', 'RFC-002'),
  ('runtime_governance.settlement_records',  NULL, NULL, 'active', '1.0.0',
   'Phase 1 Group 4 — settlements created on run completion.', 'RFC-002');

-- ---------------------------------------------------------------------------
-- Verification queries
-- ---------------------------------------------------------------------------
-- SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'runtime_governance';
-- SELECT column_name, data_type, is_nullable
--   FROM information_schema.columns
--   WHERE table_schema = 'runtime_governance' ORDER BY table_name, ordinal_position;
