# Agent Oversight System

Personal control plane for monitoring, controlling, and coordinating all AI agents across ReformAI, AfterGlow, and Personal projects.

## Stack
- **Database**: Supabase (Postgres + Realtime)
- - **Event queue**: Inngest (durable execution)
  - - **Frontend**: Next.js + Vercel
    - - **Alerts**: Resend (email)
     
      - ## Structure
      - ```
        agent-oversight/
        ├── src/                    # Next.js dashboard + API
        ├── agents/
        │   ├── library/            # Reusable agent definitions
        │   └── instances/          # Per-company deployments
        ├── python-sdk/             # oversight.py for Python agents
        └── supabase/migrations/    # Database schema
        ```

        ## Companies
        - ReformAI
        - - AfterGlow
          - - Personal
           
            - ## Docs
            - See /docs for architecture decisions, agent standards, and build notes.
           
