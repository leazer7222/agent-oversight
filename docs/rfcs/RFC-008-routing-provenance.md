# RFC-008 — Routing Provenance

```
Status: Active
Version: 1.0.0
Authors: [Platform Engineering]
Depends on: RFC-001 through RFC-007
Required before: Model Intelligence domain implementation (Phase 4)
Informational before: Phase 1–3 (recommendation artifact runs in passthrough mode)
```

---

## 1. Context

Every run on the platform uses a model. In Phase 1–3, the caller declares which model
to use, or a tenant default applies. The recommendation artifact records this as a
passthrough — no routing engine was involved.

In Phase 4, the Model Intelligence domain replaces the passthrough with an active
routing engine: it evaluates candidate models against telemetry-derived performance
profiles and selects the model most appropriate for the run's task, budget, and quality
requirements.

This RFC defines the complete routing provenance system: model performance profiles,
the routing lifecycle, all routing modes, the filtering pipeline, cold-start handling,
the recommendation artifact contract, and the audit guarantees that make every routing
decision explainable.

The routing engine does not exist yet. This RFC designs the contracts it must satisfy
so that Phase 1–3 artifacts remain compatible when Phase 4 is built.

---

## 2. Precision Definitions

**Model**: A specific deployable AI model identified by family and version.
`claude-sonnet-4-6` is a family. `claude-sonnet-4-6-20251001` is a model.

**Candidate model**: A model being evaluated for selection. Eliminated candidates
are still candidates — they were considered and rejected.

**Eligible model**: A candidate that has passed all pre-scoring filters.

**Routing mode**: A formal contract specifying the objective function used to select
among eligible models. Not a preference or hint — a binding specification.

**Quality score**: A derived, query-time composite of quality signals. Not stored.
Computed from the model performance profile using RFC-007 signal weights.

**Model performance profile**: A versioned, immutable snapshot of telemetry-derived
performance characteristics for a model-task_type-complexity combination.

**Routing confidence**: Reliability of the routing decision based on data volume.
Not a measure of output quality.

**Cold-start model**: A model with fewer than 30 telemetry observations for the given
task type and complexity bucket.

**Passthrough mode**: Phase 1–3 routing mode. No scoring. Caller-declared or
tenant-default model accepted. Recommendation artifact records the declaration.

**Budget eligible**: A model whose p95 cost estimate does not exceed remaining budget
or per-run cost ceiling.

**Quality floor**: Minimum acceptable quality score. Default: 0.0 in Phase 1.

**Orchestration effectiveness**: A derived, query-time metric for orchestration agents
computed from child run completion rates, retry rates, and workflow outcomes. Distinct
from child quality scores. Never stored. Never equal to avg(child_quality_scores).

---

## 3. Model Performance Profile

### Profile Snapshot Schema

```sql
CREATE TABLE model_intelligence.profile_snapshots (
  id              UUID          NOT NULL  DEFAULT gen_random_uuid(),
  version         TEXT          NOT NULL  UNIQUE,
  status          TEXT          NOT NULL
    CHECK (status IN ('draft','active','retired')),
  calibration_snapshot_id UUID  NOT NULL
    FK → cost_intelligence.calibration_snapshots.id,
  computed_at     TIMESTAMPTZ   NOT NULL,
  promoted_at     TIMESTAMPTZ,
  retired_at      TIMESTAMPTZ,
  created_at      TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);

CREATE UNIQUE INDEX uq_one_active_profile_snapshot
  ON model_intelligence.profile_snapshots (status)
  WHERE status = 'active';
```

### Model Performance Profile Schema

