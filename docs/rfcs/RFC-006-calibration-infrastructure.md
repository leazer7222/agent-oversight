# RFC-006 — Calibration Infrastructure

```
Status: Active
Version: 1.0.0
Authors: [Platform Engineering]
Depends on: RFC-001 through RFC-005
Required before: Phase 2 implementation, any calibration pipeline code
```

---

## 1. Context

The deterministic estimator produces estimates from pricing tables and declared feature
inputs. It has no memory of whether its past estimates were accurate. Calibration is
the mechanism by which the system learns from its mistakes.

This RFC defines the complete calibration infrastructure: how observations are collected,
how they are structured into buckets, how outliers are handled, how snapshots are built
and validated, how promotion and rollback work, and how drift is detected.

---

## 2. Scope

- Calibration observation schema and ingestion pipeline
- Bucket schema versioning and bucket key structure
- Bucket assignment algorithm and hierarchical fallback chain
- Observation eligibility: quality window gate and outlier detection
- Calibration snapshot pipeline: draft → shadow → active → retired
- Shadow validation criteria and thresholds
- Promotion workflow: automated and human-gated paths
- Rollback mechanics
- Drift detection
- Cross-tenant calibration isolation
- The calibration source fallback chain

---

## 3. Definitions

**Calibration observation**: A single data point recording estimate vs actual outcome.
One per run. Immutable after creation.

**Calibration bucket**: A named grouping of observations sharing similar characteristics.
Multipliers are computed per bucket.

**Bucket schema version**: A versioned definition of how observations are assigned to
buckets.

**Calibration multiplier**: The correction factor applied to future estimates for a bucket.

**Calibration snapshot**: A complete, immutable set of calibration multipliers. Promoted
through draft → shadow → active lifecycle.

**Shadow validation**: Running a proposed snapshot against recent historical runs to
measure MAPE improvement before production use.

**Drift**: A statistically significant increase in estimation error over time.

**Observation window gate**: The requirement that a calibration observation not be used
until all expected quality signals for that run have had the opportunity to arrive.

**Eligibility**: `is_outlier = false` AND `calibration_eligible = true`
(set when `quality_finalized_at IS NOT NULL`).

---

## 4. Bucket Schema

### Schema Version Registry

```sql
CREATE TABLE cost_intelligence.bucket_schema_versions (
  id            UUID          NOT NULL  DEFAULT gen_random_uuid(),
  version       TEXT          NOT NULL  UNIQUE,  -- "bucket-schema-v1"
  status        TEXT          NOT NULL  CHECK (status IN ('draft','active','deprecated')),
  dimensions    JSONB         NOT NULL,
  created_at    TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  created_by    TEXT          NOT NULL,
  activated_at  TIMESTAMPTZ,
  deprecated_at TIMESTAMPTZ,
  PRIMARY KEY (id)
);

CREATE UNIQUE INDEX uq_one_active_bucket_schema
  ON cost_intelligence.bucket_schema_versions (status)
  WHERE status = 'active';
-- Append-only enforcement
```

### Bucket Dimensions — v1

Six dimensions. `dimensions` JSONB formally defines each including discretization rules.

1. `provider` — categorical (anthropic, openai, google, other)
2. `model_family` — derived by stripping version suffix from model name
3. `tool_profile` — canonical sorted set: sort alphabetically, join with `+`, cap at 3 named + `other`; `none` if empty
4. `context_size_bucket` — range: xs (<1000), sm (1000-5000), md (5000-20000), lg (20000-80000), xl (>80000 chars)
5. `task_type_code` — from run record FK to task_types
6. `task_complexity_bucket` — simple/medium/complex

### Bucket Key

```
{provider}.{model_family}.{tool_profile}.{context_size_bucket}.{task_type_code}.{task_complexity_bucket}

Example: anthropic.claude-sonnet.web_search.md.info_retrieval.medium
```

Treated as an opaque identifier for lookup. Structured dimension columns are used for querying.

### When a New Bucket Schema Version Is Required

Required: new dimension added, existing dimension discretization changes, dimension removed.

Not required: new tool, new task type, new model (appear in existing dimensions automatically).

---

## 5. Calibration Observation Schema

