"""
reconcile_cbc.py - C1 (Option A) registry reconciliation, P1-minimal (no full engine).

The deterministic parser is the authoritative cbc minter. This:
  1. Computes the authoritative deterministic id set (current inventory).
  2. Finds active registry ids NOT in that set (v1 LLM-minted leftovers).
  3. PRESERVES any leftover still referenced by product_graph.graph_nodes.maps_to_codebase
     (leaves them active; logs for manual review - cbc_merge is a manual call, not auto here).
  4. Marks the remaining unreferenced leftovers status='deprecated'.

Dry-run by default; pass --apply to write.
"""
from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import inventory as inventory_mod          # noqa: E402
from apply_sql import run_sql              # noqa: E402


def _rows(sql: str):
    status, body = run_sql(sql, "hdhovyrlnfojtkqbcegh")
    if status >= 400:
        raise RuntimeError(f"SQL failed: {status} {body}")
    return json.loads(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-path", default=".workspace/Reform-AI")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    inv = inventory_mod.build_inventory(Path(args.repo_path).resolve())
    deterministic = ({e["cbc_id"] for e in inv.entities}
                     | {a["cbc_id"] for a in inv.actors}
                     | {c["cbc_id"] for c in inv.capabilities})
    print(f"deterministic authoritative ids: {len(deterministic)}")

    active = {r["cbc_id"] for r in _rows(
        "select cbc_id from platform.cbc_identity_registry where status='active';")}
    print(f"active registry ids: {len(active)}")

    referenced = set()
    try:
        for r in _rows("select distinct unnest(maps_to_codebase) as cbc_id from product_graph.graph_nodes "
                       "where maps_to_codebase is not null;"):
            if r.get("cbc_id"):
                referenced.add(r["cbc_id"])
    except Exception as e:
        print(f"[warn] could not read graph references ({e}); preserving ALL leftovers to be safe")
        referenced = active  # safe fallback: deprecate nothing

    leftovers = active - deterministic
    preserve = leftovers & referenced
    deprecate = leftovers - referenced

    print(f"\nv1 leftovers (active, not in deterministic set): {len(leftovers)}")
    print(f"  PRESERVE (referenced by graph_nodes.maps_to_codebase): {len(preserve)} -> {sorted(preserve)}")
    print(f"  DEPRECATE (unreferenced): {len(deprecate)}")
    for d in sorted(deprecate):
        print(f"    - {d}")

    if not deprecate:
        print("\nnothing to deprecate.")
        return
    if not args.apply:
        print("\nDRY RUN - pass --apply to write.")
        return

    arr = ",".join("'" + d.replace("'", "''") + "'" for d in sorted(deprecate))
    status, body = run_sql(
        f"update platform.cbc_identity_registry set status='deprecated' "
        f"where status='active' and cbc_id = any(array[{arr}]) returning cbc_id;",
        "hdhovyrlnfojtkqbcegh")
    print(f"\nDEPRECATED {len(json.loads(body)) if status < 400 else 0} ids (status {status}).")


if __name__ == "__main__":
    main()
