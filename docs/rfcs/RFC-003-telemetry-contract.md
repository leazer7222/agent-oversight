# RFC-003 — Telemetry Contract

```
Status: Active
Version: 1.0.0
Authors: [Platform Engineering]
Depends on: RFC-001 (Operational Invariants), RFC-002 (Artifact Model)
Required before: RFC-004 (Runtime Governance), RFC-005 (Task Taxonomy),
                 any service implementation
```

---

## 1. Context

Every significant action in the platform produces a telemetry event. These events are
the communication substrate between bounded domains, the input to calibration, and the
foundation of replay and audit reconstruction.

This RFC defines the telemetry contract: the event envelope, the event taxonomy, the
correlation model, idempotency and ordering guarantees, schema evolution rules, and
operational constraints.

This RFC is binding on all services. A service that emits events not conforming to
this contract is non-compliant.

---

## 2. Scope

- Canonical event envelope schema
- Correlation model (trace_id, run_id, parent_run_id, sequence_number)
- Full event taxonomy with payloads
- Idempotency contract and deduplication pattern
- Ordering guarantees — what is and is not guaranteed
- Hot-path discipline
- Schema evolution rules
- Ingestion model and raw_events store
- Consumer contract obligations
- estimation_features_snapshot emission chain
- Replay event requirements
- Tenant isolation

---

## 3. Event Envelope Specification

Every event from every service must conform to this envelope. The envelope is frozen
at v1.0.0.

```json
{
  "event_id":       "uuid-v4",
  "schema_version": "1.0.0",
  "event_type":     "run.completed",
  "emitted_at":     "2026-05-18T14:23:01.442Z",
  "sequence_number": 4,
  "trace_id":       "uuid",
  "run_id":         "uuid",
  "parent_run_id":  "uuid | null",
  "campaign_id":    "uuid | null",
  "tenant_id":      "uuid",
  "is_replay":      false,
  "replay_id":      "uuid | null",
  "payload":        { }
}
```

### Field Specifications

**`event_id`**: UUID. Globally unique. Used as primary key of `raw_events`.
Deduplication relies on collision-free generation.

**`schema_version`**: Semantic version of the payload schema for this event type.
Envelope schema is fixed. Payload version evolves per event type.

**`emitted_at`**: UTC, ISO 8601, millisecond precision. Never use for ordering.

**`sequence_number`**: Monotonically increasing per `run_id`. Consumers sort by
`(run_id, sequence_number)` to reconstruct within-run order.

**`trace_id`**: Spans the entire top-level request including all child runs.
Never null. For non-orchestrated runs, equals a UUID generated at request receipt.

**`parent_run_id`**: Direct parent run_id. Null for root runs.

**`is_replay`**: Must be `true` for simulation events. Live events always `false`.
Consumers that modify state must check this field and no-op on replay events.

---

## 4. Correlation Model

### The Four Identifiers

```
trace_id       — "which top-level request does this belong to?"
run_id         — "which agent invocation does this belong to?"
parent_run_id  — "who spawned this agent?"
sequence_number — "what position in this run's event stream?"
```

All four must be propagated when spawning child operations.

### Event ID Generation

**Non-deterministic events** (most): UUID v4 at emission time.

**Deterministic events** (must be re-emittable with the same ID):

```python
PLATFORM_NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
event_id = uuid5(PLATFORM_NAMESPACE, f"{run_id}:{event_type}:{ended_at.isoformat()}")
```

Use deterministic IDs for: `run.completed`, `run.aborted`, `run.force_terminated`,
`run.timed_out`.

### Trace Propagation Rules

When an orchestrating agent spawns a child run:
- Child's `trace_id` = parent's `trace_id`
- Child's `parent_run_id` = parent's `run_id`
- Child generates a new `run_id`
- Child's `sequence_number` starts at 1 (separate stream)

---

## 5. Event Taxonomy

Namespaces by owning domain:

```
run.*           → Agent Oversight
estimate.*      → Cost Intelligence
evaluation.*    → Cost Intelligence
calibration.*   → Cost Intelligence
pricing.*       → Cost Intelligence
budget.*        → Runtime Governance
spend.*         → Runtime Governance
abort.*         → Runtime Governance
recommendation.* → Model Intelligence (Phase 4)
quality.*       → Platform (cross-cutting)
tool.*          → Agent Runtime (opt-in)
child.*         → Agent Runtime
platform.*      → Infrastructure
```