```sql
CREATE TABLE cost_intelligence.calibration_observations (
  id                        UUID          NOT NULL  DEFAULT gen_random_uuid(),
  run_id                    UUID          NOT NULL  UNIQUE,
  tenant_id                 UUID          NOT NULL,
  evaluation_id             UUID          NOT NULL  FK → evaluation_artifacts.id,
  bucket_schema_version     TEXT          NOT NULL,
  bucket_key                TEXT          NOT NULL,
  provider                  TEXT          NOT NULL,
  model_family              TEXT          NOT NULL,
  tool_profile              TEXT          NOT NULL,
  context_size_bucket       TEXT          NOT NULL
    CHECK (context_size_bucket IN ('xs','sm','md','lg','xl')),
  task_type_code            TEXT          NOT NULL,
  task_complexity_bucket    TEXT          NOT NULL
    CHECK (task_complexity_bucket IN ('simple','medium','complex')),
  agent_definition_id       UUID          NOT NULL,
  estimation_tier           TEXT          NOT NULL,
  estimated_cost_usd        NUMERIC(10,6) NOT NULL,
  actual_cost_usd           NUMERIC(10,6) NOT NULL,
  absolute_error_usd        NUMERIC(10,6) NOT NULL,
  percentage_error          NUMERIC(8,4)  NOT NULL,
  underestimated            BOOLEAN       NOT NULL,
  telemetry_status          TEXT          NOT NULL,
  is_outlier                BOOLEAN       NOT NULL  DEFAULT false,
  outlier_reason            TEXT          NULL,
  outlier_z_score           NUMERIC(8,4)  NULL,
  outlier_reviewed_at       TIMESTAMPTZ   NULL,
  outlier_review_decision   TEXT          NULL
    CHECK (outlier_review_decision IN ('confirmed_outlier','include_despite_outlier',NULL)),
  quality_finalized_at      TIMESTAMPTZ   NULL,
  calibration_eligible      BOOLEAN       NOT NULL  DEFAULT false,
  first_included_snapshot_id UUID         NULL,
  created_at                TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);
-- Append-only enforcement
-- Exception: quality_finalized_at and calibration_eligible updated once by finalization job
```

### Ineligible Observations (permanently excluded)

- `telemetry_status IN ('incomplete','provisional')`
- `is_outlier = true AND outlier_review_decision != 'include_despite_outlier'`
- `estimation_tier = 'embedded_fallback'`
- `quality_finalized_at IS NULL`

---

## 6. Bucket Assignment Algorithm

```python
def extract_bucket_dimensions(evaluation_artifact, run_record, estimate_artifact) -> dict:
    features = estimate_artifact.estimation_features_snapshot
    model_family = derive_model_family(estimate_artifact.model)
    tools = sorted(features.get("tools_enabled", []))
    if len(tools) == 0:
        tool_profile = "none"
    elif len(tools) <= 3:
        tool_profile = "+".join(tools)
    else:
        tool_profile = "+".join(tools[:3]) + "+other"
    return {
        "provider": estimate_artifact.provider,
        "model_family": model_family,
        "tool_profile": tool_profile,
        "context_size_bucket": discretize_context_size(features.get("prompt_chars", 0)),
        "task_type_code": run_record.task_type_code,
        "task_complexity_bucket": run_record.task_complexity_bucket,
    }
```

### Hierarchical Fallback Chain

```
Level 1: {provider}.{model_family}.{tool_profile}.{context_size}.{task_type}.{complexity}
Level 2: drop complexity
Level 3: drop task_type
Level 4: drop context_size
Level 5: drop tool_profile → {provider}.{model_family}
Level 6: no calibration — deterministic pricing only
```

Minimum observation thresholds: 30 for levels 1-4; 20 for level 5.
Buckets below threshold: marked `confidence_level = 'insufficient'`; fall back.

---

## 7. Quality Window Gate

### The Gate Invariant

A calibration observation must not be used in snapshot computation until all expected
quality signals for that run have resolved. Enforced via `quality_finalized_at`.

Any observation with `quality_finalized_at IS NULL` has `calibration_eligible = false`.

### Quality Finalization Job

Runs every 6 hours. Sets `quality_finalized_at` on observations where all expected
observation windows have elapsed.

