# RFC-001 — Operational Invariants

```
Status: Active
Version: 1.0.0
Authors: [Platform Engineering]
Established: Through design sessions RFC-001 through RFC-010
Required by: All bounded domains
```

---

## 1. Purpose

This RFC establishes the cross-cutting operational invariants and enforcement
classifications that all bounded domains on the platform must satisfy. It defines
the invariant taxonomy, the enforcement mechanism per class, the correction record
pattern for immutable artifacts, and the monitoring positive-signal requirement.

All domain-specific invariants (RG-001, CAL-001, ART-001, etc.) declared in
RFC-002 through RFC-010 inherit from this classification system.

---

## 2. Invariant Classification

Every operational invariant belongs to exactly one enforcement class.

### Class A — Database-Enforced

The database physically prevents violations. Application bugs cannot override them.

Mechanisms:
- `NOT NULL` column constraints
- `CHECK` constraints on enum fields
- `UNIQUE` and `UNIQUE PARTIAL` indexes
- `FOREIGN KEY` with `ON DELETE RESTRICT`
- Restrictive Row Level Security policies (UPDATE USING false, DELETE USING false)
- `CHECK` constraints on financial balances

A Class A invariant that cannot be expressed as a database constraint is
reclassified to Class B.

### Class B — Transaction-Enforced

Enforced by application code within a correctly structured database transaction.
Cannot be violated by concurrent requests when implemented correctly.

Mechanisms:
- Serializable isolation for budget reservation and settlement
- Optimistic locking with version counters
- Idempotency checks within the same transaction as the operation
- SELECT FOR UPDATE before conditional mutations

Class B invariants require adversarial concurrency testing before production.
A Class B invariant that could be bypassed by application bugs must document
exactly which code path enforces it.

### Class C — Monitoring-Enforced

Detected after the fact by scheduled monitoring queries. Violations are possible
but are detected within a defined window and trigger alerts that initiate recovery.

Requirements for Class C invariants:
- Monitoring query must return a result on every execution (never an empty result set
  that could mask a broken monitoring pipeline)
- Alert fires if: (a) violation count > 0, or (b) no result received within timeout
- Recovery path documented alongside the invariant

### Class D — Convention-Enforced

Cannot be automated. Enforced by code review, process, and team discipline.

Requirements:
- Written explicitly in PR review checklists
- Violation constitutes a process incident requiring root cause analysis
- Examples must be documented to calibrate reviewer judgment

---

## 3. Append-Only Enforcement Pattern

All artifact tables (Class I schemas per RFC-009) use this pattern applied
immediately after table creation, before any data is written:

```sql
ALTER TABLE {schema}.{table} ENABLE ROW LEVEL SECURITY;

CREATE POLICY "immutable_no_update"
  ON {schema}.{table}
  AS RESTRICTIVE FOR UPDATE USING (false);

CREATE POLICY "immutable_no_delete"
  ON {schema}.{table}
  AS RESTRICTIVE FOR DELETE USING (false);

CREATE POLICY "tenant_isolation"
  ON {schema}.{table}
  FOR SELECT
  USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

The application service role must have `INSERT` privileges only on artifact tables.
`UPDATE` and `DELETE` privileges are never granted to the application role.

**The status field exception**: Operational lifecycle status fields on reservation
records (`budget_reservations.status`) are updatable. Financial fields on the same
records are immutable. This is the only sanctioned exception to append-only
enforcement on artifact tables.

---

## 4. Correction Record Pattern

When an immutable artifact is discovered to contain incorrect data:

1. The original artifact is never modified
2. A `platform.correction_records` row is written documenting the discrepancy
3. The correction record itself is append-only
4. Consumers that need the corrected view join against correction records
5. Calibration pipelines re-evaluate affected buckets when significant corrections
   are applied (`requires_calibration_review = true` on the correction record)

Correction record volume is a health signal:
- Rate > 0.5% per week → investigate
- Rate > 1.0% per week → incident
- Same field corrected repeatedly → systemic bug; fix the code, not the data

---

## 5. Monitoring Positive-Signal Requirement

Every Class C invariant monitoring query must return a result row on every
execution. A query that can return zero rows when there is nothing to check
is a broken monitoring query — its silence is indistinguishable from a
pipeline failure.

Required pattern:

```sql
-- Returns exactly 1 row always.
-- Alert if violations > 0.
-- Alert if no result received within 60 seconds (monitoring pipeline broken).
SELECT
  COUNT(*) FILTER (WHERE <violation_condition>) AS violations,
  COUNT(*) AS records_checked,
  now() AS checked_at
