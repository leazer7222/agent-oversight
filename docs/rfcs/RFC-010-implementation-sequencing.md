# RFC-010 — Implementation Sequencing

```
Status: Active
Version: 1.0.0
Authors: [Platform Engineering]
Depends on: RFC-001 through RFC-009 (all)
Purpose: Capstone. Defines what to build, in what order, with what gates.
Audience: Every engineer on the platform team.
```

---

## 1. Context

Nine RFCs define what this platform is. This RFC defines how to build it. The
distinction matters: a correct architecture built in the wrong order creates the same
operational debt as a flawed architecture.

---

## 2. Pending RFC Amendments

These amendments were committed during design sessions and must be incorporated into
their respective RFCs before implementation begins.

| RFC | Amendment |
|---|---|
| RFC-003 | Add `run.dispatch_failed` event type to taxonomy |
| RFC-005 | Add monitoring query for orchestration runs with `declared_child_runs=0` but observed fanout |
| RFC-006 | Add `requires_re_evaluation BOOLEAN` and `re_evaluation_reason TEXT` to `calibration_snapshots` |
| RFC-006 | Add snapshot re-evaluation trigger when quality finalization lag exceeds 24 hours |
| RFC-007 | Add `quality_finalized_at` clarification: does not imply evaluator completeness |
| RFC-007 | Add downstream signal webhook authentication and idempotency requirements |
| RFC-008 | Add routing engine side-effect contract to §4 |
| RFC-008 | Expand model version drift flag to `provider_execution_drift` with structured payload |
| RFC-009 | Add constitutional CI rule: waivers require RFC amendment, not inline suppression |
| RFC-009 | Add runtime prohibition to schema registry definition |
| RFC-009 | Add three-truth-surface PR template checklist |

**Status**: All amendments have been applied to RFC files in this repository.
This table is retained for audit trail purposes.

**Gate**: All amendments verified applied before any implementation code is written.

---

## 3. Guiding Principles

**Principle 1 — Foundation before calibration.**
Telemetry must be correct, complete, and schema-frozen before calibration begins.

**Principle 2 — Dark launch before dependency.**
Every system that downstream components will depend on must be dark-launched at least
two weeks before those components go live.

**Principle 3 — Immutability before data.**
Append-only enforcement and NOT NULL constraints must be in place before the first
row is written to any artifact table.

**Principle 4 — Monitoring before trust.**
No phase is complete until its invariant monitoring queries are operational and alerting.

**Principle 5 — Freeze before calibration.**
The telemetry schema freeze must be declared before the calibration pipeline runs
for the first time.

**Principle 6 — Defer until the need is proven.**
Every system not required for the current phase is deferred.

---

## 4. The Dependency Graph

```
PHASE 0 — Pre-build (before any Phase 1 code)
  ├── CI enforcement rules active
  ├── PR template with three-truth-surface checklist
  ├── UUID policy documented and linter active
  ├── Schema registry table created
  ├── Append-only RLS policy template written and tested
  └── Correction records table created

PHASE 1 — Foundation
  ├── pricing_table_versions
  │     └── task_taxonomy_versions + task_types (seed data)
  │           └── run_records (task_type_id FK)
  │                 ├── estimate_artifacts
  │                 │     └── recommendation_artifacts (stub)
  │                 │           └── budget_periods + budget_reservations
  │                 └── raw_events → /api/ingest
  │                       └── evaluation_artifacts
  │                             └── Event deduplication
  │                                   └── Class C monitoring invariants
  └── [PHASE 1 GATE]

PHASE 2 — Calibration
  Requires: Phase 1 gate cleared + 4-6 weeks telemetry accumulation
  ├── TELEMETRY SCHEMA FREEZE declared
  ├── calibration_observations + bucket_schema_versions
  │     └── Outlier detection pipeline
  ├── quality_observation_windows + quality_finalization_job
  │     └── Calibration snapshot pipeline (daily batch)
  │           ├── Shadow validation service
  │           └── Promotion + rollback workflow
  └── Drift detection job
        └── [PHASE 2 GATE]

PHASE 3 — Runtime Governance
  Requires: Phase 2 gate cleared + 30 days stable calibration
  ├── create_reservation function (serializable)
  ├── settle_reservation function (idempotent)
  ├── live_spend + token consumption handler
  ├── abort_requests + abort coordinator
  ├── Cleanup job (full implementation)
  └── Hard limit enforcement + graceful abort
        └── [PHASE 3 GATE]

PHASE 4 — Model Intelligence
  Requires: Phase 3 gate cleared + 90 days calibration data
            + quality signals from ≥ 3 task types with ≥ 30 finalized observations
  ├── profile_snapshots + model_performance_profiles
  │     └── Profile computation pipeline
  ├── routing_policies (per-tenant)
  ├── Routing engine service (separate service deployment)
  │     ├── Budget eligibility filter
  │     ├── Quality floor filter
  │     └── All six routing modes
  └── Full recommendation artifact population
        └── [PHASE 4 GATE]
```

