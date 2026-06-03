# Domain Glossary — ReformAI Landing Pages

**Document type:** Canonical — workspace context
**Owner:** Founder/Operator
**Workspace:** reformai-landing
**Update trigger:** New domain concepts introduced, definitions corrected, brand rules changed
**Consumed by:** Landing Page Builder skill (primary), Persona Content Strategist (primary)

---

> If this document carries a staleness flag, agents reading it must surface that flag in their output and reduce their context integrity rating accordingly.

---

## Defined Terms

### Persona
One of the four audiences a landing page targets: **Homeowner** (`/owners`), **Seller** (`/sellers`), **Contractor** (`/pros`), **Supplier** (`/suppliers`). Each has a distinct hero device, tone, pain set, and CTA. Source of feature truth per persona is the Feature List doc.

### Persona Hero Device
The signature interactive element of a persona's hero. Homeowner = before/after AI slider; Seller = before/after AI-staging reveal (dated → renovated *concept*, labeled) + an **honest** interest counter (live buyers/views — **NOT** a fabricated ARV/ROI %); Contractor = portfolio-first + an **honest** open-jobs count. **As of 2026-05-31** every persona page is **fully dark cinematic** and each hero pairs its device (a glass product card) with the one floating 3D object behind it on scroll parallax. The seller-interest and pro-open-jobs counters stay **OMITTED** until a real metric exists (no fabricated proof). Supplier hero (reach map) is unbuilt.

### Seller Tiers & Brokerage Model
The Seller persona has two distinct paths, and the brokerage relationship differs between them (Founder-locked 2026-05-30):
- **Free Listing (self-serve):** the seller lists and **coordinates everything themselves** (inquiries, viewings, the sale). **ReformAI is NOT the broker and takes no cut of the sale.** Sellers get AI visualizations with their membership (a free self-serve staging preview).
- **Signature Package (white-glove):** for listings ReformAI markets, **ReformAI IS the broker** under a broker's agreement and earns a commission **only on a completed sale**. Includes pro photography, professional AI-enhanced staging, priority placement, buyer-newsletter feature, buyer qualification, and managed viewings through close.
- **Disclosure rule:** the exact Signature commission rate (internally 5%) and the distressed-asset partner's name (internally Grupo Aval + subsidiary banks) are **INTERNAL-only — never rendered on the public page.** Public copy is qualitative on the rate and generic on the buyer anchor.
- **AI-staging honesty:** every staged image is labeled "renovation concept — not current condition." Pending legal review before launch (KNOWN-RISK).

### Signature Moment
The single WebGL moment per hero. **As of 2026-05-31 this is a floating 3D object** (`Hero3D` — R3F + drei `Float` + `MeshDistortMaterial`, teal, pointer parallax) behind the product visual; it replaced the earlier flat gradient shader. Lazy-loaded (`next/dynamic ssr:false`), disabled <768px / `prefers-reduced-motion` (static teal-glow fallback). Exactly one per hero; never per-section or full-page.

### Theme-Dark Token Scope
`.theme-dark` (in `app/globals.css`) overrides the design-token CSS vars (`--background/--foreground/--card/--surface/--border/--muted-foreground`) to dark values. Wrapping a page tree in `theme-dark` flips every token-driven component to the dark cinematic look with no per-component class changes. All three persona pages use it.

### Tier A / Tier B / Tier C (Wow Stack)
- **Tier A** — craft applied everywhere: smooth scroll, GSAP ScrollTrigger reveals, kinetic hero headline, custom cursor, grain overlay, glassmorphism nav, route transitions, animated counters, before/after, 150ms micro-interactions.
- **Tier B** — the one signature WebGL moment per hero.
- **Tier C** — BANNED: full-page Three.js scenes, **per-section** 3D, physics gimmicks, spatial audio, WebGPU experiments. (Founder lifted the original "no heavy 3D at all" stance 2026-05-31 to allow **one floating 3D object per hero** — the per-section/full-page ban stands.)

### Bento Grid
The approved feature-section layout: an asymmetric card grid with staggered scroll-reveal. The canonical alternative to a generic 3-card row, which is banned as a first impression.

### AEO (Answer Engine Optimization)
Making pages readable/citable by AI answer engines. Concretely: `public/llms.txt` (markdown site map for LLMs), per-page JSON-LD (`Service`/`Product` + `Organization`), and `robots.txt` allowing ClaudeBot/GPTBot/PerplexityBot.

