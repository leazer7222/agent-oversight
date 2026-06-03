# Lessons - Codebase Context Agent

Standing rules specific to this agent. Add entries after corrections or discoveries.
Format: `[YYYY-MM-DD] | what went wrong or was discovered | rule to apply going forward`

These seed entries are the design decisions sealed during the BA/CCA architecture threads. They are
binding from day one.

---

- [2026-06-02] | The agent describes WHAT IS, never WHAT SHOULD BE | The CCA emits code-side facts only - entities, actors, capabilities, signals, glossary, coverage, evidence. It never emits `CON-*`, Decisions, Questions, Rules, Attributes, PRDs, or recommendations. The moment it asserts a product Concept it has stepped into BA territory.

- [2026-06-02] | A finding with no evidence is an opinion | Every entity/actor/capability/signal claim must cite at least one `evidence` (path + optional lines) at `commit_sha`, or it is not emitted. (Mirrors the code-review-agent "findings must cite sources" rule.)

- [2026-06-02] | Negative findings are explicit, never silence | "Material does not exist" is an `entities[]` row with `exists:false` plus a `concept_resolution[]` entry - never the absence of a row. Silent absence reads as "didn't look", which is the worst failure. Always show the `coverage` denominator.

- [2026-06-02] | `concepts_to_check` is additive, never narrowing | It directs existence-checking only. The full `domain_signals` sweep and honest `coverage` ALWAYS run. The single most valuable signal in practice (market-scoping) came from a signal nobody asked about. A future "optimization" that prunes the sweep to requested nouns destroys the agent's main value.

- [2026-06-02] | cbc:* identity is owned by a registry, not by a name | A name-derived ID is a natural key and is NOT stable under rename. The registry (`platform.cbc_identity_registry`) owns identity; the convention only MINTS. Frozen at first mint, opaque for life. Renames update `current_name`/`aka[]` and emit a `rename` event; the ID never changes.

- [2026-06-02] | Freeze on consumption, including `exists:false` | Once the BA stores a cbc_id in `maps_to_codebase[]` (even for an absent entity), it is authoritative. Later implementation binds the real table onto the pre-assigned ID via `cbc_implement`; it never mints a parallel ID. This is what makes "absent-to-present keeps the same ID" enforceable.

- [2026-06-02] | Divergent-name realization is a candidate, not an auto-bind | When an absent `cbc:entity:material` later ships as `product_materials`: exact-or-alias match -> `cbc_implement`; no confident match -> mint a new id AND emit a `possible_realization` event (`cbc_propose_realization`) for BA/human merge confirmation. Never silently auto-bind across a name divergence - it risks mis-binding.

- [2026-06-02] | Merge collapses toward the EARLIER (BA-consumed) id | `cbc_merge` enforces `survivor.created_at <= throwaway.created_at`. A BA-consumed id always survives so `maps_to_codebase[]` never dangles. Never collapse toward the newer id.

- [2026-06-02] | cbc names follow CODE identifiers, never product nouns | If the code says `contractor`, the id is `cbc:actor:contractor` and the glossary maps `contractor <-> service_provider`. The one exception by necessity: an absent entity has no code name, so its provisional id is minted from the normalized requested noun. Do not let a product noun name a cbc id for an entity that exists in code under a different name.

- [2026-06-02] | Never analyze the wrong tree silently | Resolve `ref` -> `commit_sha` once at run start, thread it through, and ASSERT `HEAD == commit_sha` after clone. A partial/truncated clone shows up as suspiciously low `coverage` - report the denominator so it surfaces instead of producing a confident-but-empty artifact.

- [2026-06-02] | The clone is ephemeral and the agent never writes the target | Read-only clone into a gitignored `.workspace/<target_key>@<sha>/`, torn down after artifact write (or LRU-cached by immutable SHA). Add `.workspace/` to `.gitignore` immediately - worktrees/clones staged as gitlinks (mode 160000) break CI checkout (see LESSONS_LEARNED Netlify section).

- [2026-06-02] | The GitHub credential is read-only and single-repo scoped | `GITHUB_CODEBASE_AGENT_TOKEN` must be read-only contents scope on the target repo only. If the token can write the target, the design is wrong. Never persist the token into the clone's git config or the artifact/logs.

- [2026-06-02] | The registry makes this agent stateful in the DB, not in process | The agent process is stateless per run; durable state lives in `platform.cbc_identity_registry`. It is hybrid-mutability (block DELETE, allow INSERT/UPDATE) - do NOT apply `apply_append_only_rls()` to it (that is only for the append-only `cbc_registry_events`). See LESSONS_LEARNED "apply_append_only_rls is NOT for mixed-mutability tables".

- [2026-06-02] | Non-public schema access needs SECURITY DEFINER RPCs | `platform.cbc_identity_registry` is not exposed by PostgREST. Mint/rename/implement/merge/resolve ONLY through the `public.cbc_*` functions (migration 025). Never try `supabase.schema('platform').from('cbc_identity_registry')` - it silently returns null.

- [2026-06-02] | Production telemetry uses the production secret and URL | `AGENT_OVERSIGHT_SECRET` (not `OVERSIGHT_SECRET`/`INGEST_SECRET`) and `OVERSIGHT_URL=https://agent-oversight.vercel.app` (not the old Netlify URL). The dev-server secret silently fails against production.

- [2026-06-02] | Resolve the tenant/company by name, never `LIMIT 1` | The registration script and any company lookup resolve ReformAI by exact name or explicit UUID. Multiple companies exist (ReformAI, AfterGlow, Personal) and order is not guaranteed. (Mirrors the quota-sync provider_accounts split bug.)
