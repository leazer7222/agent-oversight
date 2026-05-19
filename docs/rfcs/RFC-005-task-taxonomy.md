# RFC-005 — Task Taxonomy

```
Status: Active
Version: 1.0.0
Authors: [Platform Engineering]
Depends on: RFC-001, RFC-002, RFC-003
Required before: First run record is written to the database
```

---

## 1. Context

Every run on the platform is classified by task type and complexity bucket. These two
dimensions appear on run records, estimate artifacts, evaluation artifacts, and
calibration buckets. They are the primary segmentation axes for calibration and,
eventually, model routing.

Task taxonomy is load-bearing from the first run. Free-form strings, retrospective
additions, and underdefined complexity criteria all produce uncorrectable calibration
corruption.

---

## 2. Scope

- Schema for taxonomy and task type tables
- Initial eight task types with formal definitions
- Machine-implementable complexity classifier
- Taxonomy versioning and migration model
- Multi-label semantics
- Governance gate for adding new types
- Integration requirements with run records and artifacts

---

## 3. Schema

```sql
CREATE TABLE cost_intelligence.task_taxonomy_versions (
  id             UUID          NOT NULL  DEFAULT gen_random_uuid(),
  version        TEXT          NOT NULL  UNIQUE,  -- "taxonomy-v1"
  status         TEXT          NOT NULL  CHECK (status IN ('draft','active','deprecated')),
  classifier_version TEXT      NOT NULL,           -- "complexity-v1"
  activated_at   TIMESTAMPTZ,
  deprecated_at  TIMESTAMPTZ,
  created_at     TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  created_by     TEXT          NOT NULL,
  PRIMARY KEY (id)
);

CREATE UNIQUE INDEX uq_one_active_taxonomy
  ON cost_intelligence.task_taxonomy_versions (status)
  WHERE status = 'active';

CREATE TABLE cost_intelligence.task_types (
  id                    UUID          NOT NULL  DEFAULT gen_random_uuid(),
  taxonomy_version_id   UUID          NOT NULL  FK → task_taxonomy_versions.id,
  code                  TEXT          NOT NULL,  -- stable machine identifier; never renamed
  label                 TEXT          NOT NULL,  -- human label; may change within version
  description           TEXT          NOT NULL,
  complexity_definition JSONB         NOT NULL,  -- machine-implementable classifier criteria
  primary_use_cases     TEXT[]        NOT NULL  DEFAULT '{}',
  exclusions            TEXT[]        NOT NULL  DEFAULT '{}',
  superseded_by_id      UUID          NULL  FK → task_types.id,
  min_calibration_runs  INTEGER       NOT NULL  DEFAULT 30,
  created_at            TIMESTAMPTZ   NOT NULL  DEFAULT now(),
  PRIMARY KEY (id),
  UNIQUE (taxonomy_version_id, code)
);
-- Append-only enforcement on both tables
```

### Integration on Run Records

```sql
ALTER TABLE run_records
  ADD COLUMN task_type_id              UUID          NOT NULL,
  ADD COLUMN task_complexity_bucket    TEXT          NOT NULL
    CHECK (task_complexity_bucket IN ('simple','medium','complex')),
  ADD COLUMN task_classifier_version   TEXT          NOT NULL,
  ADD COLUMN secondary_task_type_id    UUID;

ALTER TABLE run_records
  ADD FOREIGN KEY (task_type_id)
    REFERENCES cost_intelligence.task_types(id) ON DELETE RESTRICT;
```

Both `task_type_id` and `task_complexity_bucket` are NOT NULL. An invalid or missing
task type is a dispatch failure (`run.dispatch_failed`), not a defaulted null.

---

## 4. Initial Taxonomy — v1

Eight task types. Seeded before any run records are written.

### `info_retrieval` — Information Retrieval

The agent's primary work is finding, fetching, and synthesizing information from
external sources or provided context.

Primary use cases: web research, document lookup, knowledge base queries, fact
extraction, literature review.

Exclusions: tasks that primarily generate new content (use `content_gen`); tasks
that primarily analyze structured data (use `data_analysis`).

### `content_gen` — Content Generation

The agent's primary work is producing original text output — writing, rewriting,
summarizing, or transforming content.

Primary use cases: drafting documents, summarizing inputs, translating content,
rewriting for tone or format, generating marketing copy.

Exclusions: primarily retrieve rather than generate (use `info_retrieval`); primarily
write code (use `code_gen`).

### `code_gen` — Code Generation

The agent's primary work involves writing, modifying, reviewing, or debugging code
or technical artifacts.

Primary use cases: writing functions or classes, code review, bug fixing, test
generation, query writing, infrastructure configuration.

Exclusions: generating technical documentation without code (use `content_gen`).

### `data_analysis` — Data Analysis

The agent's primary work is processing, analyzing, or extracting meaning from
structured or semi-structured data.

