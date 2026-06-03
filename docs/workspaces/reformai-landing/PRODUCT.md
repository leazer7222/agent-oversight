# Product — ReformAI Persona Landing Pages

**Document type:** Canonical — workspace context
**Owner:** Founder/Operator (charles@reform-ai.com)
**Workspace:** reformai-landing
**Update trigger:** Product scope changes, persona definition changes, goal changes, "what it does not do" boundary changes
**Consumed by:** Landing Page Builder skill (primary), Persona Content Strategist (primary)

---

> If this document carries a staleness flag, agents reading it must surface that flag in their output and reduce their context integrity rating accordingly.

---

## What It Is

A set of four persona-specific marketing landing pages — **Homeowner, Seller, Contractor, Supplier** — plus a smart-selector homepage, built in the `reformAI-home` repo (Next.js 15). Each page speaks directly to one audience, replacing the single generic landing page that currently tries to address all four. Paid traffic routes to the standalone persona pages; organic traffic hits the smart selector.

The pages are premium, transformation-led, and on the ReformAI teal brand, with a signature WebGL hero moment per page. They hand off to the app for signup — they do not contain the signup/onboarding funnel themselves.

## Who It Serves

**Primary users (page visitors):**
- **Homeowner** — emotional, dream-focused; wants to visualize and safely execute a renovation. Pain: the renovation process is overwhelming and risky.
- **Seller** — ROI / property-value focused; wants to maximize sale price. Pain: doesn't know how to add value before listing; loses value when buyers can't picture a "needs work" property finished; wastes time on unqualified buyers. Served by two tiers — **Free** (self-serve; seller coordinates everything, ReformAI is not the broker, takes no cut) and **Signature** (white-glove; ReformAI is the broker, earns a commission only on sale). Copy frozen 2026-05-30 → `content/sellers.md`.
- **Contractor / Service Provider** — lead-generation focused; wants qualified clients. Pain: inconsistent pipeline.
- **Supplier** *(coming soon as a product surface)* — market-reach focused; wants exposure to serious buyers. Pain: accessing buyers at scale.

**Operator:** the Founder, who maintains these canonical docs and approves all copy and design before build.

## Core Problems It Solves

1. **One generic page can't convert four audiences.** A homeowner and a contractor see the same hero today; neither feels addressed. Persona pages lift conversion 2–5x by making each visitor feel understood.
2. **Renovation feels unsafe and unknowable.** Homeowners can't picture the outcome or trust the process. The AI visualizer (see-before-you-spend) and milestone-protected payments answer both.
3. **The brand isn't expressed at a premium tier.** The product is strong; the marketing surface must read as "$100k" to match. The wow stack (craft + one signature WebGL moment) delivers that without sacrificing conversion or performance.
4. **The site is invisible to AI answer engines.** Buyers increasingly research via ChatGPT/Perplexity/Claude. `llms.txt` + JSON-LD make every page machine-readable.

## Current Strategic Goals

1. **Ship the Homeowner page first, end-to-end and perfectly**, then repeat for Seller → Contractor → Supplier, then the smart homepage last.
2. **Nail the copy before building.** Best-possible, benefit-led messaging per persona is approved before any page UI is written.
3. **Stay rigorously on-brand and on-performance.** Teal `#00ADB5` + Red Hat Display, Lighthouse 90+/100, 60fps, WCAG 2.1 AA.
4. **Make every page AI-readable** (llms.txt + JSON-LD) as a competitive edge in the Colombian renovation market.

## What It Does Not Do

- **Does not build the signup/onboarding/AI-profile/dashboard funnel.** That is Step 2, in the app repo (`Reform-AI`). These pages only hand off via CTA to `APP_REGISTER_URL?role=<persona>`.
- **Does not introduce a second component system.** No shadcn/ui or Magic UI in this repo (the app uses them; adding here causes drift).
- **Does not use full-page WebGL / Three.js scenes or per-section 3D.** Exactly **one floating 3D object per hero** (R3F + drei), lazy (`ssr:false`), disabled <768px / reduced-motion with a static fallback. (Updated 2026-05-31: the Founder lifted the earlier "no heavy 3D" rule from a flat shader to one real floating 3D object — still scoped to the hero, never per-section/full-page.)
- **Does not adopt the Research doc's "warm-earthy" palette.** The live brand is teal; that wins.
- **Does not modify the original marketing components** beyond what a page needs. Pre-existing lint debt in those files is left untouched (out of scope).

