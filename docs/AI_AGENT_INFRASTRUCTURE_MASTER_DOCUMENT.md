# Document Purpose
This document is the persistent master record for the AI agent infrastructure project. It serves simultaneously as:
- an infrastructure architecture record
- a systems design journal
- an AI platform evolution log
- a PM learning document
- an interview preparation resource

# Document Role
Source of truth for:
- architecture evolution over time
- strategic tradeoff analysis and system-level reasoning
- cumulative operational lessons with PM interpretation
- interview-preparation framing grounded in real project decisions

Should live here:
- architectural retrospectives and maturity analysis
- strategic implications of technical decisions
- cumulative tradeoff history and milestone learnings

Should NOT live here:
- tactical session-by-session execution state
- live agent inventory snapshots
- per-agent implementation contract details

Related documents:
- Operational continuity checkpoints: `docs/HANDOFF_PROTOCOL.md`
- Phased MVP implementation sequencing: `docs/MVP_IMPLEMENTATION_ROADMAP.md`
- Agent inventory/status: `docs/AGENTS.md`
- Agent implementation/runtime standards: `docs/agent-standards.md`
- Repo-wide engineering standards: `docs/repo-standards.md`
- Concise chronological lesson log: `docs/LESSONS_LEARNED.md`
- Project entrypoint: `docs/README.md`

This is intentionally a living document, not a one-time audit artifact. It captures architecture decisions, tradeoffs, failures, assumptions, product implications, and lessons as the platform evolves from prototype into a production-grade agent control plane.

# How To Update This Document
Update rules:
1. Append major milestones chronologically in `# Architecture Evolution Timeline` and `# How This Project Evolved`.
2. Preserve previous architectural decisions; do not delete history unless factually incorrect.
3. For every meaningful change, include:
- what changed
- why it changed
- assumptions that changed
- tradeoffs considered
- lessons learned
- operational and PM impact
4. Track failures and incidents explicitly, including debugging outcomes and residual risk.
5. Distinguish:
- `Confirmed:` facts validated from repository code/schema/runtime checks
- `Inferred:` conclusions based on patterns, intent, or indirect evidence
- `Assumption:` unresolved interpretation to be validated later
6. Keep cumulative sections current:
- cumulative architecture evolution
- cumulative lessons learned
- cumulative tradeoff analysis
7. After each milestone, complete `# Milestone Update Template` and append as a dated entry.

# Architecture Evolution Timeline
1. Initial prototype phase
- Focus: proving end-to-end multi-agent generation flow quickly.
- Characteristics: local scripts, direct Python execution, minimal UI, rapid iteration over structure.
- Risk introduced: architecture and schema consistency lagged implementation speed.

2. ReformAI-focused evolution
- Focus: concrete vertical workflow (`context-agent` -> `marketing-agent` -> `ui-design-agent`) for real ReformAI output generation.
- Characteristics: per-company instance folder, orchestrator, local+Supabase output persistence, telemetry wrapper.
- Risk introduced: general control-plane capabilities remained underbuilt while single workflow matured.

3. Supabase reactivation + schema audit
- Focus: reconnecting to live Supabase and verifying real schema/data health.
- Characteristics: live table/view discovery, drift detection between migrations and code assumptions, exposure of missing migration coverage.
- Risk reduced: better understanding of actual platform state.
- Risk surfaced: migration/source-of-truth ambiguity and data contract drift.

4. Transition toward AgentOps/control-plane architecture
- Focus: moving from “agent execution scripts” toward “platform for observing/managing/executing many agents.”
- Characteristics: intention visible in schema (`projects`, `agent_events`, `policies`, cost summary views), but API/UI/runtime still only partially aligned.
- Primary challenge: close product architecture gap without over-engineering prematurely.

# Current System Maturity Assessment
## Prototype-level
- Frontend control plane UX is largely absent; `src/app/page.tsx` remains starter page and existing pages are domain mockup routes.
- Execution model is script/orchestrator-centric rather than queue- and policy-driven.
- Telemetry granularity is incomplete (lifecycle mostly, step/event/tool-call-level sparse).
- Config and secret handling patterns are development-heavy and unsafe for production posture.