### run.requested

```
Owner:         Agent Oversight
Classification: Hot path — synchronous
Replay-required: YES
```

Payload includes: `run_request_id`, `agent_definition_id`, `agent_instance_id`,
`task_type_code`, `task_complexity_bucket`, `declared_max_steps`,
`declared_child_runs`, `model`, `provider`, `model_selection_mode`, `priority`,
`cost_center_id`, `requested_by`.

### run.estimate.requested

```
Owner:         Agent Oversight
Classification: Hot path — synchronous
Replay-required: YES — contains raw feature inputs
```

Payload includes all fields of `run.requested` plus the full `estimation_features`
object that becomes `estimation_features_snapshot` in ART-001. See §9 for the
emission chain specification.

### estimate.produced

```
Owner:         Cost Intelligence
Classification: Hot path response
Replay-required: YES
```

Payload includes: `estimate_id`, `run_request_id`, `estimation_tier`, cost envelope
(p50/p75/p95), `confidence`, calibration metadata, `pricing_table_version_id`,
`warnings`, `estimation_features_echo` (verbatim copy of features received).

### recommendation.produced

```
Owner:         Model Intelligence (Phase 4); dispatch coordinator in passthrough
Classification: Hot path — synchronous
Replay-required: YES
```

Payload includes: `recommendation_id`, `run_request_id`, `routing_mode`,
`model_selection_mode`, `selected_model`, `selected_provider`, `selection_reason`,
`routing_policy_version`, `budget_eligible_models`, `candidates_evaluated`.

### run.approved

```
Owner:         Agent Oversight
Classification: Hot path — synchronous
Replay-required: YES
```

Payload: `run_request_id`, `estimate_id`, `reservation_id`, `policy_version`,
`approved_at`, `budget_reserved_usd`, `reservation_tier`.

### run.rejected

```
Owner:         Agent Oversight
Classification: Hot path — synchronous
Replay-required: YES
```

Payload: `run_request_id`, `estimate_id`, `rejection_reason`, `rejection_detail`,
`policy_version`, `rejected_at`, `budget_available_usd`, `estimation_tier_used`.

```sql
-- rejection_reason CHECK:
CHECK (rejection_reason IN (
  'budget_exceeded','policy_violation','estimation_unavailable',
  'model_not_eligible','quality_floor_unmet','operator_hold',
  'no_eligible_models','no_regulated_model_eligible',
  'task_classification_failed'
))
```

### run.dispatch_failed

```
Owner:         Agent Oversight / Runtime Governance
Classification: Hot path — fire-and-forget (non-blocking)
Replay-required: NO
```

Emitted when the run cannot proceed due to infrastructure failure, not policy rejection.

Payload: `run_request_id`, `failure_reason`, `failure_detail`, `failed_at`.

```sql
CHECK (failure_reason IN (
  'concurrency_retry_exceeded',
  'estimation_service_unavailable',
  'budget_period_not_found',
  'reservation_db_unavailable',
  'task_classification_failed'
))
```

**Note**: `run.dispatch_failed` is distinct from `run.rejected`. Rejected = policy
decision. Dispatch failed = infrastructure failure. These must never be conflated in
monitoring or reporting.

### run.started

```
Owner:         Agent Oversight / Agent Runtime
Classification: Hot path — synchronous
Replay-required: YES
```

Payload: `run_id`, `run_request_id`, `reservation_id`, `agent_definition_id`,
`agent_instance_id`, `model`, `model_version_actual`, `provider`, `started_at`,
`streaming`, `temperature`.

### run.completed

```
Owner:         Agent Runtime / Agent Oversight
Classification: Async — not in hot path
Replay-required: YES
Idempotency: Deterministic event_id
```

Payload: full execution telemetry including token counts by type, cost breakdown by type,
`wall_clock_ms`, `time_to_first_token_ms`, `retry_count`, `failure_mode`,
`tool_call_count_actual`, `actual_steps_completed`, `actual_child_runs_spawned`,
`context_window_used_pct`, `task_type_code`, `task_complexity_bucket`,
`system_prompt_hash`, `tools_definition_hash`, `telemetry_complete`, `abort_reason`.

