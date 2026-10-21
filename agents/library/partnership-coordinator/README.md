# Partnership Coordinator

Capability modules for outreach drafting, reply classification and escalation.
Registered as the agent identity `{tenant}.partnership-coordinator` (child of
`{tenant}.facility-acquisition-controller`), executed by the shared worker in
`agents/teams/swim-sourcing/worker.py`.

**Holds no send capability.** There is no send handler in the prototype worker;
drafts are written with `provider='mock'` and `status='draft'`. The design for
real sending (campaign entity, DB send chokepoint, Message-ID reconciliation)
is in `docs/reviews/pool-acquisition-final-design.md` section E.

| Module | What it does | LLM |
|---|---|---|
| `draft.py` | fixed template with slots + ONE model-written sentence; refused by `assert_no_fabrication()` if it claims anything the owner did not supply | yes (`claude-sonnet-5-5`) |
| `classify.py` | fences inbound text, model proposes intent/summary/reply, **rules decide**: commitment topics, injection, meetings and unsubscribes escalate regardless of model confidence | yes (`claude-haiku-5-5`) |
| `../outreach-agent/safety.py` | injection detection, commitment patterns, anti-fabrication, auto-reply policy | no |

Fixtures: `fixtures/replies.json` are SIMULATED, scripted replies. Rows written
from them carry a `[SIMULATED]` subject, enforced by `swim_record_inbound`.

Owner: `reformai`. Tests: `agents/tests/test_outreach_safety.py`, `test_prototype_e2e.py`.
