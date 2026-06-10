# ReformAI — PostHog Integration: Production Implementation Plan

**Audience:** Implementing engineer
**Companion docs:** [`reformai-posthog-instrumentation-audit.md`](reformai-posthog-instrumentation-audit.md) (event taxonomy + gaps)
**Target repo:** `ReformAI-Inc/Reform-AI` @ `d768f37`
**Stack confirmed by source read:** pnpm@10.11.0 + Turbo monorepo · `apps/web` (Next.js, app router, `[locale]`, `output: 'standalone'`) · `apps/api` (Express, ESM `"type":"module"`, Zod config, Node >=20) · session-cookie auth (Firebase + backend session) · Wompi payments.

> **Scope of this document:** Phase 0 (foundation) and Phase 1 (P0 events) in full, production-grade detail with exact file paths and diffs. Phases 2–3 are specified at the interface level so they drop into the same harness. This plan does NOT itself write code into the repo — `.workspace/Reform-AI` is a read-only analysis clone. All changes below must land via the product repo's normal PR flow.

---

## 0. Key technical decisions (locked, with rationale)

These were settled by reading the source. Do not re-litigate without cause.

| # | Decision | Rationale (from source) |
|---|---|---|
| D1 | **`distinct_id` = Firebase UID**, NOT the DB user UUID. | Client `AuthContext` exposes a Firebase `User` (`user.uid`, `user.email`) — the DB row/UUID is never held client-side ([AuthContext.tsx:11-18](.workspace/Reform-AI/apps/web/src/context/AuthContext.tsx)). The server has the same Firebase UID on `req.user.firebaseId`. Using the Firebase UID is the only value natively present on **both** sides, so it is the correct join key. DB `user_id`, `persona`, etc. become **person properties**. |
| D2 | **Reverse-proxy PostHog through Next rewrites** (`/ingest/*`). | App has a strict hand-rolled CSP ([next.config.ts:49-116](.workspace/Reform-AI/apps/web/next.config.ts)) and the usual ad-blocker attrition. Proxying keeps ingestion same-origin and CSP simple. The app already proxies the API the same way ([next.config.ts:124-134](.workspace/Reform-AI/apps/web/next.config.ts)). |
| D3 | **`person_profiles: 'identified_only'`.** | Nearly all analytic value is logged-in funnels (projects, bids, milestones, payments). Avoids a flood of anonymous profiles and controls cost. |
| D4 | **No session replay in v1.** | Financial app (escrow, bank details, NIT). Replay is a privacy/compliance surface we are not opening yet. |
| D5 | **Autocapture OFF; explicit events only.** | The taxonomy is curated and server-authoritative for revenue events. Autocapture noise would dilute the funnels and risk PII capture from inputs. |
| D6 | **Create a shared workspace package `@reformai/analytics`.** | Event names must stay byte-identical across `apps/web` and `apps/api`; drift is the classic failure. No `packages/` workspace exists yet (and **no `pnpm-workspace.yaml` exists at all** — see Task 1.0), so this is net-new. |
| D7 | **Server-side capture for all money/state events; client-side for UI/interaction events.** | Payment/webhook/escrow events never touch the browser and must be tamper-proof. Game/visualizer/wizard interactions have no server round-trip. |

**Consent (D8) — needs product/legal sign-off, default assumed:** there is a legal-acceptance gate ([LegalComplianceGate](.workspace/Reform-AI/apps/web/src/components/LegalComplianceGate.tsx)) but **no cookie/analytics consent banner**. Colombia = Ley 1581 (Habeas Data). Default plan: `identified_only` + opt-out API + PII denylist (Task 1.7), no banner in v1. If legal requires explicit opt-in, add a banner that gates `posthog.opt_in_capturing()` — interface noted in Task 1.7.

---

## 1. Phase 0 — Foundation (no business events yet)

Estimated: **3–5 engineer-days.** Definition of done in §1.9.

### Task 1.0 — Formalize the pnpm workspace (PREREQUISITE)

`pnpm-workspace.yaml` is **absent**, yet scripts call `pnpm --filter api` ([package.json:14](.workspace/Reform-AI/package.json)). Create it so the new shared package resolves via `workspace:*`.

