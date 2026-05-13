# Document Purpose
This roadmap is the canonical implementation strategy for building the AgentOps/control-plane MVP in this repository.

It exists because the project now has two simultaneous responsibilities:
1. deliver a usable operational platform for agent visibility and controlled execution
2. serve as a deliberate learning system for modern AI infrastructure and AI product leadership

This roadmap is intentionally phased to avoid architectural chaos. The sequencing enforces:
- one phase at a time
- explicit phase completion before expansion
- trust-building infrastructure before autonomy features
- contract stability before scale

Why this matters:
- AI systems can produce impressive demos without operational reliability.
- A control plane fails if operators cannot trust telemetry, state transitions, and governance boundaries.
- Visibility and controllability must precede autonomous behavior to prevent fragile, unsafe runtime growth.

This document therefore sequences core infrastructure before advanced AI behavior by design.

# Document Role
Source of truth for:
- phased MVP sequencing and implementation strategy
- operational maturity roadmap from prototype to control plane
- what to build now vs what to defer

Should live here:
- phase-by-phase goals, deliverables, and success criteria
- sequencing rationale, risks, and tradeoffs
- explicit non-goals and deferrals for MVP scope discipline

Should NOT live here:
- active execution/session state
- tactical debugging logs
- deep retrospective architecture essays

Related documents:
- Operational continuity checkpoints: `docs/HANDOFF_PROTOCOL.md`
- Strategic architecture/tradeoff retrospectives: `docs/AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md`
- Agent inventory/status: `docs/AGENTS.md`
- Agent implementation/runtime standards: `docs/agent-standards.md`
- Repo-wide engineering standards: `docs/repo-standards.md`
- Concise chronological lessons: `docs/LESSONS_LEARNED.md`
- Project entrypoint: `docs/README.md`

# MVP Definition
## What the MVP actually is
The MVP is an operational control plane where an operator can:
- view all agents
- inspect runs and execution history
- inspect outputs and errors
- monitor token and cost behavior
- safely execute agents through controlled workflows
- understand system health and runtime confidence

Core target architecture:
Dashboard UI
  -> Read APIs
  -> Supabase
  -> Execution Queue
  -> Python Workers
  -> Telemetry Events
  -> Dashboard

## What the MVP is NOT
- autonomous agent swarms
- AGI-style planning systems
- advanced vector-memory-heavy architectures
- unrestricted multi-agent autonomy
- no-code workflow orchestration products

## What success looks like
- Operators can answer: "what is running, what failed, what it cost, and what to do next?"
- Execution is auditable and recoverable.
- Runtime behavior is observable enough to trust operational decisions.
- Schema/API/runtime contracts are aligned and stable.

## What operational trust means here
Operational trust means:
- state transitions are durable and explainable
- telemetry is consistent across agents
- failures are diagnosable
- costs are measurable
- operator actions are governed and auditable
- system behavior is predictable under normal and failure conditions

# Key Architectural Principles
1. Observability before autonomy  
2. Contracts before scale  
3. Durable state over conversational state  
4. Visibility before automation  
5. Governance before unrestricted execution  
6. Operational trust over flashy demos  
7. Reliability before complexity

Interpretation guidance:
- If a proposed feature increases complexity but does not improve operator trust, defer it.
- If a proposed shortcut undermines schema or telemetry contracts, reject it.
- If execution cannot be audited or replayed, it is not MVP-complete.

# Phase Completion Status

| Phase | Status | Completed |
|-------|--------|-----------|
| Phase 1 — Schema Stabilization | ✅ Complete | 2026-05-12 |
| Phase 2 — Telemetry Standardization | ✅ Complete | 2026-05-12 |
| Phase 3 — Read APIs | ✅ Complete | 2026-05-12 |
| Phase 4 — Dashboard MVP | 🔜 In Progress | — |
| Phase 5 — Execution Queue | ⏳ Deferred | — |
| Phase 6 — Controlled Execute | ⏳ Deferred | — |
| Phase 7 — Observability Hardening | ⏳ Deferred | — |
| Phase 8 — Governance + Eval | ⏳ Deferred | — |

# Current System State
## Confirmed current architecture
- Python runtime with modular agents and orchestrator-based execution.
- Next.js app with ingest API, project-state API, and 8 operational Read API endpoints.
- Supabase as persistence layer (schema stabilized; migrations 001–007 applied or documented).
- Telemetry/oversight layer: full run lifecycle + step events + error taxonomy.
- `python-sdk/oversight.py`: RunContext, StepTimer, error categorization, cost estimation.

