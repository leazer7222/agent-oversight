# Known Risks — Agent Oversight / Agent Agile Force

**Document type:** Canonical — workspace context  
**Owner:** Founder/Operator + Engineer  
**Workspace:** agent-oversight  
**Update trigger:** New risks discovered, existing risks mitigated or resolved, severity changes  
**Consumed by:** QA / Release Confidence Agent (primary), Product Clarification Agent (secondary — staleness check)

---

## RISK-001: Context Staleness

**Status:** Active  
**Severity:** High  
**Area:** All agents

**Description:** An agent invoked on stale canonical documents (PRODUCT.md, DOMAIN.md, etc.) will produce confidently wrong outputs that pass schema validation and look correct on first read. There is no automatic staleness detection in v1. The failure is silent until a human notices the output doesn't match current product reality.

**Mitigation:** The 48-hour update rule: canonical documents must be updated within 48 hours of any trigger event (architectural decision, product change, resolved risk, new constraint). The Team Orchestrator enforces a staleness gate by comparing file modification times against the 48-hour threshold — it refuses to start a run if any required document exceeds the threshold. The Product Clarification Agent checks for staleness flags (`> STALE` markers) in received docs and surfaces them in its output.

**Resolution:** This risk partially resolves when automated git-based staleness detection is implemented (Phase 3). It never fully resolves — it depends on human discipline in maintaining documents.

---

## RISK-002: The Plausibility Trap

**Status:** Active  
**Severity:** High  
**Area:** All agent outputs

**Description:** LLMs produce well-formatted, internally consistent outputs regardless of whether the underlying reasoning is correct. A Clarification Brief or Story that looks complete may have subtle errors — wrong problem framing, incorrect domain term usage, unmeasurable success criteria, scope that doesn't match PRODUCT.md — that are not caught without careful human review. The danger is not that outputs look obviously wrong. It is that they look obviously right.

**Mitigation:** Every agent output is explicitly labeled a hypothesis. The quality rubric for each agent (defined in its README.md) provides specific pass/fail signals for human reviewers. No output automatically advances to the next stage. Human review is required at every quality gate.

**Resolution:** None. Human review is the mitigation — no automated tool resolves the fundamental reliability limitation of LLM reasoning. Treat every agent output as a hypothesis until a human approves it.

---

## RISK-003: Missing Canonical Documents

**Status:** Active — transitioning (documents being created this session)  
**Severity:** High  
**Area:** Product Clarification Agent, Story Structuring Agent

**Description:** If PRODUCT.md or DOMAIN.md are absent when the PCA is invoked, the agent falls back to general-purpose LLM reasoning without product context. The output will look like a Clarification Brief — structured, plausible — but will not be grounded in the actual product. Schema validation passes. The content is useless.

**Mitigation:** The Team Orchestrator refuses to start a run if any document listed in the context bundle is missing. It exits with an explicit error naming the missing documents. The PCA itself checks for doc presence and rates context integrity Red if required docs are absent.

**Resolution:** This risk resolves when all canonical documents listed in the context bundle exist and are current. Currently in progress.

---

## RISK-004: LLM Cost Overrun

**Status:** Active  
**Severity:** Medium  
**Area:** Agent runtime — all agents

**Description:** Agents invoked repeatedly — especially during debugging, prompt iteration, or with long documents in context — can accumulate significant LLM API costs without visibility. Free-tier providers (Gemini) may exhaust quotas silently, switching behavior unexpectedly. Paid providers (Anthropic, OpenAI) accumulate real costs per token.

**Mitigation:** All agents report `tokens_in`, `tokens_out`, `cost_usd` on `run_completed`. Cost is visible per agent and per team in the Agent Oversight dashboard. The `AGILE_LLM_PROVIDER` env var makes provider switching explicit. Watch dashboard cost charts before extended prompt iteration sessions.

**Resolution:** When the Agent Oversight dashboard supports per-agent cost alerts on configurable thresholds (Phase 2 of dashboard enhancement).

---

## RISK-005: Scope Drift in Clarification Briefs

**Status:** Active  
**Severity:** Medium  
**Area:** Product Clarification Agent output quality

**Description:** When the human provides a solution-framed input ("add a button that does X," "build a feature that Y"), the PCA may restate the proposed solution as the goal instead of extracting the underlying user problem. This leads to downstream stories that are implementation specifications rather than user-value statements. The engineering plan then optimizes for building the proposed solution rather than solving the actual problem — which may or may not be the right solution.

**Mitigation:** The PCA system prompt explicitly instructs: always restate as a user problem ("users currently cannot Z"), never restate as a proposed solution. The quality rubric's first check is "does the Problem Statement describe a user problem, not a feature?" Human reviewers check this explicitly before approving a Brief.

**Resolution:** Track via dashboard — if Story Structuring consistently produces implementation-spec stories, it signals PCA prompt revision is needed. This risk evolves as the prompt is refined through real runs.

---

## RISK-006: Definition of Ready Bypass

**Status:** Active  
**Severity:** Medium  
**Area:** Story Structuring Agent → Engineering handoff

**Description:** A story missing one or more of the ten Definition of Ready fields may advance to engineering because the human reviewer doesn't check every field systematically. The result is the engineer encountering missing information mid-implementation — wasted context-switching and potential rework.

**Mitigation:** STORY-READY.md defines the ten fields explicitly and is a canonical document the Story Structuring Agent reads as its primary constraint. The SSA is instructed to refuse to produce incomplete stories. The quality gate at the SSA → human → engineering handoff requires explicit field-by-field validation. A checklist in STORY-READY.md supports this review.

**Resolution:** When the Story Structuring Agent is built and the automated schema validation of story output enforces field completeness programmatically.

---

## RISK-007: Orchestrator Non-Determinism

**Status:** Mitigated by design  
**Severity:** High if violated  
**Area:** Team Orchestrator

**Description:** If the Team Orchestrator uses LLM reasoning to make workflow decisions (which agent to call next, whether to skip a quality gate, how to interpret ambiguous output), the coordination layer becomes non-deterministic. Failures become untraceable. Quality gates become unreliable.

**Mitigation:** The Team Orchestrator is a deterministic Python state machine. It makes no LLM calls. Every workflow transition is a rule, not a judgment. LLM reasoning belongs exclusively in specialist agents. This constraint is enforced at the architectural level and must be maintained as orchestrator complexity grows.

**Resolution:** This risk is mitigated by design. It re-activates if anyone adds LLM calls to the orchestrator. Review any orchestrator changes for this violation.
