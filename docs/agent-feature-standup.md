# Feature Standup Agent

Status: DRAFT (design only - not built, not registered) | Owner: `reformai` | Type: capability within Agent Oversight
Last updated: 2026-06-24

This document specifies the **Feature Standup Agent**: a daily agent that, at ~06:00 every day,
compiles where each feature you are working on stands, what the next step is, and how important it
is - across BOTH personal and ReformAI work, grouped by project. It also runs a decommission lens
over your Claude Code chats (still working on it, or can it be killed).

It is a capability inside the existing Agent Oversight framework, NOT new agent infrastructure.
Orchestration, oversight, telemetry, and scheduling already exist and are reused.

Working name: **Standup Agent** (`reformai.standup-agent`). Alternatives considered: Daybreak,
Compass, Ledger.

---

## 1. Problem statement (verbatim intent)

> "I have lots of different features that I am building both personal and reformai at the same time.
> Sometimes I forget where I am with them. At approximately 6:00 am every day, I want a compiled
> list of where I am at with each feature, the next steps, and the importance."

Plus a second, related ask: a single list of all open Claude Code chats - what each was working on,
whether it is still active, and whether it can be decommissioned.

These are the SAME agent viewed through two lenses:
- **Feature lens** -> the 6am digest (where am I, next step, importance), grouped by project.
- **Session lens** -> the decommission sweep (is this chat live or dead).
One inventory feeds both.

---

## 2. The core modeling decision: what is a "feature"?

A "feature" = a unit of work the user thinks of as one thing (e.g. "Supplier Catalog"). It does NOT
map cleanly to any single underlying artifact, because the work splits into incompatible patterns:

| Pattern | Example repo | Feature unit in the wild |
|---|---|---|
| PR-per-feature | `reformai` | a branch -> a PR (often a cloud worktree) |
| Straight-to-main | `agent-oversight` | no branch, no PR - WIP checkpoints on `main` |
| Script/utility work | `WebScraper`, `Visualization_Engine` | a PR sometimes, else just chats |

So no single artifact (branch, PR, or Jira story) is universal. **The anchor is a `feature_register`
row** that the agent assembles; underlying artifacts attach to it as evidence.

### Jira is an attribute, not the anchor
Only `reformai` design stories carry a Jira key. Everything else (agent-oversight, WebScraper,
Visualization_Engine, Landing Pages, Outdoor Glazed, ExcelLoader) has NO Jira link. If Jira were the
anchor the agent would see only reformai-design work and be blind to the majority. Therefore
`jira_key` is a **nullable attribute** of the register row, set only for the reformai-design subset.

### The only universal unit is the Claude Code chat
A feature may lack a Jira key, a PR, and a branch - but it always has at least one Claude Code chat.
The chat layer is therefore foundational: it is the substrate the agent clusters into features, and
the source of the decommission lens.

---

## 3. Architecture: four feeds into one register

```
  Jira (reformai design subset) ----------------\
                                                  \
  git + PR state via live `gh` (universal) -------+---> RECONCILE --> feature_register (Supabase)
                                                  /                          |
  memory / session-logs (narrative, delta) ------/                          |  you confirm
                                                 /                           |  importance / next_step
  Claude Code chats (universal, foundational) --/                           v
                                                                  DIGEST (grouped by project)
                                                                          |
                                          md file -> email -> dashboard -> Notion(P2)
                                                                          |
                                                                  write-back to memory layer
```

### 3.1 The four feeds

| # | Feed | Coverage | Supplies | Trust |
|---|---|---|---|---|
| 1 | **Jira** (live) | reformai-design only | status, sprint, priority | authoritative for its subset |
| 2 | **git + PR / `gh`** (live) | any work that branches/PRs | ship-state, branches, recency | authoritative; verified live |
| 3 | **Memory / session-logs** | any logged repo | next_step, blockers, decisions, daily delta | narrative; human-authored |
| 4 | **Claude Code chats** | EVERY feature | clustering substrate, decommission lens | lossy hint; always reconciled |

### 3.2 Hard rule: never trust the session cache
`list_sessions` metadata is stale. Observed: a chat reported `cwd=Landing Pages, PR #2, CLOSED` had
actually shipped via `PR #7, MERGED, deployed`. The cached `prNumber`, `prState`, AND `cwd` were all
wrong. Consequences (all mandatory):
- **Ship-state comes from live `gh`**, never the cached field. Scan the transcript for "Created PR
  #N / Merged PR #N", and/or match the branch via `gh pr list`, then `gh pr view` for ground truth.
