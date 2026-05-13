# AI-Assisted Software Delivery Operating System

**Document type:** Foundational architecture
**Owner:** Founder/Operator
**Status:** Canonical
**Update trigger:** Operating model changes, agent additions, team structure changes

---

## Purpose

This document defines the architecture, philosophy, and governance of the AI-assisted software delivery operating system for a two-person startup team. It exists to ensure that AI agents produce genuine leverage — not plausible-looking noise — by operating on accurate, current, human-maintained context.

This is not an enterprise agile simulation. It is a deliberately minimal system designed around the actual constraints of a two-person team moving fast under uncertainty.

---

## Core Philosophy

**Context integrity is the real operating system.**

AI agents are only as useful as the documents they read. A well-prompted agent running on stale or incomplete context will produce confident, well-formatted outputs that are wrong. No amount of prompt engineering fixes a context problem.

The primary discipline of this operating system is not agent design — it is document maintenance. The agents are the easy part.

---

## Guiding Principles

1. **Context before capability.** Before adding a new agent, ask whether the canonical documents it would read are accurate and current. If not, fix the documents first.

2. **Human judgment at every threshold.** Agents clarify, structure, and surface — they do not decide. Every workflow transition that matters has a human in the loop.

3. **Async over ceremony.** A two-person team has no coordination cost to solve with ceremonies. Agent-produced artifacts replace synchronous planning sessions.

4. **Event-triggered updates, not schedule-based.** Documents are updated when named trigger events occur — not because it is sprint review day.

5. **One source of truth per information type.** If the same fact lives in two places, one of them is wrong. The system is designed to prevent duplication.

6. **Minimum viable documentation.** Only maintain documents that agents actually read or that inform human decisions. Documentation that no one reads and no agent consumes is operational overhead with no return.

7. **Complexity escalates on demonstrated need.** New documents, new agents, and new processes are added only when the absence creates an identifiable, recurring cost.

8. **The plausibility trap is the primary failure mode.** AI produces confident outputs. Garbage in, polished garbage out. Treat every agent output as a hypothesis, not a deliverable, until a human reviews it.

---

## Startup Constraints This System Is Designed Around

| Constraint | Implication |
|---|---|
| Two people total | No coordination overhead to manage; ceremonies have negative ROI |
| One engineer | Engineering capacity is the binding constraint; protect it from ambiguity |
| Founder acts as PM/PO/BA/QA | Context lives in one person's head by default; must be externalized deliberately |
| Moving fast under uncertainty | Processes must bend without breaking; flexibility over rigidity |
| No second human to catch AI errors | Human review of agent outputs is non-negotiable |
| Context window as a real resource | Agents cannot read the entire codebase; canonical summaries are critical |

---

## Operating Model

```
Founder/Operator                    AI Agents                    Engineer
─────────────────                   ─────────────                ──────────────

Product idea / change               
    │
    ▼
[Product Clarification Agent]
    │ Structured brief
    ▼
Human review + approval ──────────────────────────────────────────────────────►
    │                                                                          │
    ▼                                                                          │
[Story Structuring Agent]                                                      │
    │ Stories in Definition of Ready format                                    │
    ▼                                                                          │
Human review + refinement ─────────────────────────────────────────────────►  │
    │                                                                          │
    ▼                                                                          │
[Engineering Planning Agent] ──────────────────────────────────────────────►  │
    │ Implementation notes, risk flags, approach options                       │
    ▼                                                                          │
                                                            Engineering work   │
                                                                    │          │
                                                                    ▼          │
                                                        [QA/Release Confidence Agent]
                                                                    │
                                                                    ▼
                                                        Human release decision
```

---

## Human Responsibilities

### Founder / Operator
- Maintains all canonical documents in `/docs/`
- Reviews and approves all agent outputs before they inform engineering
- Makes all product, priority, and release decisions
- Updates documents within 48 hours of a trigger event
- Flags documents as stale when context has shifted but update is pending

### Engineer
- Maintains `ARCHITECTURE.md` and `STACK.md` as live documents
- Creates ADRs when making significant decisions
- Updates `KNOWN-RISKS.md` when new risks are identified or existing ones resolve
- Flags when agent-provided engineering context appears incorrect

---

## Role of AI Agents

### What agents do
- Clarify ambiguous product requirements into structured form
- Convert approved briefs into stories meeting the Definition of Ready
- Surface relevant architectural constraints and risks from canonical docs
- Flag missing or potentially stale context before generating output
- Produce structured outputs that reduce the engineer's cognitive load at story start

### What agents never do
- Update canonical documents (human-only responsibility)
- Make product or priority decisions
- Approve their own outputs for engineering use
- Substitute for human judgment at decision thresholds

---

## Context Integrity Philosophy

### The Four-Tier Source-of-Truth Hierarchy