**New file — `pnpm-workspace.yaml`** (repo root):
```yaml
packages:
  - 'apps/*'
  - 'functions'
  - 'packages/*'
```

Verify: `pnpm install` then `pnpm --filter @reformai/analytics exec true` resolves once Task 1.1 exists.

---

### Task 1.1 — Shared event registry package `@reformai/analytics`

Single source of truth for event names + payload types, imported by both apps.

**New file — `packages/analytics/package.json`:**
```json
{
  "name": "@reformai/analytics",
  "version": "0.0.1",
  "private": true,
  "type": "module",
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "exports": { ".": "./src/index.ts" },
  "scripts": {
    "type-check": "tsc --noEmit",
    "lint": "eslint . --ext .ts"
  },
  "devDependencies": { "typescript": "^5.8.3" }
}
```
> Ships as raw TS (no build step). `apps/web` (Next/SWC) and `apps/api` (`tsc`) both compile workspace TS directly. If `apps/api`'s `tsc` build excludes external sources, add `packages/analytics/src` to its `tsconfig` `include` or mark the package `composite` — verify during Task 1.1 acceptance.

**New file — `packages/analytics/tsconfig.json`:**
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "declaration": true,
    "skipLibCheck": true
  },
  "include": ["src"]
}
```

**New file — `packages/analytics/src/events.ts`** (seed with the P0 set from the audit; extend per phase):
```ts
// The canonical event name registry. Adding an event = adding it here FIRST.
export const ANALYTICS_EVENTS = {
  // --- Auth / platform (P0) ---
  USER_SIGNED_UP: 'user_signed_up',
  USER_ROLE_SELECTED: 'user_role_selected',
  FEATURE_GATE_HIT: 'feature_gate_hit',
  UPGRADE_MODAL_VIEWED: 'upgrade_modal_viewed',

  // --- Homeowner funnel (P0) ---
  PROJECT_CREATED: 'project_created',
  PROJECT_SUBMITTED: 'project_submitted',
  AGREEMENT_SIGNED: 'agreement_signed',
  MILESTONE_APPROVED: 'milestone_approved',
  MILESTONE_DISPUTED: 'milestone_disputed',
  PAYMENT_INITIATED: 'payment_initiated',
  PAYMENT_SETTLED: 'payment_settled',
  PAYMENT_FAILED: 'payment_failed',
  SUBSCRIPTION_CHECKOUT_STARTED: 'subscription_checkout_started',
  SUBSCRIPTION_ADDON_PURCHASED: 'subscription_addon_purchased',

  // --- Service provider (P0) ---
  SERVICE_PROVIDER_REGISTERED: 'service_provider_registered',
  SP_ONBOARDING_COMPLETED: 'sp_onboarding_completed',
  BID_SUBMITTED: 'bid_submitted',
  BID_VALIDATED: 'bid_validated',
  AGREEMENT_PROVIDER_SIGNED: 'agreement_provider_signed',
  MILESTONE_SUBMITTED: 'milestone_submitted',
  BANK_DETAILS_ADDED: 'bank_details_added',
  BANK_DETAILS_VERIFIED: 'bank_details_verified',
  PAYOUT_COMPLETED: 'payout_completed',
  PAYOUT_FAILED: 'payout_failed',

  // --- Seller (P0) ---
  PROPERTY_LISTING_CREATED: 'property_listing_created',
  PROPERTY_LISTING_PUBLISHED: 'property_listing_published',
  SELLER_LEAD_RECEIVED: 'seller_lead_received',

  // --- Hypothesis-critical (P0 subset; full set Phase 2) ---
  VISUALIZER_RENDER_REQUESTED: 'visualizer_render_requested',
  VISUALIZER_RENDERED: 'visualizer_rendered',
  STYLE_GAME_STARTED: 'style_game_started',
  STYLE_MATCH_VOTED: 'style_match_voted',
  STYLE_PROFILE_SAVED: 'style_profile_saved',
  STYLE_GAME_TO_PROJECT: 'style_game_to_project',
} as const;

