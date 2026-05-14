-- Migration 009: Add window_type to provider_quota_snapshots
-- Allows storing 5-hour and 7-day quota windows as separate rows

ALTER TABLE provider_quota_snapshots
  ADD COLUMN IF NOT EXISTS window_type TEXT
    CHECK (window_type IN ('five_hour', 'seven_day', 'primary'))
    DEFAULT 'primary';

CREATE INDEX IF NOT EXISTS idx_quota_snapshots_window
  ON provider_quota_snapshots (provider_account_id, window_type, snapshotted_at DESC);

COMMENT ON COLUMN provider_quota_snapshots.window_type IS
  'five_hour = short rolling window, seven_day = weekly budget, primary = unspecified/legacy';