### CTA Handoff
Every primary CTA points to `APP_REGISTER_URL?role=<persona>` via `lib/links.ts`. The exact app register path + role-param support is confirmed in Step 2; until then it is a single configurable constant.

### Source-of-Truth Tiers
- **Tier 1 — Ground Truth:** the running code in `reformAI-home` + the live app/site.
- **Tier 2 — Canonical Documents:** these `docs/` files + `brand/` pack. Human-maintained; agents read them.
- **Tier 3 — Derived Standards:** the `landing-page-builder` skill, `CLAUDE.md`, component patterns.
- **Tier 4 — Generated Outputs:** page code, copy drafts, content briefs. Always hypotheses; require human approval.

### Staleness Flag
A marker prepended to a canonical doc signalling it may be outdated:
```
> **STALE — as of YYYY-MM-DD:** [what changed. Will be updated by YYYY-MM-DD.]
```
An agent reading it must surface the flagged doc and lower its context integrity rating.

### Context Integrity
The property that the canonical docs an agent reads reflect current reality. **Green** (all present, no staleness), **Yellow** (present but flagged / undefined terms), **Red** (a required doc absent — output is best-effort and must not advance without explicit human override).

### The Plausibility Trap
The primary LLM failure mode: well-formatted, internally consistent output that is wrong because the context was stale or incomplete. Mitigation: every copy/design output is a hypothesis until a human approves it against the brand + persona brief.

### Pitch-deck concepts (canonical narrative — keep consistent across site + copy)
From the Jan-2026 investor deck (`memory/reformai-pitch-deck.md`):
- **PWR Properties / Ready-To-Renovate (RTR)** — properties with renovation potential; the marketplace's core inventory. Buyers come *for* a place with potential.
- **i-Hire Enabled Transaction** — ReformAI as a "broker 2.0" / digital centaur: AI tools + an expert renovation contractor connect client and contractor from the moment of purchase intent. The signature mechanism.
- **Real-Estate MVP** — a fast, low-cost project pre-feasibility (visualize → quote → validate) that aligns stakeholders before contracting.
- **RGI — Renovation General Intelligence** — the vision: the day renovating a space is as easy as buying a new one ("many talk about AGI, we talk about RGI"). Surfaced in the home `WhyNow` band.
- **"We sell a project, not a commodity"** — positioning line; ReformAI sells the property + vision + the pros to build it, in one place. Analogy: **Zillow × Uber × Mercado Libre, for renovations.**
- **Homebuyer (ICP2)** — first-time millennial/Gen-Z buyers ("70% fear they'll never own") who buy a fixer and renovate. Deck keystone ICP; **no `/buyers` page built yet** (top gap). The Lele/Andrés Sorgi testimonial belongs here.
- **Citable stats (sourced — OK to use):** 80% of 2050's buildings already exist (WEF 2024); 10× renovation gap (Paris/UN); 70–80% of OECD housing is 20+ yrs; own 500+ survey 95%/89%/87%; "120–450 decisions per renovation."

## Business Rules (invariants — must not be violated)

1. **Brand is fixed.** Red Hat Display only (no Inter/Roboto/Arial/Space Grotesk); teal `#00ADB5` the only accent (no purple/neon/warm-earthy). Use tokens, not raw hex.
2. **One signature moment per page; Tier C is banned.** WebGL stays scoped, lazy, fps-capped, with a reduced-motion fallback.
3. **Motion only where it builds hierarchy** and always honors `prefers-reduced-motion`.
4. **Hero shows the product in motion** — never a static screenshot. Feature section is a bento grid, never a generic card row first.
5. **Copy is approved before UI is built.** Benefit statements, not feature lists.
6. **No funnel/backend in this repo.** CTAs hand off to the app only.
7. **Canonical docs are updated by humans.** Agents flag staleness; humans edit. 48-hour update rule after any trigger event.
8. **Every page ships AEO** (llms.txt entry + JSON-LD) and passes the anti-slop checklist before "done".
9. **Seller brokerage split is fixed.** Free tier = ReformAI is NOT the broker and takes no cut (seller coordinates everything); Signature = ReformAI is the broker and earns a commission only on a completed sale. See *Seller Tiers & Brokerage Model*.
10. **Internal-only disclosures.** Never render the Signature commission rate (5%) or the distressed-asset partner name (Grupo Aval) on a public page. Qualitative/generic public framing only.
11. **AI-staged seller visuals must be labeled** "renovation concept — not current condition" on every image; the seller is the party making the representation (pending legal review — see KNOWN-RISKS).