## Production-leaning
- Clear repository organization for agent library vs instance deployments.
- Reusable Python telemetry client (`python-sdk/oversight.py`) with run lifecycle context manager.
- Supabase-backed persistence for core entities (`agents`, `runs`, `project_state`, `agent_outputs`) with active project connectivity.
- Strong intent toward platform governance visible in live schema (policies, event views, QA results, cost summaries).

## Missing for production readiness
- Canonical schema governance (live DB vs migration mismatch).
- Durable async execution control plane (run queue, retries, leases, cancellation, idempotency).
- End-to-end observability (run/event/tool traces, failure drill-down, SLO-oriented dashboards).
- Formal evaluation system tied to quality gates and release confidence.
- Secure, role-aware execution authorization and secret management.

## Biggest infrastructure risks
- Schema drift causes runtime fragility and onboarding confusion.
- Shared secret ingestion and plaintext local credential patterns increase security exposure.
- Cost/token fields exist but are weakly populated; financial observability remains low-confidence.
- Lack of standardized agent contract compliance tests allows hidden regressions.

## Biggest product risks
- Platform vision exceeds current UX/API capabilities, causing strategy-execution gap.
- Weak runtime and governance controls hinder trust for “execute from dashboard” use case.
- Without reliable metrics (quality, latency, cost, failure), PM decision-making remains intuition-heavy.

# Executive Summary
This repository is a serious in-progress transition from a practical multi-agent prototype into an AI AgentOps/control-plane platform.

`Confirmed:` The system combines:
- Next.js app + server routes
- Python agent runtime and orchestrator
- Supabase persistence and telemetry ingestion
- modular agent library and company instance structure

`Confirmed:` It already demonstrates critical platform primitives:
- agent identity
- run lifecycle events
- output persistence
- multi-company modeling intent

`Confirmed:` The live Supabase schema has evolved beyond local migrations and already contains control-plane-oriented entities (`projects`, `agent_events`, `policies`, QA and cost summary views), indicating product direction is ahead of repository migration hygiene.

`Inferred:` The project’s biggest value is not just output generation, but accelerated learning of architecture, operational tradeoffs, and PM judgment under ambiguity. The next maturity phase is contract hardening, observability depth, secure execution controls, and dashboard productization.

# Current System Architecture
## High-level architecture
`Confirmed:`
- Web/API layer: Next.js app-router project under `src/app`.
- Runtime layer: Python agents under `agents/library/*` and orchestrator under `agents/instances/reformai/orchestrator.py`.
- Telemetry layer: shared `OversightClient` in `python-sdk/oversight.py`.
- Persistence layer: Supabase PostgREST via service role access in server code and Python client usage.
- Operational artifacts: local output files under `agents/instances/reformai/outputs`.

## Current execution flow
`Confirmed:` typical reformai workflow:
1. Orchestrator receives goal.
2. Context agent reads Google Drive docs.
3. Marketing agent synthesizes strategy blueprint.
4. UI design agent generates frontend components/pages.
5. Outputs written to local filesystem and optionally to Supabase `agent_outputs`.
6. Run lifecycle events posted to `/api/ingest` (when configured correctly).

`Confirmed:` `/api/ingest` validates payload via Zod, authenticates using shared secret, checks agent status, and writes/upserts run state in `runs`.

## Architectural patterns currently used
`Confirmed:`
- Modular agent library pattern (`agents/library/<agent>/...`).
- Company deployment pattern (`agents/instances/<company>/...`).
- Orchestrator-to-worker chain pattern.
- SDK-encapsulated telemetry emission.
- API gateway-ish ingestion route as contract boundary.

`Inferred:`
- Platform is evolving toward event-driven control plane but currently still mostly synchronous and orchestrator-local.

## Data architecture state
`Confirmed from live schema + code audit:`
- Live schema includes broader entities/views than local migrations.
- API and runtime only exploit a subset, leaving advanced control-plane entities underused.
- Drift exists among:
  - local migrations (`supabase/migrations/*.sql`)
  - live schema (OpenAPI definitions from `/rest/v1/`)
  - API assumptions (`src/app/api/*`)

