# RFC-009 — Schema Evolution

```
Status: Active
Version: 1.0.0
Authors: [Platform Engineering]
Depends on: RFC-001 through RFC-008
Applies to: All schemas, all services, all artifact types, all event contracts
Binding on: Every engineer making schema changes to the platform
```

---

## 1. Context

Schema changes are the most common source of long-term operational debt in platform
engineering. A field renamed under time pressure, an enum value added without consumer
coordination, a type changed with a "quick migration" — each looks small in the PR.
Accumulated over three years across ten services and forty tables, they produce a system
where no one is confident what a given field means, whether historical values are
consistent, or whether a consumer will break if a new value appears.

This RFC establishes the binding rules for how schemas evolve on this platform.

---

## 2. Scope

- Schema classification and rules per class
- The three-truth-surface protection
- Semantic versioning for schemas
- Field lifecycle: active → deprecated → removed
- Enum lifecycle policy
- Type policies (UUID, TIMESTAMP, NUMERIC, JSONB)
- Naming conventions
- Migration approval workflow
- CI enforcement requirements
- Event contract evolution alignment with RFC-003

---

## 3. The Three-Truth-Surface Protection

From RFC-008 OQ-3. Schema changes that collapse these surfaces are always prohibited.

**Decision truth**: what the system believed at decision time.  
Owners: `estimate_artifacts`, `recommendation_artifacts`, `budget_reservations` (at creation).

**Execution truth**: what actually happened during execution.  
Owners: `run_records`, `raw_events`, `settlement_records`.

**Outcome truth**: quality, cost, and reliability results.  
Owners: `quality_signals`, `evaluation_artifacts`, `calibration_observations`.

### Prohibited Cross-Surface Contaminations

```
VIOLATION A: Embedding execution truth in decision artifacts
  Example: adding actual_cost_usd to estimate_artifacts
  Why: replay systems use estimate_artifacts to reconstruct decision-time state

VIOLATION B: Embedding decision truth in execution records
  Example: adding estimated_cost_usd to run_records
  Why: creates redundant, potentially inconsistent copy of decision truth

VIOLATION C: Deriving outcome truth from decision truth without going through execution
  Example: computing quality_score on estimate_artifacts from features alone

VIOLATION D: Mutating decision truth fields after execution completes
  Example: updating estimate_artifacts.cost_p50_usd after learning actual cost
```

Any PR introducing a cross-surface field requires a mandatory RFC amendment before
merge. Not a reviewer judgment call.

---

## 4. Schema Classification

Every table belongs to exactly one class.

### Class I — Immutable Artifact Schemas

Rows never updated or deleted after creation. Evolution must be backward-compatible.

Tables: all artifact tables listed in RFC-002, RFC-006, RFC-007, RFC-008.

**Additional constraint**: Adding NOT NULL requires a default meaningful for historical
rows. `NOT NULL DEFAULT ''` on a semantically required text field is prohibited.

### Class II — Operational State Schemas

Rows are updated as state transitions occur. Migration-safe but not exact-state-preserving.

Tables: `budget_periods`, `live_spend`, `abort_requests`, operational fields on `run_records`.

### Class III — Reference and Configuration Schemas

Slowly changing, explicitly versioned. New versions added as rows; old versions retired.

Tables: `bucket_schema_versions`, `task_taxonomy_versions`, `profile_snapshots`, `schema_registry`.

### Class IV — Ephemeral Schemas

Short-lived operational data. Less constrained but still requires consumer coordination.

Tables: `live_spend` (row lifetime = run duration), `seen_events` (deduplication window).

---

## 5. Versioning Rules

### Semantic Version Format

Every artifact schema carries `schema_version`: `MAJOR.MINOR.PATCH`.

| Change type | Bump | Approval |
|---|---|---|
| Add optional field | MINOR | PR review |
| Add required field with meaningful default | MINOR | PR review + impact assessment |
| Add required field without default | MAJOR | RFC amendment |
| Remove field | MAJOR | RFC amendment + migration window |
| Rename field | MAJOR | RFC amendment + migration window |
| Change field type | MAJOR | RFC amendment + migration window |
| Change field meaning | MAJOR | RFC amendment |
| Add enum value | MINOR | PR review + consumer notification |
| Remove enum value | MAJOR | RFC amendment + migration window |
| Rename enum value | MAJOR | RFC amendment + migration window |
| Tighten CHECK constraint | PATCH or MAJOR | Depends on existing data |
| Loosen CHECK constraint | MINOR | PR review |
| Add/remove index | PATCH | PR review |
| Add new table | MINOR | PR review |
| Remove table | MAJOR | RFC amendment + migration window |

### Consumer Unknown-Field Contract

Every consumer of any schema must handle unknown fields without erroring.

```python
# PROHIBITED — will break on any new field:
class EstimateArtifact(BaseModel):
    class Config:
        extra = "forbid"

# REQUIRED:
class EstimateArtifact(BaseModel):
    class Config:
        extra = "ignore"
```

All switch/match statements on platform enum values must have a default case that
logs a warning and no-ops — never raises.

---