export type AnalyticsEvent = (typeof ANALYTICS_EVENTS)[keyof typeof ANALYTICS_EVENTS];

export type Persona = 'home_owner' | 'service_provider' | 'sellers' | 'admin';
```

**New file — `packages/analytics/src/properties.ts`** (typed payloads for the highest-value events; keep additive):
```ts
// Property shapes. Money is ALWAYS integer minor units + currency, never floats.
export interface MoneyProps { amount_minor: number; currency: 'COP' | 'USD'; }

export interface ProjectSubmittedProps {
  project_id: string;
  space_type?: string;
  budget_minor?: number;
}
export interface PaymentSettledProps extends MoneyProps {
  transaction_id: string;
  invoice_id?: string;
}
export interface StyleMatchVotedProps {
  phase: string;
  chosen_option_id: string;
  round: number;
  match_index: number;
}
// ...extend as events are instrumented. One interface per non-trivial event.
```

**New file — `packages/analytics/src/index.ts`:**
```ts
export * from './events.js';
export * from './properties.js';
```

Add the dependency to both apps (run from repo root):
```bash
pnpm --filter web    add @reformai/analytics@workspace:*
pnpm --filter api    add @reformai/analytics@workspace:*
```

**Acceptance:** `import { ANALYTICS_EVENTS } from '@reformai/analytics'` type-checks in both apps; `pnpm type-check` green.

---

### Task 1.2 — Environment variables

**Frontend — create `apps/web/.env.example`** (none exists today):
```bash
# PostHog (reverse-proxied through /ingest — see next.config.ts)
NEXT_PUBLIC_POSTHOG_KEY=phc_xxx           # project API key (safe to expose)
NEXT_PUBLIC_POSTHOG_HOST=https://us.i.posthog.com   # ingestion host the proxy forwards to
NEXT_PUBLIC_POSTHOG_UI_HOST=https://us.posthog.com  # for toolbar/links
```

**Backend — extend Zod schema** in [apps/api/src/config/index.ts](.workspace/Reform-AI/apps/api/src/config/index.ts). Add to `configSchema` (after line 76):
```ts
  // PostHog (server-side capture). Optional: absent key => no-op (dev/CI safe).
  posthogApiKey: z.string().optional(),
  posthogHost: z.string().default('https://us.i.posthog.com'),
```
Add to `rawConfig` (after line 111):
```ts
  posthogApiKey: process.env.POSTHOG_API_KEY,
  posthogHost: process.env.POSTHOG_HOST || 'https://us.i.posthog.com',
```
Append `POSTHOG_API_KEY` (commented, optional) to **`apps/api/.env.example`**.

> Use the **same PostHog project** for client + server (D1 join requires it). Use **separate PostHog projects per environment** (dev/staging/prod) — not one project with mixed data.

**Acceptance:** server boots with and without `POSTHOG_API_KEY` set; absent key logs one line and disables capture (Task 1.5).

---

### Task 1.3 — Next.js reverse proxy + CSP + middleware exclusion

**3a. Rewrites** — extend `rewrites()` in [apps/web/next.config.ts:124](.workspace/Reform-AI/apps/web/next.config.ts). Add the two PostHog routes **before** the API route, and add `skipTrailingSlashRedirect`:
```ts
const nextConfig: NextConfig = {
  output: 'standalone',
  skipTrailingSlashRedirect: true, // required so /ingest/decide etc. are not 308-redirected
  // ...existing config...
  async rewrites() {
    const fullApiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:3001/api/v1';
    const baseApiUrl = fullApiUrl.replace(/\/api\/v1\/?$/, '');
    return [
      { source: '/ingest/static/:path*', destination: 'https://us-assets.i.posthog.com/static/:path*' },
      { source: '/ingest/:path*',        destination: 'https://us.i.posthog.com/:path*' },
      { source: '/api/v1/:path*',        destination: `${baseApiUrl}/api/v1/:path*` },
    ];
  },
};
```

**3b. CSP** — in the `connect-src` block ([next.config.ts:77](.workspace/Reform-AI/apps/web/next.config.ts)) append the PostHog hosts (belt-and-suspenders; same-origin `'self'` already covers the proxied path, but this keeps the direct-mode fallback and toolbar working):
```
"connect-src 'self' data: blob: " +
  "https://us.i.posthog.com https://us-assets.i.posthog.com " +
  /* ...existing wompi/google/firebase entries... */
