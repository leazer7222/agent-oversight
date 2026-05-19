# RFC-004 — Runtime Governance

```
Status: Active
Version: 1.0.0
Authors: [Platform Engineering]
Depends on: RFC-001, RFC-002, RFC-003
Required before: Phase 3 implementation, any budget enforcement code
```

---

## 1. Context

Runtime Governance is the domain responsible for financial enforcement during agent
execution. It owns three things: the budget state that determines whether a run may
proceed, the live spend tracking that monitors cost during execution, and the abort
coordination that enforces hard limits mid-execution.

---

## 2. Scope

- Budget period model and balance accounting
- Reservation lifecycle: all states and transitions
- Settlement lifecycle
- Live spend tracking
- Hard limit enforcement
- Graceful abort protocol and state machine
- Force termination protocol
- Timeout state semantics
- Parent/child reservation mechanics
- Fallback posture when governance infrastructure is degraded
- Budget correction mechanics
- Cleanup job specification
- Operational invariants
- Race condition catalog and mitigations

---

## 3. Definitions

**Budget period**: Time-bounded budget allocation for a tenant, optionally scoped to
a cost center.

**Reservation**: Pre-run budget hold. Immutable after creation (financial fields).

**Settlement**: Final cost accounting. Separate record from the reservation.

**Live spend**: Running actual cost total during execution. Mutable operational state.

**Hard limit**: Maximum spend for a run. Abort is triggered when live spend reaches it.

**Grace window**: Period after abort signal during which agent may complete current
work before force termination.

**Cleanup job**: Background process that identifies and resolves unsettled reservations.

**Budget correction**: Post-hoc billing adjustment. Append-only record.

---

## 4. Budget Period Model

```sql
CREATE TABLE runtime_governance.budget_periods (
  id              UUID          NOT NULL  DEFAULT gen_random_uuid(),
  tenant_id       UUID          NOT NULL,
  cost_center_id  UUID,
  period_key      TEXT          NOT NULL,  -- "2026-05"
  period_type     TEXT          NOT NULL  CHECK (period_type IN (
                                  'monthly','quarterly','annual','custom')),
  budget_usd      NUMERIC(12,4) NOT NULL  CHECK (budget_usd > 0),
  reserved_usd    NUMERIC(12,4) NOT NULL  DEFAULT 0 CHECK (reserved_usd >= 0),
  consumed_usd    NUMERIC(12,4) NOT NULL  DEFAULT 0 CHECK (consumed_usd >= 0),
  version         INTEGER       NOT NULL  DEFAULT 0,
  created_at      TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  updated_at      TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id),
  UNIQUE (tenant_id, cost_center_id, period_key),
  CONSTRAINT budget_not_exceeded
    CHECK (reserved_usd + consumed_usd <= budget_usd)
);
```

Available budget query (always includes corrections):

```sql
SELECT
  bp.budget_usd - bp.reserved_usd - bp.consumed_usd
  + COALESCE(SUM(bc.correction_amount_usd), 0) AS available_usd
FROM runtime_governance.budget_periods bp
LEFT JOIN runtime_governance.budget_corrections bc
  ON bc.tenant_id = bp.tenant_id AND bc.period_key = bp.period_key
WHERE bp.tenant_id = $tenant_id AND bp.period_key = $period_key
GROUP BY bp.budget_usd, bp.reserved_usd, bp.consumed_usd;
```

---

## 5. Reservation Lifecycle

### State Machine

```
                    ┌─────────────┐
   run approved ───▶│   ACTIVE    │
                    └──────┬──────┘
          ┌────────────────┼──────────────────┬─────────────────┐
          ▼                ▼                  ▼                 ▼
   ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │CANCELLED │  │SOFT_TIMEOUT  │  │HARD_TIMEOUT  │  │   SETTLED    │
   └──────────┘  └──────┬───────┘  └──────┬───────┘  └──────────────┘
                        │                 │
                        ▼                 ▼
                 ┌────────────────────────────────┐
                 │    PROVISIONAL_SETTLEMENT       │
                 └──────────────┬─────────────────┘
                    ┌───────────┴───────────┐
                    ▼                       ▼
             ┌──────────────┐       ┌──────────────┐
             │   SETTLED    │       │   OVERRUN    │
             └──────────────┘       └──────────────┘
```

