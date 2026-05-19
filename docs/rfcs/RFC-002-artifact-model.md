# RFC-002 — Artifact Model

```
Status: Active
Version: 1.0.0
Authors: [Platform Engineering]
Depends on: RFC-001 (Operational Invariants)
Required before: RFC-003 (Telemetry Contract), RFC-004 (Runtime Governance)
```

---

## 1. Context

Every significant decision in the platform — cost estimation, model selection, budget
reservation, quality evaluation — produces a durable record. This RFC defines what
those records are, how they are structured, who owns them, and what guarantees they carry.

This document is binding. Schema implementations must conform to it. Deviations require
a formal RFC amendment.

---

## 2. Motivation

Without a canonical artifact model:
- Immutability is enforced by convention, not by the database
- Replayability requires preserved decision inputs that will be missing when needed
- Audit reconstruction depends on mutable external state that changes over time
- Correction workflows default to direct UPDATEs that corrupt audit trails

---

## 3. Scope

- Artifact taxonomy and ownership
- Immutability guarantees and enforcement
- Correction record semantics
- Reference vs snapshot rules
- Required fields, constraints, schema guidance per artifact type
- Inter-artifact invariants
- Append-only enforcement patterns
- Replay and audit implications
- Monitoring obligations per artifact type

---

## 4. Non-Goals

- Application business logic for run dispatch or governance decisions
- Telemetry event contract (RFC-003)
- Runtime governance mechanics beyond reservation and settlement (RFC-004)
- Model Intelligence routing algorithm
- Data retention, archival, cold storage policies

---

## 5. Definitions

**Artifact**: A durable, structured record produced at a specific point in the platform
lifecycle. Once written, an artifact is never modified.

**Immutable artifact**: An artifact whose rows may never be updated or deleted after
creation. Errors are addressed through correction records.

**Append-only table**: INSERT permitted; UPDATE and DELETE prohibited via restrictive RLS.

**Correction record**: An immutable record documenting that a previously written artifact
contained incorrect data. Never replaces the original.

**Reference**: A FK from one artifact to another versioned, immutable artifact.

**Snapshot (embed)**: Copying critical fields from referenced state into the artifact
at write time.

**Passthrough mode**: Initial operating mode for recommendation artifacts. Written with
`routing_mode = 'passthrough'` and `candidates_evaluated = []`.

**Estimation tier**: Degradation ladder level: `calibrated` → `cached_calibration` →
`deterministic` → `embedded_fallback`.

**Telemetry completeness status**: State of run telemetry at evaluation time:
`complete`, `incomplete`, `provisional`, `reconciled`.

---

## 6. Artifact Taxonomy

```
Domain: Cost Intelligence
  ART-001  Estimate Artifact
  ART-002  Evaluation Artifact
  ART-003  Pricing Table Version
  ART-004  Calibration Snapshot

Domain: Runtime Governance
  ART-005  Budget Reservation
  ART-006  Settlement Record

Domain: Model Intelligence (stub Phase 1–3)
  ART-007  Recommendation Artifact

Cross-cutting
  ART-008  Quality Signal
  ART-009  Correction Record
```

---

## 7. Ownership Boundaries

| Artifact | Owning Domain | Created When |
|---|---|---|
| Estimate Artifact | Cost Intelligence | Before run execution begins |
| Evaluation Artifact | Cost Intelligence | After run reaches terminal state |
| Pricing Table Version | Cost Intelligence | On pricing change |
| Calibration Snapshot | Cost Intelligence | On calibration pipeline completion |
| Budget Reservation | Runtime Governance | At dispatch approval |
| Settlement Record | Runtime Governance | On run terminal state |
| Recommendation Artifact | Model Intelligence | At dispatch time |
| Quality Signal | Cross-cutting | Asynchronously after run completion |
| Correction Record | Cross-cutting | When incorrect data is discovered |

No domain may write to an artifact owned by another domain.

---

## 8. Immutability Rules

### 8.1 The Fundamental Rule

No artifact row may be updated or deleted after creation. Enforced at the database
layer via restrictive RLS policies (see RFC-001 §3 for the canonical pattern).

### 8.2 Partial Creation Failure

If an artifact cannot be created completely, it must not be created at all.
A partial artifact is worse than no artifact.

If `estimation_features_snapshot` cannot be populated, the estimate artifact must
not be written. The run request fails with a clear error.

### 8.3 Correction Record Pattern

