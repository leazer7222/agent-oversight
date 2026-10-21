# Cameron's Pool Acquisition System - Executive Summary

Date: 2026-10-20
Scope of this summary: the four-stage engagement completed today - independent assessment, final design, same-day prototype plan, and prototype execution.
Repository: `leazer7222/agent-oversight` - branch `claude/pool-prototype-2026-10-20`, commit `838523b` (pushed)

---

## 1. The business objective

Secure one commercially viable, recurring pool partnership for Cameron's private swimming lessons (children eight and under) within 60 days, starting in Katy, Texas (15 miles, expandable to 30), with a system that advances the work on its own while Cameron keeps authority over money, contracts, meetings and safety.

## 2. What was decided

| Question | Decision | Why |
|---|---|---|
| Architecture | **Rejected** the original "autonomous orchestrator + two reasoning agents". **Approved** a deterministic, event-driven controller plus two AI-enabled capabilities (Facility Researcher, Partnership Coordinator) on the existing Agent Oversight infrastructure | The next action in this pipeline is a database query, not a judgement; an LLM planner adds cost and a new failure class while removing inspectability. AI is kept where it genuinely adds value: extracting facts from web pages, writing one personalised sentence, classifying replies, proposing new search queries |
| Identities vs processes | Three registered agent identities, **one** worker process, no agent-to-agent protocol | Identities give per-capability kill switches, cost caps and attributable telemetry; a second process would add nothing |
| Pre-contact scoring | Replaced the numeric suitability score with four-state evidence triage (contact first / research further / not currently suitable / disqualified); safety is a hard gate, never a weighted criterion | Measured: before contact the score carried one attribute's worth of information |
| Autonomy | Supervised first, then campaign-scoped autonomous outreach once ten machine-checkable conditions are met; revocable at any time; commercial terms, meetings and safety stay with Cameron | Preserves the long-term autonomy goal without letting an LLM own an irreversible action |
| Tonight's build | A genuine end-to-end prototype with real AI, real persistence and real telemetry, with the two external integrations (Google Places, email) simulated and labelled | No Places key exists; nothing may be sent yet |

## 3. What was built and proven today

All of the following ran against the production Supabase project through the real durable job queue, with every job recorded in the Agent Oversight run ledger under the identity that owns it.

| Stage | Result |
|---|---|
| Controller | Deterministic stage gating; saturation, replenishment and radius-expansion policy rules evaluated and recorded (expansion to 30 miles was **recommended, not acted on**); objective-progress summary; its own runs in the ledger |
| Discovery | 33 facilities ingested from recorded Places responses, every row labelled `source='fixture'`; **re-running created zero duplicates** |
| Enrichment | 33 facilities enriched by live model calls; **149 facts and 13 contacts written, each backed by a verbatim quote found in the source page; 0 unsupported claims accepted** |
| Triage | 16 contact-first, 8 research-further, 9 disqualified; 180 open qualification questions generated (these become the email body and the call script) |
| Drafting | 10 personalised outreach drafts, each asking that facility's own open questions; all passed the anti-fabrication gate; **none sent** - the prototype has no send capability at all |
| Replies | 10 simulated replies (labelled `[SIMULATED]`), all classified. The prompt-injection scenario was **flagged and escalated, not acted on**; a price quote escalated; an opt-out was routed to suppression; a meeting request went to Cameron's decision; two routine questions were marked as FAQ auto-reply candidates |
| Governance | Per-identity kill switch proven: pausing the Coordinator blocked its next job while the Researcher kept running. Budget cap $5/month enforced before every job. Spend for the whole build: **$0.05** |
| Dashboard | Objective progress, pipeline, next actions, replies with classification, drafts and the research worksheet - all read from the database; prototype data labelled on the page |
| Quality gates | 111 automated tests pass (22 new), TypeScript clean, migration lint clean, 499 API authorization checks pass, secret scan clean |

## 4. What is real and what is simulated

**Real:** the database and queue (lease, heartbeat, retry, cancellation), the three identities, telemetry and cost attribution, the budget cap, the credential vault, the model calls for enrichment / drafting / classification, the evidence rule, the anti-fabrication gate, the escalation rules, the dashboard reads.

**Simulated, and labelled in the data:** Google Places results (recorded fixtures, `source='fixture'`), inbound replies (scripted, `[SIMULATED]` subject enforced by the database), and sending (does not exist).

## 5. Defects found and fixed along the way

Found by verification before writing the plan, each would have broken the build: the API layer cannot read the business schema directly (PostgREST does not expose it) - every read now goes through audited database functions; the telemetry SDK read the wrong secret - fixed and verified against production; the worker emitted no telemetry and only enforced the kill switch conditionally - fixed; fixture facilities were labelled as live Places data - fixed; the vault had no encryption key - generated. Found during execution: a job paused mid-flight could be stranded because telemetry was opened before the kill-switch check - fixed and re-proven; a model schema rule rejected a tool definition - fixed, and the queue's retry recovered the job on its own.

## 6. Decisions still needed from Cameron (unchanged)

Legal name and postal address; rate ceiling and whether revenue share is acceptable; insurance and certification posture stated as fact; safety minimums; approved campaign positioning text; the pre-approved FAQ; who makes phone calls and in what weekly time box; whether a booking link replaces calendar integration in v1.

## 7. Known limitations and next steps

- The dashboard pages on the new branch were not visually verified tonight (sign-in blocked by a Supabase redirect setting, see below); their data was verified by query.
- The vault currently holds the platform's Anthropic key by instruction; it must be replaced with Cameron's own key before any real campaign.
- One pre-existing route (`approvals`) is broken by the schema-exposure finding and is scheduled for the next milestone.
- CI still does not run on GitHub; the workflow exists and is parked.

Next milestones, in order: campaigns entity and a single database send chokepoint; real provider integration with reconciliation; supervised pilot at 5-8 messages a day; then the measured transition to campaign-scoped autonomy.

## 8. How to run it

```
python scripts/seed_prototype.py --status          # tenant, identities, counts
python scripts/demo_prototype.py --pause-demo      # full demonstration including the kill switch
python scripts/seed_prototype.py --teardown        # pause agents, cancel jobs (ledger rows are kept by design)
```

Dashboard (after the branch is deployed): `https://agent-oversight.vercel.app/dashboard/sourcing?company=16f34273-6744-4ea7-8042-7562e409189c`

Documents: `docs/reviews/pool-acquisition-architecture-assessment.md`, `pool-acquisition-final-design.md`, `pool-acquisition-prototype-implementation-plan.md`.