- **A chat can reference multiple PRs over its life** (#2 abandoned -> #7 shipped). Take the
  latest/merged one as the outcome.
- **The project (`cwd`) can be wrong** - cross-check against where the PRs actually live.

### 3.3 PR keys are per-repo - always qualify
PR numbers collide across repos (multiple `#1`s, etc.). The register and digest MUST key PRs as
`repo + number` (e.g. `WebScraper#7`), never a bare number. A bare number is a guaranteed misread.

### 3.4 GitHub is multi-account, and not every project is a git repo
`gh` has TWO accounts in the keyring: `reformai-admin` (active; covers the `ReformAI-Inc` org +
`reformai-admin` repos) and `leazer7222` (personal). Repos span three owners:

| Repo | Owner | Account |
|---|---|---|
| `agent-oversight` | `leazer7222` | personal |
| `reformai` (Reform-AI) | `ReformAI-Inc` org | reformai-admin |
| `WebScraper` (web-scraper) | `ReformAI-Inc` org | reformai-admin |
| `Visualization_Engine` | `reformai-admin` | reformai-admin |

`gh` queries the ACTIVE account by default. To read a repo owned by the other account, target it
explicitly (`gh -R owner/repo`) and `gh auth switch` where access does not overlap. The agent must
resolve owner+account per repo, not assume one global account.

Also verified: `Outdoor Glazed`, `Landing Pages`, and `ReformAI_ExcelLoader` (at their session cwd)
are **NOT git repos**. For these, feed 2 is empty - they exist only as chats (feed 4) + memory
(feed 3). This is the strongest confirmation that the chat feed is foundational. Caveat: ExcelLoader
has merged PRs, so its git root is at a different path than the chat cwd - the agent must resolve the
actual repo root, never assume `cwd == git root`.

---

## 4. Data model: `feature_register`

Lives in Supabase next to the other agent data (NOT in Notion - Notion is a Phase 2 render target).
`status` is an OPEN text column, never a closed CHECK enum (per LESSONS_LEARNED: keep categorical
distinctions in an open column).

| column | type | purpose |
|---|---|---|
| `id` | uuid pk | identity |
| `project` | text | grouping key: `reformai`, `agent-oversight`, `webscraper`, ... |
| `slug` | text | local feature key, e.g. `supplier-catalog`, `viz-v8` |
| `name` | text | human-readable feature name |
| `summary` | text | one-line what-it-is |
| `jira_key` | text NULL | set only for reformai-design features |
| `status` | text (open) | `active` / `blocked` / `paused` / `shipped` / `decommission` |
| `next_step` | text | the one thing to do next |
| `importance` | text | agent-proposed (Jira-seeded where present) |
| `importance_locked` | bool | once you confirm, agent stops re-proposing |
| `evidence` | jsonb | `{ prs:[{repo,num,state}], branches:[], sessions:[], jira:{} }` |
| `last_touched` | timestamptz | max activity across all evidence |
| `last_signal` | text | what last moved it (sha / PR / chat / log) |
| `created_at` | timestamptz | NOT NULL DEFAULT now() |

One row per feature. Evidence aggregates {PRs, branches, sessions, Jira}, each verified live.

---

## 5. Feature definition: agent drafts, you confirm

For the non-Jira majority there is no external ID to anchor on, so the agent SYNTHESIZES feature
identity:
1. Cluster chats + PRs + branches per repo by topic similarity.
2. Propose a grouping + a `slug` + a `name` ("WebScraper has 4 chats that look like one feature:
   *property scoring* - confirm?").
3. You confirm / merge / split. The register row is never hand-built; you curate the draft.

For the reformai-design subset, the Jira story seeds the feature (1 story -> 1 feature), and chats /
PRs attach as evidence.

---

## 6. Naming convention (the chat -> feature join key)

The session title is currently the only thing tying a chat to a feature, and titles are ad-hoc
("Local setup", "Project overview" x2, "Rate limit reached error"). Proposed convention:

```
[<key>] <feature> - <what this chat does>
  [RAI-42] Supplier Catalog - schema + ingest        (key = Jira key, reformai-design)
  [RAI-42] Supplier Catalog - dashboard UI           (same feature, 2nd chat)
  [webscraper-scoring] Property Scoring - model v2    (key = local slug, everything else)
```

The `key` is EITHER a Jira key (reformai-design) OR a local slug (everything else). The agent groups
on the bracket; no bracket -> an "unfiled" bucket the digest nags you to triage.

- **Soft (Phase 1):** agent parses whatever convention it can + proposes renames; LLM fallback
  backfills meaning from transcript + git for legacy untitled chats. Zero friction.
- **Hard (later):** a Claude Code hook prompts for a `[key]` when a session lacks one.

---

## 7. The daily run (06:00)

The digest is a DELTA since the last run. The memory layer (feed 3) is what makes the delta
narratively meaningful ("blocked on Wompi sandbox keys" not "3 commits").

1. **Pull chat index** (cheap `list_sessions`) - the universal unit list.
2. **Compute delta** - chats with activity since last run; deep-read only those transcripts.
3. **Verify live** - resolve real PR/ship-state via `gh`; pull Jira for `jira_key` rows; read
   memory/session-logs for next_step + blockers.
4. **Reconcile** - update evidence, `last_touched`, `last_signal`; detect NEW features -> propose
   grouping (Section 5); detect stale/merged -> propose `decommission`.
5. **Propose importance** - from recency + blockers + sprint commitment + Jira priority; NEVER
   overwrite a row where `importance_locked=true`.
6. **Emit digest** - grouped by project, "needs attention" band on top (Section 8).
7. **Write-back** - `digests/YYYY-MM-DD.md` + a one-line append to each project's `current-state.md`
   so tomorrow's run (and any session you start) is primed.
8. **Telemetry** - `run_started` / `run_completed` to `/api/ingest` with tokens + cost.

Cost control: the full ~50-chat read is a one-time bootstrap + occasional GC, NOT the daily hot
path. Daily cost = index + the few chats that moved yesterday.

---

## 8. Digest layout

```
STANDUP - Tuesday June 24

== NEEDS YOUR ATTENTION ==
  [blocked]   Supplier Catalog (reformai)      - blocked on Wompi sandbox keys (3d)
  [stale]     Property Scoring (webscraper)    - no activity 9d
  [confirm?]  2 new features proposed; 1 importance proposal awaiting confirm

== REFORMAI ==
  P1  Supplier Catalog        RAI-42   blocked   next: get Wompi keys        (chat x2, no PR yet)
  P2  Service Providers       RAI-39   active    next: review PR             (reformai#52 OPEN)
  ...

== AGENT-OVERSIGHT ==
  P2  Standup Agent           -        active    next: write design doc      (this chat)
  ...

== DECOMMISSION CANDIDATES ==
  Website vibe analysis  - shipped reformai#7, merged + deployed  -> archive chat
```

Within each project, sorted by importance. Each line: importance, feature, jira_key (or `-`),
status, next step, evidence (live-verified).

---

## 9. Delivery channels (phased)

The digest IS a markdown artifact; every other channel renders it.

| Phase | Channel | Notes |
|---|---|---|
| 1 | **Markdown file** | `digests/YYYY-MM-DD.md`, committed. The canonical artifact. |
| 2 | **Email** | same markdown, sent ~06:00. Reuses the Jira PDF/email pattern. Highest-value channel. |
| 3 | **Dashboard page** | `/dashboard/features` - live register + latest digest. Where you confirm importance / next_step / groupings. |
| 4 | **Notion page** | optional mirror. Only after 1-3 earn their keep. |

State always lives in Supabase; Notion is a render target, not a source of truth.

---

## 10. Build phasing

| Phase | Scope | Gate to next |
|---|---|---|
| P1 | `feature_register` table; chat-index + git/`gh` feeds; clustering + draft groupings; md digest; bootstrap inventory | digest is trustworthy on a manual run |
| P2 | Jira feed (reformai-design subset); memory/session-log feed; write-back | reformai features show real Jira state |
| P3 | Email delivery + `0 6 * * *` cloud routine | lands in inbox at 6am unattended |
| P4 | `/dashboard/features` page (confirm importance / groupings) | you curate from the UI |
| P5 | Notion mirror; hard naming-convention hook | - |
| P6 | **Day Planner layer** (optional, decoupled): pull Google Calendar -> today's meetings -> free blocks -> suggest which feature `next_step` fits which slot, ranked by importance | core must stand alone without it |

### P6 - Day Planner (scope-creep parking lot, kept decoupled)
Adds a `== TODAY ==` digest section: meetings + free blocks, with each block mapped to a top
feature's `next_step`. Pairs the existing importance ranking with calendar gaps. New ingredient: a
rough effort estimate (t-shirt) per `next_step` so a step fits a block. Access: share the Gmail
calendar with the Google service account (`reformai-catalog-agent@reformai-agent.iam.gserviceaccount.com`,
same pattern as Drive) and read via Calendar API, OR a Google Calendar MCP. The status digest (P1-P3)
must NOT depend on this; the planner is purely additive.

---

## 11. Agent standards / registration (mandatory checklist)

- Registered in Supabase `agents` as instance `reformai.standup-agent` (definition + instance UUIDs).
- `README.md` + `agent.json` in the agent library dir.
- Emits `run_started` / `run_completed` per run with unique `run_id`; reports tokens + cost.
- Declares MCP deps (Jira/Atlassian, Notion P2) in `agent.json`.
- `LESSONS.md` for standing rules (e.g. "never trust the session cache").

---

## 12. Scheduling

`0 6 * * *` via a cloud routine (the `/schedule` skill), NOT a local guardian-style job - the cloud
routine survives the machine being off. Wired once the agent runs clean manually.

---

## 13. Open questions (to resolve before build)

1. **Name** - Standup vs Daybreak / Compass / Ledger.
2. **Non-git projects** - Outdoor Glazed / Landing Pages / ExcelLoader-at-cwd have no feed 2 (chats
   only). Confirmed acceptable (chat feed covers them), but: are any of these dormant enough to
   exclude from v1 entirely?
3. **Importance scale** - P0-P3, 1-5, or H/M/L?
4. **Email target + sender** - reuse the Jira agent's send path?
5. **Bootstrap scope** - seed the register from all ~50 chats at once, or only the ~7 currently-live
   ones and let the rest get picked up by the GC pass?
6. **Day Planner (P6)** - is the Calendar layer in scope for the roadmap at all, and is Calendar
   access via the shared service account or a dedicated Calendar MCP?
7. **Effort estimates** - P6 needs a t-shirt size per `next_step` to fit calendar blocks. Agent
   proposes these too (consistent with importance), or skip until P6?
```
