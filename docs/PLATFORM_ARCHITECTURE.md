# Platform Architecture

**Document type:** Foundational architecture and philosophy  
**Scope:** Agent Oversight platform — design rationale, architectural principles, and long-term direction  
**Intended audience:** Engineers, architects, technical leadership, platform contributors  
**What this document is not:** A sprint plan, implementation spec, feature list, or technology reference

---

## Preamble

This document records the architectural reasoning behind Agent Oversight — what it is, what it deliberately refuses to become, and why the platform was designed this way.

It is organized around principles and reasoning rather than features and implementations. Principles outlast implementations. The specific technologies, schema details, and API surfaces will evolve; the foundational reasoning should not. When those details change, they belong in implementation documents, migration notes, and session logs. When the reasoning changes, it belongs here.

This document should be read as an argument, not a reference. The goal is not to describe what was built but to make the logic behind the architecture legible — so that future contributors, reviewers, and stakeholders can evaluate decisions against the reasoning that produced them rather than treating the architecture as an inherited artifact whose origins are unclear.

---

## The Core Thesis

Most thinking about AI infrastructure concentrates on the prompting layer — model selection, chain-of-thought patterns, tool-calling interfaces, output quality. These are real concerns, but they are second-order. The foundational problem is different.

**AI infrastructure is fundamentally a state-management and operational-governance problem.**

The hard problem is not coordinating agents. It is maintaining coherent, auditable, trustable state across a system where the workers are probabilistic, context-sensitive, and expensive to operate. An agent that produces excellent outputs on Monday may produce inconsistent outputs on Tuesday if the context it consumed drifted without detection. A multi-agent pipeline may produce internally inconsistent results if different agents operated from different versions of shared institutional knowledge. A platform that cannot answer "why did the system do that?" cannot be trusted at scale, regardless of how good its average outputs are.

This framing has a specific implication for architecture sequencing. A system that prioritizes execution capability before operational governance will eventually produce outputs that cannot be explained, costs that cannot be attributed, and failures that cannot be diagnosed. The capability exists, but the trust does not. And trust, in AI infrastructure, is not a soft requirement — it is the property that determines whether the system can be safely extended, delegated to, or relied upon.

The sequencing that follows from this thesis:

**Observability → Governance → Execution Reliability → Orchestration → Autonomy**

Each phase presupposes the previous. Governance without observability cannot enforce what it cannot see. Execution reliability without governance cannot enforce operational limits. Orchestration without execution reliability cannot recover from failures. Autonomy without all of the preceding is an ungovernable system operating at scale.

This is not a conservative sequencing. It is the only sequencing that produces a platform that remains trustworthy as capability expands.

---

## What Agent Oversight Is

Agent Oversight is an **operational ledger with a governance enforcement surface**.

This framing is precise and intentional. Each part carries architectural weight.

**The ledger.** A ledger is an append-only, authoritative record of what happened. It does not make decisions. It does not interpret domain semantics. It records operational facts — what ran, when, at what cost, with what outcome — and it records them permanently. When something changes, a new entry is written; the old entry remains. The ledger is trusted precisely because it is complete and immutable. A ledger that can be edited is not a ledger; it is a mutable store that might have been edited.

**The governance enforcement surface.** Agent Oversight evaluates whether a proposed execution is permitted before allowing it to proceed. It checks agent status, cost constraints, authorization boundaries, and operational policies at dispatch time — before execution begins, not after. Post-hoc governance is auditing. Dispatch-time governance is enforcement. The distinction matters because enforcement prevents violations; auditing only records them.

The operational analogy that holds most precisely: Agent Oversight is to AI agents what a compliance and audit system is to a financial institution's trading operations. The traders make decisions. The compliance system tracks what they did, enforces position limits, and provides audit trails. The compliance system does not know about trading strategy. It knows about rule violations, transaction history, and cost exposure. The compliance system is trusted precisely because it is insulated from the business decisions it oversees. Its neutrality is not a weakness; it is the source of its authority.

Agent Oversight is the compliance system for AI operations.

---

## What Agent Oversight Is Not