```
No `script-src` change needed: `posthog-js` is bundled via npm, not loaded from a CDN.

**3c. i18n middleware exclusion** — the matcher in [apps/web/src/middleware.ts:332](.workspace/Reform-AI/apps/web/src/middleware.ts) must not let next-intl rewrite `/ingest` into `/[locale]/ingest`. Add `ingest` to the negative lookahead (it already excludes `api`):
```ts
export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|api|ingest|firebase-messaging-sw.js|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
};
```

**Acceptance:** `curl -s https://<host>/ingest/static/array/<KEY>/array.js` returns JS; in the browser, network shows event posts to `/ingest/e/` returning 200; no CSP violations in console.

---

### Task 1.4 — Client SDK: provider + identity bridge + pageviews

Install: `pnpm --filter web add posthog-js`.

**New file — `apps/web/src/analytics/posthog-client.ts`:**
```ts
import posthog from 'posthog-js';

let initialized = false;

export function initPostHog() {
  if (initialized || typeof window === 'undefined') return;
  const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
  if (!key) return; // no-op when unconfigured (local/CI)
  posthog.init(key, {
    api_host: '/ingest', // reverse proxy (Task 1.3)
    ui_host: process.env.NEXT_PUBLIC_POSTHOG_UI_HOST ?? 'https://us.posthog.com',
    person_profiles: 'identified_only', // D3
    autocapture: false,                 // D5
    capture_pageview: false,            // app router => manual (Task 1.4c)
    capture_pageleave: true,
    disable_session_recording: true,    // D4
    // PII guardrail (D8 / Task 1.7): never send these even if a caller passes them
    sanitize_properties: (props) => {
      for (const k of ['email','phone','password','token','nit','bank_account','iban','card']) {
        if (k in props) delete (props as Record<string, unknown>)[k];
      }
      return props;
    },
  });
  initialized = true;
}

export { posthog };
```

**New file — `apps/web/src/analytics/PostHogBridge.tsx`** — initializes, identifies on auth, captures pageviews. Mounted inside `AuthProvider` + `DeviceIdProvider` so it can read both:
```tsx
'use client';
import { useEffect } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { useAuth } from '@/context/AuthContext';
import { useDeviceId } from '@/context/DeviceIdContext';
import { initPostHog, posthog } from './posthog-client';

export function PostHogBridge() {
  const { user, isAuthenticated, sessionReady } = useAuth();
  const { deviceId } = useDeviceId();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => { initPostHog(); }, []);

  // Anonymous continuity: pin the anon id to the existing device id pre-login,
  // so landing-page / logged-out style-game activity stitches to the account.
  useEffect(() => {
    if (!process.env.NEXT_PUBLIC_POSTHOG_KEY || !deviceId) return;
    if (!isAuthenticated) posthog.identify(deviceId); // anon device-scoped id
  }, [deviceId, isAuthenticated]);

  // Identify with the Firebase UID once the session is ready (D1).
  useEffect(() => {
    if (!process.env.NEXT_PUBLIC_POSTHOG_KEY) return;
    if (isAuthenticated && sessionReady && user) {
      posthog.identify(user.uid, { email_present: !!user.email }); // no raw PII (D8)
    }
  }, [isAuthenticated, sessionReady, user]);

  // Manual pageviews; strip the [locale] prefix into a property.
  useEffect(() => {
    if (!process.env.NEXT_PUBLIC_POSTHOG_KEY || !pathname) return;
    const locale = pathname.match(/^\/(en|es|fr|de)(?=\/|$)/)?.[1] ?? null;
    const path = pathname.replace(/^\/(en|es|fr|de)(?=\/|$)/, '') || '/';
    posthog.capture('$pageview', { path, locale, query: searchParams?.toString() || undefined });
  }, [pathname, searchParams]);

  return null;
}
```
> `reset()` on logout: the simplest hook is in [AuthContext.tsx:247-260](.workspace/Reform-AI/apps/web/src/context/AuthContext.tsx) (the `else`/sign-out branch) — add `posthog.reset()` there, or extend the bridge to call it when `isAuthenticated` flips true→false. Keep it in one place.

