-- Migration 012: Adaptive Cost Risk Engine — Phase 0 Pre-Build Foundations
-- Apply to live project: hdhovyrlnfojtkqbcegh
--
-- What this does:
--   1. Creates the `platform` schema for cross-cutting governance infrastructure
--   2. Creates platform.schema_registry — governance metadata for all artifact schemas
--   3. Creates platform.correction_records — the amendment pattern for immutable artifacts
--   4. Creates platform.apply_append_only_rls() — reusable RLS enforcement function
--   5. Applies append-only enforcement to both new tables themselves
--
-- These are the governance foundations that ALL Phase 1+ tables depend on.
-- Nothing in the Adaptive Cost Risk Engine is built before this migration runs.
--
-- RFC references: RFC-001 §3-4, RFC-002 §8, RFC-009 §12
-- Phase: 0 (Pre-Build)
-- Gate: Must be applied and verified before any Phase 1 code is written.

-- ---------------------------------------------------------------------------
-- 1. Platform schema
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS platform;

-- ---------------------------------------------------------------------------
-- 2. Schema Registry
--    Governance metadata for all artifact schemas, field lifecycles, and enum values.
--    Consulted by CI pipelines, monitoring jobs, and human reviewers.
--    NEVER queried by application services at runtime (RFC-009 §12).
-- ---------------------------------------------------------------------------

CREATE TABLE platform.schema_registry (
  id                  UUID          NOT NULL  DEFAULT gen_random_uuid(),
  artifact_type       TEXT          NOT NULL,  -- table or event type name
  field_name          TEXT,                    -- NULL for table-level entries
  enum_value          TEXT,                    -- NULL for non-enum entries
  lifecycle_status    TEXT          NOT NULL
                        CHECK (lifecycle_status IN ('active', 'deprecated', 'removed')),
  schema_version      TEXT          NOT NULL,  -- version when this lifecycle state began
  deprecated_at       TIMESTAMPTZ,
  planned_removal_at  TIMESTAMPTZ,
  removed_at          TIMESTAMPTZ,
  replacement_field   TEXT,                    -- what to use instead if deprecated
  deprecation_reason  TEXT,
  rfc_reference       TEXT,                    -- e.g. "RFC-009"
  created_at          TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);

COMMENT ON TABLE platform.schema_registry IS
  'Governance metadata for artifact schemas, field lifecycles, and enum values. '
  'Authoritative for governance. NOT a runtime dependency. '
  'See RFC-009 §12.';

-- ---------------------------------------------------------------------------
-- 3. Correction Records
--    The formal pattern for noting that an immutable artifact contained
--    incorrect data. Correction records never replace originals — they annotate them.
--    See RFC-001 §4, RFC-002 §8.3.
-- ---------------------------------------------------------------------------

CREATE TABLE platform.correction_records (
  id                          UUID          NOT NULL  DEFAULT gen_random_uuid(),
  artifact_type               TEXT          NOT NULL
                                CHECK (artifact_type IN (
                                  'estimate_artifact',
                                  'evaluation_artifact',
                                  'recommendation_artifact',
                                  'budget_reservation',
                                  'settlement_record',
                                  'quality_signal',
                                  'run_record',
                                  'calibration_observation'
                                )),
  artifact_id                 UUID          NOT NULL,  -- cross-table; enforced in application
  tenant_id                   UUID          NOT NULL,
  correction_category         TEXT          NOT NULL
                                CHECK (correction_category IN (
                                  'billing_adjustment',
                                  'telemetry_bug',
                                  'data_entry_error',
                                  'provider_correction',
                                  'duplicate_record',
                                  'reconciliation'
                                )),
  correction_reason           TEXT          NOT NULL,  -- human-readable description
  corrected_fields            JSONB         NOT NULL,
                                -- [{field: str, old_value: any, new_value: any, correction_source: str}]
  corrected_by                TEXT          NOT NULL,  -- service identity or human operator ID
  evidence_reference          TEXT,                    -- support ticket URL, billing statement ID
  requires_calibration_review BOOLEAN       NOT NULL  DEFAULT false,
                                -- true when corrected artifact is evaluation_artifact
                                -- and corrected fields are used in calibration bucket computation
  created_at                  TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);

COMMENT ON TABLE platform.correction_records IS
  'Immutable amendment records for immutable artifacts. '
  'Never replaces the original artifact. Annotates it. '
  'See RFC-001 §4, RFC-002 §8.3.';

