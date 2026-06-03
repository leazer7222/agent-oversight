# PRODUCT.md - ReformAI Product (`reformai-product`)

Product grounding for the Product Clarification Agent. Describes WHAT the ReformAI product is,
WHO it serves, and what it deliberately does NOT do. The PCA reads this to validate scope fit
and to ground `target_user` against real user definitions. This is curated product knowledge,
not codebase reality (the Codebase Context Agent owns code reality).

> Last reviewed: 2026-06-03. Update within 48h of any product/role change.

## What ReformAI is

ReformAI is a home renovation and real-estate platform for the **Colombian market**. It connects
property owners and buyers with the service providers and sellers who help them plan, source, and
execute renovation projects, room by room. The product is a Turborepo application: a Next.js web
app (`apps/web`) and an Express API (`apps/api`) backed by Drizzle/PostgreSQL. Messaging,
notifications, and support are handled separately (Firestore) and are out of scope for product
feature intake unless a feature explicitly concerns them.

## User roles (the canonical actors)

These are the authoritative user definitions. `target_user` in a Clarification Brief MUST
reference one or more of these.

- **`home_owner`** - owns a property; initiates and manages renovation projects on their rooms.
- **`home_buyer`** - is acquiring a property; evaluates renovation scope and cost before/after purchase.
- **`service_provider`** - a contractor/professional who performs renovation work and is engaged on projects.
- **`seller`** - lists and sells (property or goods) on the platform.
- **`admin`** - ReformAI staff; platform administration and oversight.

There is NO `supplier` role today. "Supplier" is a net-new concept; the closest existing actors
are `service_provider` and `seller`.

## What exists today (product surface)

- **Projects** scoped to a property, decomposed by **Room**.
- **Room material selection**: a home owner selects materials for a room from a catalogue of
  options (`roomMaterialOptions`), captured per project room (`projectRoomMaterials`). This is
  **room-scoped product selection for a renovation**, NOT supplier-owned inventory.
- Service provider engagement on projects; seller listings.
- Colombian-market commerce primitives (see DOMAIN.md): COP pricing, NIT identification, IVA tax,
  Wompi payments.

## What ReformAI does NOT do (boundaries)

- No supplier-owned inventory / wholesale catalogue today (the existing catalogue is room-scoped
  selection, not seller/supplier stock).
- No multi-country / multi-currency operation - single market is Colombia (a `country` field
  exists but there is no regional partitioning).
- Messaging/notifications/support internals are not product-feature intake surface by default.

## How the PCA should use this

- Ground `target_user` in the roles above; flag if intake implies a role that does not exist
  (e.g. "supplier") as a scope/structure question, not an assumption.
- Treat "add a materials catalogue" as a **reconciliation** against the existing room-material
  catalogue, not greenfield - the central forks are about ownership and inventory vs. selection.
- If this document or DOMAIN.md is absent or stale, set `context_integrity.rating` accordingly.