**Wire into providers** — [apps/web/src/app/[locale]/providers.tsx](.workspace/Reform-AI/apps/web/src/app/[locale]/providers.tsx). The component has **two** return paths (pre-mount line 44, mounted line 58); add the bridge to the **mounted** branch inside `DeviceIdProvider`+`AuthProvider`:
```tsx
// inside the mounted return, just under <AuthProvider> / above <LanguageProvider>:
<AuthProvider>
  <PostHogBridge />
  <LanguageProvider>
    {/* ...existing... */}
```
(Leave the pre-mount fallback branch unchanged — no analytics before hydration.)

**New file — `apps/web/src/analytics/capture.ts`** — typed client helper everyone calls:
```ts
import type { AnalyticsEvent } from '@reformai/analytics';
import { posthog } from './posthog-client';

export function track(event: AnalyticsEvent, properties?: Record<string, unknown>) {
  if (!process.env.NEXT_PUBLIC_POSTHOG_KEY) return;
  posthog.capture(event, properties);
}
```

**Acceptance:** logging in produces an `identify` with `distinct_id === firebase uid`; navigating fires `$pageview` with `path`/`locale`; logged-out browsing then logging in shows one merged person (anon device id → uid).

---

### Task 1.5 — Server SDK: singleton + helper + shutdown flush

Install: `pnpm --filter api add posthog-node`.

**New file — `apps/api/src/lib/analytics.ts`:**
```ts
import { PostHog } from 'posthog-node';
import config from '../config/index.js';
import logger from '../utils/logger.js';

let client: PostHog | null = null;

if (config.posthogApiKey) {
  client = new PostHog(config.posthogApiKey, {
    host: config.posthogHost,
    flushAt: 20,
    flushInterval: 10_000,
  });
  logger.info('📊 PostHog server analytics enabled');
} else {
  logger.info('📊 PostHog server analytics disabled (POSTHOG_API_KEY not set)');
}

/**
 * Capture a server-side event. distinctId MUST be the Firebase UID (req.user.firebaseId)
 * so server events join client events (D1). No-op when unconfigured.
 */
export function captureServer(
  distinctId: string | undefined | null,
  event: string,
  properties: Record<string, unknown> = {},
): void {
  if (!client || !distinctId) return;
  try {
    client.capture({ distinctId, event, properties });
  } catch (err) {
    logger.warn('PostHog capture failed (non-fatal):', err);
  }
}

export async function shutdownAnalytics(): Promise<void> {
  if (!client) return;
  try { await client.shutdown(); } catch { /* ignore */ }
}
```
> Helper swallows its own errors — analytics must **never** break a payment/webhook path.

**Flush on shutdown** — [apps/api/src/server.ts:40-55](.workspace/Reform-AI/apps/api/src/server.ts), inside `gracefulShutdown`, before `process.exit(0)`:
```ts
import { shutdownAnalytics } from './lib/analytics.js';
// ...
    await EmailService.gracefulShutdown?.();
    await shutdownAnalytics();   // <-- add: flush buffered events
    process.exit(0);
```

**Acceptance:** an event captured via `captureServer('<firebase-uid>', 'test_server_event')` appears in PostHog within the flush window and is attributed to the same person as the client `identify`.

> **Distinct-id contract (write into the PR description):** every `captureServer(...)` call passes `req.user.firebaseId`. Routes use the existing `authenticate` middleware ([auth.middleware.ts](.workspace/Reform-AI/apps/api/src/middlewares/auth.middleware.ts)), which already populates `req.user` (`id`, `firebaseId`, `roles`, `role`, `serviceProviderId`, …). For Wompi webhooks (unauthenticated), resolve the Firebase UID from the transaction's user record before capturing (Task 2 / §2.3).

---

### Task 1.6 — Super-properties & person properties

