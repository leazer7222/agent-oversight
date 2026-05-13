# Agent Oversight System

Personal control plane for monitoring, controlling, and coordinating all AI agents across ReformAI, AfterGlow, and Personal projects.

## Stack
- **Database**: Supabase (Postgres + Realtime)
- **Event queue**: Inngest (durable execution)
- **Frontend**: Next.js + Vercel
- **Alerts**: Resend (email)
- **Agents**: Elite Python-based agents with Google Drive integration

## Elite Agents (ReformAI)
### 1. Context Agent
- **Capabilities**: Recursive Google Drive search, Multi-format extraction (PDF, DOCX, Google Docs).
- **Extraction Power**: Capable of processing 300k+ characters of rich context for high-precision synthesis.
- **Config**: `CONTEXT_FOLDER_ID`, `CONTEXT_RECURSIVE`, `CONTEXT_MAX_CHARS_PER_FILE`.

### 2. Marketing Agent
- **Capabilities**: Elite strategy synthesis and UI/Design blueprint generation.
- **Providers**: Supports OpenAI (GPT-4o, GPT-4o-mini) and Google Gemini (2.0 Flash, 1.5 Pro).
- **Dual Output**: Generates structured JSON for downstream agents and long-form Markdown for the team.

## Structure
```
# Agent Oversight System

Personal control plane for monitoring, controlling, and coordinating all AI agents across ReformAI, AfterGlow, and Personal projects.

# Document Role
Source of truth for:
- concise docs entrypoint and high-level orientation
- navigation links to canonical documents

Should live here:
- short project overview
- where to find standards, strategy, operations, roadmap, and lessons docs

Should NOT live here:
- duplicated deep architecture analysis
- detailed implementation standards
- active operational run-state/checkpoint logs

Canonical documentation map:
- **Platform architecture & philosophy**: `docs/PLATFORM_ARCHITECTURE.md` ← start here for the foundational reasoning
- Agent inventory/status: `docs/AGENTS.md`
- Agent implementation/runtime standards: `docs/agent-standards.md`
- Repo-wide engineering standards: `docs/repo-standards.md`
- Strategic architecture/tradeoffs/interview framing: `docs/AI_AGENT_INFRASTRUCTURE_MASTER_DOCUMENT.md`
- Operational continuity and checkpointing: `docs/HANDOFF_PROTOCOL.md`
- Phased MVP implementation roadmap: `docs/MVP_IMPLEMENTATION_ROADMAP.md`
- Concise chronological lesson log: `docs/LESSONS_LEARNED.md`

## Stack
- **Database**: Supabase (Postgres + Realtime)
- **Event queue**: Inngest (durable execution)
- **Frontend**: Next.js + Vercel
- **Alerts**: Resend (email)
- **Agents**: Elite Python-based agents with Google Drive integration

## Elite Agents (ReformAI)
### 1. Context Agent
- **Capabilities**: Recursive Google Drive search, Multi-format extraction (PDF, DOCX, Google Docs).
- **Extraction Power**: Capable of processing 300k+ characters of rich context for high-precision synthesis.
- **Config**: `CONTEXT_FOLDER_ID`, `CONTEXT_RECURSIVE`, `CONTEXT_MAX_CHARS_PER_FILE`.

### 2. Marketing Agent
- **Capabilities**: Elite strategy synthesis and UI/Design blueprint generation.
- **Providers**: Supports OpenAI (GPT-4o, GPT-4o-mini) and Google Gemini (2.0 Flash, 1.5 Pro).
- **Dual Output**: Generates structured JSON for downstream agents and long-form Markdown for the team.

## Structure
```
agent-oversight/
├── src/                    # Next.js dashboard + API
├── agents/
│   ├── library/            # Reusable agent definitions
│   │   ├── context-agent/  # GDrive + Binary Extraction
│   │   └── marketing-agent/# Strategic Synthesis
│   └── instances/          # Per-company deployments
├── python-sdk/             # oversight.py for Python agents
└── supabase/migrations/    # Database schema
```

## Companies / Tenants
- ReformAI
- AfterGlow
- Personal

Each company is an isolated tenant. They share governance infrastructure, observability, and run tracking. They do not share context, memory, or semantic state.

## Dashboard
Deployed at https://agentoversight.netlify.app

Pages:
- **Overview** — control-plane health summary
- **Agents** — agent registry with status, type, cost, and last-run
- **Hierarchy** — operational topology view (org chart of tenants, orchestrators, teams, and agents)
- **Runs** — execution history with filters
- **Errors** — failure taxonomy and grouped error trends
- **Costs** — token and cost aggregates by agent

## Docs
See `/docs` for architecture decisions, agent standards, and build notes. Start with `docs/PLATFORM_ARCHITECTURE.md` for the foundational platform philosophy.

## Workspace
To open this project with optimized settings for Anti-Gravity:
1. Open the `agent-oversight.code-workspace` file in Anti-Gravity / VS Code.
2. Select **Open Workspace**.
This setup excludes large directories like `node_modules` and `.next` from search and indexing, making the environment much faster for AI agents.