Explicit refusals are architecturally as important as positive definitions. Scope creep is the primary long-term risk for a platform of this type — not from malice but from reasonable-looking feature requests that each individually seem harmless and collectively undermine the platform's foundational property.

The foundational property at risk: **neutrality**. Agent Oversight's records are trustworthy because the system has no stake in what it records. The moment Agent Oversight starts participating in the decisions it observes — managing context, brokering knowledge, routing executions, making quality judgments — it forfeits the neutrality that makes its records authoritative. A governance substrate that participates in governance decisions has compromised both functions.

Agent Oversight is not:

**A context broker.** It does not store, version, or manage domain knowledge content. It records references to context that agents consumed (what, which version, when) but holds no opinions about what that content means or whether it is current. Context management requires domain semantics. Domain semantics belong in production intelligence systems, not in the control plane.

**A memory system.** It does not manage what agents remember between runs. Memory systems require relevance judgments. Relevance is domain-specific. Agent Oversight has no basis for relevance judgments and should not develop one.

**An orchestration engine.** It observes orchestration; it does not participate in it. An orchestration engine makes decisions about what to execute next. Agent Oversight records what was executed. Conflating observation with execution makes failures harder to diagnose — when something goes wrong, you cannot tell whether the problem is in the agent, in the orchestration logic, or in the control plane, because they are the same system.

**An evaluation engine.** It records that evaluations occurred and their outcomes. It does not compute quality scores, run evaluations, or make decisions based on evaluation results. Quality evaluation requires domain understanding. Agent Oversight should be blind to quality in the domain sense; it is not blind to operational outcomes (success, failure, cost, latency).

**A decision-making system.** It records what happened. It does not determine what should happen. It enforces operational rules whose content is defined elsewhere. The rule content belongs in the governance layer; the enforcement mechanism belongs in Agent Oversight.

---

## The Tenant Model

Agent Oversight currently serves three operational domains: ReformAI, Personal, and After Glow. These are not a context hierarchy. They are independent tenants.

```
Agent Oversight
├── ReformAI        [isolated tenant]
├── Personal        [isolated tenant]
└── After Glow      [isolated tenant]
```

The relationship between these tenants is operational, not semantic. They share:
- Governance rails (the same policy enforcement infrastructure)
- Observability infrastructure (the same event log, run tracking, cost monitoring)
- Hierarchy visualization (the same control-plane UI)
- Telemetry substrate (the same ingest and event model)

They do not share:
- Agent state or run history
- Context, knowledge, or memory
- Artifacts or outputs
- Cost pools or policy defaults

This isolation is a feature, not a limitation. A compliance system that participates in tenant-specific semantics is a compromised compliance system. A significant failure in one tenant — an agent runs amok, exhausts its budget, produces corrupted outputs — should not propagate to other tenants' operational records or governance state. Agent Oversight absorbs the telemetry from the failure, enforces the applicable cost constraints, and records the incident. It does not propagate the failure. That isolation is only possible if Agent Oversight does not share semantic state between tenants.

**Within ReformAI**, deeper context architecture will eventually matter: global product context, team-level context partitioning, artifact lineage, context projections, and knowledge-plane semantics. That architecture belongs inside the ReformAI tenant — not in the shared control plane. The control plane will observe and record what the ReformAI intelligence systems do. It will not become part of those systems.

---

## The Canonical Primitives

Agent Oversight's data model reflects a deliberate distinction between what the platform owns as ground truth and what it holds as references to things owned elsewhere.

**Ground truth — owned and authoritative:**

*Agent identity and status.* The registry of what agents exist, what tenants they belong to, their hierarchy position, and their operational status. This is the governance substrate's most foundational function: knowing what agents are authorized to operate.

*Run lifecycle records.* The authoritative record of every execution — started, completed, failed — with producing agent, tenant, outcome, cost, duration, and references to inputs consumed and outputs produced. This is the primary content of the ledger.

*The event log.* An append-only trace of operational events: lifecycle transitions, step completions, error events, policy evaluations. This is ground truth. Events are never modified; they accumulate. The event log is the layer from which all other operational state can be derived or verified.

