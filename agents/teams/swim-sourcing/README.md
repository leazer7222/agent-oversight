# Swim-sourcing worker

Durable worker for Cameron's facility-sourcing pipeline. Hosted, not laptop-bound.

## Why this exists separately from the agile worker

`agents/teams/agile/worker.py` says "run locally per work session" and uses
`public.claim_intake_job`, which has an atomic claim but **no lease**: if the
worker dies mid-job the row stays `running` forever with no path back. This
worker adds lease + heartbeat + bounded retry + cooperative cancellation, via
the `swim_*` RPCs in migration 050.

## Deploy to Railway

Resources are NOT provisioned by this repo. To deploy:

1. Create a Railway project and point it at this repository.
2. Set the service root to the repo root and use `railway.json` in this folder.
3. Set the variables below.
4. Add a Railway cron service for the schedulers (below).

### Required environment variables

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Worker DB access (service role bypasses RLS) |
| `CREDENTIAL_ENCRYPTION_KEY` | base64 32 bytes; decrypts tenant provider keys |
| `OVERSIGHT_URL` | Agent Oversight base URL for telemetry |
| `AGENT_OVERSIGHT_SECRET` | `x-agent-secret` for `/api/ingest` |
| `SWIM_AGENT_ID` | Registered agent UUID for this worker |
| `SWIM_WORKER_ID` | Optional stable worker name; defaults to a random id |
| `SWIM_WORKER_LEASE_SECONDS` | Default 300 |
| `GOOGLE_PLACES_API_KEY` | Optional. **Absent -> discovery uses recorded fixtures** and says so in its log line, rather than inventing facilities. |

**Do NOT set `ANTHROPIC_API_KEY` on this service.** The worker scrubs inherited
provider keys at startup and resolves each tenant's own key from
`platform.tenant_provider_credentials`. A platform key present in the
environment would be removed, but setting one invites exactly the confusion this
design exists to prevent.

### Scheduling

Railway cron services, each running the worker once:

| Cadence | Command | Purpose |
|---|---|---|
| `*/10 * * * *` | `python agents/teams/swim-sourcing/worker.py --reap` | return expired-lease jobs to the queue |
| daily | enqueue a `discover` job, then the main worker drains it | refresh the prospect list |

Enqueue work with `public.swim_enqueue_job(company_id, job_type, payload)`, or
from the dashboard.

## Local run

```
python agents/teams/swim-sourcing/worker.py --once
python agents/teams/swim-sourcing/worker.py --reap
```

## Preflight, which fails closed

Before any job does work: agent must be `active` (kill switch), tenant budget
must allow the estimate, and for LLM work the tenant credential must resolve.
A failure is recorded as `blocked`, which is **terminal** - a paused agent, an
exhausted budget or a missing credential will not fix itself on a retry.