See RFC-001 §4 for the canonical correction record pattern. Every domain must use
correction records rather than direct mutations when errors are discovered.

---

## 9. Reference vs Snapshot Rules

| Condition | Approach |
|---|---|
| Referenced artifact is immutable and platform-governed | Reference by UUID FK |
| Referenced state may evolve or be retired | Snapshot critical fields |
| Referenced state is external (provider pricing) | Always snapshot |
| Referenced state is mutable tenant configuration | Never reference; snapshot what mattered |

**The Pricing Snapshot Rule**: `pricing_table_version_id` FK + embedded `pricing_snapshot`
JSONB containing the applicable rates. Both are required. The snapshot ensures the artifact
is self-interpreting if the pricing table record ever becomes unavailable.

```json
"pricing_snapshot": {
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "rates": {
    "input_per_1k_tokens_usd": 0.003,
    "output_per_1k_tokens_usd": 0.015,
    "cached_input_per_1k_tokens_usd": 0.0003,
    "reasoning_per_1k_tokens_usd": 0.015,
    "tool_call_per_invocation_usd": 0.0
  },
  "captured_at": "2026-05-18T14:22:58.001Z"
}
```

---

## 10. Artifact Type Specifications

### ART-001 — Estimate Artifact

**Purpose**: Records the cost estimate produced before a run begins.  
**Created by**: Cost Intelligence  
**Created when**: After model selection, before run execution. Failure to create = run does not start.  
**Immutable**: Yes, immediately on write.

#### Required Fields

```
id                          UUID          NOT NULL  PK DEFAULT gen_random_uuid()
run_request_id              UUID          NOT NULL  FK → run_requests.id
tenant_id                   UUID          NOT NULL
schema_version              TEXT          NOT NULL  DEFAULT '1.0.0'

model                       TEXT          NOT NULL
provider                    TEXT          NOT NULL
model_selection_mode        TEXT          NOT NULL  CHECK (see enum)
model_selection_reason      TEXT          NOT NULL

pricing_table_version_id    UUID          NOT NULL  FK → pricing_table_versions.id
pricing_snapshot            JSONB         NOT NULL

calibration_version_id      UUID          NULL      FK → calibration_snapshots.id
calibration_source          TEXT          NULL      CHECK (see enum)
calibration_sample_tier     TEXT          NULL      CHECK (see enum)

estimation_features_snapshot JSONB        NOT NULL  -- CRITICAL: see §10.1.1
estimation_tier             TEXT          NOT NULL  CHECK (see enum)

cost_p50_usd                NUMERIC(10,6) NOT NULL
cost_p75_usd                NUMERIC(10,6) NOT NULL
cost_p95_usd                NUMERIC(10,6) NOT NULL
tokens_in_p50               INTEGER       NULL
tokens_out_p50              INTEGER       NULL
estimated_latency_ms_p50    INTEGER       NULL
estimated_quality_p50       NUMERIC(4,3)  NULL

confidence                  TEXT          NOT NULL  CHECK (see enum)
warnings                    TEXT[]        NOT NULL  DEFAULT '{}'
created_at                  TIMESTAMPTZ   NOT NULL  DEFAULT now()
```

#### Enumerations

```sql
CHECK (model_selection_mode IN (
  'user_specified','tenant_default','policy_enforced',
  'router_recommended','fallback'
))
CHECK (calibration_source IN (
  'tenant','tenant_segment','global','deterministic'
))
CHECK (calibration_sample_tier IN (
  'lt_10','10_to_100','100_to_1000','gt_1000'
))
CHECK (estimation_tier IN (
  'calibrated','cached_calibration','deterministic','embedded_fallback'
))
CHECK (confidence IN (
  'very_low','low','medium','high','very_high'
))
```

#### 10.1.1 — The `estimation_features_snapshot` Field

The most critical field in the entire artifact model. Must be populated before any
other field. If it cannot be populated, the artifact must not be created.

**Definition**: The complete set of input features extracted from the run request and
passed to the estimation algorithm, stored at artifact write time.

```json
{
  "feature_schema_version": "features-v1",
  "captured_at": "2026-05-18T14:22:58.001Z",
  "prompt_chars": 12400,
  "context_ref_count": 3,
  "artifact_ref_count": 1,
  "tools_enabled": ["web_search","file_search"],
  "tools_definition_hash": "sha256:abc123...",
  "system_prompt_hash": "sha256:def456...",
  "declared_max_steps": 8,
  "declared_child_runs": 0,
  "task_type_code": "info_retrieval",
  "task_complexity_bucket": "medium",
  "context_window_requested_pct": 0.42
}
```

