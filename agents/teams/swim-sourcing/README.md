# Swim-sourcing worker and controller

One worker process, three registered identities, no inter-agent protocol. The
job queue (`swim_sourcing.jobs`, migrations 049/050/053) is the only channel.
Design: `docs/reviews/pool-acquisition-final-design.md`.

| File | Role |
|---|---|
| `worker.py` | claims jobs with a lease, resolves the owning identity, checks the kill switch, opens a run in Agent Oversight, runs preflight (budget, tenant credential), executes the handler with heartbeats, finishes with bounded retry, reports cost |
| `controller.py` | deterministic Facility Acquisition Controller: reads goal state, enqueues stage jobs by rule, evaluates saturation / replenishment / radius policies, prints objective progress. No LLM calls |
| `railway.json` | hosting config (not provisioned) |

## Job types and identities

| Job type | Identity | LLM | Notes |
|---|---|---|---|
| `discover` | `{tenant}.facility-researcher` | no | fixtures only when payload `use_fixtures: true`; rows carry `source='fixture'` |
| `enrich` | researcher | Haiku 5.5 | every fact needs a verbatim evidence span found in the page (code check) |
| `qualify` | researcher | no | deterministic scoring + four-state triage |
| `draft_outreach` | `{tenant}.partnership-coordinator` | Sonnet 5.5 | template + one sentence; `assert_no_fabrication()` gate; `provider='mock'`, `status='draft'` |
| `poll_inbox` | coordinator | no | PROTOTYPE: scripted replies, `[SIMULATED]` subject enforced by the RPC |
| `classify_reply` | coordinator | Haiku 5.5 | model proposes, rules decide; commitment topics / injection / meetings / opt-outs escalate |

Deliberately absent: `send_outreach`, `schedule_meeting`, `reconcile_sends`.
Nothing in this directory can email anyone.

## Run

```
python scripts/seed_prototype.py                       # once; idempotent
python scripts/demo_prototype.py --pause-demo          # full demo + kill-switch proof
python agents/teams/swim-sourcing/controller.py --summary
python agents/teams/swim-sourcing/worker.py --drain    # process until the queue is empty
python agents/teams/swim-sourcing/worker.py --reap     # return expired-lease jobs to the queue
```

## Environment

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | queue and RPC access (public RPCs only; PostgREST does not expose `swim_sourcing`) |
| `OVERSIGHT_URL` | `https://agent-oversight.vercel.app` |
| `AGENT_OVERSIGHT_SECRET` | production ingest secret (the SDK reads it first) |
| `CREDENTIAL_ENCRYPTION_KEY` | base64 32 bytes; decrypts tenant provider keys |
| `SWIM_TENANT_PREFIX` | identity name prefix, default `swimschool` |
| `GOOGLE_PLACES_API_KEY` | optional; without it, discovery needs `use_fixtures: true` or it blocks |

**Do NOT set `ANTHROPIC_API_KEY` on the worker host.** The worker scrubs
inherited provider keys at startup and resolves each tenant's key from
`platform.tenant_provider_credentials`.

## Preflight, which fails closed

Order: identity resolved -> kill switch (`agents.status`) -> run opened ->
budget (`check_tenant_budget`) -> tenant credential (LLM jobs only). A failure
is `blocked`, which is terminal. The kill switch runs BEFORE the run opens
because ingest refuses `run_started` for a paused agent.