---

## 5. Phase 0 — Pre-Build

Must exist before any implementation code is written.

**CI enforcement active:**
- TIMESTAMP without TZ → hard failure
- UUID v1 usage → hard failure
- ON DELETE CASCADE on Class I tables → hard failure
- Strict deserializer on platform schemas → hard failure
- Enum switch without default → hard failure
- Constitutional waiver rule documented

**Database foundations:**
```sql
CREATE TABLE platform.schema_registry (...);
CREATE TABLE platform.correction_records (...);
CREATE OR REPLACE FUNCTION platform.apply_append_only_rls(table_name TEXT) ...
```

**PR template deployed** with three-truth-surface checklist (RFC-009).

**Team alignment**: every engineer has read RFC-001 through RFC-009.

---

## 6. Phase 1 — Foundation

**Goal**: Every run has an estimate artifact before it starts and an evaluation
artifact after it completes.

**Duration**: 6–8 weeks.

### Build Order (groups may build in parallel; groups depend on predecessors)

**Group 1** (no dependencies):
- `pricing_table_versions` + seed
- `task_taxonomy_versions` + `task_types` + seed (8 types)
- `raw_events` + `/api/ingest`

**Group 2** (depends on Group 1):
- `run_records` (task_type_id FK)

**Group 3** (depends on Group 2):
- `estimate_artifacts`
- Deterministic estimation service
- `recommendation_artifacts` (stub mode)

**Group 4** (depends on Group 3):
- `budget_periods` + `budget_reservations`
- Dispatch coordinator

**Group 5** (depends on Group 3):
- `evaluation_artifacts`
- Evaluation pipeline (idempotent)
- Event deduplication

**Group 6** (depends on Groups 4 and 5):
- Class C monitoring invariants
- Invariant monitoring dashboard

### Dark Launch Sequence

```
T-14 days: Dark launch /api/ingest
  Validate: schema compliance, volume, deduplication.

T-7 days:  Dark launch evaluation pipeline
  Validate: 100% coverage, idempotency.

T-7 days:  Dark launch recommendation artifact stub writer
  Validate: every run request produces a recommendation artifact row.

T-0: Phase 1 launch
```

### Phase 1 Gate Checklist

- [ ] 100% of run requests produce an `estimate_artifact` before `run.started`
- [ ] 100% of terminal runs produce an `evaluation_artifact` within 10 minutes
- [ ] 100% of run requests produce a `recommendation_artifact` (passthrough mode)
- [ ] Zero `estimate_artifacts` with `estimation_features_snapshot IS NULL`
- [ ] `pg_stat_user_tables.n_tup_upd = 0` for all Class I tables — 72 hours verified
- [ ] Correction records pattern used for all corrections; zero direct UPDATEs
- [ ] No TIMESTAMP (without TZ) columns in database
- [ ] All artifact tables have append-only RLS policies
- [ ] All FK constraints use `ON DELETE RESTRICT`
- [ ] `task_type_id` IS NOT NULL on all `run_records`
- [ ] `estimation_features_echo` mismatch rate = 0
- [ ] `model_version_actual` populated on all `run.completed` events
- [ ] All Class C monitoring queries return results on every execution (never zero rows)
- [ ] All four degradation ladder tiers tested under simulated failures
- [ ] Stable for minimum 14 days with no Class A invariant violations

---

## 7. Telemetry Schema Freeze

**Declared at the start of Phase 2, before the calibration pipeline runs once.**

### Frozen Fields

Changes to any of the following require a bucket schema version bump and a historical
observation re-bucketing plan:

```
run_records:
  task_type_id, task_complexity_bucket, task_classifier_version

estimate_artifacts:
  estimation_features_snapshot (including feature_schema_version)
  provider, model, pricing_table_version_id, calibration_version_id

evaluation_artifacts:
  actual_cost_usd, all actual_cost_{type}_usd fields
  tokens_in_actual, tokens_out_actual, tokens_cached_actual, tokens_reasoning_actual
  wall_clock_ms, time_to_first_token_ms
  retry_count, failure_mode, actual_tool_calls

calibration_observations (all bucket dimension fields):
  provider, model_family, tool_profile, context_size_bucket,
  task_type_code, task_complexity_bucket
```

### Freeze Date Record

```sql
INSERT INTO platform.schema_registry (
  artifact_type, field_name, lifecycle_status, schema_version,
  deprecation_reason, rfc_reference
) VALUES (
  'calibration_observations', 'ALL_CALIBRATION_SENSITIVE_FIELDS', 'active', '1.0.0',
  'TELEMETRY SCHEMA FREEZE — declared at Phase 2 start. Changes require bucket schema
   version bump. See RFC-006.',
  'RFC-010'
);
```

### What Frozen Means

A calibration pipeline startup check verifies the freeze is declared. If the freeze
record does not exist in the schema registry, the pipeline aborts with a clear error.

---

## 8. Phase 2 — Calibration

**Goal**: Estimates improve automatically over time. Drift is detected.

**Requires**: Phase 1 gate cleared + minimum 4-6 weeks telemetry accumulation.

**Duration**: 6–10 weeks to first promoted snapshot.

### Build Order

**Group 1**: Declare schema freeze. `calibration_observations` + bucket assignment algorithm.
`bucket_schema_versions` + seed.

**Group 2**: `quality_observation_windows` + seed. Quality finalization job.
Outlier detection service + review queue.

**Group 3**: Calibration snapshot pipeline (daily batch). Multiplier computation.

**Group 4**: Shadow validation service. Promotion workflow. Rollback mechanics.
`requires_re_evaluation` trigger.

**Group 5**: Drift detection job. Frozen bucket handling.

### Dark Launch Sequence for Phase 2

```
T-14 days: Dark launch calibration observation ingestion.
           Validate: count matches evaluation artifact count;
           bucket key construction is deterministic.

T-7 days:  Dark launch quality finalization job.
           Validate: quality_finalized_at set correctly;
           absent signals recorded; observation_window_closed flags correct.

T-0: First calibration snapshot pipeline run.
     Shadow validate before any promotion. Human review before first promotion.
```

### Phase 2 Gate Checklist

- [ ] Telemetry schema freeze formally declared in schema registry
- [ ] At least one calibration snapshot promoted through full shadow validation
- [ ] Rollback tested: rolled back to predecessor and estimates reverted
- [ ] Drift detection job operational with correct alerts in staging
- [ ] Quality finalization job: `quality_finalized_at` set within 7 days for ≥99% of eligible observations
- [ ] Observation ingestion coverage: every evaluation_artifact produces a calibration observation within 1 hour
- [ ] Outlier detection operational; review queue drained at least once
- [ ] Pricing table change → calibration review trigger wired and tested
- [ ] No multiplier outside [0.3, 5.0] in any promoted snapshot
- [ ] `calibration_source` and `calibration_sample_tier` correctly populated on all estimates
- [ ] Stable for minimum 30 days with at least one full calibration cycle

---

## 9. Phase 3 — Runtime Governance

**Goal**: Hard budget limits enforced.

**Requires**: Phase 2 gate cleared + 30 days stable calibration.

**Duration**: 8–12 weeks to full enforcement mode.

### Build Order

**Group 1**: `create_reservation` function (serializable isolation, optimistic locking).
`settle_reservation` function (idempotent). Budget pre-check API. Cleanup job (full).

**Group 2**: `live_spend` table. Token consumption handler. Threshold events.

**Group 3**: `abort_requests` table. Graceful abort coordinator. Grace window timer.

**Group 4**: Force termination path. Provisional settlement for force-killed runs.
Provider outage batch abort. Timeout state transitions.

**Group 5**: Budget period rollover handling. Parent/child reservation mechanics.
`budget_corrections` table.

### Staged Rollout

```
Week 1:   Sandbox tenants. Permissive fallback. Observe.
Week 3:   Production standard tenants. p95 reservations. Soft limits only.
Week 6:   Hard limits for production standard.
          Monitor overrun rate. If > 2%, pause and investigate.
Week 10:  Regulated tenants. Hard limits + fail-closed fallback.
          Requires customer communication and SLA review.
```