Primary use cases: CSV/JSON processing, statistical analysis, data extraction,
report generation from structured sources.

Exclusions: primarily retrieves unstructured content (use `info_retrieval`); primarily
writes analysis code (use `code_gen`).

### `orchestration` — Orchestration

The agent's primary work is coordinating, planning, or sequencing work across
multiple steps or sub-agents.

Primary use cases: multi-agent pipelines, workflow planning, task decomposition,
step sequencing, sub-agent delegation.

Note: any run with `declared_child_runs > 0` must use `orchestration` as primary
or secondary type.

Exclusions: single-step agents using multiple tools; agents that call child agents
only as tools without directing them.

### `classification` — Classification

The agent's primary work is categorizing, tagging, labeling, or routing inputs
according to a defined schema.

Primary use cases: content moderation, topic tagging, intent detection, entity
recognition, routing decisions, priority assignment.

Exclusions: free-form evaluation without a category schema (use `evaluation`).

### `conversation` — Conversation

The agent's primary work is conducting a dialog — responding to a human turn in
an ongoing conversation with conversation history.

Primary use cases: customer support, interactive Q&A, tutoring, assistant
interactions, multi-turn dialog.

Exclusions: single-turn Q&A with no history (consider `info_retrieval`); automated
pipelines with no human in the loop.

### `evaluation` — Evaluation

The agent's primary work is assessing, grading, or scoring work produced by another
agent, human, or system.

Primary use cases: code review scoring, content quality assessment, rubric-based
grading, A/B output comparison, LLM-as-judge.

Exclusions: classification tasks where output is a category, not a quality judgment.

---

## 5. Complexity Classification

### Design Principles

The classifier must be:
- **Deterministic**: identical feature vectors always produce the same bucket
- **Input-only**: uses only `estimation_features_snapshot` fields
- **Versioned**: stored in `complexity_definition` JSONB on each task type
- **Explainable**: reconstructable from stored features + stored criteria

### Complexity Definition Schema

```json
{
  "classifier_version": "complexity-v1",
  "override_rules": [
    {
      "condition": "declared_child_runs > 0",
      "result": "complex",
      "reason": "Any run spawning child agents is complex by definition"
    }
  ],
  "dimensions": {
    "prompt_chars": {"simple_max": 2000, "medium_max": 10000},
    "context_ref_count": {"simple_max": 1, "medium_max": 5},
    "declared_max_steps": {"simple_max": 2, "medium_max": 6},
    "tool_count": {"simple_max": 1, "medium_max": 3}
  },
  "scoring": {
    "simple_max_score": 1,
    "complex_min_score": 4
  }
}
```

Each dimension contributes 0 (≤ simple_max), 1 (> simple_max and ≤ medium_max),
or 2 (> medium_max). Total score determines the bucket.
Override rules are evaluated first.

### Thresholds by Task Type

```
task_type         prompt_chars    context_refs    max_steps   tool_count
                  simple/medium   simple/medium   simple/med  simple/med

info_retrieval    2000/10000      1/5             2/6         1/3
content_gen       1000/8000       1/4             2/5         0/2
code_gen          500/5000        1/6             2/8         1/4
data_analysis     500/4000        1/5             2/6         1/3
orchestration     500/5000        1/5             3/8         2/6
classification    200/2000        0/3             1/3         0/2
conversation      100/2000        0/5             1/3         0/2
evaluation        500/4000        1/5             2/5         0/2
```

Additional override rules:
- All `orchestration` runs with `declared_child_runs > 0` → `complex`
- All `conversation` runs with `context_ref_count > 5` → `complex`

### Classifier Implementation

The classifier is a pure function with no side effects. Not an LLM. No external calls.

```python
def classify_complexity(
    task_type_code: str,
    features: dict,
    classifier_version: str = "complexity-v1"
) -> tuple[str, str]:
    """Returns (bucket, classifier_version). Raises on unknown task_type_code."""
    task_def = get_task_type(task_type_code, classifier_version)
    if task_def is None:
        raise TaskClassificationError(f"Unknown task type: {task_type_code}")

    complexity_def = task_def["complexity_definition"]

    for rule in complexity_def.get("override_rules", []):
        if _evaluate_condition(rule["condition"], features):
            return rule["result"], classifier_version

    score = 0
    for dimension, thresholds in complexity_def.get("dimensions", {}).items():
        value = len(features.get("tools_enabled", [])) if dimension == "tool_count" \
                else features.get(dimension, 0)
        if value > thresholds["medium_max"]:
            score += 2
        elif value > thresholds["simple_max"]:
            score += 1

    scoring = complexity_def.get("scoring", {})
    if score <= scoring.get("simple_max_score", 1):
        return "simple", classifier_version
    elif score >= scoring.get("complex_min_score", 4):
        return "complex", classifier_version
    else:
        return "medium", classifier_version
```

The classifier is called at dispatch time. Output stored on run record.
`task_classifier_version` records which version produced the result.

