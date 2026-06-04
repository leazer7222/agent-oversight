"""
coverage.py - honest, layer-specific coverage + the snapshot-vs-source completeness guard (C3).

Coverage governs trust: a concept may resolve to `not_found` ONLY when the relevant
layer is green. Non-green => `indeterminate`. Never present a partial sample as complete.

Layers (P1): schema, auth, routes, integrations.
"""
from __future__ import annotations

import re
from pathlib import Path

SCHEMA_GLOB = "apps/api/src/database/schema/*.ts"
_PGTABLE_RE = re.compile(r"pgTable\s*\(")

# completeness threshold: |source_tables - snapshot_tables| / snapshot_tables
STALE_THRESHOLD = 0.05


def _count_source_pgtables(repo_root: Path) -> tuple[int, int]:
    files = sorted(repo_root.glob(SCHEMA_GLOB))
    total = 0
    for f in files:
        try:
            total += len(_PGTABLE_RE.findall(f.read_text(encoding="utf-8", errors="replace")))
        except Exception:
            pass
    return total, len(files)


def build_coverage(repo_root: Path, schema_inv, source_scan) -> dict:
    layers: dict[str, dict] = {}
    known_gaps: list[dict] = []

    # --- schema layer (drizzle snapshot + completeness guard) ---
    snap_tables = len(schema_inv.entities)
    src_pgtables, src_files = _count_source_pgtables(repo_root)
    divergence = abs(src_pgtables - snap_tables) / snap_tables if snap_tables else 1.0
    if snap_tables == 0:
        schema_status = "red"
    elif divergence > STALE_THRESHOLD:
        schema_status = "yellow"
        known_gaps.append({
            "layer": "schema",
            "reason": f"snapshot may be stale: source has {src_pgtables} pgTable() across {src_files} files "
                      f"but snapshot has {snap_tables} tables (divergence {divergence:.1%} > {STALE_THRESHOLD:.0%})",
        })
    else:
        schema_status = "green"
    layers["schema"] = {
        "status": schema_status, "snapshot_tables": snap_tables, "source_pgtables": src_pgtables,
        "source_files": src_files, "divergence": round(divergence, 4),
        "snapshot": schema_inv.snapshot_path, "snapshot_tag": schema_inv.snapshot_tag,
    }

    # --- auth layer (literal roles) ---
    # Canonical role set is parsed from scripts/seed-roles.ts (seeded literals), unioned with
    # USER_ROLES + authorize() args. Green requires the seed (or USER_ROLES) + middleware + actors.
    has_roles_table = any(e.pg_table == "roles" for e in schema_inv.entities)
    roles_source = source_scan.seed_roles_found or source_scan.user_roles_found
    if roles_source and source_scan.auth_middleware_found and source_scan.actors:
        auth_status = "green"
    elif source_scan.actors:
        auth_status = "yellow"
    else:
        auth_status = "red"
    # Only a gap if the canonical seed could NOT be parsed (then we'd be relying on literals alone).
    if has_roles_table and not source_scan.seed_roles_found:
        known_gaps.append({
            "layer": "auth",
            "reason": "roles seed (scripts/seed-roles.ts) not parsed; only literal-enforced roles "
                      "(USER_ROLES + authorize() args) are inventoried - canonical role set may be incomplete",
        })
    layers["auth"] = {
        "status": auth_status, "actors_found": len(source_scan.actors),
        "seed_roles": source_scan.seed_roles_found, "user_roles_const": source_scan.user_roles_found,
        "auth_middleware": source_scan.auth_middleware_found, "roles_table_present": has_roles_table,
    }

    # --- routes layer ---
    routes_status = "red"
    if source_scan.route_files_discovered > 0:
        routes_status = "green" if not source_scan.route_files_failed else "yellow"
    layers["routes"] = {
        "status": routes_status, "routes": len(source_scan.routes),
        "files_discovered": source_scan.route_files_discovered,
        "files_parsed": source_scan.route_files_parsed,
        "files_failed": source_scan.route_files_failed,
    }

    # --- integrations layer ---
    integ_status = "green" if source_scan.integrations else "red"
    layers["integrations"] = {"status": integ_status, "integrations_found": len(source_scan.integrations)}

    order = {"green": 0, "yellow": 1, "red": 2}
    overall = max((v["status"] for v in layers.values()), key=lambda s: order[s], default="red")
    return {
        "artifact_type": "codebase_coverage_report",
        "coverage_status": overall,
        "layers": layers,
        "known_gaps": known_gaps,
    }


def layer_status(coverage: dict, layer: str) -> str:
    return coverage.get("layers", {}).get(layer, {}).get("status", "red")


def all_green(coverage: dict, layers: list[str]) -> bool:
    return all(layer_status(coverage, l) == "green" for l in layers)