## Current maturity level
- Early-platform stage. Control-plane API surface is complete. Dashboard UI is the remaining gap.
- Agent execution is functional and telemetry-emitting. Cost/token data is present in code but zero until LLM billing is enabled.

## Strongest existing foundations
- Stable schema contract (migrations as governance source of truth, live DB as operational reality).
- Consistent telemetry (run lifecycle + step events + error taxonomy all implemented).
- 8 operational Read API endpoints covering all MVP data needs.
- Modular agent library with step-instrumented agents.

## Biggest gaps
- No dashboard UI yet — operators cannot view agent/run/cost/error data without querying APIs directly.
- LLM billing not enabled — token/cost columns are null in all current run rows.
- No Supabase TypeScript generated types — Phase 3 routes use `as any[]` casts.

## Biggest remaining risks
- LLM cost visibility blocked until billing is enabled
- Execution fragility from synchronous orchestration (no queue — Phase 5)
- No operator execution controls (Phase 6)
- Secret handling not hardened (Vercel SSO, env var discipline)

# Lessons Already Learned
1. Token exhaustion creates operational continuity problems.  
2. Checkpointing is mandatory for multi-model collaboration.  
3. Schema drift compounds quickly once live systems evolve faster than migrations.  
4. Observability becomes critical much earlier than expected.  
5. AI collaboration requires persistent, repo-native state.  
6. Infrastructure governance lags experimentation unless intentionally prioritized.  
7. Operational trust matters more than demo quality.

Operational implication:
- durability, observability, and governance are not "later optimizations"; they are enabling prerequisites for safe platform growth.

# Phase 1 — Canonical Schema Stabilization
## Purpose
Establish one authoritative schema contract across:
- live Supabase
- migrations in repo
- runtime expectations
- API expectations

## Architectural reasoning
Without schema certainty, every subsequent phase is built on unstable assumptions. Read APIs, queue models, and telemetry consistency all depend on deterministic data contracts.

## Deliverables
- schema reconciliation plan (live vs migrations vs code assumptions)
- canonical migration structure (forward-only, reproducible)
- contract definitions for core entities:
  - agents
  - runs
  - run-related events
  - outputs/artifacts
  - project/workspace context
- run/event model decision document (summary row + event stream relationship)
- explicit ownership policy for schema changes

## Success criteria
- runtime/API/database alignment validated
- no ambiguous schema source-of-truth
- documented, versioned contracts for key tables and fields
- known drift resolved or explicitly tracked with remediation plan

## Risks reduced
- contract breakage between API and DB
- migration uncertainty
- inconsistent runtime writes

## Risks introduced
- temporary delivery slowdown while contracts are normalized
- short-term migration overhead and data reconciliation complexity

## Tradeoffs
- slower feature velocity now vs reduced systemic rework later
- strict contract discipline vs rapid ad-hoc schema changes

## Likely debugging pain points
- hidden assumptions in existing API routes
- historical rows that violate new constraints
- field naming mismatch (`run_id` vs `id`, etc.) semantics

## PM/system-thinking lessons
- schema is product infrastructure, not a back-office concern
- measurement capability is determined at schema design time

## What should explicitly NOT be built yet
- new dashboard features dependent on unstable schema
- execution queue implementation
- advanced governance controls

## Interview-story opportunities
- "How I stabilized a drifting live schema before scaling platform capabilities."

# Phase 2 — Telemetry Standardization
## Goals
- standardize lifecycle events
- standardize token/cost reporting
- define event taxonomy
- improve observability consistency

## Telemetry contract v2
Define required events and payload fields:
- `run_requested`
- `run_queued`
- `run_started`
- `run_step` / `run_event`
- `run_completed`
- `run_failed`
- `run_cancelled` (if applicable)

Payload standards include:
- stable run identifiers
- agent identity + workspace/project context
- timestamps, durations, status transitions
- tokens/cost metrics
- error envelope structure
- optional metadata with bounded schema policy

## Run/event relationships
- runs table: lifecycle summary and durable status
- events table: append-only operational trace
- outputs: linked to runs/events with clear lineage

## Operational metrics strategy
- reliability: success rate, failure rate, retry rate
- latency: queue delay, execution time, end-to-end time
- cost: total/per-run/per-agent/per-workspace
- quality proxy: rerun rate, failure clusters, optional eval outcomes

## Cost visibility strategy
- define canonical cost fields and units
- enforce reporting conventions in runtime
- generate dashboard-ready aggregates from trusted raw telemetry