On `identify` (Task 1.4) and on the first server event per user, set durable person properties (never raw PII):
- `persona` / `role`, `is_admin`, `onboarding_completed`, `service_provider_id`, `db_user_id` (the UUID — as a property, not the distinct_id), `subscription_plan`, `locale`, `signup_source`.

Server-side, attach these with `$set` on a natural event (e.g. login or first capture):
```ts
client?.capture({ distinctId: firebaseUid, event: 'user_logged_in',
  properties: { $set: { persona: req.user.role, db_user_id: req.user.id,
    is_admin: req.user.isAdmin, onboarding_completed: req.user.onboardingCompleted } } });
```

**Acceptance:** a person in PostHog shows `persona`, `db_user_id`, `onboarding_completed`.

---

### Task 1.7 — PII guardrails & consent hooks

1. **Client denylist:** the `sanitize_properties` in Task 1.4 strips email/phone/nit/bank/token/card. Keep the list in `posthog-client.ts` and mirror it server-side: add a `scrub()` pass in `captureServer` that drops the same keys.
2. **Never put raw money as floats or PII in properties.** Money = `amount_minor` (integer) + `currency` (D-rule in `properties.ts`).
3. **Consent (D8):** if legal mandates opt-in, gate capture behind `posthog.opt_in_capturing()` / `opt_out_capturing()` driven by a banner, and set `opt_out_capturing_by_default: true` in `init`. Default plan ships without a banner (`identified_only` + opt-out endpoint). **Get explicit sign-off before go-live.**

**Acceptance:** deliberately pass `{ email }` to `track()` and confirm it does NOT appear on the event in PostHog.

---

### Task 1.8 — Governance: tracking plan as code + CI guard

- The audit doc is the human tracking plan; `@reformai/analytics/events.ts` is the machine copy.
- **Lint rule:** no string literals to `track()` / `captureServer()` — only `ANALYTICS_EVENTS.*`. Add an ESLint `no-restricted-syntax` rule (or a tiny custom rule) in both apps. This is what stops names drifting.
- **PR template line:** "New analytics event? Added to `@reformai/analytics`, given a typed prop interface, and listed in the audit doc."

---

### 1.9 Phase 0 — Definition of Done
- [ ] `pnpm-workspace.yaml` created; `@reformai/analytics` importable from both apps; `pnpm type-check` green.
- [ ] Reverse proxy live; `/ingest/*` returns 200; excluded from i18n middleware; CSP updated; no console violations.
- [ ] Client: provider mounted, `identify` uses Firebase UID, manual pageviews fire, anon→identified merge verified, `reset()` on logout.
- [ ] Server: singleton config-gated, `captureServer` helper, flush on SIGTERM/SIGINT.
- [ ] One client event + one server event verified as a **single joined person**.
- [ ] PII denylist active both sides; money-as-minor-units rule documented.
- [ ] ESLint guard rejecting literal event names.
- [ ] **No business events yet.** (That is Phase 1.)

---

## 2. Phase 1 — P0 events (revenue + funnel)

Estimated: **4–6 engineer-days.** Instrument the P0 rows from the audit using the harness from Phase 0. Pattern below; replicate per event.

### 2.1 Server-side events (the revenue/state spine — preferred, tamper-proof)

Wire `captureServer(req.user.firebaseId, ANALYTICS_EVENTS.X, props)` into the controller **right after the successful state transition / DB commit** (not before — only count real successes). Targets and their transition points (from the audit + route read):

| Event | Controller / route | Fire when |
|---|---|---|
| `project_submitted` | `POST /projects/:id/submit` | status → `active` committed |
| `bid_submitted` | `POST /milestones/bids` | bid row created |
| `bid_validated` | `POST /agreements/bids/:id/validated` | status → `validated` |
| `agreement_signed` / `agreement_provider_signed` | `POST /agreements/:id/sign` · `/provider-sign` | status → `signed` |
| `milestone_submitted` | `POST /milestones/:id/submit` | status → `submitted_for_approval` |
| `milestone_approved` / `milestone_disputed` | `POST /milestones/:id/approve` · `/dispute` | status set |
| `subscription_checkout_started` | `POST /wompi/subscription/checkout` | checkout intent created |
| `subscription_addon_purchased` | `POST /wompi/subscription/addon` | charge accepted |
| `property_listing_created` | `POST /marketplace/listings` | row created |
| `seller_lead_received` | `POST /marketplace/listings/:id/inquiries` | lead created |
| `bank_details_added` | `POST /bank-details` | status `pending_verification` |
| `sp_onboarding_completed` / `service_provider_registered` | `POST /service-provider/onboarding/complete` · `/register` | success |