## 6. Field Lifecycle Policy

### Active → Deprecated → Removed

**Deprecation** begins when a replacement field exists or removal is justified.
Recorded in the schema registry with `planned_removal_at`.

During deprecation:
- Writers emit BOTH old and new fields simultaneously
- Consumers migrate to the new field
- Monitoring tracks which consumers still read the deprecated field

**Removal** requires:
- All consumers confirmed migrated (explicit sign-off per service owner)
- Minimum 90 days elapsed since deprecation
- No reads of the deprecated field in the last 14 days (query log verification)

### Field Naming Freeze

A field name that has ever existed in a Class I table is permanently reserved.
It may not be reused for a different purpose even after removal.

---

## 7. Enum Lifecycle Policy

### Adding Values

Non-breaking when all consumers handle unknown enum values. Add to CHECK constraint,
notify consumers, begin emitting. MINOR bump.

### Removing Values

Always MAJOR. Procedure:
1. Stop emitting the value
2. 90-day waiting period with no new rows using this value
3. Document the value's historical meaning in the schema registry (permanent record)
4. Remove from CHECK constraint

Never remove from schema documentation. Historical records with the value must remain
interpretable.

### Enum Type Policy

Use CHECK constraints, not PostgreSQL ENUM types. PostgreSQL ENUM requires `ALTER TYPE`
to add values (complex migration). CHECK constraints are simpler to evolve.

```sql
-- PROHIBITED:
CREATE TYPE signal_source_enum AS ENUM ('system_automatic', 'user_explicit');

-- REQUIRED:
CHECK (signal_source IN ('system_automatic', 'user_explicit'))
```

---

## 8. Type Policies

### Primary Keys

```sql
-- REQUIRED:
id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY
-- UUID v7 preferred; v4 acceptable; v1 prohibited (leaks MAC address)

-- PROHIBITED:
id SERIAL PRIMARY KEY   -- not globally unique
id BIGSERIAL PRIMARY KEY
```

### Timestamps

```sql
-- REQUIRED:
created_at TIMESTAMPTZ NOT NULL DEFAULT now()

-- PROHIBITED:
created_at TIMESTAMP NOT NULL DEFAULT now()  -- no timezone; silently wrong
```

Every table must have `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`. CI hard failure
if a TIMESTAMP (without TZ) column is added.

### Financial Amounts

```sql
-- REQUIRED:
cost_usd   NUMERIC(10,6)   -- 6 decimal places; sufficient for per-token precision
budget_usd NUMERIC(12,4)   -- 4 decimal places for budget totals

-- PROHIBITED:
cost_usd   FLOAT            -- floating point errors in financial calculations
```

### Scores and Ratios

```sql
quality_score NUMERIC(4,3)   -- 0.000 to 1.000
multiplier    NUMERIC(8,4)   -- up to 9999.9999x
```

### Text

```sql
-- REQUIRED:
description TEXT              -- no length limit

-- PROHIBITED:
description VARCHAR(255)      -- arbitrary limits create migration debt
description CHAR(10)          -- fixed-length padding
```

### Structured Data

```sql
-- REQUIRED:
features JSONB                -- binary JSON; supports indexing

-- PROHIBITED:
features JSON                 -- no indexing
features TEXT                 -- untyped
```

JSONB fields must use descriptive suffix: `_snapshot`, `_definition`, `_data`, `_payload`.

---

## 9. Naming Conventions

### Tables

`{schema}.{entity_plural}` — lowercase, underscore-separated, plural.

### Columns

```
Primary key:      id
Foreign keys:     {entity}_id
Timestamps:       {event}_at  (created_at, ended_at, promoted_at)
Booleans:         is_{adjective} or has_{noun}
Status fields:    status  (with CHECK constraint)
Version strings:  {artifact}_version
Version UUIDs:    {artifact}_version_id
JSONB:            {contents}_snapshot / _definition / _data
```

### Constraints

```sql
CONSTRAINT {table}_pkey PRIMARY KEY (id)
CONSTRAINT uq_{table}_{columns} UNIQUE (col1, col2)
CONSTRAINT chk_{table}_{column} CHECK (column IN (...))
CONSTRAINT fk_{table}_{referenced} FOREIGN KEY (col)
  REFERENCES {schema}.{table}(id) ON DELETE RESTRICT
```

`ON DELETE RESTRICT` is the default for all FK constraints on Class I tables.
`ON DELETE CASCADE` is prohibited on Class I tables — it enables accidental deletion
of immutable records by deleting their parent.

---

## 10. Migration Approval Workflow

### Non-Breaking Changes (MINOR or PATCH)

Required: PR with migration file, consumer impact assessment, schema registry updated.
Not required: RFC amendment, migration window, formal service owner sign-off.

### Breaking Changes (MAJOR)

Required:
- RFC amendment documenting the change, impact, and rollback plan
- Explicit sign-off from every affected service owner
- Migration window opened (minimum 90 days)
- Schema registry updated with `planned_removal_at`
- Both old and new states supported simultaneously during window
- CI flag disabling breaking behavior until window closes

### Three-Truth-Surface Violations