### Phase 3 Gate Checklist

- [ ] Concurrent reservation stress test: 100 simultaneous requests against $5 budget, never exceeds $5 — 1,000 iterations
- [ ] Settlement idempotency: settling twice = same result as settling once
- [ ] Cleanup job idempotent: running twice in succession = same result as once
- [ ] Graceful abort tested end-to-end: agent receives signal, produces partial result
- [ ] Force kill path tested: agent ignoring abort is terminated after grace window
- [ ] Budget period rollover verified: reservations settle against originating period
- [ ] Parent/child reservation verified: parent covers declared children; undeclared trigger spend.warning
- [ ] Provider outage simulation: all active reservations → provisional_settlement correctly
- [ ] Overrun rate < 2% for 30 consecutive days
- [ ] `budget_available_at_dispatch` populated on every reservation
- [ ] INV-RG-001 through INV-RG-010 verified in production for 30 days with zero violations

---

## 10. Phase 4 — Model Intelligence

**Goal**: Routing engine selects models based on telemetry-derived performance profiles.

**Requires**: Phase 3 gate cleared + 90 days calibration data + quality signals from
≥ 3 task types with ≥ 30 finalized observations each.

**Duration**: 12–16 weeks.

### Build Order

**Group 1**: `profile_snapshots` + `model_performance_profiles`. Profile computation pipeline.

**Group 2**: `routing_policies` (per-tenant). Default policy seed per tier.

**Group 3**: Routing engine service (separate service deployment):
- Budget eligibility filter
- Quality floor filter
- All six routing modes
- Routing engine side-effect contract enforcement
- Fallback ladder

**Group 4**: Full recommendation artifact population (all candidates including eliminated).
`provider_execution_drift` detection.

**Group 5**: Quality-weighted calibration integration. Evaluator correlation monitoring.

### Dark Launch Sequence for Phase 4

```
T-14 days: Dark launch profile computation.
           Validate: coverage across all active models and task types;
           cold-start models correctly identified.

T-7 days:  Routing engine in shadow mode.
           Compute recommendations silently; compare to actual model used.
           Measure: how often would routing choose differently?

T-0: Go live for sandbox → production standard → regulated (staged).
```

### Phase 4 Gate Checklist

- [ ] Routing engine has zero write access to any table except `recommendation_artifacts` — verified by role grants
- [ ] All six routing modes tested with adversarial inputs
- [ ] `candidates_evaluated` populated for 100% of non-passthrough recommendations including eliminated candidates
- [ ] Cold-start model selection blocked in `highest_quality` and `regulated` — verified by unit tests
- [ ] Routing engine fallback ladder tested: all four levels activated
- [ ] `provider_execution_drift` detection tested with simulated version mismatch
- [ ] Evaluator correlation monitoring operational: alert fires when r < 0.30
- [ ] `routing_confidence` correctly populated in all scenarios
- [ ] Live for 60 days with no semantic boundary erosion incidents

---

## 11. What Must NOT Be Built in Each Phase

### Deferred from Phase 1

- Calibration pipeline, ML-based estimation, LLM evaluator agent, hard budget limits,
  model routing, campaign forecasting, Monte Carlo simulation, cross-tenant calibration,
  custom retention/archival

### Deferred from Phase 2

- Hard limit enforcement, routing engine, per-tenant model profiles, campaign forecasting

### Deferred from Phase 3

- Full routing engine, quality-weighted routing, hierarchical tenant calibration

### Deferred from Phase 4 (indefinitely)

- Per-tenant model profiles (most tenants will never have sufficient volume)
- Execution replay (LLM outputs are non-deterministic — impossible by design)
- Automatic task type inference from prompt content

---

## 12. Operational Maturity Stages

| Stage | After | Capabilities |
|---|---|---|
| **Observable** | Phase 1 gate | Estimate, evaluate, observe. Accuracy visible but not improving. |
| **Calibrated** | Phase 2 gate + 30 days stable | Estimates improve over time. Drift detected. |
| **Governed** | Phase 3 gate + 30 days stable | Hard limits enforced. Financially trustworthy. |
| **Intelligent** | Phase 4 gate + 60 days | Data-driven model selection. Every decision explainable. |
| **Auditable** | Ongoing discipline | Full compliance posture. Every decision reconstructable from artifacts. |