## Key Product Decisions

| Decision | Rationale |
|---|---|
| Teal `#00ADB5` + Red Hat Display | Confirmed from the live app + design-system skill; overrides the Research doc's warm-earthy idea |
| Keep the existing stack, no shadcn here | Avoid two-system drift; the repo already has motion + locomotive-scroll |
| Tier A craft everywhere + one signature WebGL moment per hero | Reads as "$100k" while protecting conversion/perf (Tier C avoided) |
| EN + ES copy together | Colombian market is Spanish-heavy; pt follows |
| CTAs hand off to the app | Funnel is a separate effort; landing pages are marketing-only |
| Homeowner first, end-to-end | Ship one thing perfectly, then repeat (Planning doc recommendation) |
| Copy approved before UI | Avoids building on weak messaging; every output is a hypothesis until approved |
| Seller brokerage split: Free = not brokered/no cut; Signature = brokered/commission on sale | Founder-locked 2026-05-30; the seller coordinates the free tier themselves, ReformAI only brokers (and earns) on the listings it markets |
| Keep the Signature commission rate (5%) and the distressed-asset partner (Grupo Aval) off public pages | Founder directive; internal-only facts — public copy stays qualitative/generic, no fabricated numbers |
| **Fully dark cinematic theme** for persona pages (Founder, 2026-05-31) | Founder preferred dark over light after seeing v1; overrides earlier "light base + one dark band" |
| **One floating 3D object per hero** (Founder, 2026-05-31) | Founder wanted the "wow" 3D; lifts the earlier "no heavy 3D" ban — still scoped to the hero |
| **Home stays as the hub** (Founder, 2026-05-31) | Original baseline page is kept as the flow's homepage with a persona-picker band + navbar tabs into the 3 dark persona pages (the "sever the old page" move was reversed) |

## Build status & architecture (2026-05-31)
- **Live:** `/[locale]` homepage hub (original page + `PersonaPicker` band + `WhyNow` story band) → `/owners`, `/sellers`, `/pros` persona pages (dark, one 3D object per hero), all EN+ES. `/suppliers` not built (removed from nav).
- **Real product imagery — DONE on all 3 persona pages (2026-05-31).** Each page's feature section is the large `FeatureRows` alternating showcase, wired to real ES product screens (and live recreations where a screenshot would be unreadable / carry test data): `/owners` (Visualizer, find-a-pro, milestones, etc. + live `MilestoneSchedule`), `/pros` (portfolio-first hero + live `JobBoard` & `BidDashboard`, scrubbed demo data; §4 trio retired), `/sellers` (AI-staging tool + real marketplace listing; §4 before/after staging proof kept). `FeatureBento` is now unused. Remaining placeholders: the seller hero before/after reuses the owners kitchen (no real seller pair yet); the `/pros` "products (coming soon)" row uses a moodboard stand-in (image-gen key expired).
- **Persona ICP coverage vs the pitch deck:** the deck's three ICPs are **Seller** (↔ /sellers ✓), **Contractor** (↔ /pros ✓), and first-time **Homebuyer** (buy a PWR property + renovate) — **the Homebuyer page is NOT built yet and is the top content gap.** Our `/owners` (homeowner renovating their existing home) is adjacent but not a direct deck ICP.
- **Story:** the home `WhyNow` band now carries the deck's category thesis (era of renovation), real sourced stats, the "sell a project, not a commodity" positioning, and the **RGI** vision. See `docs/DOMAIN.md` for the deck's canonical terms.
- **Supplier** remains "coming soon" and is intentionally not in the persona nav.
