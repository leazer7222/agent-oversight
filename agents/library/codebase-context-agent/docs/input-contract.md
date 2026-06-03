# Input Contract - Codebase Context Agent

## Invocation inputs

| Field | Type | Required | Notes |
|---|---|---|---|
| `target_key` | string | Yes | Resolves to a repo URL + read-only credential via the target registry. Mirrors the BA's `product_key` (e.g. `reformai-product`). |
| `ref` | string | Yes | Branch, tag, or SHA. Resolved to a concrete `commit_sha` at run start and pinned for the whole run. |
| `feature_intent` | string | Yes | Drives existence-check coverage and the focus of the human `.md` brief. Does NOT narrow the entity/signal sweep. |
| `concepts_to_check` | string[] \| object[] | No | Directed existence-check list. Additive only. Entries are plain nouns (`"Material"`) or typed (`{"noun": "Supplier", "expected_kind": "actor"}`). |

The agent does **not** consume the product graph (`CON-*`). The glossary is produced from code, not
consumed. The only registry it reads is its own `platform.cbc_identity_registry` (via `public.cbc_*`).

## Mandatory vs optional

- **Mandatory grounding:** `target_key`, `ref`, `feature_intent`. These determine the tree analyzed
  and what gets existence-checked.
- **Optional signal:** `concepts_to_check` - a relevance hint that directs existence-checking, never a
  filter on the sweep.

## Target resolution

`target_key` is resolved through the target registry to `{repo_url, default_branch, auth,
include_globs, exclude_globs}`. The credential (`GITHUB_CODEBASE_AGENT_TOKEN`) is read-only and
single-repo scoped. The agent clones read-only into an ephemeral `.workspace/<target_key>@<sha>/` and
asserts `HEAD == commit_sha` before analyzing. It never writes the target repo.

## concepts_to_check semantics (HARD INVARIANT)

`concepts_to_check` is **additive only**. It directs the agent's existence-checking; it never narrows
the `domain_signals` sweep or `coverage`. The single most valuable signal in practice (market-scoping)
came from a signal nobody asked about - so the agent always runs the full sweep and reports honest
coverage, then *additionally* resolves every requested noun.

A future optimization MUST NOT prune the sweep to only the requested nouns. This is recorded in
[LESSONS.md](../LESSONS.md) and the schema description.

Typed entries carry an optional `expected_kind` (`entity | actor | capability`) to help disambiguation
(e.g. is "Supplier" an entity, an actor, or both), while plain strings remain valid.

## Commit pinning

`ref` is resolved to a concrete `commit_sha` exactly once at run start and threaded through every step.
The artifact is stamped with `repo`, `commit_sha`, `ref_requested`. Artifact identity is
`(target_key, commit_sha, feature_intent)` - re-running the same triple is reproducible because a clone
of an immutable SHA is deterministic.

## No silent assumptions

Everything the agent asserts as code reality must cite `evidence` (path + optional lines) at
`commit_sha`. Anything it cannot find is reported as a negative finding (`exists:false` +
`concept_resolution[]`), never as silence. Anything it did not scan is reported in `coverage.omitted`.
The agent never fills a gap silently - it surfaces it.