**Auditable is not a phase to complete. It is a discipline to maintain.**

---

## 13. Semantic Boundary Erosion Monitoring

From RFC-009 OQ-3 and RFC-008 OQ-3. These six patterns are the primary long-term risk.
Monitoring begins at Phase 4.

### Pattern 1: Runtime services introspecting governance metadata

```sql
SELECT count FROM pg_stat_statements
WHERE query ILIKE '%platform.schema_registry%' AND calls > 0;
-- Expected: 0 for all non-CI, non-monitoring callers
```

### Pattern 2: Routing engine mutating execution state

```sql
SELECT grantee, table_schema, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'routing_service_role'
  AND privilege_type IN ('INSERT','UPDATE','DELETE')
  AND table_name != 'recommendation_artifacts';
-- Expected: 0 rows
```

### Pattern 3: Execution truth in decision artifacts

```sql
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'cost_intelligence'
  AND table_name = 'estimate_artifacts'
  AND column_name IN (
    'actual_cost_usd','wall_clock_ms','tokens_in_actual',
    'tokens_out_actual','model_version_actual'
  );
-- Expected: 0 rows
```

### Pattern 4: Calibration rewriting historical estimates

```sql
SELECT n_tup_upd FROM pg_stat_user_tables
WHERE schemaname = 'cost_intelligence' AND relname = 'estimate_artifacts';
-- Expected: 0, always
```

### Patterns 5 and 6

Pattern 5 (schema registry queried at runtime): covered by Pattern 1 plus API latency
monitoring for routes referencing schema registry.

Pattern 6 (evaluator scores treated as ground truth): reviewed manually weekly via
routing policy audit showing multi-signal quality composition.

These six queries run weekly. Any non-zero result for patterns 1–4 is an immediate incident.

---

## 14. Operational Invariants

```
INV-SEQ-001  [Class D] No Phase N+1 work begins until Phase N gate checklist fully verified.
             Architecture review sign-off required.

INV-SEQ-002  [Class D] Telemetry schema freeze declared before calibration pipeline
             runs for the first time.
             Schema registry entry created; pipeline startup check enforces this.

INV-SEQ-003  [Class D] All RFC amendments from §2 applied before any implementation
             code is written.

INV-SEQ-004  [Class C] Semantic boundary erosion monitoring queries run weekly from
             Phase 4 onward. Review must complete within 8 days of scheduled run.

INV-SEQ-005  [Class D] Phase 3 hard limits not enabled for regulated tenants until
             30 days after production standard, and only after customer communication.
```

---

## 15. Team Sequencing and Expertise Requirements

| Phase | New skills required | Minimum team |
|---|---|---|
| Phase 1 | PostgreSQL, event-driven architecture | 2–3 engineers |
| Phase 2 | Statistical computing (EMA, percentiles, z-scores, MAPE) | 3–4 engineers |
| Phase 3 | Financial systems, serializable transactions, concurrency patterns | 3–4 engineers |
| Phase 4 | Service architecture, scoring functions, full Phases 1–3 stack | 4–5 engineers |

**Phase 2 critical requirement**: at least one person who can reason about calibration
correctness under sparse data conditions. Platform engineering alone is insufficient.

**Phase 3 critical requirement**: financial correctness takes precedence over performance
optimization. Any "optimization" that weakens consistency guarantees must be escalated.

**Phase 4 critical requirement**: at least one engineer who has read and internalized
RFC-008 §10 (Routing Provenance Gaps) before writing any routing engine code.

---

## 16. The Capstone Synthesis

Ten RFCs. The platform that emerges has three properties that most adaptive AI systems
sacrifice:

**Replayability**: every decision can be reconstructed from immutable artifacts.
"What would the estimator have predicted six months ago, with last year's calibration?"
is a query, not a guess.

**Explainability**: every routing, estimation, and governance decision has a
human-readable explanation derivable from its artifact alone. No join to mutable state.

**Evolvability**: the schema evolution rules, the three-truth-surface protection, and
the versioning discipline ensure that the system can change without corrupting its
historical record.

These properties are not automatic. They are the result of every constraint in every
RFC, applied consistently from the first migration to the last Phase 4 deployment.

The central risk is that they erode gradually — one inline suppression, one
cross-surface field, one runtime registry query — until the properties are gone.

**The defenses are in place. Maintaining them is the work.**