# Architectural Strengths
1. Clear modularity foundation
- `Confirmed:` agent code separation (context/marketing/ui/optimization/audit) and template-driven standardization intent.

2. Practical orchestration proof
- `Confirmed:` real, chained value delivery from context to strategy to UI artifacts.

3. Shared telemetry abstraction
- `Confirmed:` `OversightClient` enforces run lifecycle semantics and reduces duplicate lifecycle handling logic.

4. Early platform schema ambition
- `Confirmed:` live Supabase already includes policy, event, QA, and cost summary entities consistent with AgentOps direction.

5. Learning velocity
- `Inferred:` rapid iteration generated broad exposure to core AI infra concerns (runtime, schema, telemetry, model provider tradeoffs, output persistence).

# Architectural Weaknesses
1. Source-of-truth ambiguity
- `Confirmed:` migrations do not fully represent live schema.
- Impact: difficult reproducibility, onboarding, CI confidence.

2. Observability incompleteness
- `Confirmed:` event-level telemetry model exists live but runtime/API primarily use run-level lifecycle.

3. Execution architecture immaturity
- `Confirmed:` no durable queue/worker scheduler path in this repo for dashboard-triggered runs.

4. Security debt
- `Confirmed:` sensitive values appear in local config files and shared ingest secret model is weak for scaled multi-user operation.

5. Product surface gap
- `Confirmed:` control-plane UI/API features (agents list, run history/detail, execute actions, error investigation) are mostly unimplemented.

# Major Infrastructure Lessons Learned
## Cross-cutting lesson
Fast prototyping can successfully prove multi-agent product value, but if schema contracts and observability contracts are not locked early, later platform hardening gets expensive.

## What was attempted / worked / broke / learned
1. Attempted: direct orchestrator-driven chained generation
- Worked: end-to-end artifact output and meaningful workflow demonstration.
- Broke: generalization and governance lagged behind happy-path delivery.
- Learned: prototype workflows should still emit structured events from day one.

2. Attempted: local + Supabase dual persistence
- Worked: useful local debugging artifacts and cloud-backed records.
- Became difficult: consistency and lineage between local outputs and run/event entities.
- Learned: treat local outputs as cache/debug, not primary system-of-record.

3. Attempted: centralized ingest API
- Worked: unified authentication/checkpoint for run status transitions.
- Broke: mismatch risks when runtime assumptions drift from database contract.
- Learned: explicit versioned ingestion schema is necessary.

# Orchestration Lessons
`Confirmed observations from repo:`
- Orchestration is deterministic and synchronous.
- Context -> Marketing -> UI pattern is concrete and understandable.
- Audit step exists but is bypassed in orchestrator flow.

Lessons:
1. Deterministic chains accelerate learning
- Easy to debug and reason about.
- Good for early product demos.

2. Missing durable execution is the major scaling gap
- No persisted run request lifecycle, retry orchestration, timeout/backoff control plane.
- Failures in one step can leave partial outputs and weak run-state fidelity.

3. Orchestrator ownership boundaries must mature
- Current orchestrator has responsibilities spanning execution, persistence, and output file management.
- Future split should separate:
  - execution state machine
  - persistence adapters
  - artifact handlers

# Observability Lessons
`Confirmed:`
- Run lifecycle events are modeled and partially implemented.
- Live schema includes `agent_events` and cost summary views.
- Actual event/cost population appears sparse.

Lessons:
1. Lifecycle-only telemetry is insufficient
- Need per-step/phase/tool-call eventing for actionable debugging.

2. Cost observability requires discipline, not just fields
- `tokens_in/out` and `cost_usd` columns exist, but agent implementations need consistent reporting hooks.

3. Platform metrics should be first-class product features
- PM-critical metrics: success rate, rerun rate, median latency per agent, cost per successful outcome, output quality score, and error taxonomy trends.

# Database & Persistence Lessons
`Confirmed:`
- Supabase live DB includes richer control-plane schema than local migrations.
- Drift exists for core tables (`runs`, `project_state`, and beyond).

Lessons:
1. Migrations must represent reality
- A paused/reactivated project amplifies drift if migration discipline is weak.

2. Treat schema as product contract
- API and runtime should both derive from one canonical contract.

