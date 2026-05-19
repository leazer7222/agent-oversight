## Summary

<!-- What does this PR do and why? -->

---

## Type of Change

- [ ] Feature implementation
- [ ] Bug fix
- [ ] Schema change (migration)
- [ ] RFC amendment
- [ ] Documentation
- [ ] Refactor
- [ ] Other: ___

---

## Schema Change Checklist

> Complete this section for any PR that modifies a database table, event payload, or API contract.
> Skip if this PR contains no schema changes.

### Three-Truth-Surface Review

- [ ] I have identified which truth surface owns every new or modified field
- [ ] No execution truth fields exist on decision artifact tables (`estimate_artifacts`, `recommendation_artifacts`, `budget_reservations`)
- [ ] No decision truth fields exist on execution record tables (`run_records`, `raw_events`, `settlement_records`)
- [ ] No outcome truth is derived from decision truth without going through execution
- [ ] This field is not a duplicate of a field that exists on a different truth surface

For fields whose **meaning is changing** (not just new fields):
- [ ] The field's new meaning belongs to the same truth surface as its old meaning
- [ ] If the meaning changed surfaces, a new field was added and the old deprecated

**I confirm I have consciously asked: "Which truth surface owns this field?"**

Reviewer signature: _______________

### Schema Evolution Compliance (RFC-009)

- [ ] No `TIMESTAMP` (without TZ) columns — use `TIMESTAMPTZ`
- [ ] No `SERIAL` or `BIGSERIAL` primary keys — use `UUID DEFAULT gen_random_uuid()`
- [ ] No `ON DELETE CASCADE` on Class I (immutable artifact) tables
- [ ] New tables include `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- [ ] New artifact tables will have `platform.apply_append_only_rls()` called after creation
- [ ] Enum fields use `CHECK` constraints, not PostgreSQL `ENUM` types
- [ ] JSONB columns have descriptive suffix (`_snapshot`, `_definition`, `_data`, `_payload`)
- [ ] `schema_version` field bumped if artifact table schema changed (MINOR or MAJOR)
- [ ] New deprecated fields have an entry in `platform.schema_registry`

### Breaking Changes

- [ ] This PR contains a MAJOR schema change (field removal, rename, type change, meaning change)

If yes — RFC amendment reference: RFC-___

---

## Testing

- [ ] Migration runs without errors on a local/staging database
- [ ] Existing tests pass
- [ ] New tests added for changed behavior
- [ ] If runtime governance change: concurrency and idempotency tested

---

## Notes for Reviewer

<!-- Anything specific the reviewer should look at, or context they need -->