```
Tier 1 — Ground Truth
    The codebase. What is actually running. Authoritative for implementation.

Tier 2 — Canonical Documents  ← This system governs these
    Human-maintained. Updated on trigger events. The source agents read.
    /docs/PRODUCT.md, ARCHITECTURE.md, STACK.md, DOMAIN.md, KNOWN-RISKS.md

Tier 3 — Derived Standards and Workflows
    Documented patterns derived from Tier 2. Updated when Tier 2 changes.
    /docs/standards/*, /docs/workflows/*

Tier 4 — Generated Outputs
    Agent artifacts: stories, plans, release assessments. Ephemeral.
    Never canonical. Always require human review before acting on them.
```

### The 48-Hour Update Rule

When a trigger event occurs (architectural decision, product pivot, resolved risk, new constraint), the relevant canonical document must be updated within 48 hours. After 48 hours without an update, the document should be flagged as potentially stale.

### The Staleness Flag Pattern

When a document may be outdated but an update is not yet complete, prepend:

```markdown
> **STALE — as of YYYY-MM-DD:** [Brief description of what has changed.
> This document will be updated by YYYY-MM-DD.]
```

Agents reading a staleness flag should surface it in their output rather than silently proceeding on outdated context.

### Pre-Agent Invocation Freshness Check

Before invoking any agent, verify:
1. The canonical documents it reads have been updated since the last relevant trigger event
2. No staleness flags are present on those documents
3. If trigger events have occurred since the last update — update the documents before invoking the agent

---

## Canonical Source-of-Truth Design

| Information Type | Canonical Location | Owner | Update Trigger |
|---|---|---|---|
| Product vision and goals | `docs/PRODUCT.md` | Founder/Operator | Product pivots, goal changes |
| Domain concepts and terminology | `docs/DOMAIN.md` | Founder/Operator | New domain concepts, terminology changes |
| System architecture | `docs/ARCHITECTURE.md` | Engineer | Architectural decisions, ADRs |
| Technology stack | `docs/STACK.md` | Engineer | Technology additions, removals, version changes |
| Known risks and mitigations | `docs/KNOWN-RISKS.md` | Both | New risks discovered, risks resolved |
| Significant decisions | `docs/decisions/` | Decision owner | Each significant decision |
| Delivery workflow | `docs/workflows/DELIVERY.md` | Both | Process changes |
| Story readiness criteria | `docs/workflows/STORY-READY.md` | Both | Definition of Ready changes |
| Release criteria | `docs/workflows/RELEASE.md` | Both | Release criteria changes |
| Engineering standards | `docs/standards/` | Engineer | Standards decisions |
| Agent architecture | `docs/ai-operating-system/` | Founder/Operator | Operating model changes |

---

## Recommended Repository Structure

```
/
├── README.md                           # Project overview and navigation
├── AGENTS.md                           # Agent checklist and registry
└── docs/
    ├── README.md                       # Documentation index
    ├── PRODUCT.md                      # Product vision, goals, target users
    ├── ARCHITECTURE.md                 # System architecture, component map
    ├── STACK.md                        # Technology stack with rationale
    ├── DOMAIN.md                       # Domain concepts, terminology, rules
    ├── KNOWN-RISKS.md                  # Active risks with mitigations
    ├── decisions/
    │   ├── README.md                   # ADR index
    │   ├── template.md                 # ADR template
    │   ├── 0001-deployment-model.md
    │   ├── 0002-authentication.md
    │   ├── 0003-queue-system.md
    │   ├── 0004-file-storage.md
    │   └── 0005-database-orm.md
    ├── workflows/
    │   ├── DELIVERY.md                 # End-to-end delivery process
    │   ├── STORY-READY.md              # Definition of Ready
    │   └── RELEASE.md                  # Release criteria and process
    ├── standards/
    │   ├── TYPESCRIPT.md               # TypeScript conventions
    │   ├── DATABASE.md                 # Schema and migration conventions
    │   └── TESTING.md                  # Testing strategy and standards
    └── ai-operating-system/
        ├── SYSTEM.md                   # This document
        ├── CONTEXT-INTEGRITY.md        # Context freshness protocols
        └── AGENT-CONSUMPTION.md        # Agent-to-document consumption map
```

---

## Core Document Specifications

### `docs/PRODUCT.md`
The canonical source of product truth. Agents read this before producing any product-facing output.

Must contain:
- What the product does (one paragraph, precise)
- Who it serves (primary user, secondary users)
- Core problems it solves (numbered, concrete)
- Current strategic goals (time-bounded, measurable where possible)
- What the product explicitly does not do (scope boundary)
- Key product decisions and their rationale

Must not contain: implementation details, technical architecture, feature lists without context.

### `docs/ARCHITECTURE.md`
The canonical source of architectural truth. The Engineering Planning Agent reads this before producing any technical output.

