# RFC-007 — Quality Signal

```
Status: Active
Version: 1.0.0
Authors: [Platform Engineering]
Depends on: RFC-001 through RFC-006
Required before: Phase 2 quality integration, any evaluator agent deployment
```

---

## 1. Context

Cost estimation tells you what a run will cost. Quality signals tell you whether it
was worth it. The two together enable reasoning about cost/quality tradeoffs —
routing toward models that produce the best outcomes per dollar, not simply the
cheapest outputs.

Quality is the most difficult dimension to measure. Unlike cost, it is not directly
observable. It arrives as a collection of imperfect proxy signals — some immediate,
some delayed by days — each capturing a different facet of whether the output was useful.

---

## 2. Scope

- Quality signal type taxonomy with formal definitions
- Signal source classification
- Quality signal schema (extends RFC-002 ART-008)
- Observation window definitions per signal type
- Agent-specific window configuration
- `quality_finalized_at` mechanics
- Absent signal handling
- Evaluator agent contract and lifecycle
- Evaluator versioning requirements
- Multi-evaluator disagreement representation
- Goodhart's Law structural mitigations
- Anti-gaming rules
- Quality signal integration with calibration

---

## 3. Definitions

**Quality signal**: A single, raw, timestamped observation about the usefulness or
correctness of an agent's output.

**Observation window**: The time period after run completion during which a specific
signal type is expected to arrive.

**Quality finalization**: The state a run reaches when all expected observation windows
have closed. Recorded as `quality_finalized_at` on the calibration observation.

**Evaluator agent**: A specialized agent assessing quality of another agent's output.
Subject to the same governance and telemetry requirements as any other agent.

**Evaluator disagreement**: The variance in scores from multiple evaluators on the
same output. High disagreement is itself a signal.

**Ground truth signal**: A signal reflecting real-world outcome rather than proxy
assessment. `downstream_workflow_success` is the primary ground truth signal.

**Absent signal**: A signal expected within its window that did not arrive. Recorded
as a quality signal row with `signal_value: {"present": false}` at window closure.

---

## 4. Quality Signal Taxonomy

### Signal Types by Availability Window

**Group 1 — Immediate (T+0)**

`task_completed` — did the agent finish without failure or abort?  
Source: `system_automatic`. Value: `{"completed": bool, "failure_mode": str|null}`.

`tool_success_rate` — fraction of tool calls that succeeded.  
Source: `system_automatic`. Value: `{"success_count": int, "total_count": int, "rate": float}`.

**Group 2 — Short-term (T+0 to T+2h)**

`output_accepted` — was output used without immediate regeneration?  
Source: `user_implicit`. Value: `{"accepted": bool, "time_to_decision_ms": int}`.

`immediate_revision_requested` — did caller immediately request a revision?  
Source: `user_implicit`. Value: `{"revision_requested": bool, "time_to_revision_ms": int|null}`.

**Group 3 — Medium-term (T+2h to T+48h)**

`revision_count_update` — cumulative revisions requested. Append new value each time.  
Source: `user_implicit`. Value: `{"cumulative_revision_count": int, "updated_at": timestamp}`.

`human_override` — human manually corrected the output.  
Source: `user_explicit` or `downstream_system`. Value: `{"override_count": int, "override_types": [...]}`.

**Group 4 — Long-term (T+24h to T+7d)**

`downstream_workflow_started` — downstream workflow that should consume output actually started.  
Source: `downstream_system`. Value: `{"started": bool, "workflow_id": str|null, "lag_hours": float}`.

`downstream_workflow_success` — downstream workflow succeeded. **The ground truth signal.**  
Source: `downstream_system`. Value: `{"success": bool, "workflow_id": str, "failure_reason": str|null, "lag_hours": float}`.

**Group 5 — On-demand (no fixed window)**

`evaluator_score` — score from an evaluator agent.  
Source: `evaluator_agent`. Value: `{"score": float, "score_dimensions": {...}, "rationale": str, "evaluator_id": str, "evaluator_version": str, "model_version": str}`.

`user_explicit_rating` — explicit 1-5 rating from a human user.  
Source: `user_explicit`. Value: `{"rating": int, "comment": str|null}`.

### Signal Type Reference

| Signal type | Window | Source | Ground truth? | Gameable? |
|---|---|---|---|---|
| `task_completed` | Immediate | System | No | Low |
| `tool_success_rate` | Immediate | System | No | Low |
| `output_accepted` | 2h | User implicit | No | High |
| `immediate_revision_requested` | 2h | User implicit | No | Medium |
| `revision_count_update` | 48h | User implicit | No | Medium |
| `human_override` | 48h | User/System | No | Low |
| `downstream_workflow_started` | 24h | Downstream | No | Low |
| `downstream_workflow_success` | 7d | Downstream | **Yes** | Very low |
| `evaluator_score` | On-demand | Evaluator | No | **High** |
| `user_explicit_rating` | On-demand | User | No | Low |

---

## 5. Signal Source Classification