*Policy state.* The current and historical governance rules: cost caps, execution permissions, authorization requirements. The system of record for what is permitted. Each policy change is itself recorded as an event — the governance record is complete and auditable.

*Cost and error summaries.* Materialized from runs and events. These are derived, but Agent Oversight maintains them because they are the primary operational signal.

**References only — not owned:**

*Context references.* Runs declare what context they consumed (a stable reference identifier and version label). Agent Oversight records that this run operated against this context version. It does not store or manage the content.

*Artifact references.* Runs declare what they produced (type, external location, version label). Agent Oversight records the provenance metadata. It does not store content.

*Evaluation records.* Thin records associating quality judgments with runs. Agent Oversight knows evaluations occurred and their scores. It does not run evaluation logic or act on evaluation results.

The governing principle: **Agent Oversight owns the shape. Production systems own the substance.**

This principle determines every future scoping decision. If a proposed addition requires Agent Oversight to hold, interpret, or reason about domain content — rather than recording references to it — that addition belongs in the production system.

---

## The Platform Boundary

The architectural separation between Agent Oversight and production intelligence systems is not a temporary boundary pending further development. It is a principled boundary that should be held permanently.

**Agent Oversight is the control plane. Production intelligence systems are the knowledge plane.**

These planes have different jobs, different trust properties, and different failure modes. Conflating them produces a system that tries to be simultaneously the authoritative operational record (which requires immutability and neutrality) and the active knowledge broker (which requires mutability and domain participation). These requirements are in direct tension.

The clean statement of what each plane owns:

| Concern | Agent Oversight | Production Intelligence System |
|---|---|---|
| What happened | Authoritative | — |
| What it cost | Authoritative | — |
| Whether it was permitted | Authoritative | — |
| What context was consumed | Reference metadata | Authoritative (content, versioning) |
| What was produced | Reference metadata | Authoritative (content, quality) |
| Whether it was good | Reference metadata | Authoritative (evaluation, feedback) |
| What should happen next | — | Authoritative (orchestration, routing) |

Within ReformAI production, the intelligence architecture will eventually require: versioned artifact stores, context projections at global and team scope, evaluation pipelines with quality feedback, and deeper knowledge-plane semantics for institutional memory. That architecture is not premature — it is appropriate for a system that must manage shared institutional knowledge across multiple AI teams operating at production scale. It belongs inside ReformAI. It does not belong in the control plane.

---

## Architectural Principles

The following principles are the load-bearing reasoning behind the architecture. They are stated as principles rather than decisions because they generalize: new decisions should be evaluated against them.

**P1: Governance Before Autonomy.**  
Operational governance — the ability to observe, constrain, and audit what the system does — must precede expansion of the system's autonomy. A system that achieves high capability without corresponding governance is one whose failures cannot be diagnosed, whose costs cannot be controlled, and whose outputs cannot be trusted. Governance is not a constraint on capability; it is the prerequisite for safely expanding it.

**P2: Observability Before Orchestration Complexity.**  
The system must be able to answer "what happened?" clearly before it is safe to ask "what should happen next?" with increasing complexity. Orchestration decisions that cannot be traced to their inputs and observed in their execution are ungovernable. Observability is the foundation; orchestration is built on top of it.

**P3: Schema Reflects Mature Architecture; Behavior Reflects Current Maturity.**  
The data model should anticipate the end state even when runtime behavior has not yet grown into it. This principle makes platform evolution additive rather than disruptive. A schema that reserved the right shape for context references, artifact provenance, and evaluation records can receive production semantics as a graduation — filling in content without reshaping containers. A schema that did not make this reservation requires disruptive restructuring at exactly the moment the platform is attempting to scale.

**P4: Operational Metadata Separate from Intelligence Semantics.**  
Operational records (what happened, when, at what cost) and intelligence content (what agents know, what strategy means, what quality looks like) have different lifecycle, access, and trust properties. Operational records are append-only, universally accessible, and optimized for completeness. Intelligence content is versioned, scope-restricted, and optimized for freshness and relevance. A system that conflates these must simultaneously optimize for properties that are in direct tension. The separation is not a convenience; it is an architectural correctness requirement.