```python
def run_quality_finalization_job():
    cutoff = now() - timedelta(days=7)  # longest default window
    db.execute("""
        UPDATE cost_intelligence.calibration_observations
        SET quality_finalized_at = now(), calibration_eligible = true
        WHERE quality_finalized_at IS NULL
          AND telemetry_status IN ('complete','reconciled')
          AND is_outlier = false
          AND created_at < $1
    """, cutoff)

    lag_hours = compute_finalization_lag()
    if lag_hours > 24:
        trigger_snapshot_re_evaluation_flag(lag_hours)
        emit_alert("quality_finalization_lag_exceeded", lag_hours=lag_hours)
```

### Finalization Lag Rule

If quality finalization lag exceeds 24 hours, any calibration snapshots promoted during
the lag window must be marked for re-evaluation:

```sql
UPDATE cost_intelligence.calibration_snapshots
SET requires_re_evaluation = true,
    re_evaluation_reason = 'quality_finalization_lag_exceeded_24h'
WHERE status IN ('active','retired')
  AND promoted_at > now() - ($lag_hours || ' hours')::interval
  AND requires_re_evaluation = false;
```

Operators must clear these flags manually after reviewing affected snapshots.

### Calibration Pipeline Must Not Bypass the Gate

Every calibration computation query must include:

```sql
WHERE calibration_eligible = true
  AND is_outlier = false
  AND telemetry_status IN ('complete','reconciled')
```

---

## 8. Outlier Detection

### Z-Score Detection

```python
def detect_outlier(observation, bucket_history):
    if len(bucket_history) < 10:
        return False, None, None  # insufficient history
    mean = statistics.mean(bucket_history)
    stddev = statistics.stdev(bucket_history)
    if stddev == 0:
        if observation.percentage_error > 2.0:
            return True, "zero_variance_bucket_extreme_error", None
        return False, None, None
    z_score = (observation.percentage_error - mean) / stddev
    if abs(z_score) > 5.0:
        return True, "z_score_gt_5_auto_exclude", z_score
    if abs(z_score) > 3.0:
        return True, "z_score_gt_3_pending_review", z_score
    return False, None, z_score
```

### Absolute Bounds

- `percentage_error > 10.0` (>1000% error) → always outlier
- `actual_cost_usd > 500.0` → flagged for review
- `absolute_error_usd > 50.0` → flagged for review

### Winsorization

Before computing multipliers, winsorize at p1/p99 of the bucket's historical
distribution. Applied even to non-outlier observations.

### Outlier Review Queue

`z_score_gt_3_pending_review` observations enter a human review queue.
Queue must be drained weekly. Stale unreviewed outliers (>14 days) generate an alert.

---

## 9. Multiplier Computation

```
multiplier = EMA(actual_cost / estimated_cost, alpha=0.15)
```

Applied over observations in chronological order. Alpha=0.15 is global for Phase 2.
Per-bucket alpha is deferred to Phase 3+.

Multiplier bounds: [0.3, 5.0]. A computed multiplier outside these bounds blocks
snapshot promotion until human review.

Error distribution stored per bucket: `p50_error`, `p75_error`, `p95_error`, `mape`.

---

## 10. Calibration Snapshot Pipeline

### Daily Batch Procedure

1. Verify no draft snapshot exists for today (idempotent)
2. Identify active pricing table and predecessor snapshot
3. Compute multipliers for all eligible buckets
4. Create draft snapshot
5. Validate multiplier bounds — flag violations, block shadow validation if found
6. Initiate shadow validation

### Shadow Validation

```python
def run_shadow_validation(snapshot_id, current_snapshot_id) -> ShadowResult:
    shadow_runs = get_shadow_validation_set()  # last 500 runs or 30 days
    # For each run: compute proposed estimate and current estimate
    # Compare aggregate MAPE and per-bucket MAPE
    passed = (
        proposed_mape <= current_mape * 1.02  # aggregate within 2%
        and len(bucket_regressions) == 0       # no per-bucket regression > 15%
        and len(shadow_runs) >= 200            # sufficient coverage
    )
    return ShadowResult(...)
```

### Promotion Decision Matrix