```sql
CHECK (signal_source IN (
  'system_automatic',
  'user_explicit',
  'user_implicit',
  'downstream_system',
  'evaluator_agent'
))
```

Source is immutable on write. Cannot be reclassified after the fact.

---

## 6. Supplementary Schema

### Observation Window Configuration

```sql
CREATE TABLE cost_intelligence.quality_observation_windows (
  id                  UUID          NOT NULL  DEFAULT gen_random_uuid(),
  agent_definition_id UUID          NULL,   -- NULL = platform default for all agents
  signal_type         TEXT          NOT NULL,
  window_hours        INTEGER       NULL,   -- NULL = on-demand; no window
  is_expected         BOOLEAN       NOT NULL  DEFAULT true,
  created_at          TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id),
  UNIQUE (agent_definition_id, signal_type)
);

-- Platform defaults (agent_definition_id IS NULL)
-- task_completed: 0h expected
-- tool_success_rate: 0h expected
-- output_accepted: 2h expected
-- immediate_revision_requested: 2h expected
-- revision_count_update: 48h expected
-- human_override: 48h NOT expected by default
-- downstream_workflow_started: 24h NOT expected by default
-- downstream_workflow_success: 168h NOT expected by default
-- evaluator_score: null (on-demand) NOT expected by default
-- user_explicit_rating: null (on-demand) NOT expected by default
```

Agents that produce downstream workflow signals register their windows with a specific
`agent_definition_id` row overriding the platform default.

### Evaluator Registry

```sql
CREATE TABLE cost_intelligence.evaluator_registry (
  id                      UUID          NOT NULL  DEFAULT gen_random_uuid(),
  evaluator_id            UUID          NOT NULL  UNIQUE,
  agent_definition_id     UUID          NOT NULL,
  version                 TEXT          NOT NULL,
  status                  TEXT          NOT NULL
    CHECK (status IN ('active','deprecated','retired')),
  model                   TEXT          NOT NULL,
  scoring_dimensions      TEXT[]        NOT NULL,
  score_range_min         NUMERIC(4,2)  NOT NULL  DEFAULT 0.0,
  score_range_max         NUMERIC(4,2)  NOT NULL  DEFAULT 1.0,
  applicable_task_types   TEXT[]        NOT NULL  DEFAULT '{}',
  cross_version_comparable BOOLEAN      NOT NULL  DEFAULT false,
  predecessor_id          UUID          NULL,
  created_at              TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);
```

`cross_version_comparable` defaults to `false`. Two evaluator versions are comparable
only if a formal equivalence study (Pearson r > 0.85) has been conducted and documented.
Without this, scores from different versions must never be averaged or aggregated.

---

## 7. Observation Windows and Finalization

### The Finalization Rule

A run's quality profile is finalized when, for all signal types where `is_expected = true`
AND `window_hours IS NOT NULL`:

```
now() >= run.ended_at + window_hours
```

### quality_finalized_at Clarification

**`quality_finalized_at` does NOT mean "all quality data is complete."**

It means: all REQUIRED window-based quality signals have resolved (arrived or recorded as absent).

Evaluator signals (Group 5) have no observation window. They may continue arriving
indefinitely after `quality_finalized_at` is set. Late-arriving evaluator scores are valid
and incorporated into model performance profiles. They do not retroactively change
`calibration_eligible` status.

### Absent Signal Recording

When a signal window closes and no signal of that type was received:

```python
db.insert("platform.quality_signals", {
    "run_id": run_id,
    "signal_type": signal_type,
    "signal_value": {"present": False},
    "signal_schema_version": "1.0",
    "captured_at": now(),
    "signal_source": "system_automatic",
    "observation_window_closed": True,
    "confidence": 1.0
})
```

Absent signals must be recorded. Silence is not distinguishable from "window not yet closed."

### Quality Finalization Job

Runs every 6 hours. Idempotent. Records absent signals for closed windows.
Sets `quality_finalized_at` and `calibration_eligible = true` on eligible observations.

Checks finalization lag and triggers snapshot re-evaluation flag if lag > 24 hours.
See RFC-006 §9.4 for the re-evaluation rule.

---

## 8. Evaluator Agent Architecture

### The Evaluator Is an Agent

An evaluator agent is a first-class agent. It must have its own `agent_definition_id`,
its own cost tracked in the budget ledger, its own run telemetry, and its own
`model_version_actual` recorded.

**The evaluator's cost must be visible.** An evaluator at $0.10/evaluation on 10,000
runs/day costs $1,000/day. This is a material operational cost attributable to the
tenant whose runs are being evaluated.

### When Evaluators Run

All evaluator runs are async. Never synchronous in the dispatch hot path.

| Trigger | Coverage |
|---|---|
| Stratified sampling | 10% of all runs, stratified by task type and complexity |
| High-stakes threshold | 100% of runs above configured cost threshold |
| Regulated workflow | 100% of regulated tenant tier runs |
| Calibration gap | Monthly sample per bucket with insufficient quality signal |
| On-demand | Explicit operator or customer request |

### Evaluator Output Contract

