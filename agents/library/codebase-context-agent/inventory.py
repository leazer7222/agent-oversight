"""
inventory.py - assemble the canonical codebase_inventory + deterministic cbc:* minting (step 6).

The deterministic parsers (drizzle snapshot + source scan) are the AUTHORITATIVE cbc minter
(C1 = Option A). Every entity traces to snapshot evidence; every actor/route/integration traces
to a literal source citation. No LLM. No invented objects.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from parser import drizzle_snapshot, source_scan       # noqa: E402
from parser.naming import Minter                        # noqa: E402

PARSER_VERSION = "cca-parser-v1.1"  # v1.1: actors include seeded roles (scripts/seed-roles.ts)


@dataclass
class Inventory:
    parser_version: str
    snapshot_tag: str
    entities: list[dict]
    actors: list[dict]
    routes: list[dict]
    capabilities: list[dict]
    integrations: list[dict]
    enums: list[dict]
    schema_inv: object
    src: object


def build_inventory(repo_root: Path) -> Inventory:
    schema_inv = drizzle_snapshot.extract(repo_root)
    src = source_scan.scan(repo_root)
    m = Minter()

    entities = []
    for e in schema_inv.entities:
        entities.append({
            "cbc_id": m.mint("entity", e.pg_table),
            "name": e.pg_table, "source": "drizzle_table", "table": e.pg_table,
            "columns": [{"name": c.name, "semantic_hint": c.semantic_hint, "nullable": c.nullable} for c in e.columns],
            "relations": [{"to_table": r.to_table, "kind": r.kind, "via": r.via} for r in e.relations],
            "pk": e.pk, "enums_used": e.enums_used, "evidence": [e.evidence],
        })

    actors = [{"cbc_id": m.mint("actor", a.name), "name": a.name, "source": a.source, "evidence": [a.evidence]}
              for a in src.actors]

    integrations = [{"cbc_id": m.mint("integration", i.name, normalizer="raw"), "name": i.name, "evidence": [i.evidence]}
                    for i in src.integrations]

    # cbc ids require [a-z0-9_] (no hyphens) -> use the "raw" normalizer; keep the hyphenated slug for display.
    capabilities = [{"cbc_id": m.mint("capability", c.slug, normalizer="raw"), "slug": c.slug, "evidence": [c.evidence]}
                    for c in src.capabilities]

    routes = [{"cbc_id": m.mint("route", f"{r.method}:{r.path}", normalizer="raw"),
               "method": r.method, "path": r.path, "required_roles": r.required_roles,
               "auth_required": r.auth_required, "evidence": [r.evidence]}
              for r in src.routes]

    enums = [{"name": en.name, "values": en.values} for en in schema_inv.enums]

    return Inventory(
        parser_version=PARSER_VERSION, snapshot_tag=schema_inv.snapshot_tag,
        entities=entities, actors=actors, routes=routes, capabilities=capabilities,
        integrations=integrations, enums=enums, schema_inv=schema_inv, src=src)


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".workspace/Reform-AI").resolve()
    inv = build_inventory(root)
    print(f"parser_version: {inv.parser_version}  snapshot: {inv.snapshot_tag}")
    print(f"entities={len(inv.entities)} actors={len(inv.actors)} routes={len(inv.routes)} "
          f"capabilities={len(inv.capabilities)} integrations={len(inv.integrations)} enums={len(inv.enums)}")
    print("partner cbc:", next((e["cbc_id"] for e in inv.entities if e["name"] == "partners"), None))
    print("admin cbc:", next((a["cbc_id"] for a in inv.actors if a["name"] == "admin"), None))