**P5: Control Planes Observe; They Do Not Participate.**  
A governance substrate that participates in the decisions it oversees loses the neutrality that makes its records trustworthy. This is not merely theoretical. The practical failure mode is: the control plane accrues semantic knowledge about the domain it observes, starts making routing or quality decisions based on that knowledge, and becomes both the auditor and an actor in the same system. At that point, its records can no longer be fully trusted as neutral operational facts — because the system that produced the records was also shaping the operations it recorded.

**P6: The Ledger Is the Foundation of Trust.**  
Append-only operational history is not an implementation choice. It is the property from which all auditability, lineage, and governance derive. A mutable operational record cannot support the question "what exactly happened during run 456?" with full confidence, because any record might have been modified. Immutability of the event log is the single most important architectural commitment in the system. Everything that depends on trust — governance, lineage, evaluation, HITL — depends on this commitment first.

**P7: Lineage and Provenance Are First-Class Operational Concerns.**  
The ability to reconstruct "why did the system produce this output?" from the operational record is a product requirement, not an optimization. Lineage requires that every context read, every artifact write, and every execution decision is recorded with sufficient foreign-key linkage to reconstruct the causal chain. A platform that generates outputs but cannot explain them is a platform that cannot be trusted in high-stakes operational contexts.

**P8: Neutrality Is the Source of Authority.**  
The operational ledger is trusted because it has no stake in what it records. The governance enforcement layer is trusted because it applies rules whose content was defined elsewhere. The moment the control plane starts making domain decisions — what context is relevant, what quality is acceptable, what should run next — it forfeits both the neutrality and the authority. Preserving neutrality is not passivity; it is the discipline that makes the platform's records worth relying on.

**P9: Prove Patterns Before Implementing Production Semantics.**  
The correct role for the testbed phase is to prove the shape of architectural patterns at low cost, without implementing the full production semantics. Context references in run metadata prove the lineage pattern without requiring a context broker. Artifact metadata records prove the provenance pattern without requiring content-addressed storage. Thin evaluation records prove the evaluation primitive without requiring feedback loops. When production systems are ready to implement the substance, the shape has already been exercised, the schema is already reserved, and graduation is additive.

**P10: Isolated Tenants, Shared Governance Substrate.**  
Tenants share infrastructure and governance rails; they do not share semantic state. The governance substrate's universality is its value. Its tenant isolation is the property that allows it to remain neutral and trustworthy across domains with different purposes, different stakeholders, and different risk profiles.

---

## The Graduation Pattern

Agent Oversight's relationship to production intelligence systems follows a specific pattern: **the testbed proves the shape; production implements the substance.**

This pattern is not merely practical — it is the correct epistemic sequence. A pattern that cannot be proven at metadata level in the testbed is probably not understood well enough to implement at production scale. The discipline of implementing patterns at reference-only fidelity first forces architectural clarity: you cannot hide design uncertainty behind implementation complexity.

The graduation sequence for key patterns:

| Agent Oversight proves | Production implements |
|---|---|
| Context references in run metadata | Full context broker with versioned artifact store |
| Artifact metadata and external references | Content-addressed artifact store with provenance |
| Lightweight dispatch-time policy check | Full governance plane with policy inheritance |
| Thin evaluation records | Evaluation pipeline with quality-gating and feedback |
| Hierarchy as organizational metadata | Coordination semantics, team context projections |
| Append-only event log | Full knowledge plane with fact provenance |

Each row represents a pattern that has been architecturally proven at low cost in the testbed, and whose full implementation belongs in the production intelligence system when that system is mature enough to receive it.

This sequence also has an important failure prevention property: features that are built prematurely in the testbed — before the pattern is well understood — tend to either become load-bearing in ways that block later evolution, or become dead code that creates maintenance burden without delivering value. Graduating from proven patterns avoids both failure modes.

---

## Long-Term Direction