3. Introduce explicit lineage design
- run -> event -> artifact -> evaluation should be queryable as one graph.

4. Keep summary views derived, not hand-written into runtime
- Live summary views are promising; runtime should write raw facts consistently.

# Dashboard/Product Architecture Lessons
`Confirmed:`
- Control-plane dashboard isn’t implemented yet; current app root is starter scaffold.
- Existing UI routes are domain-specific generated pages, not platform operations pages.

Lessons:
1. Product narrative outran product surface
- Vision is clear, but user-facing capabilities are not yet aligned.

2. Build platform UI from observability backward
- First pages should be:
  - Agents
  - Runs
  - Run detail
  - Errors
  - Costs
- Execute action should come only after runtime policy controls are ready.

3. PM principle
- In AI systems, “manageability UX” is as important as “generation UX.”

# Security & Governance Lessons
`Confirmed:`
- Service role key and other sensitive values are present in local repo config.
- Shared secret ingestion model is used.
- Live schema includes `policies` and `audit_log`, but governance flow in code is minimal.

Lessons:
1. Security debt compounds quickly in AI infra
- Early convenience patterns (shared secrets, broad service-role use) become serious blockers for productionization.

2. Governance should be built as product capability
- Who can execute which agent, with what cost cap, under what approvals, must be explicit.

3. HITL must be intentional
- High-impact actions should support review/approval checkpoints.

# Runtime Reliability Lessons
`Confirmed:`
- Agents generally generate run IDs and use telemetry context manager pattern.
- Error handling exists but retry strategy is limited/inconsistent.

Lessons:
1. Reliability needs policy, not ad-hoc try/except
- Define retryable error classes, max attempts, timeout policies, and dead-letter treatment.

2. Contract tests reduce hidden fragility
- Every agent should pass standardized contract tests:
  - run_id consistency
  - lifecycle emission
  - error payload shape
  - token/cost report behavior

3. Runtime portability matters
- Hardcoded paths and environment assumptions hurt deployability and dashboard-driven execution compatibility.

# Product Management Lessons
1. AI platform PM scope is broader than feature PM
- Includes model behavior, reliability, observability, governance, and unit economics.

2. Metrics strategy must evolve early
- Traditional SaaS conversion and retention are insufficient.
- Need quality + cost + latency + failure + operator workload metrics.

3. Platform sequencing is strategic
- Build visibility and control before broadening execution autonomy.

4. PM/infra integration
- Schema and telemetry design are product decisions, not only engineering decisions, because they define what can be measured and managed.

# AI Infrastructure Concepts Learned
1. Orchestration
- Coordinating multi-agent workflows and dependency ordering.

2. Durable execution
- Need for persisted run state, retries, and resume semantics beyond in-process orchestration.

3. Telemetry and tracing
- Lifecycle events are minimum baseline; deep traces needed for root-cause analysis.

4. Evals
- Quality assessment must be structured and persisted (`agent_qa_results` direction is strong).

5. HITL
- Policy/approval checkpoints reduce risk for costly or sensitive actions.

6. Tool calling
- External tool integrations require strong contract boundaries and failure handling.

7. Agent contracts
- Standard manifests + runtime behavior contracts enable scaling across many agents.

8. Memory systems
- Current system mostly uses file/db persistence, not full retrieval memory architecture yet.

9. Model routing
- Provider/model switching appears in agent code; requires explicit policy and metrics.

10. Token economics
- Columns exist; consistent capture is needed to make cost tradeoffs real.

11. Governance
- Live `policies` schema indicates intended control-plane guardrails.

12. Reliability engineering for AI systems
- Error taxonomies, retries, run/event lineage, and quality confidence are essential.

# Tradeoffs and Decision Analysis
1. Speed vs architecture quality
- Decision: prioritize proof-of-value workflows.
- Benefit: rapid learning and tangible outcomes.
- Cost: schema drift and governance debt.

2. Custom orchestration vs external frameworks
- Decision: custom Python orchestrator.
- Benefit: full control and learning depth.
- Cost: must build durable execution, retries, state semantics manually.

3. Sync vs async execution
- Decision: synchronous local orchestration.
- Benefit: simpler mental model.
- Cost: brittle long-running behavior and weak operational control.

