# Feature Re-Entry Agent (v2)

Status: DRAFT v2 (design only - not built) | Owner: `reformai` | Type: capability within Agent Oversight
Last updated: 2026-06-24
Supersedes: `docs/agent-feature-standup.md` (v1). v1 is retained for history; this is the design of record.

This v2 is a deliberate redesign after an adversarial review of v1. v1 over-committed to a scheduled,
cloud, register-backed, multi-project "status report" before resolving its riskiest assumptions. v2
is leaner, more honest about what is reliable, and sequenced so the cheapest version proves the value
before any expensive infrastructure is built.

Name: **Compass** (settled). Phase-1 form: a **Claude Code slash command** `/compass` (settled).

---

## 0. What changed from v1, and why (the redesign in one table)

| # | v1 said | v2 says | Why |
|---|---|---|---|
| A | Scheduled cloud routine at 06:00 | **On-demand local command first**; schedule only after proven | The chat feed reads LOCAL files - a cloud cron cannot see them if the machine is off (v1's fatal contradiction). And daily push is the most-ignored automation genre. |
| B | "Status report" (where everything stands) | **Re-entry briefing** (what you need to resume THIS) | The real pain is context-restoration on switch, not a list. Reframes every field. |
| C | `feature_register` caches derived data | **Overlay** persists only human-added facts; derive the rest live | A cache of 4 source systems is a guaranteed drift surface (the exact failure class in LESSONS_LEARNED). |
| D | Agent proposes importance from activity | **Importance = human, sticky**; **neglect = computed**; two axes, never conflated | Activity-based importance is anti-correlated with truth - the important thing is often the one you are avoiding. |
| E | Agent clusters chats from scratch each run | **Deterministic-first + sticky**; LLM only on residual unfiled chats | Clustering 50 noisy transcripts is the fuzziest task; make it shrink each use, not re-roll nightly. |
| F | "Next step" inferred and presented as fact | **Provenance-tagged**; ask when unknown, never hallucinate | A confidently-wrong next step at 6am is worse than a blank. |
| G | You type `[KEY]` titles; Notion feed; hard hook | **Agent maintains the naming convention** (renames); Notion + hard hook dropped from core | Do not build feeds on aspirational discipline you do not have yet. |
| H | Default = all 7 projects | **All projects by default** (the whole point); narrow to one with `/compass here` (cwd) or `/compass <project>` | The product exists to fix cross-project memory loss. Single-project is a deliberate focus mode, not the default. Manage firehose via the IMPORTANT x NEGLECTED band + grouping, not by hiding projects. |
| I | Decommission lens in the daily path | **Separate, conservative, weekly sweep**; suggest-only, bias-keep | A wrong "kill" costs work; a wrong "keep" costs nothing - asymmetric, so lopsided bar + different cadence. |

---

## 1. Problem statement (verbatim intent)

> "I have lots of different features that I am building both personal and reformai at the same time.
> Sometimes I forget where I am with them ... I want a compiled list of where I am at with each
> feature, the next steps, and the importance."

Reframed (change B): the underlying need is **fast re-entry into a feature's context after switching
away from it**, across many projects. The deliverable is a briefing that gets you back to work, not a
status table you read and archive.

Secondary ask: a single view of all Claude Code chats - still live, or decommissionable (change I:
this is a separate weekly sweep, not the daily briefing).

---

## 2. What a "feature" is (unchanged core, leaner storage)

A feature = a unit of work the user thinks of as one thing. It maps to no single artifact, because
work splits into incompatible patterns:

| Pattern | Example repo | Unit in the wild |
|---|---|---|
| PR-per-feature | `reformai` | branch -> PR (often a cloud worktree) |
| Straight-to-main | `agent-oversight` | no branch/PR - WIP checkpoints on `main` |
| Chats-only (no git) | `Outdoor Glazed`, `Landing Pages` | only Claude Code chats |

The only universal unit is the **Claude Code chat** - every feature has at least one; many features
have no Jira key, no PR, no branch. So the chat layer is foundational. Jira is a nullable attribute
of one subset (reformai-design), never the anchor.

---

## 3. Storage model: overlay, not register (change C)

Persist ONLY facts a human added that cannot be derived from a source system. Everything else is
recomputed live each run. This eliminates drift by construction.

### 3.1 What is persisted (`feature_overlay`)
| column | type | persisted because... |
|---|---|---|
| `id` | uuid pk | identity |
| `project` | text | grouping key |
| `slug` | text | confirmed local feature key |
| `name` | text | human-readable name (confirmable) |
| `member_keys` | jsonb | **confirmed grouping**: which chats/PRs/branches belong (sticky - change E) |
| `importance` | text NULL | **human-set only; NULL = needs triage** (change D) |
| `next_step_override` | text NULL | human-authored next step that wins over inference (change F) |
| `decommission_decision` | text NULL | human verdict from the weekly sweep (change I) |
| `jira_key` | text NULL | reformai-design subset only |
| `created_at` | timestamptz | NOT NULL DEFAULT now() |

### 3.2 What is NEVER persisted (derived live every run)
status, ship-state, evidence, last_touched, last_signal, neglect score, inferred next step. These all
have a source of truth (`gh` / Jira / chats / session-logs); storing them = a cache = drift.

For the on-demand probe (Phase 1), the overlay can even be a single committed JSON/markdown file
(`.standup/overlay.json`) - no DB needed until the scheduled version.

---

## 4. The four feeds (coverage + trust)

| # | Feed | Coverage | Supplies | Trust |
|---|---|---|---|---|
| 1 | Jira (live) | reformai-design only | status, sprint, priority | authoritative for its subset |
| 2 | git + PR / `gh` (live) | repos that branch/PR | ship-state, branches, recency | authoritative; verified live |
| 3 | memory / session-logs | logged repos | **next_step (logged)**, blockers, decisions | human-authored narrative |
| 4 | Claude Code chats | EVERY feature | clustering substrate, re-entry context | lossy hint; always reconciled |

### 4.1 Hard rules carried over from the live investigation
- **Never trust the session cache.** Observed: a chat cached as `PR #2 CLOSED, cwd=Landing Pages` had
  actually shipped via `PR #7 MERGED + deployed`, labeled `agent-oversight`. Resolve ship-state from
  live `gh` (scan transcript for "Created/Merged PR #N", match branch via `gh pr list`, then
  `gh pr view`). A chat may reference multiple PRs over its life - take the latest/merged as outcome.
- **PR keys are per-repo** - always `repo + number` (`WebScraper#7`), never a bare number.
- **GitHub is multi-account.** `gh` keyring has `reformai-admin` (active; `ReformAI-Inc` org +
  `reformai-admin` repos) and `leazer7222` (personal). Target repos explicitly (`gh -R owner/repo`),
  `gh auth switch` where access does not overlap.
- **cwd != git root.** Some project cwds are not git repos (`Outdoor Glazed`, `Landing Pages`) or have
  their git root elsewhere (`ExcelLoader`). Resolve the real repo root; never assume.

---

## 5. The two-axis model: importance vs neglect (change D)

Never conflate these. They are orthogonal and the valuable signal is their intersection.

- **Importance** - human-set, sticky, defaults to NULL ("needs triage"). The agent NEVER guesses it.
- **Neglect** - computed each run: days since activity, blocked-age, sprint-commitment-vs-movement.

The briefing leads with the cell that matters most: **high importance x high neglect = "the important
thing you are avoiding."** Untriaged-but-active features get a gentle "set importance?" nudge. The
agent's job is to surface neglect against your importance, not to invent importance.

---

## 6. Clustering: deterministic-first, sticky (change E)

1. **Hard-key pass (deterministic):** group by `jira_key`, branch, `repo+PR`, and the `[key]` title
   prefix. This resolves most chats with zero LLM guesswork.
2. **Sticky pass:** any grouping already confirmed in `member_keys` is locked - never re-clustered.
3. **Residual pass (LLM, last resort):** only the still-unfiled chats are LLM-grouped, and presented
   as "guess - confirm?", never as authoritative.

Effect: the fuzzy surface SHRINKS every time you confirm a grouping, instead of being re-rolled (and
re-broken) on each run.

---

## 7. Provenance on every field (change F)

- Every `next_step` is tagged `[logged]` (from feed 3 / `next_step_override`) or `[inferred]` (from
  git/transcript). Inferred steps are clearly marked, never rendered as fact.
- When there is no logged next step, the agent **asks** ("Supplier Catalog has no recorded next step -
  what is it?") rather than inventing one. The answer is written to `next_step_override` and bootstraps
  session-log discipline.
- Same principle for ship-state: an entry derived from the stale cache without `gh` confirmation is
  marked `unverified` until reconciled.

---

## 8. The naming convention is the agent's job (change G)

Format: `[<key>] <feature> - <what this chat does>`, where `key` is a Jira key (reformai-design) or a
local slug (everything else). But **you never type it** - once the agent is confident of a chat's
grouping, it RENAMES the session to carry the `[key]` prefix itself. The convention becomes the
agent's self-maintained join key, not a discipline imposed on you. Chats it cannot place go to an
"unfiled" bucket the briefing surfaces for a one-line confirm.

Dropped from the core roadmap (change G): the Notion feed and the hard naming-hook. Both assume future
behavior change; revisit only if the proven core demands them.

---

## 9. The on-demand briefing (Phase 1 - the probe, change A)

Form: a **Claude Code slash command `/compass`** - a single markdown file at `.claude/commands/compass.md`
(or `~/.claude/commands/compass.md` to make it global across projects, which fits Compass's
cross-project nature). The file body IS the agent: it is the run sequence below written as a prompt,
executed in the current session with its tools (`gh`/git via Bash, the session-list MCP, Read for
session-logs). No Python, no DB, no registration in Phase 1. `$ARGUMENTS` carries flags; a `!`-prefixed
line can pre-embed `git`/`gh` output; `@.compass/overlay.json` embeds the overlay. The same logic moves
into a registered Python agent only when it graduates to the scheduled version (P4).

Invocation: run it when you sit down. **All projects by default** (the cross-project picture is the
point); narrow to a focus mode with `/compass here` (cwd's project only) or `/compass <project>`.

Run sequence:
1. Resolve scope: all projects (default), or one project from `here`/`<project>`.
2. Pull chat index for that project (cheap); deep-read only chats active since last briefing.
3. Verify live: `gh` ship-state, Jira for `jira_key` rows, session-logs for next_step + blockers.
4. Cluster (Section 6); apply sticky overlay; flag residual unfiled.
5. Compute neglect; read importance from overlay (Section 5).
6. Render the re-entry briefing (Section 10).
7. Capture any human answers (next-step prompts, grouping confirms, importance sets) back to the
   overlay; optionally rename chats (Section 8).

No schedule, no register, no cloud, no drift. This is the whole product until it earns more.

---

## 10. Briefing layout (re-entry framing, change B)

```
RE-ENTRY - reformai - Tue Jun 24

== IMPORTANT x NEGLECTED (resume these first) ==
  Supplier Catalog   [P1]  stalled 3d, blocked
     last decision : use roomMaterialOptions pattern, add Supplier as net-new entity
     blocker       : Wompi sandbox keys (3d)
     next step     : [logged] get Wompi keys from finance
     resume at     : reformai#52 (OPEN), chat "Supplier catalogue design analysis"

== ACTIVE ==
  Service Providers  [P2]  next: [logged] review PR    reformai#52 (OPEN)
  Data Quality Dash  [--]  next: [inferred] wire chart to RPC   <- set importance?

== NEEDS YOU ==
  next step unknown : Visualization materials extraction - what is the next step?
  unfiled chat      : "Local setup" - part of a feature, or noise?
```

Default scope is ALL projects, grouped under project headers (the mockup above shows one group);
`/compass here` collapses to the current project only. Each entry is built to get you BACK INTO the
work: last decision, blocker, provenance-tagged next step, and the exact place to resume. The
IMPORTANT x NEGLECTED band sits ABOVE the per-project groups so the one urgent thing is never buried
under organization - it spans all projects.

---

## 11. Decommission: separate weekly sweep (change I)

NOT in the daily briefing. A distinct `--decommission` (or weekly) pass over ALL chats:
- Flags a chat only when BOTH the cache AND live `gh` agree it is merged/closed AND no activity > N
  days. Bias-toward-keep: when in doubt, keep.
- Suggest-only; the human verdict is written to `decommission_decision`. The agent never archives
  anything itself in v1.
Rationale: a wrong "kill" costs real work/context; a wrong "keep" costs an un-archived chat.

---

## 12. Build phasing (re-sequenced)

| Phase | Scope | Gate to next |
|---|---|---|
| **P1 (probe)** | On-demand `/compass`; ALL projects by default (`here` to focus); overlay-as-file; feeds 2+4; deterministic clustering; re-entry briefing | You actually use it when you sit down, for ~2 weeks |
| P2 | Add feed 1 (Jira) + feed 3 (session-logs) + provenance prompts + agent-owned renames | reformai features show real Jira state; next-step prompts working |
| P3 | Overlay -> Supabase; weekly decommission sweep; `/compass here` focus mode polish | overlay durable |
| P4 | **Resolve cloud-vs-local** (see Section 13) + scheduled 06:00 delivery (md + email) | lands unattended only if Section 13 is solved |
| P5 | `/dashboard/features` (confirm importance / groupings in UI) | you curate from the UI |
| P6 | Day Planner (Calendar -> free blocks -> slot suggestions), fully decoupled and additive | core stands alone without it |

Notion + hard naming-hook are explicitly OUT unless the proven core demands them.

---

## 13. The cloud-vs-local decision (must resolve before P4)

The chat feed (feed 4) reads LOCAL files (`C:\Users\cjlea\.claude\projects\...`). A 06:00 cloud cron
cannot see them with the machine off. Mutually exclusive options - pick one at P4, not now:

- **Option L (local scheduled):** run on the machine via a local scheduler; machine must be on at
  06:00. Re-inherits the 5-hour-limit / guardian concerns this repo already manages.
- **Option S (sync-then-cloud):** continuously sync chat metadata (index + resolved PR/ship-state)
  into Supabase; the cloud runner reads the DB, not local disk. Cleaner schedule, but a whole new
  ingestion pipeline to build and keep honest.

P1-P3 dodge this entirely by being on-demand and local. The decision is deferred until the value is
proven - if the probe shows you prefer pulling on-demand, P4 may never be needed.

---

## 14. Agent standards / registration (when it graduates past the probe)

- Register as `reformai.compass` (definition + instance UUIDs) once it is a scheduled agent.
- `README.md` + `agent.json` + `LESSONS.md` (lead rule: "never trust the session cache").
- Emits `run_started` / `run_completed` with unique `run_id`, tokens, cost.
- Declares MCP deps (Jira/Atlassian; Calendar at P6) in `agent.json`.
- The Phase-1 probe is a local command and is NOT a registered agent - registration is a P4 concern.

---

## 15. Open questions

1. ~~Name~~ - SETTLED: **Compass**.
2. ~~Probe form~~ - SETTLED: **`/compass` slash command** (`.claude/commands/compass.md`).
3. **Importance scale** - P0-P3, 1-5, or H/M/L? (Human-set, so pick what you will actually maintain.)
4. **Neglect thresholds** - what "stalled N days" means per project (reformai vs a dormant personal repo differ).
5. **Cloud-vs-local (Section 13)** - only forced at P4; flag now if you already have a preference.
6. **Day Planner (P6)** - on the roadmap at all? Calendar via shared service account or a Calendar MCP?