**Reference implementation (one controller):**
```ts
import { captureServer } from '../lib/analytics.js';
import { ANALYTICS_EVENTS } from '@reformai/analytics';

// inside the submit handler, AFTER the status update commits:
captureServer(req.user?.firebaseId, ANALYTICS_EVENTS.PROJECT_SUBMITTED, {
  project_id: project.id,
  space_type: project.spaceType,
  budget_minor: project.budgetMinor, // integer minor units
});
```

### 2.2 Client-side P0 events

Use `track()` (Task 1.4) at the interaction point:
- `user_role_selected` — `/onboarding/select-user-type` choice.
- `feature_gate_hit` / `upgrade_modal_viewed` — in `UpgradeModal` / `SubscriptionPaymentModal` and the `quota/check` over-limit branch.
- `visualizer_render_requested` / `visualizer_rendered` — in `handleGenerate()` (request) and the success branch (`setGeneratedImageUrl` + success toast) of `RoomUpload.tsx` / `PropertyImageStudio.tsx`.
- `style_game_started` / `style_match_voted` / `style_profile_saved` / `style_game_to_project` — in `useGameEngine.ts` (`startGame`, `selectOption`) and `FinalReveal.tsx` (`autoSaveToInspirationHub` success).

### 2.3 Wompi webhooks (unauthenticated — special handling)

`payment_settled` / `payment_failed` / `payout_completed` / `payout_failed` arrive at `POST /wompi/webhooks/` with **no `req.user`**. In `processWebhook()`, after updating the transaction/payout, **look up the owning user**, resolve their **Firebase UID** (from the user row → `firebaseId`), then:
```ts
captureServer(user.firebaseId, ANALYTICS_EVENTS.PAYMENT_SETTLED, {
  transaction_id: tx.id, invoice_id: tx.invoiceId,
  amount_minor: tx.amountInCents, currency: tx.currency, // 'COP'
});
```
If the user/UID cannot be resolved, **capture with the DB user id as a fallback distinct_id is NOT allowed** (would split the person). Instead skip + log; never invent a distinct_id.

### 2.4 Build the funnels (PostHog, no code)
1. **Marketplace conversion:** `user_signed_up → project_submitted → bid_submitted → agreement_signed → milestone_approved → payment_settled`.
2. **Feature → revenue hypothesis:** `style_game_started → style_profile_saved → style_game_to_project → project_submitted`.
3. **Provider activation:** `service_provider_registered → sp_onboarding_completed → bid_submitted → bid_validated → payout_completed`.

### 2.5 Phase 1 — Definition of Done
- [ ] All P0 events from the audit firing from the correct success/transition points.
- [ ] Webhook events resolve the Firebase UID; no orphaned/duplicate persons.
- [ ] Three funnels built and showing data end-to-end in staging.
- [ ] Money always `amount_minor` + `currency`; spot-check no PII on any event.

---

## 3. Phase 2 — Hypothesis-critical features (full instrumentation)

Drops into the same harness. Reference the dedicated audit sections.

