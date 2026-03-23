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

## Companies
- ReformAI
- AfterGlow
- Personal

## Docs
See /docs for architecture decisions, agent standards, and build notes.