`telemetry_complete: false` when mandatory telemetry fields are null. Triggers
`telemetry_status = 'incomplete'` on the evaluation artifact.

### run.aborted

```
Owner:         Agent Runtime
Classification: Async
Replay-required: YES
Idempotency: Deterministic event_id
```

Same structure as `run.completed` plus: `abort_reason`, `abort_initiated_at`,
`partial_result_produced`, `work_completed_description`.

### run.force_terminated

```
Owner:         Runtime Governance
Classification: Async
Replay-required: YES
```

Payload: `run_id`, `reservation_id`, `termination_reason`, `abort_requested_at`,
`force_terminated_at`, `grace_window_ms`, `partial_result_produced`.

### run.timed_out

```
Owner:         Runtime Governance
Classification: Async
Replay-required: YES
```

Payload: `run_id`, `reservation_id`, `timeout_type`, `max_run_time_ms`,
`elapsed_ms`, `provider_responsive`.

### budget.reservation.created

```
Owner:         Runtime Governance
Classification: Hot path — emitted after reservation INSERT commits
Replay-required: YES
```

### spend.warning / spend.limit_exceeded

```
Owner:         Runtime Governance
Classification: Async
```

### abort.requested / abort.confirmed

```
Owner:         Runtime Governance / Agent Runtime
Classification: Async
```

### budget.reservation.settled

```
Owner:         Runtime Governance
Classification: Async
```

### evaluation.written

```
Owner:         Cost Intelligence
Classification: Async
Replay-required: YES — triggers calibration observation ingestion
```

### calibration.snapshot.promoted / calibration.snapshot.rolled_back

```
Owner:         Cost Intelligence
Classification: Async
```

Consumers must invalidate calibration caches on `promoted` receipt.

### pricing_table.activated

```
Owner:         Cost Intelligence
Classification: Async
```

All estimation service instances must refresh pricing cache within 60 seconds.

### calibration.drift_detected

```
Owner:         Cost Intelligence
Classification: Async — emitted by drift detection job
```

### estimation.tier_degraded

```
Owner:         Cost Intelligence
Classification: Async — fire-and-forget, never blocking
```

Must be emitted whenever a non-calibrated estimation tier is used. Fire-and-forget.
If emission would block the hot path, drop silently.

### tool_call.completed

```
Owner:         Agent Runtime
Classification: Async — OPT-IN, not default
```

Not emitted by default. Enable per agent definition for debugging. High cardinality —
do not enable globally.

### child_run.spawned

```
Owner:         Agent Runtime
Classification: Async
```

Payload includes `declared: boolean` — whether this child run was declared in
`declared_child_runs` at estimation time. Undeclared children (`declared: false`)
trigger `spend.warning` immediately.

### quality_signal.received

```
Owner:         Platform (cross-cutting)
Classification: Async
```

### platform.invariant_violation

```
Owner:         Infrastructure / Monitoring
Classification: Async
```

---

## 6. Idempotency Contract

### Two-Layer Model

**Layer 1 — Event-ID deduplication** (within TTL window):

```sql
INSERT INTO telemetry.raw_events (id, event_type, ...)
VALUES ($event_id, ...)
ON CONFLICT (id) DO NOTHING;
```

If 0 rows returned: duplicate. Return HTTP 200 with `"duplicate": true`. Never 409.

**Layer 2 — Business-logic idempotency** (permanent):

Check if the result of processing the event already exists before processing.
The check and the operation must be within the same transaction.

```python
# REQUIRED: check and work in same transaction
with db.transaction():
    existing = db.query("SELECT 1 FROM evaluation_artifacts WHERE run_id = $1", run_id)
    if existing:
        return  # idempotent no-op
    create_evaluation_artifact(run_record)
```

### Replay Events

Events with `is_replay: true` must produce no state changes. All state-changing
consumers must check `is_replay` before processing.

---

## 7. Ordering Guarantees

### Guaranteed

- Within a single `run_id`, events have monotonically increasing `sequence_numbers`
- Events written to `raw_events` are durable before HTTP 200 is returned

### Explicitly NOT Guaranteed

- Ordering across different `run_id` values
- Wall-clock ordering (`emitted_at` does not reflect delivery order)
- Cross-service ordering between independently emitting services
- Contiguous sequence numbers (gaps may appear)
- `run.started` arriving before `run.completed`

