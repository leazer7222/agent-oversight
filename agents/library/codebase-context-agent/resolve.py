"""
resolve.py - deterministic Tier-1 concept resolution (step 10), coverage-gated.

Resolves PCA/BA feature concepts against the canonical inventory using ONLY deterministic
matching (exact / prefix / token / alias). No LLM in P1 (the Tier-2 ambiguous-tail LLM is P2).

Coverage contract (hard rule):
  - `not_found` is emitted ONLY when the relevant layer(s) are green.
  - Non-green relevant coverage => `indeterminate` (BA must NOT classify net-new from this).

Status vocabulary: exists | partially_exists | ambiguous | conflicts | not_found | indeterminate.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import inventory as inventory_mod   # noqa: E402
import coverage as coverage_mod     # noqa: E402
from parser.naming import normalize_name  # noqa: E402

# layers whose green status is required before a concept may be declared not_found
NOT_FOUND_RELEVANT_LAYERS = ["schema", "integrations"]


def _exists(concept, status, cbc_id, method, confidence, evidence, layer, coverage, **extra):
    return {
        "concept": concept, "status": status, "matched_cbc_id": cbc_id,
        "match_confidence": confidence, "resolution_method": method,
        "evidence": evidence,
        "coverage_basis": {"layer": layer, "coverage_status": coverage_mod.layer_status(coverage, layer)},
        **extra,
    }


def _resolve_one(concept: str, inv: inventory_mod.Inventory, cov: dict,
                 ent_exact, actor_exact, integ_exact, cap_exact, ent_list) -> dict:
    cn = normalize_name(concept)

    # 1. exact entity
    if cn in ent_exact:
        e = ent_exact[cn]
        return _exists(concept, "exists", e["cbc_id"], "deterministic_exact_match", "high", e["evidence"], "schema", cov)
    # 2. exact actor (before entity prefix/token so 'Admin' -> actor, not dispute_admin_notes)
    if cn in actor_exact:
        a = actor_exact[cn]
        return _exists(concept, "exists", a["cbc_id"], "deterministic_exact_match", "high", a["evidence"], "auth", cov)
    # 3. exact integration
    if cn in integ_exact:
        i = integ_exact[cn]
        return _exists(concept, "exists", i["cbc_id"], "deterministic_exact_match", "high", i["evidence"], "integrations", cov)
    # 4. prefix entity (e.g. Property -> property_listings, property_leads)
    prefix_hits = [e for e in ent_list if normalize_name(e["name"]).startswith(cn + "_")]
    if prefix_hits:
        first = prefix_hits[0]
        extra = {}
        if len(prefix_hits) > 1:
            extra["possible_matches"] = [e["cbc_id"] for e in prefix_hits[:8]]
        return _exists(concept, "exists", first["cbc_id"], "deterministic_prefix_match", "medium",
                       first["evidence"], "schema", cov, **extra)
    # 5. token-substring entity (weaker)
    token_hits = [e for e in ent_list if cn in normalize_name(e["name"]).split("_")]
    if token_hits:
        first = token_hits[0]
        return _exists(concept, "partially_exists", first["cbc_id"], "deterministic_token_match", "medium",
                       first["evidence"], "schema", cov,
                       possible_matches=[e["cbc_id"] for e in token_hits[:8]])
    # 6. exact capability (route group)
    if cn in cap_exact:
        c = cap_exact[cn]
        return _exists(concept, "exists", c["cbc_id"], "deterministic_capability_match", "medium", c["evidence"], "routes", cov)

    # 7. no match -> not_found ONLY if relevant layers green, else indeterminate
    statuses = {l: coverage_mod.layer_status(cov, l) for l in NOT_FOUND_RELEVANT_LAYERS}
    green = all(s == "green" for s in statuses.values())
    return {
        "concept": concept,
        "status": "not_found" if green else "indeterminate",
        "matched_cbc_id": None,
        "match_confidence": "high" if green else "low",
        "resolution_method": "deterministic_no_match" if green else "coverage_insufficient",
        "evidence": [],
        "coverage_basis": {"layers": NOT_FOUND_RELEVANT_LAYERS, "coverage_status": statuses},
    }


def resolve_concepts(repo_root, concepts: list[str], inv: inventory_mod.Inventory | None = None,
                     cov: dict | None = None) -> dict:
    repo_root = Path(repo_root)
    inv = inv or inventory_mod.build_inventory(repo_root)
    # cov may be supplied (e.g. from a cache hit) to avoid re-running the source scan.
    if cov is None:
        cov = coverage_mod.build_coverage(repo_root, inv.schema_inv, inv.src)

    ent_exact = {}
    for e in inv.entities:
        ent_exact.setdefault(normalize_name(e["name"]), e)
    actor_exact = {normalize_name(a["name"]): a for a in inv.actors}
    integ_exact = {normalize_name(i["name"]): i for i in inv.integrations}
    cap_exact = {normalize_name(c["slug"]): c for c in inv.capabilities}

    resolved = [_resolve_one(c, inv, cov, ent_exact, actor_exact, integ_exact, cap_exact, inv.entities)
                for c in concepts]
    return {
        "artifact_type": "concept_resolution",
        "parser_version": inv.parser_version,
        "snapshot_tag": inv.snapshot_tag,
        "coverage_status": cov["coverage_status"],
        "coverage": cov,
        "resolved_concepts": resolved,
    }


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".workspace/Reform-AI").resolve()
    concepts = sys.argv[2:] or ["Partner", "Admin", "Habi", "Property", "Inventory"]
    out = resolve_concepts(root, concepts)
    print(f"coverage: {out['coverage_status']}  parser: {out['parser_version']}")
    for l, v in out["coverage"]["layers"].items():
        print(f"  layer {l}: {v['status']}")
    print()
    for r in out["resolved_concepts"]:
        ev = (r["evidence"][0].get("file_path") or r["evidence"][0].get("snapshot")) if r["evidence"] else "-"
        print(f"  {r['concept']:14s} -> {r['status']:16s} {r['matched_cbc_id'] or ''}  [{r['resolution_method']}]  ev:{ev}")
