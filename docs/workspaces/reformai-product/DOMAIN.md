# DOMAIN.md - ReformAI Product (`reformai-product`)

Domain glossary and business rules for the Product Clarification Agent. The PCA reads this to
apply correct terminology in `domain_terms` and to enforce known business rules in the Brief.
Curated domain knowledge - not codebase reality.

> Last reviewed: 2026-06-03. Update within 48h of any domain/market change.

## Market and commerce terms (Colombia)

- **COP** - Colombian Peso. The platform's single operating currency. Prices and money values are COP.
- **NIT** - Numero de Identificacion Tributaria. Colombian tax identifier for businesses/sellers.
- **IVA** - Impuesto al Valor Agregado. Colombian value-added tax applied to taxable transactions.
- **Wompi** - the payment gateway used for processing payments in COP.
- **Single market** - operations are Colombia-only. A `country` field exists but there is no
  multi-region or multi-currency partitioning. Do not assume market-scoping; treat it as a
  confirmed single-market constraint.

## Renovation domain terms

- **Project** - a renovation effort tied to a property, owned by a `home_owner`.
- **Room** - a unit within a project; renovation and material selection happen at the room level.
- **Room Material Option** (`roomMaterialOptions`) - a selectable material choice presented for a
  room. The existing "catalogue" is this set of selectable options.
- **Project Room Material** (`projectRoomMaterials`) - a material chosen for a specific room in a
  specific project (the selection record). NOT inventory; a per-project selection.
- **Service Provider** - a contractor/professional engaged to perform renovation work.
- **Seller** - a platform participant who lists and sells.

## Net-new / ambiguous terms (flag, do not assume)

- **Supplier** - not an existing role or entity. If intake introduces "supplier", the PCA must
  surface the structural fork (new role vs. attribute of `service_provider`/`seller`) rather than
  silently assume.
- **Catalogue (supplier inventory)** - distinct from the existing room-material catalogue. If
  intake means supplier-owned stock, it is net-new and must be reconciled against
  `roomMaterialOptions` (selection) - not assumed equivalent.

## Business rules (known constraints)

1. Currency is COP; do not introduce multi-currency assumptions.
2. Tax handling follows IVA; payments route through Wompi.
3. Sellers are identified by NIT.
4. Material selection is room-scoped per project; "inventory" is a different concept and is net-new.
5. Single-market (Colombia); no regional partitioning beyond the `country` field.