`feature_schema_version` is mandatory. Replay engines must apply the correct algorithm
version to the correct feature schema version.

#### Constraints

```sql
CREATE UNIQUE INDEX uq_estimate_per_run_request
  ON cost_intelligence.estimate_artifacts (run_request_id);

FOREIGN KEY (pricing_table_version_id)
  REFERENCES cost_intelligence.pricing_table_versions(id) ON DELETE RESTRICT
FOREIGN KEY (calibration_version_id)
  REFERENCES cost_intelligence.calibration_snapshots(id) ON DELETE RESTRICT
```

---

### ART-002 — Evaluation Artifact

**Purpose**: Records the comparison between the pre-run estimate and the actual outcome.
Created for every run that reaches a terminal state, including failures and aborts.  
**Created by**: Cost Intelligence evaluation pipeline  
**Created when**: Asynchronously after `run.completed`, `run.aborted`, or `run.force_terminated`  
**Immutable**: Yes. Creation is idempotent (check for existing before creating).

#### Required Fields

```
id                          UUID          NOT NULL  PK
estimate_id                 UUID          NOT NULL  FK → estimate_artifacts.id
run_id                      UUID          NOT NULL  FK → run_records.id  UNIQUE
tenant_id                   UUID          NOT NULL
schema_version              TEXT          NOT NULL  DEFAULT '1.0.0'
eval_algorithm_version      TEXT          NOT NULL

telemetry_status            TEXT          NOT NULL  CHECK (see enum)

actual_cost_usd             NUMERIC(10,6) NOT NULL
actual_cost_input_usd       NUMERIC(10,6) NULL
actual_cost_output_usd      NUMERIC(10,6) NULL
actual_cost_cached_usd      NUMERIC(10,6) NULL
actual_cost_tools_usd       NUMERIC(10,6) NULL
actual_cost_reasoning_usd   NUMERIC(10,6) NULL

tokens_in_actual            INTEGER       NULL
tokens_out_actual           INTEGER       NULL
tokens_cached_actual        INTEGER       NULL
tokens_reasoning_actual     INTEGER       NULL

wall_clock_ms               INTEGER       NULL
time_to_first_token_ms      INTEGER       NULL
retry_count                 INTEGER       NULL  DEFAULT 0
failure_mode                TEXT          NULL  CHECK (see enum)
actual_tool_calls           INTEGER       NULL
actual_child_runs           INTEGER       NULL
context_window_used_pct     NUMERIC(5,2)  NULL

absolute_error_usd          NUMERIC(10,6) NULL
percentage_error            NUMERIC(8,4)  NULL
underestimated              BOOLEAN       NULL

calibration_bucket_id       UUID          NULL  FK → calibration_buckets.id
calibration_bucket_key      TEXT          NULL
is_outlier                  BOOLEAN       NOT NULL  DEFAULT false
outlier_reason              TEXT          NULL

is_recomputable             BOOLEAN       NOT NULL  DEFAULT true
derivation_manifest         JSONB         NOT NULL

created_at                  TIMESTAMPTZ   NOT NULL  DEFAULT now()
```

#### Enumerations

```sql
CHECK (telemetry_status IN (
  'complete','incomplete','provisional','reconciled'
))
CHECK (failure_mode IN (
  'rate_limit','context_overflow','content_filter','api_error',
  'timeout','user_cancelled','cost_limit_abort','force_killed','provider_unreachable'
))
```

#### Handling Incomplete Telemetry

When token telemetry is missing at run completion:
1. Create with `telemetry_status = 'incomplete'`, `actual_cost_usd = 0.0`
2. Set error metrics to NULL — do not use the estimate
3. Artifact is excluded from calibration until reconciled
4. When telemetry arrives or is declared lost: write a correction record and a new
   settlement record — do NOT update the original evaluation artifact

---

### ART-003 — Pricing Table Version

**Purpose**: Records cost per token and per tool call for each provider/model.  
**Immutable**: Yes. Status transitions recorded via `activated_at`/`retired_at` columns.  
**One active at a time**: Enforced by unique partial index.

```sql
CREATE UNIQUE INDEX one_active_pricing_table
  ON cost_intelligence.pricing_table_versions(status)
  WHERE status = 'active';
```

#### Required Fields