### Immutable vs Mutable Fields

**Permanently immutable after creation**:
`id, run_id, tenant_id, estimate_id, recommendation_id, trace_id,
parent_reservation_id, period_key, reserved_usd, reservation_tier,
hard_limit_usd, soft_limit_usd, budget_available_at_dispatch,
max_run_time_ms, expires_at, created_at`

**Mutable (operational state only)**: `status`, `updated_at`

### Creating a Reservation

```sql
CREATE OR REPLACE FUNCTION runtime_governance.create_reservation(
  p_run_id UUID, p_tenant_id UUID, p_estimate_id UUID,
  p_recommendation_id UUID, p_trace_id UUID,
  p_parent_reservation_id UUID, p_period_key TEXT,
  p_reserved_usd NUMERIC, p_reservation_tier TEXT,
  p_hard_limit_usd NUMERIC, p_expires_at TIMESTAMPTZ
) RETURNS TABLE (reservation_id UUID, result TEXT, budget_available NUMERIC)
```

Uses optimistic locking with version counter. Returns:
- `'created'` — success
- `'budget_exceeded'` — insufficient budget
- `'period_not_found'` — no budget period configured
- `'concurrency_retry_exceeded'` — transient contention (caller retries)

`concurrency_retry_exceeded` must be returned as HTTP 503 with `Retry-After: 1`.
It must NOT be converted to `run.rejected`. It is a dispatch failure (emit
`run.dispatch_failed`), not a policy rejection.

`budget_available_at_dispatch` is captured within the same transaction as the UPDATE.

---

## 6. Settlement Lifecycle

### Settlement Creation

```sql
CREATE OR REPLACE FUNCTION runtime_governance.settle_reservation(
  p_reservation_id UUID, p_actual_cost_usd NUMERIC,
  p_settlement_type TEXT, p_settlement_source TEXT,
  p_is_provisional BOOLEAN DEFAULT false
) RETURNS TEXT  -- 'settled' | 'already_settled' | 'not_found'
```

Uses `SELECT ... FOR UPDATE` to lock the reservation row. Existence check and INSERT
within the same transaction. Updates `budget_periods.reserved_usd` and
`budget_periods.consumed_usd` atomically with the settlement INSERT.

### The Status Field Exception

Settlement updates `budget_reservations.status`. This is the only sanctioned mutation
of a reservation record. Financial fields are never touched.

### Provisional Settlement Promotion

When provisional settlement is reconciled with actual data:
1. Write a correction record documenting the delta
2. Apply a `budget_correction` for the delta amount
3. Write a new settlement record with `is_provisional = false`
4. Do NOT update the original provisional settlement record

---

## 7. Live Spend Tracking

```sql
CREATE TABLE runtime_governance.live_spend (
  run_id                UUID          NOT NULL,
  tenant_id             UUID          NOT NULL,
  reservation_id        UUID          NOT NULL,
  trace_id              UUID          NOT NULL,
  current_spend_usd     NUMERIC(10,6) NOT NULL  DEFAULT 0,
  soft_limit_usd        NUMERIC(10,6) NOT NULL,
  hard_limit_usd        NUMERIC(10,6) NOT NULL,
  warning_fired         BOOLEAN       NOT NULL  DEFAULT false,
  abort_requested       BOOLEAN       NOT NULL  DEFAULT false,
  abort_requested_at    TIMESTAMPTZ,
  last_token_event_at   TIMESTAMPTZ,
  last_updated_at       TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (run_id)
);
```

Live spend is mutable operational state. Not an artifact. Deleted after settlement.

Token consumption uses READ COMMITTED isolation — advisory signal; slight delay acceptable.
Budget reservation creation and settlement use SERIALIZABLE isolation — financial accuracy required.

---

## 8. Graceful Abort Protocol

### State Machine

```
RUNNING → ABORT_REQUESTED → GRACEFUL_STOP_CONFIRMED → SETTLED
                          ↘ GRACE_TIMEOUT_EXPIRED → FORCE_KILLED → PROVISIONAL_SETTLEMENT
```

### Grace Window by Tenant Tier

