"""
compose.py - assemble the BA-facing codebase_context view (step 12).

Truth is stored once (cache); the BA-facing view is composed many times. This maps the
deterministic inventory + coverage + concept_resolution (+ optional label-only semantic
context) into the EXISTING docs/schemas/codebase-context.schema.json shape, so the BA
contract and the get_latest_codebase_context resolver (028) keep working unchanged.

The existing schema's cbc_id pattern only allows entity|actor|capability, so route/integration
identities live in the cache inventory but are not surfaced as cbc_ids in the composed view.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

_CBC_BA_OK = re.compile(r"^cbc:(entity|actor|capability):[a-z0-9_]+$")
_CONF_FROM_COVERAGE = {"green": "high", "yellow": "medium", "red": "low"}


def _ev(evlist: list[dict]) -> list[dict]:
    out = []
    for e in evlist or []:
        path = e.get("snapshot") or e.get("file_path") or e.get("prefix")
        if not path:
            continue
        item = {"path": str(path)}
        if e.get("line"):
            item["lines"] = str(e["line"])
        out.append(item)
    return out


def _ba_ids(ids: list[str]) -> list[str]:
    seen, out = set(), []
    for i in ids:
        if i and _CBC_BA_OK.match(i) and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def compose(*, inventory, coverage: dict, resolution: dict, repo: str, commit_sha: str,
            ref: str, feature_intent: str, concepts: list, run_id: str,
            semantic: dict | None = None) -> dict:
    semantic = semantic or {}
    name_to_cbc = {e["name"]: e["cbc_id"] for e in inventory.entities}

    entities = []
    for e in inventory.entities:
        rels = []
        for r in e["relations"]:
            tid = name_to_cbc.get(r["to_table"])
            if tid:
                rels.append({"to": tid, "kind": r["kind"], **({"via": r["via"]} if r.get("via") else {})})
        entities.append({
            "id": e["cbc_id"], "name": e["name"], "exists": True,
            "source": f"drizzle_table:{e['table']}", "description": "",
            "fields": [{"name": c["name"], **({"semantic_hint": c["semantic_hint"]} if c.get("semantic_hint") else {}),
                        **({"nullable": c["nullable"]} if isinstance(c.get("nullable"), bool) else {})}
                       for c in e["columns"]],
            "relationships": rels, "confidence": "high", "evidence": _ev(e["evidence"]),
        })

    auth_conf = _CONF_FROM_COVERAGE.get(coverage["layers"]["auth"]["status"], "medium")
    actors = [{"id": a["cbc_id"], "name": a["name"], "exists": True, "auth_role": a["name"],
               "source": "role", "confidence": auth_conf, "evidence": _ev(a["evidence"])}
              for a in inventory.actors]

    capabilities = [{"id": c["cbc_id"], "name": c["slug"], "description": "",
                     "entities": [], "confidence": "medium", "evidence": _ev(c["evidence"])}
                    for c in inventory.capabilities]

    # concept_resolution -> existing BA shape {requested_noun, cbc_ids[], exists}
    concept_resolution = []
    for r in resolution["resolved_concepts"]:
        ids = _ba_ids(([r["matched_cbc_id"]] if r.get("matched_cbc_id") else []) + (r.get("possible_matches") or []))
        concept_resolution.append({
            "requested_noun": r["concept"],
            "cbc_ids": ids,
            "exists": r["status"] in ("exists", "partially_exists"),
            "note": f"{r['status']} via {r['resolution_method']}",
        })

    cov_conf = _CONF_FROM_COVERAGE.get(coverage["coverage_status"], "medium")
    schema_layer = coverage["layers"]["schema"]
    coverage_block = {
        "scanned_paths": ["apps/api/src/database/schema/*", "apps/api/src/routes/*", "apps/api/src/config/*",
                          schema_layer.get("snapshot", "")],
        "omitted": ["apps/web frontend", "functions/ (Firebase functions)", "service internals",
                    "seeded role data (roles table rows)"],
        "confidence": cov_conf,
        "files_scanned": schema_layer.get("source_files", 0) + coverage["layers"]["routes"].get("files_parsed", 0),
        "files_total": schema_layer.get("source_files", 0) + coverage["layers"]["routes"].get("files_discovered", 0),
        "note": f"deterministic P1; coverage={coverage['coverage_status']}; "
                f"layers " + ", ".join(f"{k}:{v['status']}" for k, v in coverage["layers"].items()),
    }

    # semantic enrichment -> BA view: filter cbc ids to BA-allowed types (entity|actor|capability).
    # The label-only pass may legitimately reference integrations; the BA schema does not surface them.
    domain_signals = []
    for s in semantic.get("domain_signals", []):
        ids = _ba_ids(s.get("entities", []))
        domain_signals.append({"signal": s["signal"], "implication_hint": s["implication_hint"],
                               "confidence": s.get("confidence", "medium"),
                               **({"entities": ids} if ids else {})})
    glossary = []
    for g in semantic.get("glossary", []):
        mt = g.get("maps_to")
        mt = mt if (mt and _CBC_BA_OK.match(mt)) else None
        glossary.append({"term": g["term"], **({"aka": g["aka"]} if g.get("aka") else {}),
                         **({"maps_to": mt} if mt else {})})

    return {
        "schema_version": "1.0", "artifact_type": "codebase_context",
        "artifact_id": str(uuid.uuid4()), "run_id": run_id,
        "repo": repo, "commit_sha": commit_sha, "ref_requested": ref,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feature_intent": feature_intent,
        "generator": {"agent": "reformai.codebase-context-agent", "version": "1.0.0",
                      "model": "deterministic+" + (semantic.get("model", "none"))},
        "inputs": {"target_key": repo, "ref_requested": ref, "feature_intent": feature_intent,
                   "concepts_to_check": list(concepts)},
        "entities": entities, "actors": actors, "capabilities": capabilities,
        "domain_signals": domain_signals,
        "glossary": glossary,
        "concept_resolution": concept_resolution,
        "coverage": coverage_block,
    }