4. Flexibility vs standardization
- Decision: flexible per-agent evolution with evolving standards docs.
- Benefit: experimentation velocity.
- Cost: inconsistent runtime contract adherence.

5. Local outputs vs persistent storage
- Decision: keep both.
- Benefit: easy debugging and artifact review.
- Cost: potential source-of-truth confusion and lineage ambiguity.

6. Developer velocity vs governance
- Decision: defer strict controls to later phase.
- Benefit: faster build progress.
- Cost: production-readiness blockers accumulate.

# Biggest Technical Roadblocks
1. Schema drift between migrations, live DB, and code paths.
2. Incomplete telemetry depth and sparse cost/token population.
3. Missing durable execution mechanism.
4. Missing API surface for operational dashboards and execution control.
5. Security hardening gaps for secrets and execution authorization.

# Biggest Product Roadblocks
1. Platform promise > current product surface (dashboard not yet operationally useful).
2. Limited trust signals for operators (run detail quality, event visibility, eval confidence).
3. Ambiguity in target operating model (single-tenant learning lab vs multi-tenant production control plane).
4. Lack of explicit PM KPI framework for AI operations maturity.

# How This Project Evolved
## Phase narrative
1. Prototype execution lab
- Built practical agent workflows first.

2. Structured agent library and company instance pattern
- Introduced reusable architecture and beginnings of platform organization.

3. Telemetry and Supabase persistence
- Added shared oversight client and ingest API.

4. Live schema expansion + drift
- Live DB became richer than repo migrations.

5. Control-plane intent crystallization
- Need shifted from “can agents produce output?” to “can system be operated, governed, measured, and trusted?”

## Cumulative architecture evolution notes
- Strong trajectory toward AgentOps model is evident.
- Primary maturity gap is contract and governance rigor, not conceptual direction.

# What Would Be Done Differently
1. Lock schema governance earlier with migration discipline and automated drift checks.
2. Define run/event/tool-call telemetry contract before scaling agent count.
3. Introduce execution queue and idempotent run request model sooner.
4. Keep secrets out of repo-local plaintext and adopt environment/secret management from first iteration.
5. Build minimal operations dashboard in parallel with runtime to validate product assumptions continuously.

# Recommended Future Architecture
1. Canonical contract layer
- Single source for schema and API contracts.
- Automated checks for drift in CI.

2. Event-driven execution core
- `run_requests` + worker execution + step/event emission + completion summarization.

3. Observability-first model
- Persist raw events and derive summary views.
- Add failure taxonomy and incident-oriented diagnostics.

4. Governance framework
- Policy engine (cost caps, execution permissions, auto-pause on anomalies).
- HITL approval hooks for risky tasks.

5. Evaluation framework
- Persist structured eval scores and constraints checks for every significant run.

# Recommended MVP Priorities
1. Stabilize schema and migration truth.
2. Implement operational read APIs (`agents`, `runs`, `run detail`, `cost summaries`, `errors`).
3. Build minimal dashboard pages for visibility.
4. Implement secure, auditable execute-run request path.
5. Standardize runtime telemetry (tokens/cost/errors/events).
6. Add baseline tests: API contract, ingestion contract, agent runtime contract.

Avoid over-engineering now:
- Advanced model routers
- complex memory/vector architecture
- broad multi-cloud abstractions
until core control-plane loop is reliable.

# Interview Preparation Notes
## Strong architectural decisions to discuss
1. Chose modular agent-library + per-company instance architecture to separate reusable logic from deployment context.
2. Introduced centralized telemetry client and ingestion route to standardize lifecycle observability.
3. Evolved from single workflow mindset toward control-plane model with policy/eval/cost entities.

## Strong PM decisions to discuss
1. Prioritized proving value flow before broad platform build.
2. Used audits to convert technical debt into explicit roadmap priorities.
3. Framed schema and telemetry contracts as product decisions tied to trust and operability.

## Systems-thinking examples
1. Recognized that run-level telemetry without event-level lineage blocks root-cause and quality management.
2. Identified that local outputs are useful for development but not sufficient for platform observability.
3. Connected security/governance gaps directly to inability to safely enable dashboard-triggered execution.