| Condition | Action |
|---|---|
| Shadow passed AND no material changes | Auto-promote |
| Shadow passed AND material changes | Queue for human review |
| Shadow failed (aggregate MAPE) | Block — alert |
| Shadow failed (per-bucket regression) | Block — alert with affected buckets |
| Multiplier out of bounds | Block — requires human resolution |
| Snapshot created after pricing table change | Always queue for human review |
| Shadow run count < 200 | Block — wait for more data |

**Material changes**: any bucket multiplier change > 20% from predecessor, or new bucket
affecting > 5% of recent run volume.

### Rollback

```python
def rollback_snapshot(current_id, predecessor_id, reason, actor):
    with db.transaction(isolation="SERIALIZABLE"):
        db.execute("UPDATE calibration_snapshots SET status='rolled_back', ...")
        db.execute("UPDATE calibration_snapshots SET status='active', ...")
    emit_event("calibration.snapshot.rolled_back", ...)
    invalidate_estimation_cache()
```

After rollback: calibration pipeline paused 24 hours; rolled-back snapshot's buckets
audited; affected estimates flagged for re-evaluation.

---

## 11. Drift Detection

Daily job. Does not modify calibration state — emits alerts only.

```python
for bucket in active_snapshot.buckets:
    mape_7d = compute_bucket_mape(bucket.bucket_key, window_days=7)
    mape_30d = compute_bucket_mape(bucket.bucket_key, window_days=30)

    if last_obs and (now() - last_obs).days > 14:
        emit_event("calibration.drift_detected", alert_type="stale_bucket", severity="info")

    if mape_30d and mape_7d > mape_30d * 1.5:
        emit_event("calibration.drift_detected", alert_type="mape_drift", severity="warning")

    if mape_7d > 0.40:
        emit_event("calibration.drift_detected", alert_type="high_absolute_mape", severity="critical")
        freeze_bucket_for_review(bucket.id)
```

**Frozen buckets** revert multiplier to `1.0` (deterministic, no calibration adjustment).
Frozen bucket status surfaces in estimate artifact `warnings` field.
Reverting to the previous multiplier is prohibited — that multiplier was frozen because it
produced high error.

---

## 12. Cross-Tenant Calibration Isolation

### The Isolation Boundary

Individual calibration observation records never cross tenant boundaries. Cross-tenant
aggregation uses pre-aggregated statistics only.

### Minimum Tenant Thresholds

- Segment-level calibration: ≥ 5 distinct tenants contributing to bucket
- Global calibration: ≥ 10 distinct tenants contributing to bucket

### Aggregation Pipeline

Cross-tenant pipeline runs with elevated privileges but produces only statistical
aggregates (count, mean, std_dev, p50, p75, p95 per bucket). Individual records
never flow to the cross-tenant pipeline.

### Calibration Source Fallback

```
1. Tenant-specific bucket (n≥30)         → calibration_source: 'tenant'
2. Tenant-segment bucket (n≥30, ≥5 tenants) → calibration_source: 'tenant_segment'
3. Global bucket (n≥30, ≥10 tenants)     → calibration_source: 'global'
4. Any bucket at higher level (n≥10)     → lower confidence
5. No calibration                         → calibration_source: 'deterministic'
```

`calibration_source` and `calibration_sample_tier` populated on every estimate artifact.

---

## 13. Operational Invariants

```
INV-CAL-001  [Class A] One active calibration snapshot at any time.
INV-CAL-002  [Class A] One active bucket schema version at any time.
INV-CAL-003  [Class A] calibration_eligible = false when quality_finalized_at IS NULL.
             Cannot be overridden.
INV-CAL-004  [Class B] No snapshot promoted without completed shadow validation
             (passed=true) or explicit human review approval.
INV-CAL-005  [Class B] No snapshot references observations from after its created_at.
INV-CAL-006  [Class C] No bucket multiplier outside [0.3, 5.0] in active snapshot.
             Alert immediately if violated.
INV-CAL-007  [Class C] Outlier review queue drained — no observations >14 days unreviewed.
INV-CAL-008  [Class C] Daily drift detection job completes within 2 hours.
INV-CAL-009  [Class C] No cross-tenant query returns individual run records.
INV-CAL-010  [Class D] Human-reviewed promotions have named human in promotion_approved_by.
```