```sql
CREATE TABLE model_intelligence.model_performance_profiles (
  id                        UUID          NOT NULL  DEFAULT gen_random_uuid(),
  snapshot_id               UUID          NOT NULL
    FK → model_intelligence.profile_snapshots.id,
  provider                  TEXT          NOT NULL,
  model_family              TEXT          NOT NULL,
  task_type_code            TEXT          NOT NULL,
  task_complexity_bucket    TEXT          NOT NULL
    CHECK (task_complexity_bucket IN ('simple','medium','complex')),
  cost_p50_usd              NUMERIC(10,6) NULL,
  cost_p75_usd              NUMERIC(10,6) NULL,
  cost_p95_usd              NUMERIC(10,6) NULL,
  cost_multiplier           NUMERIC(8,4)  NULL,
  latency_p50_ms            INTEGER       NULL,
  latency_p95_ms            INTEGER       NULL,
  time_to_first_token_p50_ms INTEGER      NULL,
  downstream_success_rate   NUMERIC(4,3)  NULL,
  evaluator_score_mean      NUMERIC(4,3)  NULL,
  evaluator_score_stddev    NUMERIC(4,3)  NULL,
  revision_rate             NUMERIC(4,3)  NULL,
  task_completion_rate      NUMERIC(4,3)  NULL,
  retry_rate                NUMERIC(4,3)  NULL,
  failure_rate              NUMERIC(4,3)  NULL,
  abort_rate                NUMERIC(4,3)  NULL,
  cost_observation_count    INTEGER       NOT NULL  DEFAULT 0,
  quality_observation_count INTEGER       NOT NULL  DEFAULT 0,
  tenant_count              INTEGER       NOT NULL  DEFAULT 0,
  is_cold_start             BOOLEAN       NOT NULL  DEFAULT false,
  cold_start_reason         TEXT          NULL,
  prior_quality_score       NUMERIC(4,3)  NULL,
  prior_source              TEXT          NULL,
  created_at                TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id),
  UNIQUE (snapshot_id, provider, model_family, task_type_code, task_complexity_bucket)
);
-- Append-only enforcement
```

### Cold-Start Priors

```python
COLD_START_QUALITY_PRIORS = {
    "anthropic": 0.75,
    "openai":    0.75,
    "google":    0.70,
    "other":     0.60,
}
```

Fallback order: sibling model profile → adjacent task type profile → provider prior.

---

## 4. Routing Lifecycle

### Dispatch Sequence

```
[1] Budget eligibility computed (Runtime Governance)
[2] Quality floor applied (Model Intelligence)
[3] Tier restrictions applied (Model Intelligence)
[4] Routing engine scores eligible candidates (Model Intelligence)
[5] Recommendation artifact written (immutable)
[6] Cost Intelligence estimates for selected model
[7] Oversight policy check
[8] Budget reservation (Runtime Governance)
[9] Agent executes with selected model
```

The routing engine never sees the budget reservation system. It receives the filtered
candidate set and returns a ranked list. Cost estimation is downstream of routing.

### Budget Eligibility Filter (Runtime Governance)

Eliminates candidates where:
- `cost_p95_usd > available_budget`
- `cost_p95_usd > tenant_per_run_ceiling`
- No cost profile available and no provider average for cold-start estimate

All eliminated candidates recorded with `elimination_reason`.

### Quality Floor Filter (Model Intelligence)

Eliminates candidates below `quality_floor` (0.0 = no floor enforced).
Cold-start models use `prior_quality_score`.

### No Eligible Models

If all candidates are eliminated, the run is rejected with
`rejection_reason: 'no_eligible_models'`. Not a budget exceeded error. Not a
dispatch failed error. A distinct rejection type.

### Routing Engine Side-Effect Contract

**The routing engine is side-effect free except for one operation: writing the
recommendation artifact.**

Prohibited side effects:
- No budget reservation writes
- No governance state mutations
- No telemetry record mutations
- No calibration state changes
- No run lifecycle transitions

Permitted operations:
- Read model performance profiles
- Read routing policy
- Read budget eligibility (read-only snapshot)
- Score and rank candidates
- Write recommendation artifact

This constraint is enforced at the service boundary. The routing engine service role
has INSERT on `recommendation_artifacts` and SELECT on profile/policy tables only.
No other write privileges are granted.

---

## 5. Routing Modes

### `passthrough`

No routing engine active. Model is caller-declared or tenant-default.
No scoring. No candidates evaluated. Artifact records the declaration.
Used in Phase 1–3 and as fallback level 3–4.

### `cheapest_acceptable`

From the eligible set, select the model with the lowest `cost_p50_usd`.
Ties (within $0.001) broken by higher `downstream_success_rate`.
Cold-start models included with prior cost estimate. `routing_confidence: low`
when cold-start model is selected.

### `balanced`

Weighted composite score across cost, quality, latency, and reliability.

Default weights: `{cost: 0.30, quality: 0.40, latency: 0.20, reliability: 0.10}`.