```
id              UUID          NOT NULL  PK
version         TEXT          NOT NULL  UNIQUE  -- "pricing-2026-05"
status          TEXT          NOT NULL  CHECK (status IN ('draft','active','retired'))
effective_from  TIMESTAMPTZ   NOT NULL
effective_until TIMESTAMPTZ   NULL
entries         JSONB         NOT NULL
created_at      TIMESTAMPTZ   NOT NULL  DEFAULT now()
created_by      TEXT          NOT NULL
activated_at    TIMESTAMPTZ   NULL
activated_by    TEXT          NULL
retired_at      TIMESTAMPTZ   NULL
retired_by      TEXT          NULL
predecessor_id  UUID          NULL  FK → pricing_table_versions.id
```

Activation is a single transaction that retires the current active table and
activates the new one simultaneously.

---

### ART-004 — Calibration Snapshot

**Purpose**: A complete, versioned set of calibration multipliers for all active
calibration buckets at a point in time.  
**Immutable**: After promotion to `active`.

```sql
CREATE UNIQUE INDEX uq_single_active_calibration
  ON cost_intelligence.calibration_snapshots(status)
  WHERE status = 'active';
```

#### Required Fields

```
id                        UUID          NOT NULL  PK
version                   TEXT          NOT NULL  UNIQUE  -- "calibration-v2026-05-18-01"
status                    TEXT          NOT NULL  CHECK (status IN (
                            'draft','shadow','active','retired','rolled_back'))
predecessor_id            UUID          NULL  FK → calibration_snapshots.id
pricing_table_version_id  UUID          NOT NULL  FK → pricing_table_versions.id
bucket_schema_version     TEXT          NOT NULL
shadow_mape               NUMERIC(8,4)  NULL
shadow_predecessor_mape   NUMERIC(8,4)  NULL
shadow_run_count          INTEGER       NULL
shadow_started_at         TIMESTAMPTZ   NULL
shadow_completed_at       TIMESTAMPTZ   NULL
shadow_passed             BOOLEAN       NULL
shadow_failure_reason     TEXT          NULL
promotion_approved_by     TEXT          NULL
promotion_approved_at     TIMESTAMPTZ   NULL
promoted_at               TIMESTAMPTZ   NULL
retired_at                TIMESTAMPTZ   NULL
rollback_reason           TEXT          NULL
requires_re_evaluation    BOOLEAN       NOT NULL  DEFAULT false
re_evaluation_reason      TEXT          NULL
created_at                TIMESTAMPTZ   NOT NULL  DEFAULT now()
```

`requires_re_evaluation` and `re_evaluation_reason` are set by the quality
finalization job when finalization lag exceeds 24 hours (RFC-006 §9.4).

---

### ART-005 — Budget Reservation

**Purpose**: Pre-run budget hold established at dispatch time.  
**Immutable**: Financial fields are immutable after creation. `status` is the only
updatable field (operational lifecycle, not financial record).  
**See RFC-004 §7 for full state machine.**

#### Required Fields

```
id                            UUID          NOT NULL  PK
run_id                        UUID          NOT NULL  UNIQUE  FK → run_records.id
tenant_id                     UUID          NOT NULL
estimate_id                   UUID          NOT NULL  FK → estimate_artifacts.id
recommendation_id             UUID          NULL      FK → recommendation_artifacts.id
trace_id                      UUID          NOT NULL
parent_reservation_id         UUID          NULL      FK → budget_reservations.id
period_key                    TEXT          NOT NULL
reserved_usd                  NUMERIC(10,6) NOT NULL
reservation_tier              TEXT          NOT NULL  CHECK (tier IN ('p50','p75','p95'))
hard_limit_usd                NUMERIC(10,6) NULL
soft_limit_usd                NUMERIC(10,6) NULL
max_run_time_ms               INTEGER       NULL
budget_available_at_dispatch  NUMERIC(12,4) NOT NULL  -- snapshot at reservation time
status                        TEXT          NOT NULL  DEFAULT 'active'
                                CHECK (status IN (
                                  'active','soft_timeout','hard_timeout',
                                  'provisional_settlement','settled',
                                  'overrun','expired','cancelled'))
expires_at                    TIMESTAMPTZ   NOT NULL
created_at                    TIMESTAMPTZ   NOT NULL  DEFAULT now()
```

**Immutable fields** (never updated after creation):
`id, run_id, tenant_id, estimate_id, recommendation_id, trace_id,
parent_reservation_id, period_key, reserved_usd, reservation_tier,
hard_limit_usd, soft_limit_usd, budget_available_at_dispatch,
max_run_time_ms, expires_at, created_at`

