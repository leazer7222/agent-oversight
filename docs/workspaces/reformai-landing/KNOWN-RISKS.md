# Known Risks — ReformAI Landing Pages

**Document type:** Canonical — workspace context
**Owner:** Founder/Operator + Engineer
**Workspace:** reformai-landing
**Update trigger:** New risks discovered, existing risks mitigated or resolved, severity changes
**Consumed by:** Landing Page Builder skill, QA pass (primary)

---

## RISK-001: Brand / Token Drift
**Status:** Active · **Severity:** Medium · **Area:** All pages
**Description:** Across four pages built over multiple sessions, hard-coded hex values, off-brand fonts, or purple/neon gradients can creep in, breaking the teal + Red Hat identity.
**Mitigation:** Design tokens in `brand/design-tokens.css` + Tailwind aliases; `scripts/check-banned.mjs` runs as a PostToolUse hook and via `pnpm verify`; anti-slop checklist in `brand/brand-pack.md §7`.
**Resolution:** Consistency reviewer pass after all four pages; never fully resolves (depends on discipline).

## RISK-002: WebGL Performance / Conversion Hit
**Status:** Active · **Severity:** High · **Area:** Hero signature moment
**Description:** The signature shader can tank mobile performance and LCP, hurting conversion — the exact failure the Research doc warns about for landing-page 3D.
**Mitigation:** One scoped shader per hero only (Tier C banned); lazy via `next/dynamic ssr:false`; `IntersectionObserver`-gated; fps-capped (~30); `dpr` clamped; static `prefers-reduced-motion`/mobile fallback. Target 60fps desktop, Lighthouse 90+.
**Resolution:** Per-page performance audit in the QA pass; re-evaluate if Core Web Vitals regress.

## RISK-003: Scope Creep into the Funnel
**Status:** Active · **Severity:** High · **Area:** Whole project
**Description:** The Planning doc describes a full signup→onboarding→dashboard funnel. Pulling that into this repo would blow scope; that backend lives in the app repo (`Reform-AI`).
**Mitigation:** PRODUCT.md "What It Does Not Do" is explicit; CTAs hand off via `APP_REGISTER_URL` only. Funnel is Step 2, separate thread/repo.
**Resolution:** Resolves when Step 2 begins as its own tracked effort.

## RISK-004: i18n Incompleteness
**Status:** Active · **Severity:** Medium · **Area:** Copy / messages
**Description:** Building EN + ES together (pt later) risks ES lagging or untranslated keys shipping, breaking the Colombian-primary experience.
**Mitigation:** Every persona namespace added to `messages/en.json` AND `messages/es.json` in the same step; no hard-coded display strings in TSX; pt tracked as explicit follow-up.
**Resolution:** Resolves per page once ES is verified; pt is a known deferred gap.

## RISK-005: Unconfirmed App Register Path / Role Param
**Status:** Active · **Severity:** Low · **Area:** CTA handoff
**Description:** `/en/register` and `/en/signup` 404; the real register path + whether the app reads `?role=` is unconfirmed (only visible logged-out). CTAs could point at a dead path.
**Mitigation:** All CTAs route through the single `APP_REGISTER_URL` constant in `lib/links.ts` — a one-line change once confirmed. Currently points to `/login?role=`.
**Resolution:** Confirm during Step 2 (app repo) or by inspecting the logged-out register page.

## RISK-006: Pre-existing Lint Debt
**Status:** Accepted · **Severity:** Low · **Area:** Original marketing components
**Description:** Original components (Footer, Mission, Vision, Testimonials, etc.) have ESLint errors. `pnpm verify` (which chains lint) will fail on them, masking new issues.
**Mitigation:** New code is lint-clean; the PostToolUse hook runs only `check:banned` (passes), not full lint, so editing isn't blocked. Original debt left untouched to respect scope.
**Resolution:** Out of scope unless the Founder requests a cleanup task.

## RISK-007: The Plausibility Trap (Copy)
**Status:** Active · **Severity:** High · **Area:** Persona copy
**Description:** AI-drafted copy can read as polished and on-brand while mis-framing the persona's real pain or overclaiming a feature — and pass a casual read.
**Mitigation:** Every content brief + copy draft is a hypothesis; the Founder approves messaging against PRODUCT.md + the Feature List before any UI is built. Benefit statements, not feature lists.
**Resolution:** None — human approval at the copy gate is the mitigation.

## RISK-008: AI-Staged Seller Listings — Misrepresentation Exposure
**Status:** Active · **Severity:** High · **Area:** Seller page (`/sellers`) — AI staging
**Description:** The Seller page shows buyers an AI-rendered *renovated* version of a property that isn't renovated. Even labeled, presenting a "finished" concept on a live for-sale listing may trigger Colombian real-estate / consumer-protection disclosure rules — and the **seller** is the party making the representation, so the seller (and the platform marketing it) carries the exposure. Surfaced by the skeptical-seller critic during the `sellers.md` freeze.
**Mitigation:** Every staged image is labeled "renovation concept — not current condition" (mandatory in the build; encoded in frozen `content/sellers.md` and DOMAIN business rule #11). Copy never implies the staging is the current state.
**Build note (2026-05-31):** `/sellers` imagery pass wired real product screens. The §4 before/after retains the mandatory "renovation concept — not current condition" label on the AI-staged *after*. The new marketplace **listing screen** (`/sellers/listing.png`) shows a room photo the **Founder confirmed is REAL photography** (not an AI render) → no concept label needed on that asset. The AI-**staging tool** screenshot shown in FeatureRows is the tool UI itself (not a published listing), so it doesn't make a property representation. Risk is unchanged in severity.
**Resolution:** **OPEN — requires human/legal review before launch** (frozen-copy decision #9). Until cleared, the label is mandatory and the feature should not go live.