# Strongest Stories for Interviews
1. Story: Prototype to platform pivot
- Situation: system produced outputs but lacked operational controls.
- Task: shift architecture toward controllability and observability.
- Action: audited runtime/API/schema, identified drift and missing control-plane primitives, prioritized architecture hardening roadmap.
- Result: clear maturation path from ad-hoc execution to AgentOps platform design.

2. Story: Ambiguity management under live schema drift
- Situation: migrations and live schema diverged after project pause/reactivation.
- Task: determine real system contract and reduce reliability risk.
- Action: validated live Supabase entities, compared with local code/migrations, isolated drift points and impact.
- Result: actionable reconciliation plan and clearer source-of-truth strategy.

3. Story: PM + architecture integration
- Situation: product goal required “execute/manage agents from dashboard,” but platform lacked observability/governance depth.
- Task: avoid premature UI work that would create unsafe controls.
- Action: sequenced roadmap: visibility first, secure execution second, advanced automation third.
- Result: product strategy grounded in operational reality and risk containment.

# Likely Interview Questions and Suggested Answers
1. Q: “How did you balance shipping speed with architectural rigor?”
- Suggested answer: “I deliberately optimized for proof-of-value first with a synchronous orchestrated flow, then used structured audits to convert discovered debt into explicit architecture milestones—schema contract hardening, observability depth, and secure execution controls.”

2. Q: “What was the biggest technical risk and how did you handle it?”
- Suggested answer: “Schema drift between migrations, live DB, and API assumptions. I validated the live schema directly, mapped drift impact by path, and created a contract-first remediation plan to make runtime/API/database consistent.”

3. Q: “How do AI platform metrics differ from traditional SaaS?”
- Suggested answer: “Beyond engagement metrics, I track operational trust metrics: run success rate, latency by agent/stage, cost per successful outcome, evaluation pass rates, error taxonomy trends, and rerun rates.”

4. Q: “What governance controls are required before enabling one-click execution?”
- Suggested answer: “Role-based execution permissions, policy-based cost caps, auditable execution requests, approval/HITL for risky runs, and strong telemetry so every action is attributable and diagnosable.”

5. Q: “Give an example of learning from failure.”
- Suggested answer (STAR): “We had strong generation demos but weak platform observability and schema consistency. I led an audit, found contract gaps, and re-sequenced roadmap priorities toward reliability and control-plane fundamentals before expansion.”

# Final Reflection
This project is already valuable as an infrastructure learning system: it exposes real-world AI platform challenges that are often abstract in interview settings—contract drift, observability depth, runtime reliability, security debt, and PM tradeoff sequencing.

`Confirmed:` the system has crossed the threshold from “toy scripts” to “serious platform foundation,” but it has not yet crossed into production-grade AgentOps.

`Inferred:` the strongest strategic move now is disciplined maturation, not more feature breadth:
- stabilize contracts
- strengthen observability
- secure execution
- build the minimum useful control-plane UX

If maintained as intended, this document becomes both:
- operational architecture memory for the project
- a high-quality narrative asset for senior AI PM and infrastructure interviews

## Milestone Entry: Git/Worktree Operational Validation (Pre-Phase-1)
Date: 2026-05-12

`Confirmed:`
- GitHub repository connectivity was validated against `https://github.com/leazer7222/agent-oversight.git`.
- Prior Git status failures were traced to stale, tool-managed worktree metadata referencing a moved repository path.
- The issue pattern demonstrated that AI-assisted workflows can leave hidden orchestration state in `.git/worktrees`.

Operational lessons added:
1. AI tooling creates hidden orchestration state that can silently degrade baseline Git reliability.
2. Stale worktree metadata becomes infrastructure debt, not just local inconvenience.
3. Repository path changes can break orchestration tooling expectations unless Git hygiene steps are performed.
4. Operational continuity requires proactive Git maintenance (safe-directory, worktree health checks, metadata cleanup).
5. Durable repository state remains the only reliable continuity layer across model/tool boundaries.

PM/system-thinking implications:
- Reliability includes developer workflow reliability, not only runtime behavior.
- Pre-implementation operational validation reduces hidden risk before infrastructure phases begin.
- Toolchain drift should be treated as a platform risk category with explicit mitigation runbooks.

