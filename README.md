# Agent Oversight System

Personal control plane for monitoring, controlling, and coordinating all AI agents across ReformAI, AfterGlow, and Personal projects.

## Stack
- **Database**: Supabase (Postgres) — project `hdhovyrlnfojtkqbcegh`
- **Frontend**: Next.js 15 + Vercel
- **Agents**: Python-based agents with Google Drive integration
- **Telemetry**: Custom oversight SDK (`python-sdk/oversight.py`)
- **Deferred**: Inngest (execution queue — Phase 5), Resend (email alerts — post-Phase 4)

## Build Status

| Phase | Status |
|-------|--------|
| Schema Stabilization | ✅ Complete |
| Telemetry Standardization | ✅ Complete |
| Read APIs | ✅ Complete |
| Dashboard MVP | 🔜 In Progress |

## Agent Library (ReformAI)

| Agent | Purpose |
|-------|---------|
| `context-agent` | Recursive Google Drive search + multi-format extraction |
| `marketing-agent` | Strategic synthesis + UI/design blueprint generation |
| `ui-design-agent` | High-fidelity UI/UX and frontend code generation |
| `audit-agent` | Quality assurance; scores context relevance (1–10) |
| `optimization-agent` | Repo standards compliance scanner |

## Structure
```
agent-oversight/
├── src/
│   └── app/
│       └── api/
│           ├── ingest/         # POST — agent telemetry ingestion
│           ├── project-state/  # GET/PUT — project context state
│           ├── agents/         # GET — agent list + detail + runs
│           ├── runs/           # GET — run list + detail + events
│           ├── cost/           # GET — cost aggregates
│           └── errors/         # GET — failed runs + breakdown
├── agents/
│   ├── library/                # Reusable agent definitions
│   └── instances/              # Per-company deployments (orchestrators)
├── python-sdk/                 # oversight.py — OversightClient, StepTimer, error taxonomy
└── supabase/migrations/        # Forward-only DB schema migrations
```

## Companies
- ReformAI
- AfterGlow
- Personal

## Docs
See `/docs/` for architecture decisions, agent standards, MVP roadmap, and lessons.
Key entry points:
- `docs/MVP_IMPLEMENTATION_ROADMAP.md` — phased build plan + current status
- `docs/agent-standards.md` — API reference + agent runtime contract
- `docs/HANDOFF_PROTOCOL.md` — operational continuity and session state
- `tasks/current-state.md` — what's active right now