Must contain:
- System component map (what exists, how components relate)
- Data flow (how data moves through the system)
- External integrations and their purpose
- Deployment topology (where things run)
- Key architectural constraints and invariants

Must not contain: code snippets, detailed implementation, stack versions (those live in STACK.md).

### `docs/STACK.md`
The authoritative list of every technology in the system with its version, purpose, and known limitations.

Must contain: technology name, version, purpose, key configuration notes, known limitations or risks.

Format: one technology per section, consistent structure.

### `docs/DOMAIN.md`
The domain glossary and rules. Prevents agents from guessing at business terminology.

Must contain:
- Definitions for all domain-specific terms (precise, not encyclopedic)
- Core business rules that constrain implementation
- Entities and their relationships (conceptual, not database schema)

### `docs/KNOWN-RISKS.md`
The active risk register. The QA/Release Confidence Agent reads this before producing any release assessment.

Format per risk:
```markdown
## [Risk ID]: [Risk Title]
**Status:** Active | Mitigated | Resolved
**Severity:** High | Medium | Low
**Area:** [System area affected]
**Description:** [What could go wrong]
**Mitigation:** [What is in place or planned]
**Resolution:** [If resolved, how and when]
```

---

## Context Ownership Rules

| Action | Human | Agent |
|---|---|---|
| Create canonical documents | ✓ | ✗ |
| Update canonical documents | ✓ | ✗ |
| Flag documents as stale | ✓ | Read-only (surface to human) |
| Read canonical documents | ✓ | ✓ |
| Create Tier 4 generated outputs | — | ✓ |
| Approve Tier 4 outputs for engineering use | ✓ | ✗ |
| Create ADRs | ✓ | ✗ |

---

## Agent Consumption Model

| Agent | Primary Documents | Secondary Documents |
|---|---|---|
| Product Clarification Agent | `PRODUCT.md`, `DOMAIN.md` | `workflows/STORY-READY.md` |
| Story Structuring Agent | `PRODUCT.md`, `DOMAIN.md`, `workflows/STORY-READY.md` | `ARCHITECTURE.md` |
| Engineering Planning Agent | `ARCHITECTURE.md`, `STACK.md`, `KNOWN-RISKS.md`, `standards/*` | `DOMAIN.md`, `decisions/` |
| QA / Release Confidence Agent | `workflows/RELEASE.md`, `KNOWN-RISKS.md` | `ARCHITECTURE.md`, `standards/TESTING.md` |

---

## Architectural Decision Records (ADRs)

ADRs are the canonical record of why the system is the way it is. They are append-only. A superseded ADR is never deleted — it is updated with a status of `Superseded by ADR-NNNN`.

### ADR Template

```markdown
# ADR-NNNN: [Decision Title]

**Date:** YYYY-MM-DD
**Status:** Accepted | Superseded by ADR-NNNN
**Owner:** Engineer | Founder/Operator

## Context
[What situation required a decision? What constraints were in play?]

## Options Considered
1. [Option A] — [brief description and trade-off]
2. [Option B] — [brief description and trade-off]
3. [Option C] — [brief description and trade-off]

## Decision
[Which option was chosen and why. Be specific.]

## Consequences
**Positive:** [What this enables or simplifies]
**Negative:** [What this constrains or introduces]
**Risks:** [What could go wrong with this decision]

## Review Trigger
[Under what circumstances should this decision be revisited?]
```

### Priority ADRs for This Stack

The following decisions carry known risk and should be documented immediately:

- **ADR-0001:** Deployment model — three cloud providers (Vercel, GCP, Cloudflare R2)
- **ADR-0002:** Authentication — Firebase OTP as sole authentication mechanism
- **ADR-0003:** Queue system — BullMQ + Upstash Redis (HTTP vs persistent TCP compatibility risk)
- **ADR-0004:** File storage — Multer + S3 SDK + Cloudflare R2
- **ADR-0005:** Database ORM — Drizzle + Zod (schema divergence risk without drizzle-zod)

---

## Definition of Ready

Stories are ready for engineering when all 10 fields are populated:

1. **Title** — one sentence, verb-first
2. **Goal** — what user outcome this achieves
3. **Context** — why this matters now, what triggered it
4. **Acceptance criteria** — numbered, testable, unambiguous
5. **User-facing scope** — what the user can see or do after this story ships
6. **Out of scope** — what is explicitly excluded
7. **Domain terms** — any domain-specific terms the engineer needs to understand
8. **Affected components** — which system components are touched
9. **Known risks or constraints** — any relevant items from `KNOWN-RISKS.md`
10. **Dependencies** — what must be true before engineering starts

A story that does not meet this standard is not ready. The Story Structuring Agent produces stories in this format. The human reviews for accuracy before releasing to engineering.

