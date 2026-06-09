# Reference: UI Design Agent + Codebase Context Agent - Logo & Branding

Purpose: starting a separate thread to connect the UI Design agent to the Codebase Context Agent
(CCA) to retrieve the REAL ReformAI logo + brand assets from the product source, replace the
placeholder logo in the Sprint report PDF, and verify nothing else in the brand is stale.

Why this is needed: the Sprint 1 PDF (`reports/sprint-1-review.html`) currently uses a
hand-recreated hexagon "A" logo (inline SVG, search the file for `<svg class="mark">`). The brand
tokens came from a skill extracted off the QA website, NOT from source. We want the authoritative
asset and tokens straight from the product repo, fetched via the agent that is allowed to read code.

---

## The agents involved

### Codebase Context Agent (CCA) - the ONLY agent that reads source code
- Library: `agents/library/codebase-context-agent/agent.py`
- Definition UUID: `93b45e81-a1e5-47d8-98b1-0575de49a21b`
- Instance: `reformai.codebase-context-agent` (`b118d9e1-c3ff-49c3-bb8b-f3c1bb985d2a`)
- Reads an external target repo read-only at a pinned commit; owns the `cbc:*` identity registry.
- Output schema: `docs/schemas/codebase-context.schema.json`
- Run: `python agents/library/codebase-context-agent/agent.py --repo-path <local clone>
  --target-key reformai-product --feature-intent "..." --concepts-to-check ...`
- It describes WHAT IS in the code; it never scopes or recommends. Perfect for "find the real
  logo asset + brand tokens as they exist in source."

### UI Design agent (clarify which one)
- Existing marketing `ui-design-agent` (`agents/library/` - marketing blueprint -> React code).
  Per AGENTS.md this is the WRONG contract for lifecycle design work.
- Planned dedicated `reformai.ux-design-agent` (design-only, consumes a Feature Scope Brief) - not
  built yet.
- For logo/branding retrieval specifically, the UI agent is the CONSUMER of what CCA finds; decide
  in the new thread whether to use the marketing agent or stand up the dedicated one.

### Supporting
- `context-agent` (`agents/library/context-agent/`) - pulls project context from Google Drive,
  in case brand guidelines live there rather than in code.
- ReformAI design system skill: `anthropic-skills:reformai-design-system` - current brand tokens
  (to be verified against source).

---

## The product repo (where the real assets live)
- GitHub: `ReformAI-Inc/Reform-AI` (Turbo monorepo: Next.js `apps/web` + Express `apps/api`,
  Drizzle/PostgreSQL).
- Clone: `gh repo clone ReformAI-Inc/Reform-AI` (gh CLI is authed as `reformai-admin`, org
  `ReformAI-Inc`, scopes `read:org`+`repo`).
- Logo asset: design system references `/logo.svg` - likely `apps/web/public/logo.svg` (VERIFY the
  exact path in source; there may also be favicon / app-icon / wordmark variants).
- Also check: `apps/web` global CSS / Tailwind config / theme tokens for the authoritative color
  variables and the `Red Hat Display` font wiring.

---

## Known brand tokens (from the skill - VERIFY against source)
- Font: `Red Hat Display` (Google Fonts).
- Brand Teal `#00ADB5`; Teal Dark `#009AA2`; Badge `#3B8AA2`; Logo Teal `#5BA4B0`; Sky `#A5D0FA`.
- Chart palette: `#f05100` `#009588` `#104e64` `#fcbb00` `#f99c00`.
- Surfaces: bg `#ffffff`, sidebar `#fafafa`, secondary `#f5f5f5`, border `#e5e5e5`, muted text
  `#737373`, foreground `#0a0a0a`. Radius 10px. No heavy shadows.
- Logo: hexagonal teal/slate icon with stylised "A" + wordmark "Reform-A.i".

---

## What the new thread should produce
1. The real `logo.svg` (and any wordmark/icon variants) pulled from source via CCA.
2. A confirmed brand-token list reconciled against the actual `apps/web` theme (flag any drift
   from the skill values above).
3. Replace the placeholder `<svg class="mark">` in `reports/sprint-1-review.html` with the real
   asset (embed the SVG inline or reference a copied asset under `reports/`).
4. A short note on anything else that looks stale (fonts, colors, old logo usages).

---

## Cross-links / where the report lives
- Sprint report design spec: `docs/agent-jira-sprint-reporting.md`
- Report HTML/PDF template: `reports/sprint-1-review.html` -> `reports/sprint-1-review.pdf`
- Confluence (internal analysis): RAPD space, page id `166723587`
- AGENTS.md - registry entries for CCA, ui-design-agent, marketing-agent, context-agent.
