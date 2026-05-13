# Document Purpose
This handoff protocol exists to provide durable operational continuity across multiple AI systems working in the same repository.

This project is actively developed by multiple assistants (ChatGPT/Codex, Claude, Antigravity, and future LLM systems) under real constraints:
- token limits
- context window overflow
- interrupted or expired sessions
- partial execution across tools
- asynchronous collaboration between models

These constraints create operational risk:
- lost architectural reasoning
- duplicated analysis
- inconsistent assumptions
- partial implementation without recoverable context
- drift between decisions and execution

This protocol is the mitigation layer. It functions as:
- checkpointing
- durable execution memory
- shared collaboration state
- persistent orchestration context

This mirrors distributed systems patterns:
- conversational memory is ephemeral process memory
- repository documentation is durable state
- handoff entries are transaction checkpoints
- session boundaries are failure/restart boundaries

# Document Role
Source of truth for:
- operational continuity checkpoints across LLM/tools
- active work state, blockers, and immediate next actions
- token-risk handoff state

Should live here:
- session start/checkpoint/end entries
- tactical execution continuity notes
- current operational blockers and recovery steps

Should NOT live here:
- deep strategic architecture retrospectives
- phased implementation strategy details
- agent implementation standards

Related documents:
- Strategic architecture/tradeoffs: `docs/AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md`
- MVP sequencing roadmap: `docs/MVP_IMPLEMENTATION_ROADMAP.md`
- Agent inventory/status: `docs/AGENTS.md`
- Agent implementation standards: `docs/agent-standards.md`
- Repo-wide standards: `docs/repo-standards.md`
- Concise dated lessons: `docs/LESSONS_LEARNED.md`
- Project entrypoint: `docs/README.md`

# Core Operating Principle
**LLM context is ephemeral. Repository state must become the durable source of truth.**

Operational implications:
- Models must never rely solely on conversational memory.
- Continuity must be persisted in-repo at regular intervals.
- Handoffs are mandatory infrastructure, not optional notes.
- If a model is interrupted, the next model should recover from repository state, not chat history.

# How To Use This Handoff Protocol
Required workflow for all AI systems:

Before beginning work:
1. Read:
- `/docs/HANDOFF_PROTOCOL.md`
- `/docs/AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md`
2. Immediately create a `Work Session Start` entry including:
- current objective
- intended files to inspect
- expected task scope

During work:
- checkpoint progress after meaningful milestones
- checkpoint after architectural discoveries
- checkpoint before large context windows are consumed
- checkpoint before generating large outputs
- checkpoint after debugging discoveries
- checkpoint after architectural decisions
- checkpoint after blocker discovery

If token budget becomes constrained:
- STOP new analysis
- prioritize writing current state to `HANDOFF_PROTOCOL.md`
- include incomplete thoughts
- include blockers
- include unfinished work
- include next recommended action

At the end of work:
- update `HANDOFF_PROTOCOL.md`
- update `AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md` if:
  - architecture changed
  - major lessons were learned
  - tradeoffs emerged
  - operational insights evolved
  - PM/system-thinking insights changed

# Recommended Update Frequency
Update this document:
- every 15–30 minutes of meaningful work
- after meaningful architecture decisions
- after subsystem completion
- after blocker discovery
- before large refactors
- before context-heavy analysis
- before model switching
- before token exhaustion risk

This document should behave like:
- autosave
- transaction logs
- distributed checkpoints
- workflow persistence systems

# Current Project Context
Repository context:
- The project is evolving into an AI agent control-plane/dashboard for personal agents and ReformAI agents.
- The direction is toward an operational platform for visibility, execution, governance, and learning.

Primary goals:
- Build production-style AI agent infrastructure.
- Learn agentic systems architecture through hands-on implementation.
- Build operational understanding of orchestration, observability, governance, and reliability.
- Develop senior-level AI product management reasoning and interview-ready system stories.

Operating orientation:
- infrastructure-first
- implementation-aware
- iterative hardening from prototype to production-leaning architecture

# Current Architecture Direction
Current architecture direction:
- Python agent runtime for execution logic and agent behavior.
- Next.js dashboard/API layer for control-plane surface and ingestion endpoints.
- Supabase as persistence layer for agents, runs, state, outputs, and evolving control-plane entities.
- Telemetry/oversight layer for run lifecycle tracking.
- Orchestrator-based execution flow for multi-agent chaining.
- Transition path toward AgentOps/control-plane architecture with stronger execution, observability, and governance primitives.

# Current Major Priorities
1. Freeze canonical Supabase schema
2. Standardize telemetry contracts
3. Build read APIs
4. Build dashboard MVP
5. Build execution queue model
6. Improve observability
7. Improve security and secret handling

# Current Known Risks
- schema drift
- secret exposure
- inconsistent telemetry
- incomplete observability
- missing durable execution
- lack of execution queue
- incomplete governance/HITL
- missing eval framework
- fragmented context between LLM systems

# Model-Specific Strengths
Models should be used strategically based on strengths.

## ChatGPT / Codex
Best suited for:
- architecture reasoning
- system design
- structured implementation
- repository analysis
- operational planning

## Claude
Best suited for:
- long-form reasoning
- architecture synthesis
- conceptual systems thinking
- tradeoff analysis

## Antigravity
Best suited for:
- implementation acceleration
- rapid iteration
- coding throughput
- operational execution

# Operational Lessons Learned
Initialized lessons:
- token exhaustion creates operational continuity problems
- handoff persistence is mandatory
- architecture drift occurs quickly during AI-assisted iteration
- observability becomes critical faster than expected
- infrastructure governance lags experimentation
- durable state matters more than conversational context

