# Product — Agent Agile Force

**Document type:** Canonical — workspace context  
**Owner:** Founder/Operator  
**Workspace:** agent-oversight  
**Update trigger:** Product scope changes, user definition changes, goal changes, "what it does not do" boundary changes  
**Consumed by:** Product Clarification Agent (primary), Story Structuring Agent (primary)

---

> If this document carries a staleness flag, agents reading it must surface that flag in their output and reduce their context integrity rating accordingly.

---

## What It Is

Agent Agile Force is a four-agent AI-assisted delivery operating system for a two-person startup team. It replaces the PM/BA/QA ceremony layer — standups, planning sessions, grooming, refinement — with async, agent-produced artifacts at each stage of the delivery workflow. The founder describes a fuzzy goal; the system produces a structured Clarification Brief, then Definition-of-Ready stories, then an Engineering Plan, then a Release Assessment — each reviewed and approved by a human before advancing.

The system is being built inside Agent Oversight as a sandbox to validate the pattern. Once proven, the identical agent workflow will be applied to ReformAI production using ReformAI's own canonical documents.

---

## Who It Serves

**Primary users:**

- **Founder/Operator** — Acts simultaneously as product manager, product owner, and business analyst. Has deep product and market insight, limited engineering bandwidth. Provides fuzzy goals as input; receives structured, actionable artifacts as output. Makes all product, priority, and release decisions. Maintains all canonical documents.

- **Engineer** — Receives clear, unambiguous stories meeting the Definition of Ready. Contributes to ARCHITECTURE.md and STACK.md. Flags when agent-provided technical context appears incorrect. Makes implementation decisions within the scope established by the Founder/Operator.

**This system is not built for:**
- Large engineering teams where coordination ceremonies have real value
- Teams that need real-time collaboration features
- Organizations that require external ticket system integration in v1

---

## Core Problems It Solves

1. **Ambiguous requirements waste engineering time.** Without a structured clarification step, engineers begin work on poorly-scoped stories and discover missing information mid-implementation. The Product Clarification Agent converts fuzzy input into a structured Brief before any story is written.

2. **Synchronous ceremony has negative ROI for a two-person team.** Standups, planning sessions, and grooming exist to coordinate multiple people. A two-person team has no coordination overhead worth solving with ceremonies. Agent-produced artifacts replace the ceremonies without losing the information they were supposed to generate.

3. **Context lives in one person's head by default.** The founder holds product intent, domain knowledge, and strategic context internally. Agents cannot access tribal knowledge — only documents. The canonical doc system forces externalization of context that agents need to function, which also makes that context available to the engineer without synchronous explanation.

4. **QA and release decisions are inconsistent without a checklist.** Without a systematic process, release confidence depends on whoever happens to be thinking carefully that day. The QA / Release Confidence Agent applies KNOWN-RISKS.md systematically against every release, producing a structured assessment with explicit confidence scoring.

---

## Current Strategic Goals

1. **Validate the Agile Team end-to-end under the `agent-oversight` workspace.** The Product Clarification Agent is the pilot. Each subsequent agent (Story Structuring, Engineering Planning, QA / Release Confidence) is built using learnings from the previous one. The workflow is complete when a fuzzy founder input travels through all four agents to a Release Assessment without requiring human intervention between stages beyond explicit approval gates.

2. **Prove the canonical-docs-as-context pattern.** The system's core claim is that agents reading accurate, current, human-maintained docs produce useful output. This must be demonstrated with real runs against real goals before the pattern is applied to production.

3. **Define the reusable team template.** The Agile Team is a workflow definition, not a bespoke implementation. The agents, schemas, and orchestration logic must be generic enough to run under any workspace (ReformAI, AfterGlow, Personal) with only the canonical docs changing.

4. **Port the proven pattern to ReformAI.** Once the Agile Team runs successfully under `agent-oversight`, a separate set of canonical documents is created for the `reformai` workspace. The same agents, same schemas, same orchestrator — different context.

---

## What It Does Not Do

- **Does not replace the engineer.** Agents clarify, structure, and surface. Engineers build. No agent writes, reviews, or merges code in v1.

- **Does not make product or priority decisions.** The founder decides what to build and when. Agents produce structured information to inform those decisions — they do not make them.

- **Does not update canonical documents.** Canonical documents are maintained by humans. Agents flag when docs appear stale, but the human makes the update.

- **Does not run ceremonies or schedule anything.** No standups, no retrospectives, no sprint planning. The system produces artifacts; humans use them asynchronously.

- **Does not connect to external project management tools in v1.** No automatic Jira or Linear ticket creation. Stories are produced as structured output; humans create tickets if needed.

- **Does not have live data access.** In v1, agents read static canonical documents only. They do not query databases, APIs, or live systems mid-run.

- **Does not have memory.** Agents are stateless. Learning from past runs is accumulated by humans in LESSONS.md files and reflected in updated canonical documents and revised prompts.

---

## Key Product Decisions

| Decision | Rationale |
|---|---|
| Async over ceremony | A two-person team has no coordination overhead worth solving with synchronous sessions |
| Human approval at every workflow threshold | Agent outputs are hypotheses. No output advances automatically. Human review is non-negotiable. |
| Context before capability | Canonical docs must be accurate before agents are built. An agent with no reliable context produces general-purpose output, not context-aware leverage. |
| Orchestrators are deterministic state machines | LLM judgment belongs in specialist agents. Orchestrators enforce rules, not make reasoning decisions. |
| Specialist agents are stateless pure functions | Input + context → output. No side effects. No tool calls. No knowledge of other agents. Enables retries, parallelism, and clean failure isolation. |
| Schema contracts are defined before system prompts | The schema is the API. Prompts implement the API. Writing the prompt first guarantees incompatible agents. |
| Workspace = context parameter, not agent layer | Workspace isolation is structural (workspace-scoped doc paths), not an additional execution tier. |