FROM <table>
WHERE <scope_condition>;
```

Never design monitoring as "alert if rows returned." Always design as "alert if
violation count > 0 within a result that is always returned."

---

## 6. The Three-Truth-Surface Protection

Established in RFC-008 OQ-3 and formalized in RFC-009. Three categories of truth
must never be mixed in the same artifact field:

| Surface | Meaning | Owners |
|---|---|---|
| Decision truth | What the system believed at decision time | `estimate_artifacts`, `recommendation_artifacts`, `budget_reservations` (at creation) |
| Execution truth | What actually happened during execution | `run_records`, `raw_events`, `settlement_records` |
| Outcome truth | What quality, cost, and reliability resulted | `quality_signals`, `evaluation_artifacts`, `calibration_observations` |

**Prohibited cross-surface contaminations:**
- Embedding execution truth in decision artifacts
- Embedding decision truth in execution records
- Deriving outcome truth from decision truth without going through execution
- Mutating decision truth fields after execution completes

Any PR introducing a cross-surface field requires a mandatory RFC amendment
before merge. This is not a reviewer judgment call.

---

## 7. Cross-Cutting Invariants

These invariants apply across all bounded domains and are not owned by any
single domain RFC.

```
INV-GLOBAL-001  [Class A]
Every artifact table has append-only RLS policies applied before any data
is written. No artifact table exists in production without these policies.

INV-GLOBAL-002  [Class A]
Every table has created_at TIMESTAMPTZ NOT NULL DEFAULT now().
No TIMESTAMP (without TZ) column exists on any platform table.
Enforcement: CI hard failure rule.

INV-GLOBAL-003  [Class A]
Every FK constraint on Class I (immutable) tables uses ON DELETE RESTRICT.
ON DELETE CASCADE is prohibited on Class I tables.
Enforcement: CI hard failure rule.

INV-GLOBAL-004  [Class B]
No service role has UPDATE or DELETE privileges on Class I artifact tables.
The application role has INSERT privileges only.
Enforcement: Database role grant policy; audited on deployment.

INV-GLOBAL-005  [Class C]
pg_stat_user_tables.n_tup_upd = 0 for all Class I artifact tables at all times.
Monitoring: daily query against pg_stat_user_tables for all artifact tables.
Alert immediately if any n_tup_upd > 0.

INV-GLOBAL-006  [Class C]
Cross-tenant queries never return individual row data from
calibration_observations or quality_signals without tenant_id filter.
Monitoring: query log analysis for full-table scans on these tables.
Alert if detected.

INV-GLOBAL-007  [Class D]
Three-truth-surface violations are prohibited.
Every schema PR includes the three-truth-surface checklist from RFC-009.
Reviewer must sign off that no cross-surface fields are introduced.
```

---

## 8. Semantic Boundary Erosion Patterns

From RFC-009 OQ-3. These six patterns represent the primary long-term risk
to architectural integrity. Monitoring for them begins at Phase 4.

1. Runtime services introspecting governance metadata (schema registry)
2. Routing engine mutating execution state
3. Calibration rewriting historical estimates
4. Evaluator scores treated as ground truth
5. Schema registry becoming a runtime dependency
6. Execution truth leaking into decision artifacts

Each pattern has a corresponding monitoring query defined in RFC-010 §13.

---

## 9. References

| Domain | Invariants defined in |
|---|---|
| Artifact Model | RFC-002 (INV-ART-001 through INV-ART-016) |
| Telemetry | RFC-003 (ingestion and idempotency guarantees) |
| Runtime Governance | RFC-004 (INV-RG-001 through INV-RG-010) |
| Task Taxonomy | RFC-005 (INV-TAX-001 through INV-TAX-008) |
| Calibration | RFC-006 (INV-CAL-001 through INV-CAL-010) |
| Quality Signal | RFC-007 (INV-QS-001 through INV-QS-009) |
| Routing Provenance | RFC-008 (INV-RP-001 through INV-RP-008) |
| Schema Evolution | RFC-009 (INV-SE-001 through INV-SE-008) |
| Implementation | RFC-010 (INV-SEQ-001 through INV-SEQ-005) |
