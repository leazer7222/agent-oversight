# Runtime Workflow - Codebase Context Agent

The run flow for the P1 **deterministic truth service**. Deterministic parsers discover structure; the
LLM only LABELS. The v1 single-LLM-call flow (LLM discovers entities) is RETIRED. Runtime: `pipeline.py`
(`agent.py` delegates to it). The agent process is stateless per run; durable state lives in
`platform.cbc_identity_registry` and `public.codebase_context_cache`. Telemetry is wrapped via
`OversightClient.run(...)`; it degrades gracefully (`NullRunCtx`) when the instance is paused.

## Flow (pipeline.py)

| # | Step | Action | Telemetry step |
|---|---|---|---|
| 1 | Acquire + pin | Local checkout (v1); `git rev-parse HEAD` -> `commit_sha` (clone/auth deferred) | - |
| 2 | Cache check | `codebase_context_cache` by `(product_key, repo, commit_sha, parser_version)` - HIT reuses inventory+coverage+semantic, skips 3-5 | `cache_hit` |
| 3 | Build inventory (deterministic) | Mechanism A: drizzle snapshot -> entities/enums/relations. Mechanism B: source scan -> actors/routes/capabilities/integrations. cbc minting (authoritative) | `inventory_built` |
| 4 | Coverage | Per-layer green/yellow/red + snapshot-vs-source completeness guard | `coverage_built` |
| 5 | Cache write | Upsert inventory + coverage (+ semantic) into `codebase_context_cache` | `cache_written` |
| 6 | Resolve concepts (Tier-1) | Deterministic match; `not_found` ONLY on green coverage, else `indeterminate` | - |
| 7 | Semantic (label-only, optional) | LLM labels domain_signals/glossary over the inventory; drops any cbc id not in it. Cached | `semantic_labeled` |
| 8 | Compose BA view | Map to the existing `codebase-context.schema.json`; **jsonschema validate** | `composed_validated` |
| 9 | Publish + register | `codebase_context` + `concept_resolution` to `agent_outputs`; register cbc ids (skipped on cache hit) | `published` |

**parser_version** (`cca-parser-v1.1`) is part of the cache key: a parser-logic change invalidates the
cache even at an unchanged commit. **cbc minting:** the deterministic parser is the sole authoritative
minter (C1 Option A); normalize (`lowercase -> snake_case -> singularize -> strip non-alphanumerics`)
and `public.cbc_register_or_get`. See [identity-registry.md](identity-registry.md).

## Controlled-workspace lifecycle

1. Resolve `ref` -> `commit_sha` (immutable handle for everything downstream).
2. Clone read-only into `.workspace/<target_key>@<sha>/` (shallow for branch tips; full for historical SHAs).
3. Assert `HEAD == commit_sha`. Abort otherwise.
4. Analyze read-only - never write the target, never `npm install` it (source read only).
5. Tear down the clone after artifact write, or keep an LRU cache keyed by the immutable SHA.

`.workspace/` is gitignored. The GitHub credential is read-only, single-repo scoped, and never
persisted into the clone config, the artifact, or logs.

## Telemetry rules

- Every meaningful step emits `run.step(name, message=..., duration_ms=t.ms, payload={...})`.
- Step emission is non-fatal - wrap in try/except, never let it block analysis.
- On completion report `tokens_in`, `tokens_out`, `cost_usd` (the LLM usage object from the
  signal/glossary extraction calls). A null `cost_usd` without reporting is indistinguishable from
  "didn't report" - always report, even if zero.
- Errors are categorized by the SDK (`quota_exceeded | auth_error | network_error | llm_error |
  validation_error`) and stored on `runs.error` as `[category] message`.

## Idempotency

- Artifact identity is `(target_key, commit_sha, feature_intent)`. Re-running the same triple should
  produce an equivalent artifact (a clone of an immutable SHA is deterministic).
- `public.cbc_register_or_get` is idempotent on `cbc_id` - re-running a pass returns the existing
  identity rather than minting a duplicate.
- Registry mutations (rename/implement/merge) are guarded by the migration-025 triggers and status
  checks, so re-emission is safe.

## Remaining steps before activation

The agent is **registered (DB), runtime pending**. To move to operationally active:

1. Apply migration `025_cbc_identity_registry.sql` (and its dependency 012) to project
   `hdhovyrlnfojtkqbcegh`. Pass `python scripts/check_migrations.py --from-migration 013` first.
2. Implement `agent.py` runtime (steps 1-13 above) using `python-sdk/oversight.py`.
3. Provision `GITHUB_CODEBASE_AGENT_TOKEN` (read-only, single-repo) and confirm the target registry
   entry for `reformai-product`.
4. Add `.workspace/` to `.gitignore`.
5. Smoke test against the real `reformai-product` repo for the materials-catalogue feature; confirm a
   schema-valid artifact and the expected `concept_resolution[]`.
6. Validate the artifact round-trips into the BA Agent (handoff).
7. Flip `agents.status` -> `active` and `metadata.runtime_implemented` -> `true` only after the smoke
   test passes.
