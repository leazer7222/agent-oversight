# Adaptive Cost Risk Engine — RFC Summary in Plain English

This document explains what each RFC (Request for Comments) in the Adaptive Cost Risk Engine
architecture actually means, in plain language. No jargon. No SQL. Just what each one does
and why it matters.

---

## What Is This System?

We are building the financial brain of the AI execution platform.

Every time an agent runs, it costs money. Right now, we don't know what a run will cost
before it starts, we don't enforce hard budget limits while it's running, and we don't
automatically get better at predicting costs over time.

This system fixes all of that. Think of it as a financial risk management layer — similar
to what banks use before approving a loan — but for AI agents.

The ten RFCs below define exactly how it works, layer by layer.

---

## RFC-001 — Operational Invariants
### "The Laws of Physics"

**What it is**: A formal list of rules the system must never break, ever, under any
circumstances.

**In plain English**: Every complex system has rules that seem obvious but get violated
under pressure — a deadline, a bug, a shortcut. This RFC writes those rules down
formally, specifies exactly how each one is enforced (by the database, by the application,
or by monitoring), and says what happens when one is violated.

Examples of rules:
- Every agent run must have a cost estimate before it starts
- Budget reservations must be settled within 10 minutes of a run finishing
- No cost record may ever be edited or deleted

**Why it matters**: Without written, enforced rules, systems drift. Engineers make
reasonable-looking shortcuts that individually look fine but collectively destroy
the integrity of the system. This RFC is the foundation everything else stands on.

---

## RFC-002 — Artifact Model
### "The Permanent Record Keeper"

**What it is**: A definition of every important document the system produces —
what it contains, who owns it, and the rule that it can never be changed once written.

**In plain English**: When something important happens — an estimate is made, a run
completes, a budget is reserved — the system writes a permanent record of it. Like
a court reporter's transcript, it cannot be altered. If something was recorded
incorrectly, you write a *correction note* alongside the original — you never
erase and rewrite the original.

The eight document types are:
1. **Estimate Artifact** — what we predicted before the run (cost, confidence, inputs used)
2. **Evaluation Artifact** — how accurate the prediction was after the run
3. **Pricing Table** — what each AI model costs per token, versioned over time
4. **Calibration Snapshot** — the learned correction patterns applied to estimates
5. **Budget Reservation** — the financial hold placed before a run starts
6. **Settlement Record** — the final accounting of what the run actually cost
7. **Recommendation Artifact** — which model was selected and why
8. **Quality Signal** — observations about whether the output was actually good
9. **Correction Record** — the formal way to note that something was wrong, without changing the original

**Why it matters**: Permanent, immutable records are what make the system auditable.
If a customer asks "why was this run approved?" or "why did costs increase 40% this
month?", the answers come from reading these records.

---

## RFC-003 — Telemetry Contract
### "The Common Language"

**What it is**: The standardized format that every part of the system uses when
communicating with every other part.

**In plain English**: The platform has many moving parts — the estimator, the budget
enforcer, the agent runtime, the calibration system. They all need to talk to each
other. This RFC defines the exact format every message must follow, what fields
every message must include, and the rules about delivery guarantees.

Key concepts:
- Every message has a unique ID so duplicates can be ignored
- Every message carries a "trace ID" so all related messages can be linked together
- Some messages must be sent before a run starts (synchronous). Most can be sent afterward (async)
- Nothing slow or expensive is ever allowed in the path that controls whether a run starts

**Why it matters**: Without a common language, different parts of the system
interpret messages differently, duplicate events corrupt data, and debugging
becomes nearly impossible. This RFC is the contract that makes all services
interoperable.

---

## RFC-004 — Runtime Governance
### "The Financial Enforcer"

**What it is**: The mechanics of budget reservations, spending tracking, and stopping
a run that is costing too much.

**In plain English**: Before a run starts, the system reserves money from the tenant's
budget — like putting a hold on a credit card. While the run executes, it watches
actual spending tick up. If spending approaches the limit, it sends a warning. If it
hits the hard limit, it tells the agent to stop cleanly. If the agent ignores the
stop signal, it force-terminates it after a short grace period.

