-- Migration 014: Adaptive Cost Risk Engine — Phase 1 Group 1 (Telemetry)
--   telemetry.raw_events — append-only event store
--
-- Depends on: 012_cost_risk_engine_phase0.sql
--   - platform schema must exist
--   - platform.apply_append_only_rls() function must exist
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- RFC references: RFC-003 §10, RFC-009

-- ---------------------------------------------------------------------------
-- 1. telemetry schema
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS telemetry;

-- ---------------------------------------------------------------------------
-- 2. raw_events — canonical append-only event store (RFC-003 §10)
--
--    Primary key is event_id from the emitter's envelope.
--    Deduplication: ON CONFLICT (id) DO NOTHING at ingest time.
--    Schema is frozen at v1.0.0 after Phase 1 gate (RFC-010 §7).
--
--    Column notes:
--      id              — event_id from the RFC-003 envelope; PK for deduplication
--      received_at     — wall-clock time the ingest endpoint committed this row
--      created_at      — RFC-009 naming convention alias for received_at;
--                        both default to now() and will always be equal
--      is_replay       — consumers must no-op on true (RFC-003 §6)
-- ---------------------------------------------------------------------------

CREATE TABLE telemetry.raw_events (
  id              UUID        NOT NULL,
  event_type      TEXT        NOT NULL,
  schema_version  TEXT        NOT NULL,
  emitted_at      TIMESTAMPTZ NOT NULL,
  sequence_number INTEGER,
  trace_id        UUID        NOT NULL,
  run_id          UUID,
  parent_run_id   UUID,
  campaign_id     UUID,
  tenant_id       UUID        NOT NULL,
  is_replay       BOOLEAN     NOT NULL  DEFAULT false,
  replay_id       UUID,
  payload         JSONB       NOT NULL,
  received_at     TIMESTAMPTZ NOT NULL  DEFAULT now(),
  created_at      TIMESTAMPTZ NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);

-- ---------------------------------------------------------------------------
-- 3. Indexes for common RFC-003 §14 monitoring and consumer patterns
-- ---------------------------------------------------------------------------

-- Health monitoring: events by tenant in recency order
CREATE INDEX idx_raw_events_tenant_received
  ON telemetry.raw_events (tenant_id, received_at DESC);

-- Consumer ordering: reconstruct per-run event stream by sequence_number
CREATE INDEX idx_raw_events_run_sequence
  ON telemetry.raw_events (run_id, sequence_number)
  WHERE run_id IS NOT NULL;

-- Trace reconstruction: all events belonging to a top-level request
CREATE INDEX idx_raw_events_trace
  ON telemetry.raw_events (trace_id);

-- Monitoring queries that filter by event_type (e.g. degradation rate queries)
CREATE INDEX idx_raw_events_type_received
  ON telemetry.raw_events (event_type, received_at DESC);

-- ---------------------------------------------------------------------------
-- 4. Append-only enforcement
--    RLS policies: no UPDATE, no DELETE.
--    tenant_id column is present, so a tenant isolation SELECT policy is also
--    applied by apply_append_only_rls (RFC-001 §3 pattern).
-- ---------------------------------------------------------------------------

SELECT platform.apply_append_only_rls('telemetry', 'raw_events');

-- ---------------------------------------------------------------------------
-- 5. Register in schema registry (governance record, RFC-009)
--    The telemetry schema freeze entry will be added at Phase 2 start
--    (RFC-010 §7) — not here.
-- ---------------------------------------------------------------------------

INSERT INTO platform.schema_registry (
  artifact_type, field_name, enum_value, lifecycle_status,
  schema_version, deprecation_reason, rfc_reference
) VALUES (
  'telemetry.raw_events', NULL, NULL, 'active',
  '1.0.0',
  'Phase 1 Group 1 foundation — event envelope frozen at v1.0.0. Schema freeze declared at Phase 2 start.',
  'RFC-003'
);

-- ---------------------------------------------------------------------------
-- Verification queries (run after applying)
-- ---------------------------------------------------------------------------
-- SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'telemetry';
-- SELECT indexname FROM pg_indexes WHERE schemaname = 'telemetry' AND tablename = 'raw_events';
-- SELECT COUNT(*) FROM telemetry.raw_events;  -- should return 0 (empty, ready for events)
