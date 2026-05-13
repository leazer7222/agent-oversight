-- Add three columns to runs required for Phase 2 reliability features:
--   timeout_at     - enables zombie run detection and cleanup
--   parent_run_id  - enables retry chain linkage
--   cost_reported  - sentinel to distinguish null-unreported from null-zero cost

ALTER TABLE runs
  ADD COLUMN IF NOT EXISTS timeout_at     timestamptz,
  ADD COLUMN IF NOT EXISTS parent_run_id  uuid REFERENCES runs(id),
  ADD COLUMN IF NOT EXISTS cost_reported  boolean NOT NULL DEFAULT false;

-- Index for zombie run detection queries (find started runs past their timeout)
CREATE INDEX IF NOT EXISTS runs_timeout_status_idx
  ON runs(timeout_at, status)
  WHERE status = 'started' AND timeout_at IS NOT NULL;
