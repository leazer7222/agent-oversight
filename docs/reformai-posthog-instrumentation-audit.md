# ReformAI — Analytics Instrumentation Audit & PostHog Event Taxonomy

**Prepared by:** Codebase Context audit (senior product-engineering pass)
**Target codebase:** `ReformAI-Inc/Reform-AI` @ commit `d768f37`
**Audit date:** 2026-06-10
**Stack audited:** Next.js (`apps/web`, app router, `[locale]` segment) · Express (`apps/api`, base path `/api/v1`) · Drizzle ORM / PostgreSQL · Wompi payments (Colombia, COP) · Firebase (messaging/notifications/support only)

---

## 1. Executive Summary

ReformAI is a multi-persona renovation + real-estate marketplace with four live personas
(Homeowner/Buyer, Service Provider/Contractor, Seller, Admin) and two hypothesis-critical
consumer features: the **AI Renovation Visualizer** and the **Style Tournament ("Renovation
Game")**. The platform monetizes through subscriptions, add-on credits, and a governed
bid → agreement → milestone → escrow → payout chain settled via Wompi.

**The single most important finding: there is no analytics instrumentation of any kind today.**
A full-repo search found zero references to PostHog, Mixpanel, Segment, Amplitude, Google
Analytics/gtag, Datadog, or Sentry, and no `track()` / `.capture()` calls. The only signal
that exists is ad-hoc `console.log`. Every event in this document is greenfield.

This audit defines **~110 named events** across all personas, with two dedicated sections for
the hypothesis-critical features, a server-vs-client capture strategy, and a prioritized
12-item list of instrumentation gaps that require new code before they can be tracked.

### Top takeaways

1. **The Style Tournament is 100% client-side.** Every vote, room pick, and add-on lives in
   React state (`useGameEngine.ts`) and never reaches the backend. Only the final style profile
   and reveal image hit the server. This is the highest-value gap — the feature is
   hypothesis-critical and currently leaves no trace of *how* a style was chosen.
2. **The payment/escrow chain has clean server signals.** Bid → agreement → milestone →
   payment → payout each maps to a controller status transition or a Wompi webhook. These
   should be captured server-side, never from the browser.
3. **The Visualizer render flow has a clear completion signal** (success toast + returned image
   URL + quota refresh) but stages reference images client-only and saves fire-and-forget.
4. **Two prompt-referenced surfaces do not exist yet:** the **Supplier** persona (no routes,
   endpoints, or schema) and a distinct **"Signature Package"** premium-listing upgrade. These
   are net-new builds, flagged as gaps rather than instrumented.

### Priority key

| Tier | Meaning |
|---|---|
| **P0** | Revenue-critical or funnel-critical — must fire correctly on day 1 |
| **P1** | Feature adoption — important but not blocking |
| **P2** | Behavioral signal — nice to have for future analysis |

### Naming conventions

- `snake_case` for all event names.
- `noun_verb` (object_action) pattern: `project_created`, `milestone_approved`, `visualizer_rendered`.
- Stable super-properties on every event: `user_id`, `persona`, `locale`.

---

## 2. Existing Instrumentation (Baseline)

| Capability | Status | Evidence |
|---|---|---|
| PostHog | Absent | No import anywhere in repo |
| Mixpanel / Segment / Amplitude | Absent | No import anywhere in repo |
| Google Analytics / gtag | Absent | No import anywhere in repo |
| Datadog / Sentry (error + APM) | Absent | No import anywhere in repo |
| Structured `track()` / `.capture()` | Absent | No calls found |
| Ad-hoc logging | Present | Dense `console.log` in `src/context/*`, `src/components/admin/*`, `src/components/forms/LoginForm`, `Navbar`, `RouteGuard` |

**Implication:** A PostHog provider must be added to `apps/web` for client events, plus a
server-side capture in Express controllers for payment/webhook/escrow events that never touch
the browser. The clean server signals are the controller status-transition points; the gaps are
the client-only flows (game, visualizer staging, wizard abandonment).

---

## 3. Persona Map (as built)

| Persona | Route group | Exists? | Core jobs |
|---|---|---|---|
| Homeowner / Buyer | `(homeowner-buyer)` | Yes | Onboarding, project creation, visualizer, style game, marketplace browse, bids received, milestone approvals, payments |
| Service Provider / Contractor | `(serviceProvider)` | Yes | Onboarding, portfolio, find clients, bids, walkthroughs, agreements, milestones, payouts |
| Seller | `(seller)` | Yes | Property listings, audits, leads, bank details, tier selection |
| Admin | `(admin)` | Yes | User/listing/payment/dispute/subscription management |
| **Supplier** | — | **No** | Product showcase + inquiries — net-new, not built |

---

## 4. Event Taxonomy

### 4.1 Platform / Cross-cutting — Auth, Navigation, Errors

#### Auth & Account
| Event Name | Trigger | Key Properties | Priority |
|---|---|---|---|
| `user_signed_up` | `POST /auth/verify-otp` completes (account active) | persona, signup_method (otp/oauth), referral_code | P0 |
| `oauth_user_created` | `POST /auth/create-or-get-user` (new user) | provider (google/apple), persona | P0 |
| `user_logged_in` | `POST /auth/session-login` sets session cookie | persona, method (password/otp/oauth) | P1 |
| `user_role_selected` | `/onboarding/select-user-type` choice | selected_role | P0 |
| `otp_requested` | `POST /auth/request-otp` | channel (email/sms), context (login/signup) | P2 |
| `otp_verified` | `POST /auth/verify-otp` success | context | P1 |
| `two_factor_verified` | `POST /auth/verify-security-otp` | — | P2 |
| `password_reset_requested` | `POST /auth/request-password-reset` | — | P1 |
| `password_reset_completed` | `POST /auth/reset-password` updates hash | — | P1 |
| `user_logged_out` | `POST /auth/session-logout` | — | P2 |
| `email_verified` | `/verify-email` completion | — | P1 |

#### Navigation / Discovery / Errors
| Event Name | Trigger | Key Properties | Priority |
|---|---|---|---|
| `page_viewed` | Route change (PostHog `$pageview`) | path, locale, persona | P1 |
| `property_search_performed` | `/home/search` submit / `GET /marketplace/listings` w/ filters | query, filters, result_count | P1 |
| `map_viewed` | `/home/maps` → `GET /marketplace/listings/map-data` | bounds, pin_count | P2 |
| `service_provider_searched` | `/home/find-serviceprovider` filter | profession, location, filters | P1 |
| `feature_gate_hit` | `POST /quota/check` returns over-limit | feature (ai_renders/bids), plan, used, limit | P0 |
| `upgrade_modal_viewed` | `UpgradeModal.tsx` / `SubscriptionPaymentModal.tsx` opens | trigger_feature, current_plan | P0 |
| `app_error_shown` | Error boundary / `/access-denied` render | error_type, path | P2 |

---

### 4.2 Homeowner / Buyer

#### Onboarding & project-creation funnel
The 7-step project wizard (`/home/projects/create/{space,goals,inspirations,design,budget,review,summary}`)
writes incrementally to the server, so each step is a clean signal. The project row is created
`draft` at step 1; **`POST /projects/:id/submit` flips it to `active`** — that is the
funnel-completion event.

| Event Name | Trigger | Key Properties | Priority |
|---|---|---|---|
| `onboarding_account_created` | `/onboarding/create-account` | persona | P0 |
| `onboarding_space_type_selected` | `/onboarding/select-space-type` | space_type | P1 |
| `onboarding_design_style_selected` | `/onboarding/select-design-style` | style | P1 |
| `onboarding_terms_accepted` | `/onboarding/terms-and-privacy` | version | P1 |
| `project_created` | `POST /projects` → status `draft` | project_id, space_type, project_kind (standard/quick_job) | P0 |
| `project_space_updated` | `PATCH /projects/:id/space-details` | project_id, room_type, dimensions | P1 |
| `project_goals_updated` | `PATCH /projects/:id` (goals) | project_id, goals[] | P1 |
| `project_inspiration_added` | `POST /projects/:id/photos` | project_id, photo_count | P1 |
| `project_design_linked` | design step (moodboard link) | project_id, style | P1 |
| `project_budget_set` | `PATCH /projects/:id/budget-timeline` | project_id, budget, timeline_weeks | P1 |
| `project_aesthetics_updated` | `PATCH /projects/:id/aesthetics` | project_id | P2 |
| `project_submitted` | `POST /projects/:id/submit` → status `active` | project_id, budget, space_type | **P0** |
| `quick_job_created` | `/home/projects/quick-job/[jobId]` create | job_id | P1 |
| `project_step_abandoned` | wizard exit without advancing (client) | last_step, project_id | P1 |

#### Marketplace, agreements, payments (homeowner side)
| Event Name | Trigger | Key Properties | Priority |
|---|---|---|---|
| `listing_viewed` | `/home/listings/[id]` → `GET /marketplace/listings/:id` | listing_id, listing_type | P1 |
| `listing_saved` | save/favorite action | listing_id | P2 |
| `listing_inquiry_created` | `POST /marketplace/listings/:id/inquiries` | listing_id, lead_id | P0 |
| `service_provider_profile_viewed` | `/home/find-serviceprovider/[id]` | provider_id | P2 |
| `bid_received_viewed` | homeowner opens bid | project_id, bid_id, bid_amount | P1 |
| `agreement_signed` | `POST /agreements/:id/sign` (client signature) | agreement_id, project_id | **P0** |
| `agreement_section_acknowledged` | `POST /agreements/:id/acknowledge-sections` | agreement_id, section_id | P2 |
| `milestone_approved` | `POST /milestones/:id/approve` → `approved` | milestone_id, project_id, amount | **P0** |
| `milestone_disputed` | `POST /milestones/:id/dispute` → `disputed` | milestone_id, reason | P0 |
| `payment_initiated` | `POST /wompi/checkout` | invoice_id, amount, currency=COP | **P0** |
| `payment_settled` | Wompi webhook `TRANSACTION.SETTLED` → `APPROVED` (server) | transaction_id, amount, invoice_id | **P0** |
| `payment_failed` | Wompi webhook `TRANSACTION.FAILED` → `DECLINED` (server) | transaction_id, reason | P0 |
| `subscription_checkout_started` | `POST /wompi/subscription/checkout` | plan, amount | **P0** |
| `subscription_addon_purchased` | `POST /wompi/subscription/addon` | addon (ai_renders/bids), amount | P0 |

---

### 4.3 ⭐ Renovation Visualizer (hypothesis-critical)

Three surfaces share one render endpoint (`POST /visualization/generate`):
**`RoomUpload.tsx`** (standalone), **`PropertyImageStudio.tsx`** (listing integration),
**`MyAIVisualsGallery.tsx`** (saved gallery). Mood-board / furniture references are staged
**client-only** and only travel to the server inside the generate call. The clean completion
signal is `toast.success("AI design generated…")` + a returned `generatedImageUrl` + a quota
refresh.

| Event Name | Trigger | Key Properties | Priority |
|---|---|---|---|
| `visualizer_opened` | RoomUpload / PropertyImageStudio mount | surface (standalone/property/game), entry_point | P1 |
| `visualizer_room_uploaded` | `handleFiles()` → `uploadApi.uploadFile()` (server) | surface, file_size | P1 |
| `visualizer_room_type_selected` | room-type dropdown (client) | room_type, surface | P2 |
| `visualizer_style_selected` | style dropdown / `handleSelectProfile()` (client) | style, source (preset/custom) | P1 |
| `visualizer_moodboard_added` | `updateReferenceImage('moodboard')` (client only) | surface | P2 |
| `visualizer_furniture_added` | `updateReferenceImage('furniture')` (client only) | surface | P2 |
| `visualizer_render_requested` | `handleGenerate()` fires (pre-result) | surface, room_type, style, has_moodboard, has_furniture, is_iteration | **P0** |
| `visualizer_rendered` | success: `setGeneratedImageUrl()` + success toast | surface, render_ms, quota_remaining | **P0** |
| `visualizer_render_failed` | generate error / quota-exceeded branch | surface, error_type, quota_exceeded (bool) | P0 |
| `visualizer_iterated` | `handleGenerate()` with existing result | surface, iteration_count | P1 |
| `visualizer_style_reset` | "Try different style" (client) | surface | P2 |
| `visual_saved_local` | `saveAIVisual()` → localStorage | — | P2 |
| `visual_saved_server` | `visualizationApi.saveUserVisual()` → `POST /visualization/visuals` | visual_id, surface | P1 |
| `visual_persisted_to_property` | `persistGeneratedImage()` → marketplace images | listing_id, image_id | P1 |
| `visual_downloaded` | download handler → blob `a.click()` + toast | surface | P1 |
| `visual_deleted` | `handleRemove()` (localStorage) / `DELETE /visualization/visuals/:id` | visual_id, scope (local/server) | P2 |
| `visuals_cleared_all` | `handleClearAll()` confirm | count | P2 |

> **Caution:** save-to-server is fire-and-forget (errors swallowed). Capture `visual_saved_server`
> on the resolved success branch explicitly, or you will over-count saves that actually failed.

---

### 4.4 ⭐ Style Tournament / Renovation Game (hypothesis-critical)

`/home/renovation-game` → `RenovationGame.tsx` driven by `useGameEngine.ts`. **The entire game
is client-side state.** Phases: `start → style-discovery → style-results → onboarding →
[voting rounds] → addons → final-reveal`. The **only** server touchpoints are at the very end:
`FinalReveal.tsx` calls `POST /visualization/generate` (reveal image), `POST /visualization/visuals`
(save), and `POST /renovation-game/profiles` (persist the style profile). **Every vote, room
pick, and add-on is invisible to the backend** — these events must be captured client-side or
they are lost forever.

| Event Name | Trigger | Key Properties | Priority |
|---|---|---|---|
| `style_game_started` | `startGame()` / `skipDiscovery()` (client) | entry (discovery/skip), source_page | P0 |
| `style_discovery_voted` | vote in `StyleDiscoveryScreen` (client) | style_id, direction (up/down), vote_index | P1 |
| `style_discovery_completed` | `completeStyleDiscovery(topStyles)` (client) | top_styles[] | P1 |
| `style_game_onboarding_completed` | `completeOnboarding()` (client) | room, budget, initial_styles[] | P1 |
| `style_match_voted` | `selectOption()` per A/B match (client) | phase (layout/shower-type/etc), chosen_option_id, round, match_index | **P0** |
| `style_round_advanced` | `continueToNextRound()` (client) | from_phase, to_phase | P1 |
| `style_addon_toggled` | addon checkbox in `AddonScreen` (client) | addon_id, enabled | P2 |
| `style_game_reveal_reached` | `FinalReveal` mounts (client) | room, winning_styles[], total_votes | **P0** |
| `style_game_reveal_rendered` | `handleGenerateAiImage()` success (server) | render_ms, quota_exceeded (bool) | P0 |
| `style_profile_saved` | `autoSaveToInspirationHub()` → `POST /renovation-game/profiles` (server) | profile_id, room, styles[] | **P0** |
| `style_game_design_downloaded` | `handleDownload()` (client) | — | P2 |
| `style_game_restarted` | `restart()` (client) | reached_phase | P2 |
| `style_game_to_project` | "use these results in a project" path | profile_id, project_id | **P0** |

> `style_game_to_project` is the revenue-linking event (game → actual project). Confirm the
> handoff path exists; if a user cannot carry a profile into `/projects/create`, that is a
> product gap worth flagging, not just an instrumentation one.

---

### 4.5 Contractor / Service Provider

Multi-step onboarding (`PUT /service-provider/onboarding/{profile,services,business-details,team-info}`)
saves per step but **only `POST /service-provider/onboarding/complete` carries a true completion
marker** — intermediate steps have no status field, so step-level funnel must be inferred from
which PUT last succeeded.

| Event Name | Trigger | Key Properties | Priority |
|---|---|---|---|
| `service_provider_registered` | `POST /service-provider/register` | provider_id | P0 |
| `sp_onboarding_profile_saved` | `PUT .../onboarding/profile` | — | P1 |
| `sp_onboarding_services_saved` | `PUT .../onboarding/services` | services[], styles[] | P1 |
| `sp_onboarding_business_saved` | `PUT .../onboarding/business-details` | — | P1 |
| `sp_onboarding_team_saved` | `PUT .../onboarding/team-info` | team_size | P2 |
| `sp_onboarding_completed` | `POST .../onboarding/complete` | provider_id | **P0** |
| `portfolio_item_created` | `/service-provider/portfolio/new` submit | portfolio_id | P1 |
| `project_browsed_for_bid` | `/service-provider/find-clients/[projectId]` view | project_id | P2 |
| `bid_submitted` | `POST /milestones/bids` (creates escrow setup) | bid_id, project_id, bid_amount, milestone_count | **P0** |
| `bid_template_created` | `POST /milestones/service-provider/bid-templates` | template_id | P2 |
| `bid_shortlisted` | `POST /agreements/projects/:id/bids/shortlist` → `shortlisted` | bid_id | P1 |
| `walkthrough_scheduled` | `POST .../bids/:id/walkthrough-slots` | bid_id, slot_count | P1 |
| `walkthrough_completed` | `POST /agreements/walkthroughs/:id/complete` → `walkthrough_completed` | bid_id, role | P1 |
| `bid_validated` | `POST /agreements/bids/:id/validated` → `validated` | bid_id, bid_amount, duration_weeks | **P0** |
| `agreement_created` | `POST /agreements` → `draft` | agreement_id, bid_id | P0 |
| `agreement_sent` | `POST /agreements/:id/send` → `sent` | agreement_id | P0 |
| `agreement_changes_requested` | `POST /agreements/:id/request-changes` → `objections_raised` | agreement_id, objection_count | P1 |
| `agreement_revision_submitted` | `POST /agreements/:id/revisions` → `revision_submitted` | agreement_id, revision_number | P1 |
| `agreement_provider_signed` | `POST /agreements/:id/provider-sign` → `signed` (if both) | agreement_id | **P0** |
| `milestone_started` | `PATCH /milestones/:id/start` → `in_progress` | milestone_id | P1 |
| `milestone_evidence_uploaded` | `POST /milestones/:id/evidence` | milestone_id, evidence_count | P2 |
| `milestone_submitted` | `POST /milestones/:id/submit` → `submitted_for_approval` | milestone_id | **P0** |
| `milestone_change_requested` | `POST /milestones/:id/change-requests` | milestone_id, change_amount | P1 |
| `bank_details_added` | `POST /bank-details` → `pending_verification` | — | P0 |
| `bank_details_verified` | Wompi verify webhook → `verified` (server) | — | P0 |
| `payout_completed` | Wompi `PAYOUT.COMPLETED` webhook → `completed` (server) | payout_id, amount | **P0** |
| `payout_failed` | Wompi payout webhook → `failed` (server) | payout_id, reason | P0 |
| `sp_subscription_purchased` | `POST /wompi/subscription/checkout` (bid quota) | plan, amount | P0 |

---

### 4.6 Seller

| Event Name | Trigger | Key Properties | Priority |
|---|---|---|---|
| `seller_onboarded` | `POST /sellers/onboard` → status `needs_profile_completion`/`active` | seller_id | P0 |
| `seller_agreement_accepted` | `POST /sellers/agreement` | version | P0 |
| `seller_tier_selected` | `/seller/tier-selection` choice | tier | P1 |
| `property_listing_created` | `POST /marketplace/listings` | listing_id, property_type | **P0** |
| `listing_image_added` | `POST /seller-marketplace/listings/:id/images` | listing_id, image_count | P2 |
| `listing_cover_set` | `PUT .../images/:id/cover` | listing_id | P2 |
| `listing_ai_transformed` | `POST /seller-marketplace/image-transformations` | listing_id | P1 |
| `listing_visualization_generated` | `POST /seller-marketplace/visualization/generate` | listing_id | P1 |
| `property_listing_updated` | `PATCH /marketplace/listings/:id` | listing_id | P2 |
| `property_listing_published` | listing status → published/active | listing_id | **P0** |
| `property_listing_deleted` | `DELETE /marketplace/listings/:id` | listing_id | P2 |
| `property_audit_viewed` | `/seller/properties/[slug]/audit` | listing_id | P2 |
| `seller_lead_received` | `POST /marketplace/listings/:id/inquiries` (lead created) | listing_id, lead_id | **P0** |
| `seller_lead_responded` | seller responds to lead | lead_id | P1 |
| `lead_status_changed` | `PUT /marketplace/leads/:id` status change | lead_id, from_status, to_status | P1 |
| `seller_bank_details_added` | `/seller/profile/bank-details` → `POST /bank-details` | — | P0 |

> **"Signature Package" / bank distressed-asset listings:** the brief references these, but the
> code surfaces them as `/home/partnered-projects/brokered-deals` (admin-managed via
> `/admin/partnered-projects/brokered-deals`) plus a generic seller `tier-selection`. There is
> **no distinct "Signature Package" upgrade route or premium-listing endpoint** in this commit.
> See gaps.

---

### 4.7 Supplier (does not exist yet)

No supplier persona exists in this codebase: no `(suppliers)` route group, no supplier routes in
`apps/api`, no product-showcase/submission endpoint. "Supplier" is net-new (consistent with the
project's own notes that suppliers are not yet built — sellers and service-providers exist
instead).

**Recommendation:** do not define supplier events yet. When the feature lands, mirror the seller
listing taxonomy:

| Future Event Name | Trigger | Priority |
|---|---|---|
| `supplier_registered` | supplier account created | P0 |
| `product_showcase_submitted` | product showcase submission | P0 |
| `product_viewed` | buyer views a product | P1 |
| `product_inquiry_created` | inquiry on a product | P0 |
| `product_inquiry_responded` | supplier responds | P1 |

---

## 5. Capture Strategy — Server vs Client

| Capture side | Events | Why |
|---|---|---|
| **Server (Express controllers / webhooks)** | All payments, payouts, bank verification, Wompi webhooks, agreement/milestone status transitions, project submit, lead creation | These never touch the browser, or must be tamper-proof and reliable for revenue reporting |
| **Client (PostHog browser SDK)** | Visualizer interactions, the entire Style Tournament, project wizard step events + abandonment, page views, search, modal/CTA interactions | These are pure UI state with no server round-trip |

**Identity stitching:** identify users with a stable `user_id` and set `persona` + `locale` as
super-properties so the two streams (client + server) join into one funnel. Use PostHog
server-side `capture` with the same `distinct_id` used on the client.

---

## 6. Instrumentation Gaps (require new code before tracking)

Ordered by value. Each is a flow with meaningful user activity but no clean signal to hook into.

1. **Style Tournament is client-only.** Votes, room/budget picks, round progression, add-ons
   never reach the backend (`useGameEngine.ts` holds all state in React). Capture every step
   client-side via PostHog, or add a lightweight `POST /renovation-game/events` endpoint.
   *Highest-value gap — the game is hypothesis-critical and currently leaves no trace of how a
   style was chosen.*
2. **Visualizer reference staging is invisible.** Mood-board / furniture images stage in browser
   memory and only transmit inside `generate`. No signal that a user *prepared* a render but did
   not generate. Track `visualizer_moodboard_added` / `_furniture_added` client-side.
3. **Visualizer save-to-server is fire-and-forget** (`saveUserVisual` errors swallowed). No
   reliable success/failure signal — capture on the resolved/rejected branches explicitly.
4. **Bid acceptance has no dedicated endpoint.** A bid transitions to `accepted` *implicitly*
   when the agreement is signed — there is no `POST /bids/:id/accept`. Derive `bid_accepted`
   from `agreement_signed`, or add an explicit transition. Same for **bid rejection**
   (admin-only / implicit).
5. **Walkthrough booking state is murky.** `POST .../walkthrough-slots/:id/book` changes bid
   status but does not cleanly emit the transition — booking vs. scheduled vs. completed are
   entangled.
6. **Milestone creation is silent.** Milestones auto-create alongside the agreement with no
   dedicated endpoint, so there is no `milestone_created` signal — the first observable milestone
   event is `milestone_started`.
7. **Escrow hold has no local signal.** The hold is managed entirely inside Wompi; there is no
   app-side webhook/state for "funds held." Escrow can only be inferred from `payment_settled`.
   If escrow timing matters, add a derived server event at settlement.
8. **SP/Seller onboarding step completion is not marked.** Intermediate onboarding PUTs save data
   but set no status; only the final `complete` endpoint is authoritative. Step-level drop-off
   must be reconstructed from client events or last-successful-PUT.
9. **Project wizard abandonment has no server signal** (un-submitted steps leave a `draft`).
   Capture `project_step_abandoned` client-side to measure funnel drop.
10. **Listing status lifecycle is under-specified in code.** `property_listings.listing_status_id`
    references a lookup table but no clean draft → published transition endpoint was found.
    Confirm where publishing happens before relying on `property_listing_published`.
11. **No "Signature Package" / premium-listing upgrade flow** exists as a distinct route/endpoint
    (only generic `seller/tier-selection` + admin brokered-deals). If this is a planned
    monetization surface, it must be built before it can be instrumented.
12. **Supplier persona does not exist** — no routes, endpoints, or schema. Net-new build required
    before any supplier events.

---

## 7. Status Enums Reference (for transition events)

Captured from the Drizzle schema; transitions in these columns are trackable events.

| Table | Status column | Values |
|---|---|---|
| `users` | `account_status` | active, suspended, blocked |
| `projects` | `status` | draft, active, awarded, ongoing, on_hold, completed, cancelled, archived |
| `project_bids` | `status` | pending, shortlisted, walkthrough_scheduled, walkthrough_completed, validated, accepted, rejected, withdrawn, expired |
| `project_agreements` | `status` | draft, sent, objections_raised, revision_submitted, signed, completed, cancelled, closed |
| `milestones` | `status` | not_started, in_progress, submitted_for_approval, approved, disputed |
| `sellers` | `status` | needs_profile_completion, agreement_pending, active, published |
| `wompi_transactions` | `status` | created, pending, approved, declined, voided, refunded |
| `wompi_payouts` | `status` | pending, processing, completed, failed, cancelled |
| `subscriptions` | `status` | active, paused, cancelled, expired |
| `invoices` | `status` | draft, pending, paid, overdue, cancelled |
| `service_provider_bank_details` | `status` | pending_verification, verified, failed, inactive |
| `usage_ledger` | (quota) | feature = ai_renders / bids; used_count, limit_count |

> Some endpoint behaviors (bid acceptance, listing publish, several onboarding statuses) were
> inferred from status enums and route shapes rather than confirmed handler bodies. Verify those
> before wiring P0 events on them.

---

## 8. Next Steps / Roadmap

### Phase 0 — Foundation (1–2 days)
- [ ] Add PostHog to `apps/web`: install `posthog-js`, wrap the app with a provider in the
      `[locale]` layout, init with project key + EU/US host.
- [ ] Add `posthog-node` to `apps/api`; create a thin `analytics.capture()` helper that takes
      `distinct_id`, event, properties. No-op if key absent (safe in dev).
- [ ] Define a single `analytics.ts` event-name enum/const + typed property shapes shared via the
      monorepo's shared package, so event names can never drift between client and server.
- [ ] Establish identity: call `posthog.identify(user_id)` on login/session restore; set
      `persona` + `locale` super-properties.

### Phase 1 — P0 revenue + funnel events (3–5 days)
- [ ] **Server-side:** wire `analytics.capture()` into the controllers for `project_submitted`,
      `bid_submitted`, `bid_validated`, `agreement_*signed`, `milestone_submitted`,
      `milestone_approved`, `payment_initiated`, `payment_settled`/`payment_failed`,
      `payout_completed`, `subscription_checkout_started`, `subscription_addon_purchased`,
      `seller_lead_received`, `property_listing_created`.
- [ ] **Client-side:** `user_signed_up`, `user_role_selected`, `feature_gate_hit`,
      `upgrade_modal_viewed`, the project-wizard step events.
- [ ] Wompi webhook handler: emit `payment_settled` / `payment_failed` / `payout_completed`
      from `processWebhook()` with the transaction/payout id and amount.

### Phase 2 — Hypothesis-critical features (3–4 days)
- [ ] Instrument the **Visualizer** fully (Section 4.3), capturing render request/success/failure
      with `surface`, `is_iteration`, `quota_remaining`. Fix the fire-and-forget save to emit
      `visual_saved_server` only on success.
- [ ] Instrument the **Style Tournament** end to end (Section 4.4). Decision required: pure
      client capture vs. a new `POST /renovation-game/events` server endpoint (see Gap #1). Pure
      client capture is faster; the server endpoint gives a durable, queryable record. Recommend
      **client capture now, server endpoint later** if the data proves valuable.
- [ ] Add `style_game_to_project` once the game → project handoff path is confirmed (it links the
      feature to revenue).

### Phase 3 — Close gaps + funnels (ongoing)
- [ ] Add explicit endpoints/signals for the instrumentation gaps that lack them: bid acceptance
      (#4), walkthrough booking (#5), milestone creation (#6), onboarding step completion (#8),
      listing publish (#10).
- [ ] Build PostHog funnels: signup → project_submitted → bid → agreement_signed → milestone →
      payment_settled (the core marketplace conversion), and game_started → reveal_reached →
      style_profile_saved → style_game_to_project (the feature → revenue hypothesis).
- [ ] Add error/exception tracking (Sentry or PostHog error tracking) — currently absent.

### Decision points to confirm with the team
1. Style Tournament capture: **client-only vs. new server endpoint?** (recommend client now)
2. Does a **game-profile → project** handoff exist? If not, that is a product gap.
3. Where does a **listing become published**? Confirm before relying on `property_listing_published`.
4. Are **Supplier** and **Signature Package** on the near-term roadmap? If so, scope their events
   alongside the build.

---

## 9. Appendix — Source Reference

Key files behind the high-value events (paths relative to `Reform-AI` root):

- Visualizer: `apps/web/src/components/.../RoomUpload.tsx`, `PropertyImageStudio.tsx`,
  `MyAIVisualsGallery.tsx`; service `apps/web/src/services/visualization.api.ts`;
  hook `apps/web/src/hooks/visualization/visualization.hooks.ts`;
  controller `apps/api/src/controllers/visualization.controller.ts`.
- Style Tournament: `apps/web/src/components/renovation-game/*`
  (`RenovationGame.tsx`, `GameScreen.tsx`, `ComparisonCard.tsx`, `FinalReveal.tsx`, etc.);
  engine `apps/web/src/hooks/renovation-game/useGameEngine.ts`;
  config `.../config/styleDiscoveryConfig.ts`; endpoint `renovation-game.routes.ts`.
- Payments/escrow: `apps/api/src/routes/{milestones,agreements,wompi,project,bank-details}.routes.ts`
  + matching controllers.
- Auth/onboarding: `apps/api/src/routes/{auth,service-provider,seller}.routes.ts`.
- Marketplace/listings: `apps/api/src/routes/{marketplace,seller-marketplace}.routes.ts`.
- Schema/enums: `apps/api/src/database/schema/*.ts`.

---

*End of audit.*