Configurable per tenant. Weight changes require a routing policy version bump.
Cold-start models receive a 15% penalty on composite score.

### `highest_quality`

Maximize quality score subject to `max_cost_premium` cap (default: 2.0×
cheapest eligible model's `cost_p50_usd`).
**Cold-start models excluded.** An unvalidated model must not be selected when
quality maximization is the objective.

### `fastest`

Minimize `time_to_first_token_p50_ms`. Quality floor still applies.

### `regulated`

Approved model whitelist only. Reject if no approved model passes all filters.
**Cold-start models excluded.** No unvalidated models for regulated workflows.

### `experimental`

Routes to beta/evaluation models. Not available to regulated tenant tiers.
Requires explicit opt-in. Records `routing_mode: experimental` for analysis.

---

## 6. Recommendation Artifact — Operational Contract

### Required Embedded Fields

All of the following must be embedded at write time. References to mutable external
records are not sufficient.

```json
{
  "recommendation_id": "uuid",
  "run_request_id": "uuid",
  "tenant_id": "uuid",
  "schema_version": "1.0.0",
  "routing_mode": "balanced",
  "model_selection_mode": "router_recommended",
  "selected_model": "claude-sonnet-4-6",
  "selected_provider": "anthropic",
  "selection_reason": "highest_composite_score_in_balanced_mode",
  "routing_policy_version": "routing-policy-v4",
  "scoring_function_version": "scorer-v2",
  "profile_snapshot_version": "profiles-v2026-05-18-01",
  "task_type_code": "info_retrieval",
  "task_complexity_bucket": "medium",
  "budget_eligible_models": ["claude-sonnet-4-6", "gpt-4o"],
  "quality_floor_applied": 0.75,
  "max_cost_premium_applied": null,
  "budget_available_at_routing": 8.42,
  "cold_start_model_selected": false,
  "routing_confidence": "high",
  "candidates_evaluated": [...],
  "created_at": "2026-05-18T14:22:58.001Z"
}
```

`profile_snapshot_version` — mandatory. Without it, routing decisions cannot be replayed.
`routing_policy_version` — mandatory. Records which weights, floors, and restrictions applied.
`budget_available_at_routing` — mandatory in all modes including passthrough.

### The `candidates_evaluated` Array — Mandatory Completeness

Every candidate — including eliminated — must appear.

```json
[
  {
    "model": "claude-sonnet-4-6",
    "provider": "anthropic",
    "model_family": "claude-sonnet",
    "is_cold_start": false,
    "eliminated": false,
    "elimination_reason": null,
    "scores": {
      "cost_score": 0.85, "quality_score": 0.89,
      "latency_score": 0.94, "reliability_score": 0.96,
      "composite_score": 0.91
    },
    "profile_data": {
      "cost_p50_usd": 0.42, "cost_p95_usd": 1.10,
      "latency_p50_ms": 38000,
      "downstream_success_rate": 0.87,
      "evaluator_score_mean": 0.88,
      "quality_observation_count": 1420,
      "cost_observation_count": 2104
    },
    "selected": true,
    "not_selected_reason": null
  },
  {
    "model": "gpt-5.5-thinking",
    "provider": "openai",
    "is_cold_start": false,
    "eliminated": true,
    "elimination_reason": "exceeds_per_run_ceiling",
    "elimination_detail": {
      "estimated_p95_usd": 3.20,
      "per_run_ceiling_usd": 2.00
    },
    "scores": null,
    "profile_data": null,
    "selected": false,
    "not_selected_reason": null
  }
]
```

### The Explainability Requirement

Every recommendation artifact must be explainable in plain language from its own
fields alone. No join to model profile tables, calibration tables, or policy tables.

Test: from a single `recommendation_artifacts` row, can you answer:
- Why was this model selected? (selection_reason + scores in candidates_evaluated)
- Why wasn't another model selected? (not_selected_reason or elimination_reason)
- Which models were considered and eliminated? (eliminated candidates in array)
- What constraints were applied? (budget_eligible_models, quality_floor_applied)
- What performance data drove scores? (profile_data embedded per candidate)

If any of these cannot be answered from the artifact, the artifact is incomplete.

---

## 7. Routing Policy Versioning

### What Requires a New Policy Version

- Default routing mode change
- Balanced mode weight changes
- Quality floor threshold change
- Per-run cost ceiling change
- Approved model whitelist change
- Maximum cost premium change
- Cold-start inclusion/exclusion rule changes

```sql
CREATE TABLE model_intelligence.routing_policies (
  id                    UUID          NOT NULL  DEFAULT gen_random_uuid(),
  tenant_id             UUID          NOT NULL,
  version               TEXT          NOT NULL,
  status                TEXT          NOT NULL
    CHECK (status IN ('draft','active','retired')),
  default_routing_mode  TEXT          NOT NULL,
  quality_floor         NUMERIC(4,3)  NOT NULL  DEFAULT 0.0,
  per_run_ceiling_usd   NUMERIC(10,4) NULL,
  balanced_weights      JSONB         NOT NULL,
  max_cost_premium      NUMERIC(4,2)  NOT NULL  DEFAULT 2.0,
  approved_models       TEXT[]        NOT NULL  DEFAULT '{}',
  cold_start_eligible_modes TEXT[]    NOT NULL
    DEFAULT '{"cheapest_acceptable","balanced","fastest"}',
  created_at            TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  activated_at          TIMESTAMPTZ,
  retired_at            TIMESTAMPTZ,
  PRIMARY KEY (id),
  UNIQUE (tenant_id, version)
);

CREATE UNIQUE INDEX uq_one_active_policy_per_tenant
  ON model_intelligence.routing_policies (tenant_id, status)
  WHERE status = 'active';
-- Append-only
```

---

## 8. Provider Execution Drift Detection

When the actual model version that executed differs from the model family selected by
routing, this is recorded on the evaluation artifact as `provider_execution_drift`:

```json
"provider_execution_drift": {
  "detected": true,
  "drift_type": "silent_provider_upgrade",
  "selected_model_family": "claude-sonnet-4-6",
  "profile_model_version": "20251001",
  "actual_model_version": "20251115",
  "provider": "anthropic",
  "detected_at": "2026-05-18T14:23:43.220Z"
}
```

`drift_type` CHECK:
```sql
CHECK (drift_type IN (
  'silent_provider_upgrade','tokenizer_change','latency_tier_change',
  'reasoning_mode_change','safety_filter_change','unknown'
))
```

The recommendation artifact is never corrected for provider drift. It records
decision-time belief state. Execution truth lives in the run record and evaluation
artifact. These are separate truth surfaces and must remain so.

---

## 9. Fallback Routing

```
Level 1: Full routing engine (preferred)
  ↓ [engine timeout or error]
Level 2: Cached routing recommendation (max age: 5 minutes; tier: 'cached_routing')
  ↓ [no cache entry]
Level 3: Tenant default model (model_selection_mode: 'tenant_default')
  ↓ [no tenant default configured]
Level 4: Platform default model (model_selection_mode: 'platform_default')
```

At every level, a recommendation artifact is written with `routing_confidence: very_low`
for levels 2–4.

---

## 10. Routing Provenance Gaps — Catastrophic Scenarios

| Gap | What becomes permanently unanswerable |
|---|---|
| Eliminated candidates missing from `candidates_evaluated` | "Why wasn't model X considered?" |
| `profile_snapshot_version` absent | Scores cannot be interpreted or replayed |
| `routing_policy_version` absent | Which weights/floors were in effect |
| Per-candidate scores missing | Why winner outscored alternatives |
| `budget_available_at_routing` absent | Whether approval was correct or a race condition |

---

## 11. Operational Invariants

```
INV-RP-001  [Class A] One active profile snapshot at any time.
INV-RP-002  [Class A] One active routing policy per tenant at any time.
INV-RP-003  [Class A] One recommendation_artifact per run_request_id.
INV-RP-004  [Class B] In active routing modes, candidates_evaluated is non-empty
            and includes every considered model (eliminated or scored).
INV-RP-005  [Class B] profile_snapshot_version populated on every active-mode artifact.
INV-RP-006  [Class C] No active-mode artifact has empty candidates_evaluated array.
INV-RP-007  [Class C] Profile snapshot age ≤ 7 days in production.
INV-RP-008  [Class D] Cold-start model selection blocked in highest_quality and regulated modes.
            Verified by routing engine unit tests.
```