Evaluator must emit a `quality_signal.received` event and write a quality signal row
referencing the evaluated run via `run_id`. The evaluator's own `run_id` is stored
in `evaluator_run_id` for cost attribution.

### Downstream Signal Authentication

Downstream webhook signals must include:
- `event_id` (UUID): for deduplication using the RFC-003 raw_events pattern
- `tenant_id`: validated against webhook credential
- `signature`: HMAC of payload + timestamp using tenant webhook secret
- `emitted_at`: signals older than 30 minutes are rejected (replay prevention)

Unauthenticated downstream signal endpoints are prohibited. `downstream_workflow_success`
is the highest-trust signal in the system — therefore the highest-value attack surface.

### Downstream Signal Idempotency

Downstream quality signals must follow the same idempotency pattern as all telemetry
events (RFC-003 §6). The ingestion layer deduplicates by `event_id` using
`ON CONFLICT DO NOTHING` on `raw_events`.

---

## 9. Multi-Evaluator Disagreement

Multiple evaluator agents may score the same run independently. Each score is a
separate quality signal row. Scores are never merged at the storage layer.

**Disagreement thresholds** (computed at query time from stddev across scores):

| Score stddev | Interpretation | Action |
|---|---|---|
| < 0.05 | Strong agreement | Use in routing |
| 0.05–0.15 | Moderate agreement | Use with reduced weight |
| > 0.15 | High disagreement | Flag for human review; exclude from routing |
| Only 1 evaluator | No measure | Use with lower confidence |

---

## 10. Goodhart's Law Mitigations

### The Core Rule

**No single quality signal may be the sole criterion for any routing or governance
decision.** Every routing decision involving quality must use at least two independent
quality signals weighted by reliability tier.

### Signal Reliability Hierarchy (for routing weights)

```
Tier 1 (ground truth): downstream_workflow_success — weight: 1.0
Tier 2 (reliable):     human_override — 0.8; revision_count_update — 0.7;
                       downstream_workflow_started — 0.5
Tier 3 (weaker):       output_accepted — 0.4; immediate_revision_requested — 0.3;
                       task_completed — 0.2; tool_success_rate — 0.1
Tier 4 (monitored):    evaluator_score — initial weight 0.5, adjusted by correlation
                       user_explicit_rating — weight 0.6
```

### Evaluator Score Correlation Monitoring

Weekly computation of Pearson correlation between `evaluator_score` and
`downstream_workflow_success` per task type.

```python
if correlation < 0.30:  # critical
    emit_alert("evaluator_correlation_critically_low", ...)
    return 0.1  # near-zero weight

if correlation < 0.50:  # warning
    emit_alert("evaluator_correlation_low", ...)
    return 0.3

return 0.3 + (correlation - 0.5) * 0.6  # interpolate to 0.6 at r=1.0
```

Evaluators with persistent low correlation are deprecated.

### Anti-Gaming Rules

```
RULE QS-AG-1: evaluator_score must never be the sole routing criterion.
RULE QS-AG-2: If evaluator scores increase while downstream_success is flat or
              declining over 3 months, initiate evaluator audit.
RULE QS-AG-3: A model with high evaluator scores but < 30 downstream_success pairs
              is unvalidated for that task type.
RULE QS-AG-4: Evaluator rubrics must not be published to model providers or
              included in agent system prompts.
RULE QS-AG-5: Any change to an evaluator rubric requires a new evaluator version.
```

---

## 11. Composite Quality Views

Composite quality scores are computed at query time, never stored. Raw signals only.

The `run_quality_profiles` view aggregates all quality signals per run using CASE
expressions. This view is the input to RFC-008 routing. See RFC-006 §5.4 for the
quality columns added to calibration buckets.

---

## 12. Operational Invariants

```
INV-QS-001  [Class A] signal_type from approved CHECK constraint.
INV-QS-002  [Class A] captured_at IS NOT NULL TIMESTAMPTZ.
INV-QS-003  [Class A] Append-only; observation_window_closed set once, never reversed.
INV-QS-004  [Class B] quality_finalized_at set from NULL only; never reverted.
INV-QS-005  [Class B] evaluator_score signals include evaluator_id and evaluator_version.
INV-QS-006  [Class C] calibration_eligible = true never coexists with quality_finalized_at IS NULL.
            Alert immediately if violated.
INV-QS-007  [Class C] Quality finalization job completes within 2 hours of scheduled run.
INV-QS-008  [Class C] Evaluator correlation monitored monthly; alert if r < 0.30.
INV-QS-009  [Class D] No composite quality score stored as source-of-truth column anywhere.
            Code review gate: any PR adding a stored quality_score column requires RFC amendment.
```

---

## 13. Dangerous Shortcuts

- Running evaluator synchronously in dispatch hot path — always async
- Comparing evaluator scores across versions without a formal equivalence study
- Using `output_accepted` as primary routing quality signal
- Setting all observation windows to 0 to speed up finalization
- Not recording absent signals — silence is not the same as "window not yet closed"
- Storing a composite quality score column anywhere in the platform