---

## 6. Multi-Label Semantics

- `task_type_id` — primary type (required, NOT NULL)
- `secondary_task_type_id` — secondary type (optional, nullable)

Rules:
- Primary and secondary must be different codes
- Both must be from the same active taxonomy version
- Secondary type does not affect calibration bucket assignment (only primary does)
- No run has more than two task type labels

---

## 7. Taxonomy Versioning and Migration

### When a New Taxonomy Version Is Required

Required:
- New task type added
- Task type code must change
- Complexity thresholds change significantly (>25% on any threshold)
- Task type split or merged

Not required:
- Human-readable `label` changes
- `description` clarified without changing boundaries
- `exclusions` list updated

### Creating a New Taxonomy Version

1. Create new version in `draft` status
2. Insert all task types (copy unchanged, update changed, set `superseded_by_id` on old)
3. Assess backfill: historical run records retain their original `task_type_id`
4. Review calibration impact: new/changed types start with zero observations
5. Activate: single transaction retiring old, activating new
6. Update classifier service (cache TTL: 60 seconds maximum)

### Historical Record Continuity

Historical run records reference their original `task_type_id` permanently. They are
not migrated. Cross-version analysis requires joining through `superseded_by_id`.

---

## 8. Governance Gate

### Adding a New Task Type Requires an RFC

Must include:
1. **Justification**: three concrete examples that fit the new type and not existing types
2. **Boundary definition**: formal description, exclusions, machine-implementable complexity definition
3. **Backfill plan**: can historical runs be reclassified?
4. **Calibration data plan**: expected runs/day; when will `min_calibration_runs` be reached?
5. **Sunset criteria**: when would this type be merged back or removed?

### Minimum Calibration Before Routing Use

New types must not be used as routing dimensions until `min_calibration_runs`
(default 30) observations with finalized quality signals are accumulated.
Calibration pipeline marks types below threshold as `calibration_status = 'insufficient_data'`.

### Taxonomy Cap

Cap at twelve types without a formal platform architecture review. At twelve types,
mandatory review: are any types underused (< 30 runs/month), redundant, or mergeable?

---

## 9. Monitoring Obligations

```sql
-- Distribution by task type (last 7 days)
SELECT tt.code, tt.label, COUNT(r.id) AS run_count
FROM run_records r
JOIN cost_intelligence.task_types tt ON tt.id = r.task_type_id
WHERE r.created_at > now() - interval '7 days'
GROUP BY tt.code, tt.label ORDER BY run_count DESC;

-- Complexity distribution per type (detect classifier drift)
SELECT tt.code, r.task_complexity_bucket, COUNT(*) AS count
FROM run_records r
JOIN cost_intelligence.task_types tt ON tt.id = r.task_type_id
WHERE r.created_at > now() - interval '7 days'
GROUP BY tt.code, r.task_complexity_bucket ORDER BY tt.code;

-- Orchestration runs with undeclared fanout (calibration signal)
SELECT COUNT(*) AS undeclared_fanout_runs,
       AVG(r.actual_child_runs_spawned) AS avg_actual_fanout
FROM run_records r
JOIN cost_intelligence.task_types tt ON tt.id = r.task_type_id
WHERE tt.code = 'orchestration'
  AND r.declared_child_runs = 0
  AND r.actual_child_runs_spawned > 0
  AND r.created_at > now() - interval '7 days';
-- High count = systematic caller misconfiguration or dynamic fanout pattern.
-- Flag in weekly calibration review.

-- Unclassified run rate (alert if > 0.1%)
SELECT COUNT(*) FILTER (WHERE task_type_id IS NULL)::float
       / NULLIF(COUNT(*), 0) AS unclassified_rate
FROM run_records WHERE created_at > now() - interval '24 hours';
```

---

## 10. Operational Invariants

```
INV-TAX-001  [Class A] task_type_id IS NOT NULL on all run_records.
INV-TAX-002  [Class A] task_complexity_bucket IS NOT NULL with CHECK constraint.
INV-TAX-003  [Class A] task_type_id FK ON DELETE RESTRICT.
INV-TAX-004  [Class A] Exactly one active taxonomy version at any time.
INV-TAX-005  [Class A] Unique (taxonomy_version_id, code) on task_types.
INV-TAX-006  [Class B] Primary and secondary task types must be different codes.
INV-TAX-007  [Class C] No new runs referencing deprecated taxonomy types after
             grace period (7 days post-deprecation).
INV-TAX-008  [Class C] No task type with insufficient observations used in routing.
```

---

## 11. Dangerous Shortcuts

- Using task_type as a free-form TEXT field "until the taxonomy is ready" — the FK must be live before the first run record
- Adding task_type_id as a nullable column — NOT NULL from day one
- Prose-only complexity definitions — must be machine-implementable
- Informal task type additions without RFC — governance gate is non-negotiable
- Not recording `task_classifier_version` on run records — required for replay