When the run finishes, the reserved money is released and the actual cost is recorded.

This RFC also covers:
- What happens when the provider goes down mid-run
- How parent agents and their child agents share a budget
- The race conditions that could allow budget to be exceeded and exactly how to prevent them
- The cleanup job that releases budget that was never properly settled

**Why it matters**: Without hard financial enforcement, a runaway agent can cost
thousands of dollars before anyone notices. This RFC is what makes the platform
financially trustworthy enough for enterprise customers.

---

## RFC-005 — Task Taxonomy
### "The Classification System"

**What it is**: A formal, versioned list of the types of work agents do, with
precise definitions of what "simple," "medium," and "complex" means for each type.

**In plain English**: Every agent run gets labeled with what kind of work it is doing:
research, writing, coding, data analysis, orchestrating other agents, and so on.
It also gets labeled with how complex that particular job is.

These labels are critically important because the system learns separately for each
combination. A complex research task and a simple coding task behave very differently —
they cost different amounts, take different amounts of time, and produce outputs of
different quality. Lumping them together would make the system less accurate.

There are eight initial task types. Adding a new one requires a formal review process,
because too many task types means not enough data to learn from each one.

**Why it matters**: The task type label is on every run record, every estimate, and
every calibration record from day one. It cannot be added later. Getting it right
early — with machine-verifiable definitions, not vague human descriptions — is
foundational to everything the system learns.

---

## RFC-006 — Calibration Infrastructure
### "The Learning System"

**What it is**: The pipeline that takes thousands of "predicted vs actual" comparisons
and turns them into correction factors that make future estimates more accurate.

**In plain English**: The deterministic estimator (Phase 1) uses a rulebook to predict
cost. It is often wrong. Over time, patterns emerge: research agents with web search
consistently underestimate by 34%. Code generation agents with large inputs consistently
overestimate by 12%.

Calibration captures these patterns. Every time a run completes, the system records
how far off the estimate was. Over time, it computes correction multipliers per category.
Future estimates for that category are automatically adjusted.

But calibration is careful about correctness:
- It never learns from incomplete or suspicious data
- It waits for all quality signals to arrive before using a run's data
- It runs proposed corrections in "shadow mode" (silent testing) before applying them
- Every version of the calibration model is permanent and can be rolled back instantly

**Why it matters**: Calibration is what transforms a rule-based estimator into an
intelligent one. Without it, estimates never improve no matter how much the system runs.
With it, estimates get meaningfully more accurate over months of operation.

---

## RFC-007 — Quality Signal
### "Measuring Whether It Was Actually Good"

**What it is**: The system for collecting and storing signals about whether an agent's
output was useful, correct, and worth what it cost.

**In plain English**: Cost and speed are easy to measure — they appear in billing records.
Quality is harder. Did the agent actually answer the question correctly? Did the user
accept the output or immediately ask for a redo? Did the downstream process that used
the output succeed?

This RFC defines the signals the system collects:
- **Immediate**: did the task complete? did tools work?
- **Short-term**: did the user accept the output, or ask for a revision?
- **Medium-term**: how many revisions did the output end up needing?
- **Long-term**: did the downstream workflow that used this output succeed?
- **On-demand**: what did an AI evaluator agent score it?

Crucially, quality is never collapsed into a single score. Different signals arrive at
different times over days and weeks. Storing them raw means the system can reweight
them later if the formula for "what is quality?" changes.

**Why it matters**: Without quality signals, the system can only optimize for cheapness
and speed. A cheap, fast agent that produces wrong answers is worse than a more
expensive one that produces correct answers. Quality signals are what eventually allow
the system to make genuinely intelligent routing decisions.

---

## RFC-008 — Routing Provenance
### "Choosing the Right Model and Explaining Why"

**What it is**: The design for how the system will eventually select which AI model
to use for each task, and how every such decision is permanently recorded and explainable.

**In plain English**: Different AI models have different strengths, costs, speeds,
and quality profiles. A complex research task might warrant an expensive, high-quality
model. A simple classification task might be perfectly served by a cheap, fast one.