Always prohibited. No RFC amendment can authorize a three-truth-surface collapse.

### Migration Runbook Template (MAJOR changes)

```markdown
## Schema Change Runbook

Change: {description}
Affected tables: {list}
Schema version: {old} → {new}
RFC amendment: RFC-{number}

### Consumers affected
| Service | Reads | Writes | Migration status |

### Rollback plan

### Data migration

### Testing requirements
- [ ] Migration runs without errors on production snapshot
- [ ] All consumers pass tests with new schema
- [ ] Rollback tested
- [ ] No performance regression

### Migration window
Open: {date}
Planned close: {date}
```

---

## 11. CI Enforcement

### Hard Failures (Block Merge)

- `TIMESTAMP` (without TZ) column in migration
- `SERIAL` or `BIGSERIAL` primary key
- New table without `created_at` TIMESTAMPTZ
- Strict deserializer on platform schemas (`extra = "forbid"`)
- `uuid_generate_v1()` in migration
- `ON DELETE CASCADE` on Class I tables
- Enum switch without default case on platform enums

### Soft Warnings (Flag for Review)

- Nullable column on Class I table
- JSONB column without descriptive suffix
- `VARCHAR` with explicit length limit
- `FLOAT` type on column with `usd` or `amount` in name
- Artifact table modified without schema_version bump

### Constitutional CI Rule

**CI governance rules are constitutional, not advisory.**

Inline suppressions are prohibited for all hard failure rules:

```
# noqa: strict-deserializer    — PROHIBITED
# schema-evolution-ignore      — PROHIBITED
# type: ignore                 — PROHIBITED on schema-governed code
```

A hard failure rule that cannot apply to a specific case requires an RFC amendment
documenting why. Not an inline suppression. Waivers are:
- Granted by: RFC amendment, reviewed by platform architecture
- Duration: specific to the case, not open-ended
- Recorded in: schema registry with `rfc_reference`

---

## 12. Schema Registry

```sql
CREATE TABLE platform.schema_registry (
  id                  UUID          NOT NULL  DEFAULT gen_random_uuid(),
  artifact_type       TEXT          NOT NULL,
  field_name          TEXT          NULL,
  enum_value          TEXT          NULL,
  lifecycle_status    TEXT          NOT NULL
    CHECK (lifecycle_status IN ('active','deprecated','removed')),
  schema_version      TEXT          NOT NULL,
  deprecated_at       TIMESTAMPTZ,
  planned_removal_at  TIMESTAMPTZ,
  removed_at          TIMESTAMPTZ,
  replacement_field   TEXT          NULL,
  deprecation_reason  TEXT          NULL,
  rfc_reference       TEXT          NULL,
  created_at          TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id)
);
```

**Runtime use is prohibited.**

The schema registry must never be queried by application services at runtime.
It is governance metadata, not runtime dependency infrastructure.

Services derive runtime expectations from:
- Generated type definitions (compiled from schema definitions)
- Versioned event contracts (RFC-003)
- Compiled artifact schemas (RFC-002)

NOT from dynamic registry lookups or runtime schema introspection.

Any PR introducing a runtime dependency on the schema registry is a hard CI failure.

### Three-Truth-Surface PR Template

Every PR modifying a schema must include this checklist:

```markdown
## Three-Truth-Surface Review (required for all schema PRs)

- [ ] I have identified which truth surface owns every new/modified field
- [ ] No execution truth fields exist on decision artifact tables
- [ ] No decision truth fields exist on execution record tables
- [ ] No outcome truth is derived from decision truth without going through execution
- [ ] This field is not a duplicate of a field on a different truth surface

For fields whose meaning is changing:
- [ ] The field's new meaning belongs to the same truth surface as its old meaning
- [ ] If the meaning changed surfaces, a new field was added and the old deprecated

I confirm I have consciously asked: "Which truth surface owns this field?"
Reviewer signature: _______________
```

---

## 13. Operational Invariants

```
INV-SE-001  [Class A — CI] No TIMESTAMP (without TZ) column on any platform table.
INV-SE-002  [Class A — CI] No enum switch without default case on platform enums.
INV-SE-003  [Class A — constraint] No FK ON DELETE CASCADE on Class I tables.
INV-SE-004  [Class B — process] Every MAJOR change has a completed migration runbook.
INV-SE-005  [Class B — process] No field name reused after removal from Class I table.
INV-SE-006  [Class C — monitoring] Every deprecated field has planned_removal_at set.
INV-SE-007  [Class C — monitoring] No deprecated field remains past planned_removal_at.
INV-SE-008  [Class D — process] Three-truth-surface violations are prohibited.
            Code review gate with PR template sign-off required.
```

---

## 14. Dangerous Shortcuts

- Renaming a field directly — always add new + deprecate old
- "Temporary" fields that become permanent — no temporary schema category exists
- Adding NOT NULL without a meaningful historical default
- Changing field meaning without changing the name
- Skipping schema registry entry for deprecations
- Using PostgreSQL ENUM types — use CHECK constraints
- Applying three-truth-surface review only to new fields (applies to meaning changes too)
