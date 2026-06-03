# Runtime Workflow - Codebase Context Agent

The complete run flow from a target-key + feature intent to a stored `codebase_context` artifact. The
agent process is stateless per run; durable identity state lives in `platform.cbc_identity_registry`.
Wrap the whole run in `OversightClient.run(...)` so `run_started` / `run_completed` / `run_failed` are
emitted with a single `run_id`.

## Flow

| # | Step | Action | Telemetry step | Failure mode |
|---|---|---|---|---|
| 1 | Validate input | Check `target_key`, `ref`, `feature_intent` present | `input_validated` | `validation_error` -> abort |
| 2 | Resolve target | `target_key` -> repo URL + read-only credential via the target registry | `target_resolved` | abort if unknown target / missing token |
| 3 | Resolve ref | `git ls-remote` resolves `ref` -> concrete `commit_sha` (no full clone needed) | `ref_resolved` | abort if ref not found |
| 4 | Clone read-only | Shallow clone into `.workspace/<target_key>@<sha>/`; **assert `HEAD == commit_sha`** | `repo_cloned` | abort on SHA mismatch (never analyze the wrong tree) |
| 5 | Map repo | Walk `include_globs`, skip `exclude_globs`; build the file inventory for `coverage` | `repo_mapped` | non-fatal; record omissions |
| 6 | Extract entities | Schema/models/migrations -> code-side `entities[]` (fields + `semantic_hint`, relationships) with evidence | `entities_extracted` | - |
| 7 | Extract actors + capabilities | Auth roles -> `actors[]`; service/route modules -> `capabilities[]`, with evidence | `actors_capabilities_extracted` | - |
| 8 | Domain-signal sweep | Full, unrequested sweep (market-scoping, multi-tenancy, currency/locale, soft-delete) | `domain_signals_swept` | - |
| 9 | Build glossary | Code terms + `aka[]` -> `maps_to` cbc:* | `glossary_built` | - |
| 10 | Existence-check | `feature_intent` nouns + `concepts_to_check[]` -> `exists` flags + `concept_resolution[]` | `existence_checked` | - |
| 11 | Reconcile registry | Mint/resolve cbc:* via `public.cbc_*`; rename/implement/possible_realization as needed; emit `registry_events[]` | `registry_reconciled` | registry write fatal (identity integrity) |
| 12 | Compute coverage | `scanned_paths`, `omitted`, `files_scanned/total`, `confidence` | `coverage_computed` | - |
| 13 | Emit artifact + render | Validate against `codebase-context.schema.json`; write `codebase_context` to `agent_outputs`; render `codebase-context.md`; tear down clone; `run.report(...)` | (run_completed) | schema-validation fatal; telemetry non-fatal |

**cbc minting (step 11):** for a NEW identity, normalize the name
(`lowercase -> snake_case -> singularize -> strip non-alphanumerics`) and call
`public.cbc_register_or_get`. The registry is the sole authority for whether an ID already exists; the
runtime never decides identity by string comparison against the artifact. See
[identity-registry.md](identity-registry.md).

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