## Debugging implications
- event-level traces enable deterministic failure reconstruction
- standardized errors reduce "unknown failure" classes

## Reliability implications
- measurable transitions are prerequisite for SLO-style reliability work
- consistency enables alerting and operational thresholds

# Phase 3 — Read APIs
## Goals
- expose operational visibility APIs
- support dashboard reads
- create stable operational query layer

## Required endpoints
- `GET /api/agents`
- `GET /api/runs`
- `GET /api/runs/[id]`
- `GET /api/cost/*`
- `GET /api/errors`

Recommended extensions:
- `GET /api/runs/[id]/events`
- `GET /api/agents/[id]/runs`

## Query philosophy
- API is an operational read layer, not raw DB passthrough.
- Responses should be operator-oriented: clear status semantics, useful filters, and stable shapes.

## Pagination/filtering direction
- cursor or deterministic offset strategy
- filters: status, agent, workspace/company, timeframe, error-only
- sortable by recent activity/cost/failure

## Operational query patterns
- latest failing runs
- high-cost runs by agent
- inactive/never-run agents
- queue backlog and execution velocity (later phases)

## Trust/visibility implications
- operators need low-friction truth access
- stable read APIs become control-plane contract for UI and future tooling

# Phase 4 — Dashboard MVP
## Phase intent
Prioritize visibility and diagnosis before execution controls.

## Page: `/agents`
- Purpose: agent registry and current operational status
- Operational value: identify active/inactive/failing agents quickly
- Required data: agent identity, status, last run, run count, aggregate cost/tokens
- Required metrics: success/failure ratio, recent activity freshness
- UX expectations: sortable/filterable table, status chips, drill-down links
- Future extensibility: ownership, policy, SLA views
- Not to overbuild yet: deep configuration editors, workflow builders

## Page: `/runs`
- Purpose: operational execution history
- Operational value: detect trends, spikes, regressions
- Required data: run id, agent, status, timestamps, duration, cost/tokens, error summary
- Required metrics: failure and latency distributions
- UX expectations: dense table, strong filters, quick "failed only" mode
- Future extensibility: saved views and alert thresholds
- Not to overbuild yet: advanced analytics modules

## Page: `/runs/[id]`
- Purpose: run-level diagnosis
- Operational value: root-cause analysis and trust recovery
- Required data: lifecycle summary, event trace, outputs, errors, metadata
- Required metrics: per-step latency/cost attribution if available
- UX expectations: timeline + structured payload view
- Future extensibility: replay tools, eval overlays
- Not to overbuild yet: full distributed tracing UI parity

## Page: `/costs`
- Purpose: cost transparency and unit economics
- Operational value: cost control and planning confidence
- Required data: cost/token aggregates by agent/workspace/time
- Required metrics: cost per successful run, cost trend, outliers
- UX expectations: concise trend visuals + tables
- Future extensibility: budgets and policy alarms
- Not to overbuild yet: predictive forecasting engines

## Page: `/errors`
- Purpose: failure management surface
- Operational value: prioritize incident response
- Required data: error taxonomy, frequency, impacted agents/runs, recency
- Required metrics: top failure classes and MTTR proxy indicators
- UX expectations: grouped failure views, direct links to run detail
- Future extensibility: incident workflows and ownership assignment
- Not to overbuild yet: full incident management platform

# Phase 5 — Execution Queue Model
## Goals
- move away from direct execution
- introduce durable execution flow
- support queued execution lifecycle

## run_requests model
Introduce durable request entity capturing:
- requester identity/context
- target agent and input payload
- requested time and priority
- policy/gating snapshot
- current queue/execution status

## Execution lifecycle states
- requested
- validated
- queued
- dequeued
- running
- completed
- failed
- cancelled

## Worker model
- Python workers consume queue entries and execute with idempotent semantics.
- Frontend/API trigger request creation, not direct long-running execution.

## Retry philosophy
- explicit retry policy by error class
- bounded attempts + backoff
- dead-letter style handling for repeated failure classes

## Queue semantics
- durable state transitions
- idempotency keys
- lease/timeout semantics for worker crashes

## Failure recovery direction
- requeue or fail-fast based on policy
- preserve partial telemetry for diagnosis
- clear operator-facing recovery actions

## Operational reasoning
Decoupling execution from HTTP request lifecycle is mandatory for reliability, scalability, and auditable control.

# Phase 6 — Controlled Execute Flow
## Goals
- safely execute agents from dashboard
- add basic governance and safety controls