---

## Anti-Patterns

### 1. Ceremony Theater
Running AI-facilitated planning sessions that perform the appearance of process without producing coordination value. For a two-person team, synchronous AI-facilitated ceremonies have negative ROI. Use async agent-produced artifacts instead.

### 2. The Plausibility Trap
Treating well-formatted AI output as correct output. Agents produce plausible-looking artifacts. Without a human reviewer, confident errors ship. Every agent output is a hypothesis until a human approves it.

### 3. Context Neglect
Invoking agents without verifying that the documents they read are current. Produces outdated analysis delivered with current-day confidence.

### 4. Agent Sprawl
Adding specialized agents for every technology, library, or process. Agents should map to workflow stages and decision types — not to technologies. Technologies are context inputs, not organizing principles.

### 5. Document Inflation
Maintaining documents that no agent reads and no human references. Every document in the canonical set is a maintenance obligation. Eliminate what is not actively consumed.

### 6. Schema Duplication
Allowing two independent schema systems (e.g., Zod validation schemas and Drizzle database schemas) to diverge silently. Use `drizzle-zod` or equivalent to derive one from the other. TypeScript will not catch this divergence.

### 7. Operational Fragmentation
Operating across multiple cloud providers without a deliberate single-pane observability strategy. Three billing accounts, three deployment pipelines, and three log systems is a real operational cost at any team size.

### 8. Founder Psychology Substitution
Using agent-generated structure as a substitute for genuine product insight. Agents can organize and surface — they cannot supply the market understanding, user empathy, or judgment that product decisions require.

---

## Complexity Escalation Rules

The system starts minimal and grows only on demonstrated need.

**Add a new canonical document when:**
- An information type is needed by an agent and has no current canonical home
- A recurring human decision requires context that is currently tribal knowledge
- A type of decision is being made repeatedly without a record of the reasoning

**Add a new agent when:**
- A recurring workflow stage has a clear input (canonical documents), a clear output (structured artifact), and a human is currently doing the structuring work manually
- The manual work is taking measurable time that could be recaptured

**Add a new workflow document when:**
- A process is being executed inconsistently because it is not written down
- An agent needs to follow a specific process that is currently implicit

**Do not add complexity when:**
- The proposed addition mirrors what an enterprise team does, not what this team actually needs
- The cost of maintaining it exceeds the benefit of having it
- The problem it solves has not yet actually occurred

---

## Minimum Viable Operating System — Phase 1

The following 8 documents, when created and maintained, constitute a functional operating system. Estimated creation time: 15–23 hours.

| Document | Estimated Hours | Creates Value By Enabling |
|---|---|---|
| `docs/PRODUCT.md` | 3–4h | Product Clarification Agent, Story Structuring Agent |
| `docs/ARCHITECTURE.md` | 4–6h | Engineering Planning Agent |
| `docs/STACK.md` | 2–3h | Engineering Planning Agent, risk surfacing |
| `docs/DOMAIN.md` | 2–3h | Product Clarification Agent, Story Structuring Agent |
| `docs/KNOWN-RISKS.md` | 1–2h | QA/Release Confidence Agent |
| `docs/workflows/STORY-READY.md` | 1h | All agents (Definition of Ready) |
| `docs/workflows/RELEASE.md` | 1h | QA/Release Confidence Agent |
| `docs/decisions/0001–0005` (5 ADRs) | 1–4h | Engineering Planning Agent, institutional memory |

**Do not build agents until these documents exist and are accurate.** An agent with no canonical documents to read produces general-purpose output, not context-aware leverage.

---

## Operating Principles

1. Canonical documents are updated by humans, read by agents. This boundary is never crossed in either direction.

2. A stale document is worse than a missing document. A missing document produces an error. A stale document produces a confidently wrong answer.

3. The 48-hour rule exists because context decay is exponential. What was true today is probably true tomorrow. After a week, assume it needs verification.

4. Agent outputs are hypotheses. They become decisions only after human review.

5. The ADR log is institutional memory. It prevents the team from relitigating settled decisions and preserves the reasoning that future engineers need to maintain the system safely.

6. Complexity is added at the margin, not the beginning. The full structure described in this document is a target state, not a starting requirement.

7. Process serves the work. If a document, workflow, or agent is not reducing cognitive load or improving output quality, it is overhead. Remove it.

8. The engineer's context window is a finite resource. Canonical documents exist to give agents the ability to surface relevant context precisely, so the engineer does not have to hold the entire system in their head.

9. Product insight cannot be delegated to agents. The founder's judgment about what users need, what the market will bear, and what to build next is the irreducible human contribution. Agents support that judgment — they do not replace it.

10. This document is the operating system contract. When the system behaves inconsistently with what is written here, update the document or update the practice — but never let them diverge silently.