### Prohibited Ordering Assumptions

```
PROHIBITED — never appear in consumer code:

"run.started has been processed before run.completed"
  → Check for started_at on run record; never assume

"events arrive in sequence_number order"
  → Sort by sequence_number; never assume

"emitted_at reflects processing order"
  → Never use emitted_at for ordering

"parent run.completed arrives before child run.completed"
  → Reconstruct tree from trace_id; never assume arrival order
```

### Consumer Ordering Pattern

```python
def process_run_events(run_id: str) -> None:
    events = db.query(
        "SELECT * FROM raw_events WHERE run_id = $1 ORDER BY sequence_number ASC",
        run_id
    )
    for event in events:
        process_event(event)
```

---

## 8. Hot Path Discipline

### Hot Path Budget (total: 500ms)

```
Estimation call:     250ms (budget; 3000ms timeout with fallback)
Budget reservation:  20ms
Policy check:        10ms
Overhead/network:    50ms
Reserve:             170ms
```

### Synchronous (hot path):

1. run_request record INSERT
2. recommendation_artifact INSERT (passthrough row)
3. Estimation service call (with timeout and fallback)
4. estimate_artifact INSERT
5. Budget period pre-check
6. budget_reservation INSERT (serializable)
7. run_record INSERT (started_at populated)
8. run.approved or run.rejected event (fire-and-forget write to raw_events)

### Async (must NOT be in hot path):

- evaluation_artifact creation
- calibration observation ingestion
- quality signal processing
- drift detection
- campaign forecast updates
- LLM evaluator calls — NEVER synchronous under any circumstance
- cross-run aggregation queries
- any operation with unbounded duration

### Estimation Timeout Fallback

```python
def get_estimate(features, timeout_ms=3000) -> EstimateResult:
    try:
        result = estimation_service.call(features, timeout=timeout_ms/1000)
        return result
    except TimeoutError:
        emit_event("estimation.tier_degraded", reason="calibration_service_timeout")
        cached = calibration_cache.get_snapshot(max_age_seconds=300)
        if cached:
            return deterministic_estimator.estimate(features, cached)
        return deterministic_estimator.estimate(features)
```

`estimation.tier_degraded` is fire-and-forget. Never block the hot path for it.

---

## 9. The `estimation_features_snapshot` Emission Chain

**Critical**: This chain is mandatory and must be verified in integration tests.

```
Step 1: Agent Oversight extracts feature vector from run request.
        Feature vector includes feature_schema_version.

Step 2: Agent Oversight includes feature vector verbatim in
        run.estimate.requested payload (estimation_features field).

Step 3: Cost Intelligence receives run.estimate.requested.
        Uses estimation_features as-is. Must not re-extract or modify.

Step 4: Cost Intelligence writes estimate_artifact.
        estimation_features_snapshot = the estimation_features object from Step 2.

Step 5: Cost Intelligence includes estimation_features_echo in estimate.produced.
        This is the same object echoed back unchanged.

Step 6: Agent Oversight receives estimate.produced.
        Compares estimation_features (Step 2) with estimation_features_echo (Step 5).
        If they differ: emit platform.invariant_violation, reject the estimate.
```

Any discrepancy means the estimation service is not using the features it was sent.
The run must not proceed with a mismatched estimate.

---

## 10. Ingestion Architecture

### The `raw_events` Table

```sql
CREATE TABLE telemetry.raw_events (
  id              UUID         NOT NULL,
  event_type      TEXT         NOT NULL,
  schema_version  TEXT         NOT NULL,
  emitted_at      TIMESTAMPTZ  NOT NULL,
  sequence_number INTEGER,
  trace_id        UUID         NOT NULL,
  run_id          UUID,
  parent_run_id   UUID,
  campaign_id     UUID,
  tenant_id       UUID         NOT NULL,
  is_replay       BOOLEAN      NOT NULL  DEFAULT false,
  replay_id       UUID,
  payload         JSONB        NOT NULL,
  received_at     TIMESTAMPTZ  NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);
-- Append-only enforcement (RFC-001 §3 pattern)
```

### Ingestion Endpoint Contract