**Mutable field** (operational state only): `status`, `updated_at`

---

### ART-006 — Settlement Record

**Purpose**: Final cost accounting for a completed run, decoupled from the reservation.  
**Immutable**: Yes. Idempotent creation (check for existing non-provisional before creating).

#### Required Fields

```
id                    UUID          NOT NULL  PK
reservation_id        UUID          NOT NULL  FK → budget_reservations.id
tenant_id             UUID          NOT NULL
settlement_type       TEXT          NOT NULL  CHECK (see enum)
actual_cost_usd       NUMERIC(10,6) NOT NULL
settlement_source     TEXT          NOT NULL  CHECK (see enum)
is_provisional        BOOLEAN       NOT NULL  DEFAULT false
created_at            TIMESTAMPTZ   NOT NULL  DEFAULT now()
reconciled_at         TIMESTAMPTZ   NULL
```

```sql
-- One non-provisional settlement per reservation
CREATE UNIQUE INDEX uq_final_settlement_per_reservation
  ON runtime_governance.settlement_records(reservation_id)
  WHERE is_provisional = false;
```

---

### ART-007 — Recommendation Artifact

**Purpose**: Records the model selection decision at dispatch time.  
**Created for every run request without exception**, including passthrough mode.  
**Immutable**: Yes.

#### Required Fields

```
id                          UUID          NOT NULL  PK
run_request_id              UUID          NOT NULL  UNIQUE  FK → run_requests.id
tenant_id                   UUID          NOT NULL
schema_version              TEXT          NOT NULL  DEFAULT '1.0.0'
routing_mode                TEXT          NOT NULL  DEFAULT 'passthrough'
                              CHECK (routing_mode IN (
                                'passthrough','cheapest_acceptable','balanced',
                                'highest_quality','fastest','regulated','experimental'))
model_selection_mode        TEXT          NOT NULL
                              CHECK (model_selection_mode IN (
                                'user_specified','tenant_default','policy_enforced',
                                'router_recommended','fallback'))
selected_model              TEXT          NOT NULL
selected_provider           TEXT          NOT NULL
selection_reason            TEXT          NOT NULL
routing_policy_version      TEXT          NULL
scoring_function_version    TEXT          NULL
profile_snapshot_version    TEXT          NULL
task_type_id                UUID          NULL  FK → task_types.id
task_complexity_bucket      TEXT          NULL
budget_eligible_models      TEXT[]        NOT NULL  DEFAULT '{}'
quality_floor_applied       NUMERIC(4,3)  NULL
budget_available_at_routing NUMERIC(12,4) NOT NULL
cold_start_model_selected   BOOLEAN       NOT NULL  DEFAULT false
routing_confidence          TEXT          NULL
                              CHECK (routing_confidence IN (
                                'very_low','low','medium','high',
                                'very_high','not_applicable'))
candidates_evaluated        JSONB         NOT NULL  DEFAULT '[]'
created_at                  TIMESTAMPTZ   NOT NULL  DEFAULT now()
```

#### The `candidates_evaluated` Array

Every candidate — eliminated, scored-but-not-selected, and selected — must appear.
An empty array is valid only in passthrough mode. In any active routing mode, an
empty array is a provenance violation.

See RFC-008 §8.2 for the full candidate object schema.

#### The Explainability Requirement

Every recommendation artifact must be explainable from its own fields alone,
without joining to model profile tables, calibration tables, or policy tables.
Embed scores and elimination reasons per candidate at write time.

---

### ART-008 — Quality Signal

**Purpose**: Individual quality observations about a completed run. Accumulates
asynchronously over time. The run record is never modified; signals append alongside it.  
**Immutable**: Each row, yes. New rows append. `observation_window_closed` is set
once from false to true; never reversed.

#### Required Fields

```
id                    UUID          NOT NULL  PK
run_id                UUID          NOT NULL  FK → run_records.id
tenant_id             UUID          NOT NULL
signal_type           TEXT          NOT NULL  CHECK (see RFC-007 §6.1)
signal_value          JSONB         NOT NULL
signal_schema_version TEXT          NOT NULL
captured_at           TIMESTAMPTZ   NOT NULL
signal_source         TEXT          NOT NULL  CHECK (see enum)
evaluator_id          UUID          NULL
evaluator_version     TEXT          NULL
confidence            NUMERIC(4,3)  NULL      CHECK (confidence BETWEEN 0 AND 1)
observation_window    TEXT          NOT NULL
observation_window_closed BOOLEAN   NOT NULL  DEFAULT false
created_at            TIMESTAMPTZ   NOT NULL  DEFAULT now()
```