### Addendum: GitHub Write-Permission Preflight
`Confirmed:`
- Remote repository reachability check succeeded (`git ls-remote --heads origin`).
- Dry-run push failed with `403 Permission denied to reformai-admin` for `leazer7222/agent-oversight`.

Operational interpretation:
- Connectivity and repository existence were healthy, but persistence rights were not.
- This is a critical pre-Phase-1 gating condition: infrastructure work should not proceed without verified write path for durable collaboration state.

Lesson reinforced:
- Operational continuity depends on both durable repository state and correct identity/permission context.

## Milestone Entry: Documentation Ownership Hygiene (Lightweight Governance Pass)
Date: 2026-05-12

`Confirmed:`
- Added concise `Document Role` sections to core docs to clarify source-of-truth boundaries.
- Added explicit cross-document references to reduce future duplication drift.
- Preserved existing content and standards while improving navigation and governance clarity.

Why this matters:
- Multi-LLM collaboration increases duplication risk when ownership boundaries are implicit.
- Clear documentation layering (inventory, standards, strategy, operations, roadmap, lessons) improves operational coherence and onboarding speed.

PM/system-thinking implication:
- Documentation architecture is platform architecture; weak ownership boundaries create hidden coordination debt.

## Milestone Entry: Phase 1 Canonical Schema Stabilization Audit
Date: 2026-05-13

`Confirmed:`
- Completed a repository-wide schema contract audit across migrations, Next.js API routes, Python runtime integrations, and registration scripts.
- Identified hard schema drift in operationally critical paths:
  - `runs` contract mismatch (`event`/`run_id` required in migration, omitted by ingest write path; `error` used by API/types but absent in migration).
  - `project_state` contract mismatch (`tag/state` in migration vs `project_tag/current_state/todo/lessons` in API).
  - `agent_outputs.output_type` mismatch (`ui_components` produced by runtime but not permitted by migration check constraint).
- Published Phase 1 audit artifact documenting source-of-truth policy, table contracts, observability requirements, mismatch inventory, migration gaps, and Phase 2 prerequisites.

Architecture decisions:
1. Canonical operational truth is the **live schema + documented runtime/API contracts**, while migrations are the reproducibility mechanism that must be reconciled to that truth.
2. `runs` must be treated as execution summary rows; `agent_events` (append-only trace) and `agent_outputs` (artifacts) are separate but linked contracts.
3. Phase 2 work should be gated on contract reconciliation for `runs`, `project_state`, and output/event lineage, not on dashboard implementation speed.

Tradeoffs:
- Accepted temporary delivery slowdown to reduce long-term reliability risk from ambiguous contracts.
- Deferred schema perfection/normalization in favor of explicit MVP-operational semantics and observability completeness.

Operational lessons:
- API/routes can silently become the de facto schema if migration discipline lags.
- Run visibility trust depends on explicit summary-vs-event contract boundaries, not just telemetry field presence.
- Source-of-truth ambiguity is itself infrastructure risk and must be tracked as an architectural issue.

PM/system-thinking implications:
- Contract stabilization is product work because it defines measurable operator truth.
- Visibility-first sequencing was validated: unresolved schema ambiguity would make Phase 2 dashboards misleading.

Interview-story opportunities:
- Contract-first stabilization under active schema drift.
- Converting architecture ambiguity into explicit operational gating criteria before feature scaling.
 
# Milestone Update Template
Use this template for every major milestone update:

## Milestone Name
[Name]

## Date
[YYYY-MM-DD]

## Architectural Changes
- [What changed in runtime/API/schema/dashboard]

## Tradeoffs Considered
- [Option A vs Option B and why chosen]

## Lessons Learned
- [Technical + product lessons]

## Failures/Issues Encountered
- [Incidents, regressions, blockers]

## PM Insights
- [Decision quality, sequencing, user/operator implications]

## Interview-Story Opportunities
- [STAR-ready stories created by this milestone]

## New Technical Concepts Learned
- [Infra/AI systems concepts validated or discovered]

## Next Priorities
1. [Priority 1]
2. [Priority 2]
3. [Priority 3]