Eventually, instead of the caller always specifying the model, the system will look at:
- What does this task require?
- What budget is available?
- What are the quality requirements?
- What does telemetry show about each model's performance on this type of task?

Then it selects the best model and records exactly why — every candidate considered,
every candidate eliminated (and why), every score, and what mode was used (cheapest
acceptable? best quality? fastest?).

The record of this decision is permanent and fully explainable. A customer asking
"why did the system use Gemini instead of Claude?" gets a factual answer from the
audit trail, not a guess.

**Why it matters**: Model selection is eventually the most impactful cost optimization
available. Routing to the right model for the right task can cut costs significantly
while maintaining quality. But it must be auditable — enterprise customers and
compliance teams need to understand every automated decision with financial consequences.

---

## RFC-009 — Schema Evolution
### "The Rules for How the System Can Change"

**What it is**: The binding rules for how the database structure, event formats, and
API contracts can be modified over time without breaking anything or corrupting data.

**In plain English**: Systems change. New fields get added. Old fields become obsolete.
The meaning of a field sometimes needs to evolve. Without strict rules, these changes
silently break consumers, corrupt historical data, and eventually make the system
impossible to reason about.

This RFC defines:
- Fields can be added carefully (backward-compatible)
- Fields can only be removed after a 90-day warning period with all consumers migrated
- Fields can never be renamed — you add the new name, deprecate the old one
- The type of a field can never be changed — you add a new field with the new type
- Three categories of data must never be mixed: what the system *decided* before a run,
  what *actually happened* during a run, and what the *outcome* was afterward

The last rule — keeping these three categories separate — is the most important.
Mixing them makes it impossible to replay past decisions, audit why something happened,
or understand the system's history.

**Why it matters**: Schema mistakes look harmless in year one and become catastrophic
in year three. A field renamed without a migration window breaks consumers. A type
changed silently corrupts analytics. A field reused for a different purpose makes
historical records uninterpretable. These rules prevent that accumulation of debt.

---

## RFC-010 — Implementation Sequencing
### "The Build Plan"

**What it is**: The master plan for what to build, in what order, with explicit
checklists for when each phase is complete and what comes next.

**In plain English**: The architecture is designed in four phases, each building on
the last:

**Phase 1 — Foundation**: Every run gets a cost estimate before it starts. Every
completed run gets an evaluation comparing the estimate to reality. The system is
*observable* — you can see what's happening — but not yet intelligent.

**Phase 2 — Calibration**: The system starts learning from its mistakes. Estimates
improve automatically over time. Drift is detected when something changes. The system
is now *calibrated*.

**Phase 3 — Runtime Governance**: Hard budget limits are enforced. Agents cannot
spend more than they are allocated. The system is now *governed* — financially
trustworthy enough for enterprise customers.

**Phase 4 — Intelligence**: The system selects models intelligently based on
everything it has learned — cost profiles, quality profiles, latency profiles.
It explains every decision it makes.

Each phase has a gate checklist — specific, verifiable criteria that must all pass
before the next phase begins. No phase is "done" when it "seems to be working."
It is done when every item on the checklist is verified.

**Why it matters**: Building systems in the wrong order creates hidden coupling and
technical debt that never fully resolves. This RFC ensures the foundation is solid
before the learning layer is built, the learning layer is solid before financial
enforcement is added, and financial enforcement is solid before intelligent routing
is layered on top.

---

## The Big Picture

These ten RFCs together define a system that is:

- **Financially trustworthy**: hard limits hold, reservations are correct, settlements are accurate
- **Self-improving**: estimates get better the more the system runs
- **Explainable**: every decision — estimate, model selection, approval, abort — has a permanent, readable explanation
- **Auditable**: historical records are immutable and can answer "why did this happen?" years later
- **Evolvable**: the schema rules ensure the system can change without breaking its history

The system is closer to a financial risk engine than a typical software feature.
The discipline required to maintain it — immutable records, permanent audit trails,
versioned calibration, governed model selection — is the same discipline that makes
financial systems trustworthy at enterprise scale.