**Rule**: No composite quality score is ever stored as a source-of-truth column.
Quality signals are raw observations. Composite scores are computed at query time.

---

### ART-009 — Correction Record

**Purpose**: Documents that a previously written artifact contained incorrect data.
The correction record is itself immutable.

#### Required Fields

```
id                          UUID          NOT NULL  PK
artifact_type               TEXT          NOT NULL  CHECK (artifact_type IN (
                              'estimate_artifact','evaluation_artifact',
                              'recommendation_artifact','budget_reservation',
                              'settlement_record','quality_signal','run_record'))
artifact_id                 UUID          NOT NULL
tenant_id                   UUID          NOT NULL
correction_category         TEXT          NOT NULL  CHECK (correction_category IN (
                              'billing_adjustment','telemetry_bug','data_entry_error',
                              'provider_correction','duplicate_record','reconciliation'))
correction_reason           TEXT          NOT NULL
corrected_fields            JSONB         NOT NULL  -- [{field, old_value, new_value}]
corrected_by                TEXT          NOT NULL
evidence_reference          TEXT          NULL
requires_calibration_review BOOLEAN       NOT NULL  DEFAULT false
created_at                  TIMESTAMPTZ   NOT NULL  DEFAULT now()
```

`requires_calibration_review = true` when the corrected artifact is an
`evaluation_artifact` and the corrected fields are used in calibration bucket
computation.

---

## 11. Inter-Artifact Invariants

```
INV-ART-001  [Class A — NOT NULL]
Every estimate_artifact has estimation_features_snapshot IS NOT NULL.

INV-ART-002  [Class A — FK constraint]
Every evaluation_artifact references an estimate_artifact that exists.

INV-ART-003  [Class A — UNIQUE index]
At most one estimate_artifact per run_request_id.

INV-ART-004  [Class A — UNIQUE index]
At most one evaluation_artifact per run_id.

INV-ART-005  [Class A — FK constraint]
Every budget_reservation references an estimate_artifact that exists.

INV-ART-006  [Class A — UNIQUE index]
At most one recommendation_artifact per run_request_id.

INV-ART-007  [Class A — UNIQUE partial index]
At most one non-provisional settlement_record per reservation_id.

INV-ART-008  [Class B — application sequencing]
No run execution signal is emitted before budget_reservation status = 'active'
is confirmed.

INV-ART-009  [Class C — monitoring]
Every run_record with ended_at IS NOT NULL has an evaluation_artifact
within 10 minutes.

INV-ART-010  [Class C — monitoring]
Every active budget_reservation for a run with ended_at IS NOT NULL
is settled within 15 minutes.

INV-ART-011  [Class C — monitoring]
Weekly correction rate does not exceed 0.5%.

INV-ART-012  [Class C — monitoring]
pg_stat_user_tables.n_tup_upd = 0 for all artifact tables at all times.

INV-ART-013  [Class C — monitoring]
Every run_request has a recommendation_artifact, including passthrough mode.
Daily query: estimate_artifacts with no corresponding recommendation_artifact.

INV-ART-014  [Class D — process]
Correction records are used for all corrections. Zero direct UPDATEs on
artifact tables.
```

---

## 12. Namespace Assignments

```
cost_intelligence.estimate_artifacts
cost_intelligence.evaluation_artifacts
cost_intelligence.pricing_table_versions
cost_intelligence.calibration_snapshots
cost_intelligence.calibration_buckets       (child of calibration_snapshots)
runtime_governance.budget_reservations
runtime_governance.budget_periods
runtime_governance.settlement_records
model_intelligence.recommendation_artifacts
platform.quality_signals
platform.correction_records
```

---

## 13. Artifact Creation Sequence (Dispatch)

```
1. recommendation_artifact created (passthrough or routing decision)
2. estimate_artifact created (references recommendation for future join)
3. budget_reservation created (references estimate_artifact)
4. run execution signal emitted
5. [run executes]
6. run_record terminal state set
7. settlement_record created (async, within 10 minutes)
8. evaluation_artifact created (async, within 10 minutes)
9. quality_signals accumulate (async, over up to 30 days)
```

Steps 1–3 are synchronous and must complete before step 4.
Steps 7–9 are asynchronous.
If any of steps 1–3 fail, the run must not start.