-- ---------------------------------------------------------------------------
-- 4. Append-Only RLS Enforcement Function
--    Call this immediately after creating any artifact table.
--    Applies three policies: no UPDATE, no DELETE, and tenant isolation for SELECT.
--    Pattern defined in RFC-001 §3.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION platform.apply_append_only_rls(
  p_schema TEXT,
  p_table  TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
  -- Enable RLS
  EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', p_schema, p_table);

  -- Block all updates
  EXECUTE format(
    'CREATE POLICY "immutable_no_update" ON %I.%I AS RESTRICTIVE FOR UPDATE USING (false)',
    p_schema, p_table
  );

  -- Block all deletes
  EXECUTE format(
    'CREATE POLICY "immutable_no_delete" ON %I.%I AS RESTRICTIVE FOR DELETE USING (false)',
    p_schema, p_table
  );

  -- Tenant isolation for SELECT
  -- Tables without tenant_id should use a custom policy after calling this function
  EXECUTE format(
    $policy$
      DO $$
      BEGIN
        IF EXISTS (
          SELECT 1 FROM information_schema.columns
          WHERE table_schema = '%1$s'
            AND table_name = '%2$s'
            AND column_name = 'tenant_id'
        ) THEN
          EXECUTE format(
            'CREATE POLICY "tenant_isolation" ON %1$s.%2$s FOR SELECT USING '
            '(tenant_id = current_setting(''app.current_tenant_id'', true)::uuid)',
            '%1$s', '%2$s'
          );
        END IF;
      END $$;
    $policy$,
    p_schema, p_table
  );

  RAISE NOTICE 'Append-only RLS applied to %.%', p_schema, p_table;
END;
$$;

COMMENT ON FUNCTION platform.apply_append_only_rls(TEXT, TEXT) IS
  'Applies the canonical append-only enforcement pattern to an artifact table. '
  'Call immediately after CREATE TABLE. See RFC-001 §3.';

-- ---------------------------------------------------------------------------
-- 5. Apply append-only enforcement to the governance tables themselves
--    These tables are also immutable records — corrections are new rows, not updates.
-- ---------------------------------------------------------------------------

-- Schema registry: append-only (no tenant_id — platform-level table)
ALTER TABLE platform.schema_registry ENABLE ROW LEVEL SECURITY;

CREATE POLICY "immutable_no_update" ON platform.schema_registry
  AS RESTRICTIVE FOR UPDATE USING (false);

CREATE POLICY "immutable_no_delete" ON platform.schema_registry
  AS RESTRICTIVE FOR DELETE USING (false);

-- Correction records: append-only
ALTER TABLE platform.correction_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY "immutable_no_update" ON platform.correction_records
  AS RESTRICTIVE FOR UPDATE USING (false);

CREATE POLICY "immutable_no_delete" ON platform.correction_records
  AS RESTRICTIVE FOR DELETE USING (false);

CREATE POLICY "tenant_isolation" ON platform.correction_records
  FOR SELECT
  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

-- ---------------------------------------------------------------------------
-- 6. Seed schema registry — telemetry schema freeze declaration will be added
--    at Phase 2 start. This entry documents that the registry exists and is active.
-- ---------------------------------------------------------------------------

INSERT INTO platform.schema_registry (
  artifact_type, field_name, lifecycle_status, schema_version,
  deprecation_reason, rfc_reference
) VALUES (
  'platform.schema_registry',
  NULL,
  'active',
  '1.0.0',
  'Phase 0 foundation. Governance registry initialized.',
  'RFC-009'
);

INSERT INTO platform.schema_registry (
  artifact_type, field_name, lifecycle_status, schema_version,
  deprecation_reason, rfc_reference
) VALUES (
  'platform.correction_records',
  NULL,
  'active',
  '1.0.0',
  'Phase 0 foundation. Correction record pattern initialized.',
  'RFC-001, RFC-002'
);

-- ---------------------------------------------------------------------------
-- Verification queries (run after applying migration)
-- ---------------------------------------------------------------------------
-- SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'platform';
-- SELECT pg_get_functiondef(oid) FROM pg_proc WHERE proname = 'apply_append_only_rls';
-- SELECT COUNT(*) FROM platform.schema_registry;  -- should return 2