- **Visualizer (audit §4.3):** full event set incl. `visualizer_room_uploaded`, `_moodboard_added`, `_furniture_added`, `_iterated`, `visual_saved_server` (on the **resolved** promise only — the current save is fire-and-forget and swallows errors, so success must be confirmed), `visual_downloaded`. All client-side via `track()`; the two server touchpoints (`/visualization/generate`, `/visualization/visuals`) can additionally emit server events for tamper-proof render counts.
- **Style Tournament (audit §4.4):** the entire game is client-only state in `useGameEngine.ts` — **decision required (Gap #1):** pure client capture (fast, ship now) vs. a new `POST /renovation-game/events` endpoint (durable, queryable). Recommend **client capture now**, add the endpoint later only if the data proves valuable. Capture every `selectOption()` as `style_match_voted`, plus discovery votes, onboarding completion, add-ons, reveal, and `style_game_to_project`.

---

## 4. Phase 3 — Close instrumentation gaps

From the audit's 12-item gap list, the ones needing **new backend signals** before they can be tracked:
- `bid_accepted` (no endpoint — derive from `agreement_signed` or add `POST /bids/:id/accept`), bid rejection.
- Walkthrough booking state machine cleanup.
- `milestone_created` (milestones auto-created with the agreement — add a signal).
- Listing draft→published transition endpoint (`property_listing_published` depends on it).
- SP/Seller onboarding **step-level** completion markers.
- `project_step_abandoned` (client-side wizard exit).
- Error/exception tracking (Sentry or PostHog error tracking) — currently absent.

Also Phase 3: optional auto-capture of API errors at the two existing choke-points — the axios response interceptor ([apps/web/src/services/api.ts](.workspace/Reform-AI/apps/web/src/services/api.ts)) and the central [error.middleware.ts](.workspace/Reform-AI/apps/api/src/middlewares/error.middleware.ts).

---

## 5. Rollout & risk

| Step | Action |
|---|---|
| 1 | Land Phase 0 behind absent prod key → effectively a no-op in prod; verify in **dev** PostHog project. |
| 2 | Enable **staging** key; run Phase 1 instrumentation; validate funnels on real staging traffic. |
| 3 | Enable **prod** key; monitor event volume + person count for 48h; watch for PII (Task 1.7 spot-check) and distinct-id splits. |
| 4 | Phase 2/3 incrementally. |

**Top risks & mitigations**
- **Distinct-id split** (client uid vs server db-id) → mitigated by D1 (Firebase UID both sides) + the §1.5 contract + webhook rule §2.3. Single highest-risk item; verify the join in §1.5 acceptance before any P0 work.
- **PII leakage on payment events** → denylist both sides + money-as-minor-units + spot-check gate in DoD.
- **Analytics breaking a payment path** → `captureServer` swallows errors; capture always **after** commit.
- **CSP / proxy breakage** → `skipTrailingSlashRedirect` + middleware matcher exclusion + curl acceptance in Task 1.3.
- **`tsc` not compiling the workspace TS package** (`apps/api`) → verify Task 1.1 acceptance; fall back to a prebuilt `dist` for `@reformai/analytics` if needed.
- **Event-name drift** → ESLint guard (Task 1.8) + shared registry.

---

## 6. File-change inventory (quick reference for the PR)

**New files**
- `pnpm-workspace.yaml`
- `packages/analytics/{package.json,tsconfig.json,src/events.ts,src/properties.ts,src/index.ts}`
- `apps/web/.env.example`
- `apps/web/src/analytics/{posthog-client.ts,PostHogBridge.tsx,capture.ts}`
- `apps/api/src/lib/analytics.ts`

**Edited files**
- `apps/web/next.config.ts` — rewrites (+`/ingest`), CSP `connect-src`, `skipTrailingSlashRedirect`.
- `apps/web/src/middleware.ts` — matcher excludes `ingest`.
- `apps/web/src/app/[locale]/providers.tsx` — mount `<PostHogBridge/>` (mounted branch).
- `apps/web/src/context/AuthContext.tsx` — `posthog.reset()` on sign-out branch.
- `apps/api/src/config/index.ts` — Zod + rawConfig PostHog fields.
- `apps/api/src/server.ts` — `shutdownAnalytics()` in graceful shutdown.
- `apps/api/.env.example` — `POSTHOG_API_KEY`.
- Phase 1: the controllers in §2.1 + Wompi webhook (§2.3) + client interaction sites (§2.2).
- `apps/web/package.json`, `apps/api/package.json` — `@reformai/analytics`, `posthog-js`/`posthog-node` deps.

---

*End of implementation plan.*