The platform is evolving toward what might be described as an **epistemic operating system**: a system that manages the lifecycle of knowledge-producing workers under governance constraints, with full provenance and quality tracking.

An operating system manages resources and mediates between processes and underlying infrastructure. It does not understand what the processes are doing in the domain sense; it enforces resource limits, provides isolation, and records operational events. Agent Oversight is evolving toward this model for AI operations.

At full operational maturity, the platform should be capable of:

**Answering operational questions without human investigation.** "Why did run 456 fail?" should produce a complete causal trace through the event log — agent state at dispatch, context versions consumed, policy constraints active, step sequence, failure event, error taxonomy. Not an error message; a full operational reconstruction.

**Enforcing governance proactively.** Budget approaching its limit should trigger dispatch suspension before the next run begins, not a post-hoc report. Policy violations should be prevented at the enforcement surface, not discovered in retrospect.

**Progressive trust governance.** New agents and new agent types should enter the platform in a restricted operational mode. Trust is accumulated through demonstrated reliability over run history, not granted at registration. Restrictions loosen as the operational record supports expanding them. Trust is revocable.

**Human-in-the-loop as a first-class primitive.** For high-stakes executions, HITL is not an emergency brake — it is a designed-in checkpoint that the platform manages. Runs that require approval wait in a governed state. The waiting itself is recorded in the event log. Approval and denial are events with attributed provenance.

These capabilities presuppose the foundational primitives in their mature form: an immutable event log, dispatch-time policy enforcement, context and artifact provenance, and evaluation records that accumulate into institutional quality signal. The long-term direction is a platform that earns operational trust incrementally — not one that asserts trustworthiness through architectural claims.

---

## Intentional Exclusions

The following are principled exclusions — not deferred features, but capabilities that would compromise the platform's foundational properties if introduced.

**Cross-tenant context sharing.** Tenants are isolated namespaces. Their agents may be observed by the same control plane, but their institutional knowledge, memory, and artifacts are not shared. Agent Oversight has no basis for relevance judgments across domain boundaries, and developing one would require domain participation that violates platform neutrality.

**Peer-to-peer agent communication.** Direct agent-to-agent messaging introduces ordering, delivery, and backpressure concerns that the platform must then manage. More importantly, it creates coordination semantics that bypass the event log — producing system behavior that cannot be fully reconstructed from the operational record. All coordination should be mediated through the event log. Agents do not message each other; they produce facts that other agents consume.

**Cognitive architecture modeling.** Modeling how agents reason — reasoning traces, cognitive state, chain-of-thought records as operational primitives — couples the control plane to specific model providers and their output formats. It also violates the boundary between "what happened" (operational) and "was it good reasoning" (evaluation). The control plane should be model-agnostic. Cognitive architecture belongs in the intelligence layer.

**Evaluation feedback loops in the control plane.** Evaluation records belong in Agent Oversight as metadata. Evaluation logic — computing quality scores, routing decisions based on quality history, agent promotion and demotion — belongs in the production intelligence system. A control plane that acts on quality signals is no longer neutral with respect to the domain decisions it observes.

**Content-addressed artifact storage.** Artifact content belongs in the systems that produce and consume it. Agent Oversight records metadata and references. Moving artifact content into the control plane creates a dependency between the governance substrate and the content lifecycle of every artifact in the system — a coupling that would make the control plane both harder to maintain and less trustworthy as a neutral record.

---

## Appendix: How to Update This Document

This document should be updated when the **reasoning** changes, not when implementations change. Implementation changes belong in session logs, migration notes, and technical specifications.

Add a new section or principle when a new class of architectural problem is identified that existing principles do not address. Revise an existing principle when the reasoning behind it has changed — and record why it changed.

Do not add to this document:
- Specific technology choices
- Schema field lists or API endpoint documentation
- Sprint state or feature timelines
- Code examples or implementation patterns

This document should remain legible to someone who has never read the codebase. Its value is in the reasoning, not the detail. When detail accumulates here, it crowds out the reasoning and the document becomes a reference rather than an argument. References go stale. Arguments, if they were right, do not.
