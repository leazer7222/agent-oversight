-- Migration 015: Adaptive Cost Risk Engine — Phase 1 Group 2
--   Add task classification columns to the runs table.
--
-- Depends on: 013_cost_risk_engine_phase1_group1.sql
--   cost_intelligence.task_types must exist and have taxonomy-v1 seeded.
--
-- Apply to project: hdhovyrlnfojtkqbcegh
-- RFC references: RFC-005 §3, RFC-009

-- ---------------------------------------------------------------------------
-- Background
-- ---------------------------------------------------------------------------
-- RFC-005 §3 requires run_records to carry:
--   task_type_id           UUID NOT NULL FK → cost_intelligence.task_types(id)
--   task_complexity_bucket TEXT NOT NULL CHECK ('simple','medium','complex')
--   task_classifier_version TEXT NOT NULL
--   secondary_task_type_id UUID  (nullable secondary label)
--
-- The runs table has existing rows that predate taxonomy-v1. These rows are
-- backfilled as task_type='code_gen', complexity='medium' in the DO block
-- below. This is a documented approximation for historical data.
--
-- INV-TAX-001 [Class A]: task_type_id IS NOT NULL enforced by column constraint.
-- INV-TAX-002 [Class A]: task_complexity_bucket IS NOT NULL + CHECK constraint.
-- INV-TAX-003 [Class A]: task_type_id FK ON DELETE RESTRICT.

-- ---------------------------------------------------------------------------
-- Step 1 — Add columns (nullable), backfill historical rows, then constrain.
-- All three steps are in a single transaction so the NOT NULL constraint is
-- added only after every row has been populated.
-- ---------------------------------------------------------------------------

DO $$
DECLARE
  v_code_gen_id UUID;
BEGIN

  -- 1a. Add four columns as nullable initially
  ALTER TABLE runs
    ADD COLUMN IF NOT EXISTS task_type_id            UUID,
    ADD COLUMN IF NOT EXISTS task_complexity_bucket  TEXT,
    ADD COLUMN IF NOT EXISTS task_classifier_version TEXT,
    ADD COLUMN IF NOT EXISTS secondary_task_type_id  UUID;

  -- 1b. Resolve code_gen from taxonomy-v1 for the historical backfill
  SELECT id INTO v_code_gen_id
  FROM cost_intelligence.task_types
  WHERE code = 'code_gen'
  LIMIT 1;

  IF v_code_gen_id IS NULL THEN
    RAISE EXCEPTION 'taxonomy-v1 not found — apply migration 013 before 015';
  END IF;

  -- 1c. Backfill all pre-taxonomy rows.
  --     code_gen / medium / complexity-v1 is an approximation for historical runs.
  --     New runs will supply accurate values at dispatch time (Phase 1 Group 3+).
  UPDATE runs
  SET
    task_type_id            = v_code_gen_id,
    task_complexity_bucket  = 'medium',
    task_classifier_version = 'complexity-v1'
  WHERE task_type_id IS NULL;

  -- 1d. Now safe to add NOT NULL constraints
  ALTER TABLE runs
    ALTER COLUMN task_type_id            SET NOT NULL,
    ALTER COLUMN task_complexity_bucket  SET NOT NULL,
    ALTER COLUMN task_classifier_version SET NOT NULL;

END $$;

-- ---------------------------------------------------------------------------
-- Step 2 — Add CHECK and FK constraints (outside the DO block)
-- ---------------------------------------------------------------------------

ALTER TABLE runs
  ADD CONSTRAINT chk_runs_task_complexity_bucket
  CHECK (task_complexity_bucket IN ('simple', 'medium', 'complex'));

-- Primary task type FK (RFC-005 INV-TAX-003)
ALTER TABLE runs
  ADD CONSTRAINT fk_runs_task_type
  FOREIGN KEY (task_type_id)
  REFERENCES cost_intelligence.task_types(id)
  ON DELETE RESTRICT;

-- Secondary task type FK (nullable — RFC-005 §6 multi-label semantics)
ALTER TABLE runs
  ADD CONSTRAINT fk_runs_secondary_task_type
  FOREIGN KEY (secondary_task_type_id)
  REFERENCES cost_intelligence.task_types(id)
  ON DELETE RESTRICT;

-- ---------------------------------------------------------------------------
-- Step 3 — Indexes for RFC-005 §9 monitoring queries
-- ---------------------------------------------------------------------------

-- Distribution by task type (weekly monitoring query from RFC-005 §9)
CREATE INDEX IF NOT EXISTS idx_runs_task_type_created
  ON runs (task_type_id, created_at DESC);

-- Complexity distribution per type (drift detection from RFC-005 §9)
CREATE INDEX IF NOT EXISTS idx_runs_task_complexity
  ON runs (task_type_id, task_complexity_bucket);

-- ---------------------------------------------------------------------------
-- Verification queries (run after applying)
-- ---------------------------------------------------------------------------
-- SELECT column_name, data_type, is_nullable
--   FROM information_schema.columns
--   WHERE table_name = 'runs'
--     AND column_name LIKE 'task%';
-- SELECT tt.code, COUNT(r.id) AS run_count
--   FROM runs r JOIN cost_intelligence.task_types tt ON tt.id = r.task_type_id
--   GROUP BY tt.code;
-- -- Expected: all rows show code_gen (historical backfill)