## Execute UX flow
- operator selects agent
- input and execution scope are reviewed
- confirmation gate shown
- request submitted to queue
- status tracked in run/request views

## Execution approvals
- minimum confirmation flow required
- optional two-step approval for high-risk categories

## Auditability
- all execution requests linked to actor identity and timestamp
- immutable request + outcome trail

## Operator trust
- visible state transitions
- clear "what happened" and "what to do next"

## Safety constraints
- execution guardrails (status checks, allowed agent set, payload validation)
- bounded execution semantics

## Operational controls
- cancel pending requests
- pause/resume agent execution eligibility (where supported)
- deny unsafe direct runtime entry points

# Phase 7 — Observability + Reliability Hardening
## Goals
- improve debugging and operational trust
- establish reliability foundations

## Deliverables
- error taxonomy with stable categories/codes
- retry conventions by class of failure
- timeout conventions by stage and agent type
- richer traces/events/log associations
- operational dashboard signals for health and incident detection
- baseline automated tests for contract-critical paths

## Testing philosophy
- contract tests for schema/API/runtime compatibility
- ingestion tests for telemetry shape and transition validity
- queue/execution lifecycle tests for durability and idempotency

## Runtime confidence outcomes
- failures are diagnosable with bounded ambiguity
- regressions are detectable before severe operator impact
- reliability metrics become decision-grade

# Phase 8 — Governance + Evaluation Foundations
## Goals
- establish production-oriented governance patterns
- prepare for future scaling

## Governance direction
- RBAC concepts: who can view/execute/administer
- ACL concepts: which actors can run which agents/workspaces
- HITL concepts: approval controls for sensitive/high-cost actions
- audit trails: policy decisions + execution requests + outcomes

## Policy engine direction
- simple policy model first (cost caps, execution eligibility, safety flags)
- policy evaluation should be observable and explainable

## Evaluation framework direction
- define where and how quality evaluation is stored
- associate eval outcomes with runs/events
- support confidence signals without blocking early MVP operation

## Quality confidence concepts
- quality as an operational metric, not just human impression
- evaluate both correctness proxy and business utility proxy where feasible

# What Explicitly Should NOT Be Built Yet
Deferred intentionally:
- autonomous swarms
- advanced planners
- long-term vector memory systems
- complicated workflow builders
- advanced multi-cloud abstractions
- over-engineered model routing
- unnecessary microservices

Why deferred:
- these features increase complexity faster than operational trust
- they distract from core MVP objective: visible, controllable, reliable execution
- premature autonomy amplifies governance and observability debt
- microservice fragmentation too early increases coordination overhead and failure modes

# MVP Success Criteria
## Operational success
- operator can inspect agents, runs, costs, and errors without manual DB spelunking
- execution lifecycle is understandable from UI/API

## Reliability success
- run/request state transitions are durable and coherent
- failure classes are diagnosable and actionable

## Visibility success
- telemetry consistently supports run-level and event-level inspection
- cost/token metrics are reliable enough for operational decisions

## PM learning success
- clear evidence of sequencing discipline, tradeoff management, and systems-level product reasoning
- explicit lessons documented at each milestone

## Interview-preparation success
- strong, concrete stories about:
  - schema contract stabilization
  - observability-first platform design
  - execution reliability architecture
  - governance sequencing under uncertainty

# Operational Risks
- schema drift
- observability gaps
- execution fragility
- governance gaps
- cost visibility gaps
- security risks
- AI collaboration continuity risks

Risk handling posture:
- treat each risk as phase-addressable
- avoid stacking unresolved risks across phases
- document residual risks at each milestone boundary

# Documentation Requirements
After every phase:
- `HANDOFF_PROTOCOL.md` must be updated
- `AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md` must be updated
- milestone entries must be appended
- tradeoffs/failures must be documented

Phase completion is not valid without documentation updates.

# Expected Evolution Path
prototype
-> operational platform
-> reliable control plane
-> governed AgentOps system

Interpretation:
- Prototype proves value flow.
- Operational platform provides visibility.
- Reliable control plane provides durable execution confidence.
- Governed AgentOps system provides safe scale and long-term trust.

# Final Reflection
The long-term value of this platform is not merely "agents generating output."

Its strategic value is the disciplined creation of:
- operational trust
- visibility
- controllability
- governance
- infrastructure maturity
- durable learning
- systems-thinking depth

For both engineering and product leadership, this roadmap treats operational coherence as the core product. That is the right foundation for scaling capability without losing reliability, safety, or decision quality.