```
POST /api/ingest
Response 200: {"status": "accepted", "event_id": "uuid", "duplicate": false|true}
Response 400: {"status": "rejected", "reason": "schema_validation_failed"}
Response 401: {"status": "rejected", "reason": "unauthorized"}
Response 422: {"status": "rejected", "reason": "unknown_tenant"}
Response 500: {"status": "error"} — emitter must retry with same event_id
```

Duplicates return 200, never 409. The emitter does not need to distinguish
duplicates from new events.

Fan-out to consumers is async after the `raw_events` INSERT commits.

---

## 11. Schema Evolution Rules for Events

See RFC-009 for the full schema evolution policy. Event-specific rules:

```
ALLOWED:
  New optional payload fields (MINOR bump)
  New enum values (MINOR bump; consumers must handle unknown values)
  New event types (consumers ignore unknown types without erroring)

PROHIBITED:
  Renaming a payload field
  Removing a payload field without 90-day deprecation window
  Changing a field's type
  Removing an enum value
  Changing the event envelope schema
  Changing the meaning of a field without a version bump
```

### Consumer Contract (mandatory)

All consumers must:
1. Handle unknown payload fields without erroring (permissive deserialization)
2. Handle unknown enum values without erroring (default case on all switches)

Both behaviors must be verified in consumer integration tests.

---

## 12. Replay Requirements

### Events Required for Replay (preserve indefinitely)

```
run.requested
run.estimate.requested
estimate.produced
recommendation.produced
run.approved / run.rejected
run.started
run.completed
run.aborted
run.force_terminated
run.timed_out
```

### What Replay Can and Cannot Reconstruct

**Can reconstruct**:
- "What estimate would have been produced under calibration version X?"
- "What routing decision would have been made under policy version Y?"
- "Would this run have been approved under a different budget policy?"

**Cannot reconstruct**:
- "What output would the agent have produced?" (LLM outputs are non-deterministic)
- "What would the tool call have returned?" (external APIs change)

This constraint is absolute. Never promise execution replay.

---

## 13. Tenant Isolation

- Every event carries `tenant_id`
- Ingestion endpoint validates `tenant_id` matches authentication credential
- `raw_events` RLS policy: queries return only rows matching the authenticated tenant
- Cross-tenant telemetry aggregation operates on pre-aggregated statistics only —
  individual event rows never cross tenant boundaries

---

## 14. Monitoring Obligations

```sql
-- Telemetry pipeline health (must return 1 row always)
SELECT
  COUNT(*) FILTER (WHERE received_at > now() - interval '5 minutes') AS events_last_5min,
  COUNT(*) FILTER (WHERE received_at > now() - interval '1 hour') AS events_last_hour,
  now() AS checked_at
FROM telemetry.raw_events;

-- Run completion → evaluation lag (alert if > 0)
SELECT COUNT(*) AS runs_awaiting_evaluation
FROM run_records r
LEFT JOIN evaluation_artifacts e ON e.run_id = r.id
WHERE r.ended_at < now() - interval '10 minutes'
  AND r.ended_at IS NOT NULL AND e.id IS NULL;

-- Estimation degradation rate (alert if > 5%)
SELECT
  COUNT(*) FILTER (WHERE event_type = 'estimation.tier_degraded'
    AND received_at > now() - interval '1 hour')::float
  / NULLIF(COUNT(*) FILTER (WHERE event_type = 'run.estimate.requested'
    AND received_at > now() - interval '1 hour'), 0) AS degradation_rate_1h
FROM telemetry.raw_events;

-- Features echo mismatch rate (alert if > 0)
SELECT COUNT(*) AS echo_mismatches
FROM telemetry.raw_events
WHERE event_type = 'platform.invariant_violation'
  AND payload->>'invariant_id' = 'features_echo_mismatch'
  AND received_at > now() - interval '1 hour';
```

---

## 15. Dangerous Shortcuts

- Relying on `emitted_at` for event ordering — use `sequence_number`
- Not implementing unknown-field tolerance in consumers
- Omitting `is_replay: false` from live events
- Fan-out via synchronous DB triggers
- Not emitting `estimation.tier_degraded` events
- Storing `emitted_at` as TIMESTAMP without TZ
- Building consumers that assume `run.started` arrives before `run.completed`
- Making `tool_call.completed` opt-out instead of opt-in
- Returning HTTP 409 for duplicate events