# Handoff Entry Template
Use this template for every session and checkpoint.

## Session Start
- date/time:
- model/tool:
- current objective:
- expected scope:
- intended files to inspect:

## Progress Checkpoint
- work completed:
- files inspected:
- files changed:
- architectural discoveries:
- blockers encountered:
- open questions:
- next recommended action:

## Token Risk Checkpoint
- current incomplete work:
- unfinished reasoning:
- partial conclusions:
- critical context to preserve:
- immediate next step for next model:

## Session End
- final work completed:
- architecture impact:
- operational lessons learned:
- PM/system-thinking lessons:
- risks introduced:
- next priorities:

# Active Workstream
- Supabase schema reconciliation
- control-plane/dashboard MVP
- telemetry standardization
- execution orchestration evolution
- security hardening
- observability improvements
- AgentOps architecture evolution

# Open Questions
- Should execution be queue-based?
- Should runs be summary rows or event-stream driven?
- What is the long-term governance model?
- What should become production-grade first?
- How should multi-workspace architecture evolve?
- What observability depth is required for MVP?
- How should AI model routing/handoff evolve?

# Final Operating Rule
**The repository is the durable memory layer.  
The handoff document is the operational continuity layer.  
Conversational context is temporary and should never be treated as the primary system of record.**

## Session Start
- date/time: 2026-05-12 21:09:09 -05:00
- model/tool: ChatGPT / Codex
- current objective: Perform pre-Phase-1 operational Git/GitHub validation and persistence workflow verification.
- expected scope: Read-only connectivity checks, dry-run push validation, documentation checkpointing, docs-only commit/push.
- intended files to inspect:
  - docs/HANDOFF_PROTOCOL.md
  - docs/AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md
  - git metadata and remote configuration

## Progress Checkpoint
- work completed:
  - Confirmed repository read access and existing documentation baseline.
  - Verified GitHub remote reachability and repository visibility after public toggle.
  - Diagnosed and confirmed prior stale worktree metadata problem pattern and its operational implications.
  - Began operational persistence workflow with explicit handoff checkpointing.
- files inspected:
  - docs/HANDOFF_PROTOCOL.md
  - docs/AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md
  - .git/config and .git/worktrees metadata (read-only)
- files changed:
  - docs/HANDOFF_PROTOCOL.md
  - docs/AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md (pending milestone append this session)
- architectural discoveries:
  - AI tooling can create hidden orchestration state in Git worktree metadata.
  - Repository path moves can invalidate tool-managed worktree pointers and break basic Git operations.
- blockers encountered:
  - None currently; proceeding with dry-run and real push checks.
- open questions:
  - Should periodic `git worktree prune` be codified as a maintenance step in ops hygiene?
- next recommended action:
  - Run required git validation commands, dry-run push, append milestone notes, and complete docs-only commit/push.

## Session End
- final work completed:
  - Git/GitHub validation run completed.
  - `git ls-remote --heads origin` succeeded (remote reachable).
  - `git push --dry-run origin HEAD` failed with HTTP 403 due permission mismatch (`reformai-admin` lacks write access to `leazer7222/agent-oversight`).
  - Documentation checkpoint persisted before commit/push attempt.
- architecture impact:
  - No runtime/application architecture changes.
  - Operational workflow strengthened by explicit Git preflight and handoff logging.
- operational lessons learned:
  - Hidden Git/tooling state and auth identity mismatch are control-plane-adjacent reliability risks.
  - Reachability does not imply write capability; dry-run push should be a standard preflight step.
- PM/system-thinking lessons:
  - "Operational readiness" must include identity/access validation, not only technical connectivity.
  - Preflight gates reduce wasted cycle time before milestone work.
- risks introduced:
  - None new; existing risk confirmed: inability to persist changes to remote under current auth identity.
- next priorities:
  1. Complete docs-only commit locally.
  2. Attempt real push and capture exact failure details.
  3. Switch/authenticate as repo writer account before Phase 1 work.

## Session Start
- date/time: 2026-05-12 21:23:00 -05:00
- model/tool: ChatGPT / Codex
- current objective: Lightweight documentation hygiene pass to clarify source-of-truth ownership boundaries and cross-document responsibilities.
- expected scope: Minimal doc governance edits only (no rewrite, no code changes).
- intended files to inspect:
  - docs/AGENTS.md
  - docs/agent-standards.md
  - docs/repo-standards.md
  - docs/AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md
  - docs/HANDOFF_PROTOCOL.md
  - docs/MVP_IMPLEMENTATION_ROADMAP.md
  - docs/LESSONS_LEARNED.md
  - docs/README.md

## Session End
- final work completed:
  - Added `Document Role` ownership sections to docs governance/strategy/operations standards documents.
  - Added explicit cross-links between standards, state, strategy, roadmap, and lessons layers.
  - Appended corresponding milestone/lesson updates.
- architecture impact:
  - Documentation architecture boundaries are now explicit; no application/runtime code changes.
- operational lessons learned:
  - Minimal governance clarifications can materially reduce future multi-LLM duplication drift.
- PM/system-thinking lessons:
  - Ownership clarity in documentation functions as coordination infrastructure and lowers execution ambiguity.
- risks introduced:
  - None significant; risk reduced: documentation boundary ambiguity.
- next priorities:
  1. Restore GitHub push permissions for the active identity before Phase 1 execution.
  2. Begin Phase 1 schema reconciliation using clarified document ownership.