| Tier | Default | Rationale |
|---|---|---|
| `sandbox` | 60s | Prioritize clean shutdown |
| `production_standard` | 30s | Balance shutdown vs cost |
| `production_regulated` | 15s | Stricter enforcement |
| `high_throughput` | 10s | Short window acceptable |

### Partial Result Requirement

An agent that handles abort gracefully must:
1. Complete the current atomic unit of work
2. Emit a `partial_result` artifact with `truncated: true`
3. Emit `run.aborted` with final token counts

Force-killed runs produce no partial result.

### Abort Request Schema

```sql
CREATE TABLE runtime_governance.abort_requests (
  id             UUID          NOT NULL  DEFAULT gen_random_uuid(),
  run_id         UUID          NOT NULL  UNIQUE,
  reservation_id UUID          NOT NULL,
  tenant_id      UUID          NOT NULL,
  abort_reason   TEXT          NOT NULL  CHECK (abort_reason IN (
                   'cost_limit','timeout','operator_command',
                   'policy_violation','provider_unreachable')),
  status         TEXT          NOT NULL  DEFAULT 'requested'
                   CHECK (status IN (
                     'requested','confirmed',
                     'grace_timeout_expired','force_killed')),
  grace_window_ms INTEGER      NOT NULL  DEFAULT 30000,
  requested_at   TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  deadline       TIMESTAMPTZ   NOT NULL,
  confirmed_at   TIMESTAMPTZ,
  force_killed_at TIMESTAMPTZ,
  PRIMARY KEY (id)
);
```

UNIQUE on `run_id` ensures only one abort request per run. Concurrent abort triggers
produce a unique constraint violation on the second; silently ignored.

---

## 9. Parent/Child Reservation Semantics

### Design Choice: Option B

Parent reservations cover all child runs. Children do not independently increment
`reserved_usd` on the budget period.

```
parent_reserved_usd = parent_estimate.cost_p95_usd
                    + SUM(declared_child_estimates.cost_p95_usd)
                    + undeclared_fanout_buffer_usd (configurable, default 0)
```

Child `budget_reservations` rows are created referencing `parent_reservation_id`.
`budget_periods.reserved_usd` is incremented only for root reservations
(`parent_reservation_id IS NULL`).

Children draw against the parent's live spend allocation.

### Undeclared Child Run Handling

When a child runs that was not declared in `declared_child_runs`:
1. Check parent reservation headroom
2. If headroom exists: allow, log, emit `child_run.spawned` with `declared: false`,
   emit `spend.warning` immediately
3. If no headroom: reject with `rejection_reason: 'parent_budget_exceeded'`

---

## 10. Concurrency Model

| Operation | Isolation | Reason |
|---|---|---|
| `create_reservation` | SERIALIZABLE | Prevent double-spend |
| `settle_reservation` (root) | SERIALIZABLE | Prevent double-credit |
| Calibration snapshot promotion | SERIALIZABLE | One active snapshot |
| Pricing table activation | SERIALIZABLE | One active table |
| `live_spend` update | READ COMMITTED | Advisory; slight delay acceptable |
| Evaluation artifact creation | READ COMMITTED | Idempotency via UNIQUE constraint |

### The Optimistic Locking Pattern

```
Thread 1: reads budget_periods (version=5, reserved=8.00)
Thread 2: reads budget_periods (version=5, reserved=8.00)
Thread 1: UPDATE ... SET reserved=9.50, version=6 WHERE version=5 → succeeds
Thread 2: UPDATE ... SET reserved=9.50, version=6 WHERE version=5 → 0 rows (retry)
Thread 2: fresh read → budget_exceeded
```

---

## 11. Timeout Semantics

```
elapsed > 2× p95_estimate_wall_clock_ms → SOFT_TIMEOUT → emit spend.warning
elapsed > max_run_time_ms               → HARD_TIMEOUT → abort protocol
provider health check fails (all runs)  → PROVIDER_UNREACHABLE → batch abort
```

`max_run_time_ms` defaults to `4 × p95_estimate_wall_clock_ms`. Flat default of
30 minutes when wall clock estimate is unavailable.

Budget must not remain locked during provider outage. Provisional settlement at
outage detection releases budget.

---

## 12. Fallback Postures

When estimation or reservation infrastructure is degraded:

| Estimate tier | Sandbox | Production standard | Regulated |
|---|---|---|---|
| `calibrated` | approve | approve | approve |
| `deterministic` | approve | approve with 1.5× buffer | human approval |
| `embedded_fallback` | approve under threshold | human approval | reject |

When reservation service is unavailable:

| Tier | Fallback |
|---|---|
| `sandbox` | Approve without reservation; log `reservation_skipped` |
| `production_standard` | Approve without reservation up to $5; reject above |
| `production_regulated` | Reject all runs |

`reservation_skipped` runs are settled post-hoc from telemetry actuals.

---

## 13. Budget Corrections

```sql
CREATE TABLE runtime_governance.budget_corrections (
  id                    UUID          NOT NULL  DEFAULT gen_random_uuid(),
  tenant_id             UUID          NOT NULL,
  period_key            TEXT          NOT NULL,
  correction_amount_usd NUMERIC(12,4) NOT NULL,  -- positive=credit, negative=debit
  correction_reason     TEXT          NOT NULL,
  correction_category   TEXT          NOT NULL  CHECK (correction_category IN (
                          'billing_adjustment','overrun_deficit',
                          'provisional_reconciliation','provider_correction',
                          'manual_credit','manual_debit')),
  reservation_id        UUID,
  settlement_id         UUID,
  correction_record_id  UUID          NOT NULL  FK → platform.correction_records.id,
  created_by            TEXT          NOT NULL,
  created_at            TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);
-- Append-only
```

Corrections are NOT reflected in `budget_periods.reserved_usd` or
`budget_periods.consumed_usd`. They are a separate ledger layer included in
available budget queries and reconciliation views.

---

## 14. Cleanup Job

Runs every 5 minutes. Idempotent.

**Procedure 1**: Settle reservations for completed runs without settlement after 10 minutes.

**Procedure 2**: Expire reservations past `expires_at` with no `started_at` on the run.
Releases `reserved_usd` from the budget period.

**Procedure 3**: Transition runs to SOFT_TIMEOUT when elapsed > 2× p95 estimate.

**Procedure 4**: Delete stale `live_spend` rows for settled runs older than 1 hour.

---

## 15. Operational Invariants

```
INV-RG-001  [Class A — CHECK constraint]
reserved_usd + consumed_usd <= budget_usd on budget_periods at all times.

INV-RG-002  [Class A — UNIQUE partial index]
At most one non-provisional settlement_record per reservation_id.

INV-RG-003  [Class A — function logic]
settle_reservation is idempotent.

INV-RG-004  [Class A — UNIQUE constraint]
At most one abort_request per run_id.

INV-RG-005  [Class B — application sequencing]
No run execution signal emitted before budget_reservation status = 'active' confirmed.

INV-RG-006  [Class B — transaction discipline]
budget_periods financial columns modified only within settle_reservation or
create_reservation functions.

INV-RG-007  [Class C — cleanup job]
Every active reservation for a run with ended_at < now() - 15 minutes is settled.
Alert if result > 0.

INV-RG-008  [Class C — monitoring]
No live_spend row exists for a run that has a final settlement.
Alert immediately if result > 0.

INV-RG-009  [Class C — monitoring]
Budget correction rate does not exceed 1% of total spend per period per week.

INV-RG-010  [Class D — process]
A correction_record must exist for every budget_correction.
Evidence_reference required for billing_adjustment, provider_correction,
manual_credit, manual_debit.
```

---

## 16. Race Condition Catalog

| Race | Scenario | Mitigation |
|---|---|---|
| RACE-1 | Concurrent reservation requests against same budget | Optimistic locking; second UPDATE returns 0 rows; retry → budget_exceeded |
| RACE-2 | Concurrent settlement of same reservation | SELECT FOR UPDATE; existence check and INSERT in same transaction |
| RACE-3 | Abort signal sent after run completes | settle_reservation idempotency; abort coordinator checks run status |
| RACE-4 | Reservation created, run never starts | expires_at on reservation; cleanup job releases |
| RACE-5 | Budget period rollover during active reservation | Reservations carry period_key; settlement applies to originating period |
| RACE-6 | Undeclared child run budget leakage | Undeclared children check parent headroom before approval |
| RACE-7 | Late token event after settlement | on_token_consumed returns COMPLETED when live_spend row absent |
