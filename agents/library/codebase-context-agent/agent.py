"""
codebase-context-agent - v1 (LLM-assisted)

Analyzes a target codebase (read-only) at a pinned commit and produces a
codebase-context.json artifact describing code reality (entities, actors,
capabilities, domain signals, glossary, coverage, evidence) for downstream BA
scoping. Describes WHAT IS; never scopes WHAT SHOULD BE.

v1 acquisition mode = local path (a repo already cloned to disk). The clone /
GitHub-auth layer is a later upgrade; point --repo-path at a checkout.

Usage:
    python agents/library/codebase-context-agent/agent.py \\
        --repo-path .workspace/Reform-AI \\
        --target-key reformai-product \\
        --feature-intent "Add a catalogue of materials for suppliers and service providers" \\
        --concepts-to-check Material Catalogue Supplier ServiceProvider Market

Required env (in .env.local):
    ANTHROPIC_API_KEY
    NEXT_PUBLIC_SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
    OVERSIGHT_URL           (default: https://agent-oversight.vercel.app)
    AGENT_OVERSIGHT_SECRET  (or OVERSIGHT_SECRET / INGEST_SECRET)

Optional env:
    CCA_MODEL               (default: claude-opus-4-5)
    CODEBASE_CONTEXT_AGENT_ID
"""

from __future__ import annotations

import os
import re
import sys
import json
import uuid
import time
import argparse
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(".env.local", usecwd=True), override=True)
except ImportError:
    pass

# Claude Code injects EMPTY ANTHROPIC_* vars into child processes. dotenv(override=True)
# restores ANTHROPIC_API_KEY, but an empty ANTHROPIC_AUTH_TOKEN makes the SDK emit an
# illegal 'Authorization: Bearer ' header. Scrub the empty ones (keep a real BASE_URL).
for _k in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS"):
    if os.environ.get(_k, None) == "":
        os.environ.pop(_k, None)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "python-sdk"))

import contextlib  # noqa: E402
from oversight import OversightClient, OversightError, StepTimer  # noqa: E402
import requests   # noqa: E402
import anthropic  # noqa: E402
import jsonschema  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("cca")

# ── Identity (operational instance) ───────────────────────────────────────────
AGENT_INSTANCE_ID = os.environ.get("CODEBASE_CONTEXT_AGENT_ID", "b118d9e1-c3ff-49c3-bb8b-f3c1bb985d2a")
COMPANY_ID        = "1021c018-fe0e-4ae8-a972-7487521cc3d9"  # ReformAI
DEFINITION_VERSION = "1.0.0"
AGENT_INSTANCE     = "reformai.codebase-context-agent"
SCHEMA_PATH        = REPO_ROOT / "docs" / "schemas" / "codebase-context.schema.json"

# ── Source-bundle selection (high-signal anchors only) ────────────────────────
# Globs are evaluated relative to the target repo root. Order = priority.
INCLUDE_GLOBS = [
    "ARCHITECTURE.md",
    "apps/api/src/database/schema/*.ts",   # Drizzle entities (the core)
    "firestore.rules",                     # Firestore auth/roles subset
    "apps/api/src/types/role.types.ts",
    "apps/api/src/types/marketplace.types.ts",
]
# Route + schema filenames feed capability/coverage context cheaply (names only).
ROUTE_GLOB = "apps/api/src/routes/*.ts"
MAX_BUNDLE_CHARS = 380_000  # keep input tokens bounded (~95k tokens)

_CLAUDE_PRICING = {"claude-opus": (15.00, 75.00), "claude-sonnet": (3.00, 15.00), "claude-haiku": (0.25, 1.25)}


class NullRunCtx:
    """No-op telemetry context used when the agent is paused (ingest rejects inactive agents)."""
    def step(self, *a, **k) -> None: pass
    def report(self, *a, **k) -> None: pass
    def timer(self) -> StepTimer: return StepTimer()


@contextlib.contextmanager
def telemetry_ctx(oversight: OversightClient, **kw):
    """Use the real run lifecycle if the agent is active; degrade to a no-op if paused/unreachable."""
    try:
        with oversight.run(**kw) as ctx:
            yield ctx
        return
    except OversightError as e:
        log.warning("telemetry disabled (%s) - proceeding without run lifecycle", str(e)[:160])
        yield NullRunCtx()


def estimate_cost(model: str, ti: int, to: int) -> float:
    for k, (ir, orr) in _CLAUDE_PRICING.items():
        if k in model.lower():
            return round((ti * ir + to * orr) / 1_000_000, 6)
    return round((ti * 3.0 + to * 15.0) / 1_000_000, 6)


# ── cbc identity minting (deterministic; sole minter) ─────────────────────────
_IRREGULAR = {"people": "person", "children": "child", "data": "datum", "media": "medium"}


def singularize(token: str) -> str:
    if token in _IRREGULAR:
        return _IRREGULAR[token]
    if token.endswith("ies") and len(token) > 3:
        return token[:-3] + "y"
    if token.endswith(("ses", "xes", "zes", "ches", "shes")):
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def normalize_name(name: str) -> str:
    """lowercase -> snake_case -> singularize(head token) -> strip non-alphanumerics."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)          # camelCase -> camel_Case
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")              # non-alnum -> _
    if not s:
        return "unknown"
    tokens = s.split("_")
    tokens[-1] = singularize(tokens[-1])
    return "_".join(t for t in tokens if t)


class Minter:
    """Assigns deterministic, collision-disambiguated cbc ids for one run."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], str] = {}   # (cbc_type, source_name) -> id
        self._ids: set[str] = set()

    def mint(self, cbc_type: str, name: str) -> str:
        key = (cbc_type, name)
        if key in self._by_key:
            return self._by_key[key]
        base = f"cbc:{cbc_type}:{normalize_name(name)}"
        cand, n = base, 1
        while cand in self._ids:                          # collision with a different identity
            n += 1
            cand = f"{base}_{n}"
        self._ids.add(cand)
        self._by_key[key] = cand
        return cand


# ── Source bundle ─────────────────────────────────────────────────────────────

def collect_bundle(repo: Path) -> tuple[str, list[str], int, list[str]]:
    """Return (bundle_text, scanned_paths, files_total, route_names)."""
    scanned: list[str] = []
    parts: list[str] = []
    total_chars = 0
    for pattern in INCLUDE_GLOBS:
        for fp in sorted(repo.glob(pattern)):
            if not fp.is_file():
                continue
            rel = fp.relative_to(repo).as_posix()
            try:
                text = fp.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if total_chars + len(text) > MAX_BUNDLE_CHARS:
                text = text[: max(0, MAX_BUNDLE_CHARS - total_chars)] + "\n... [truncated]\n"
            parts.append(f"=== {rel} ===\n{text}")
            scanned.append(rel)
            total_chars += len(text)
            if total_chars >= MAX_BUNDLE_CHARS:
                break
    route_names = sorted(p.relative_to(repo).as_posix() for p in repo.glob(ROUTE_GLOB))
    if route_names:
        parts.append("=== API route files (names only, for capabilities) ===\n" + "\n".join(route_names))
        scanned.extend(route_names)
    files_total = sum(1 for _ in repo.rglob("*") if _.is_file() and ".git" not in _.parts)
    return "\n\n".join(parts), scanned, files_total, route_names


# ── LLM extraction tool ───────────────────────────────────────────────────────

_EVIDENCE = {"type": "array", "items": {"type": "object", "properties": {
    "path": {"type": "string"}, "lines": {"type": "string"}}, "required": ["path"]}}
_CONF = {"type": "string", "enum": ["high", "medium", "low"]}

_EXTRACT_TOOL = {
    "name": "submit_codebase_context",
    "description": "Submit the extracted code reality. Names follow CODE identifiers, never product nouns. "
                   "Cite evidence (path) for every item or omit it. Report exists:false for requested nouns "
                   "with no code representation. Do not invent product Concepts, Decisions, or recommendations.",
    "input_schema": {
        "type": "object",
        "required": ["entities", "actors", "capabilities", "domain_signals", "glossary", "concept_resolution"],
        "properties": {
            "entities": {"type": "array", "items": {"type": "object",
                "required": ["name", "exists", "source"], "properties": {
                    "name": {"type": "string", "description": "Code identifier (table/model name)."},
                    "exists": {"type": "boolean"},
                    "source": {"type": "string", "description": "e.g. 'table:serviceProviders', 'model:Project', 'none'."},
                    "description": {"type": "string"},
                    "fields": {"type": "array", "items": {"type": "object", "required": ["name"], "properties": {
                        "name": {"type": "string"},
                        "semantic_hint": {"type": "string", "description": "money|enum|timestamp|foreign_key|identifier|email|url|boolean|quantity|text|json"},
                        "nullable": {"type": "boolean"}}}},
                    "relationships": {"type": "array", "items": {"type": "object", "required": ["to_name", "kind"], "properties": {
                        "to_name": {"type": "string", "description": "code name of the related entity"},
                        "kind": {"type": "string", "enum": ["one-to-one", "one-to-many", "many-to-one", "many-to-many"]},
                        "via": {"type": "string"}}}},
                    "confidence": _CONF, "evidence": _EVIDENCE}}},
            "actors": {"type": "array", "items": {"type": "object",
                "required": ["name", "exists"], "properties": {
                    "name": {"type": "string"}, "exists": {"type": "boolean"},
                    "auth_role": {"type": "string"}, "source": {"type": "string"},
                    "confidence": _CONF, "evidence": _EVIDENCE}}},
            "capabilities": {"type": "array", "items": {"type": "object",
                "required": ["name"], "properties": {
                    "name": {"type": "string"}, "description": {"type": "string"},
                    "entity_names": {"type": "array", "items": {"type": "string"}},
                    "confidence": _CONF, "evidence": _EVIDENCE}}},
            "domain_signals": {"type": "array", "items": {"type": "object",
                "required": ["signal", "implication_hint", "confidence"], "properties": {
                    "signal": {"type": "string"},
                    "entity_names": {"type": "array", "items": {"type": "string"}},
                    "implication_hint": {"type": "string"}, "confidence": _CONF, "evidence": _EVIDENCE}}},
            "glossary": {"type": "array", "items": {"type": "object",
                "required": ["term"], "properties": {
                    "term": {"type": "string"}, "aka": {"type": "array", "items": {"type": "string"}},
                    "maps_to_name": {"type": "string", "description": "code name this term maps to"}}}},
            "concept_resolution": {"type": "array", "items": {"type": "object",
                "required": ["requested_noun", "resolved_names", "exists"], "properties": {
                    "requested_noun": {"type": "string"},
                    "resolved_names": {"type": "array", "items": {"type": "string"},
                                       "description": "code names (entities/actors) this noun resolves to; empty = genuinely new"},
                    "exists": {"type": "boolean"}, "note": {"type": "string"}}}},
        },
    },
}

SYSTEM_PROMPT = """You are the Codebase Context Agent. You read source code and describe WHAT IS - the
existing code reality - so a separate BA agent can scope new features. You never scope, never invent
product Concepts, never write requirements or recommendations.

Rules:
- Names you return are CODE identifiers (the actual table/model/role names), never product nouns.
- Cite evidence (file path, optional lines) for every entity/actor/capability/signal, or omit it.
- For each requested noun, return a concept_resolution entry. If there is no code representation,
  return exists:false with an empty resolved_names array (a genuine negative finding) - never guess.
- domain_signals are the highest-value output: surface non-obvious cross-cutting facts (multi-tenancy,
  market/region/currency/locale scoping, soft-delete, ownership, status enums) with an implication hint.
  Always sweep for these even if no one asked about them.
- Do NOT decide whether two code identities are "the same" product concept. Report the facts (e.g. one
  table backs multiple roles) and let the BA decide.
Call submit_codebase_context exactly once."""


def call_llm(model: str, bundle: str, feature_intent: str, concepts: list[str]) -> tuple[dict, int, int]:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    user_blocks = [
        {"type": "text", "text": f"# Target source bundle (read-only)\n\n{bundle}",
         "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": (
            f"# Feature intent (focus, does NOT narrow your domain_signal sweep)\n{feature_intent}\n\n"
            f"# concepts_to_check (existence-check these, additive only)\n{', '.join(concepts) or '(none)'}\n\n"
            "Extract the code reality and call submit_codebase_context. Requirements for completeness:\n"
            "- ALWAYS produce a concept_resolution entry for every concepts_to_check noun (this is the "
            "primary deliverable); nouns with no code representation come back exists:false, empty resolved_names.\n"
            "- ALWAYS produce domain_signals (multi-tenancy, market/region/currency/locale scoping, "
            "ownership, soft-delete, status enums). Do not skip them.\n"
            "- Keep each entity's fields list to the MOST SIGNIFICANT fields only (keys, foreign keys, "
            "enums, money/date/status), not every column - so the budget reaches signals and resolution.")},
    ]
    resp = client.messages.create(
        model=model, max_tokens=20000,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        tools=[_EXTRACT_TOOL], tool_choice={"type": "tool", "name": "submit_codebase_context"},
        messages=[{"role": "user", "content": user_blocks}],
    )
    block = next((b for b in resp.content if b.type == "tool_use"), None)
    if block is None:
        raise RuntimeError("LLM did not call submit_codebase_context: " + str([b.type for b in resp.content]))
    return block.input, resp.usage.input_tokens, resp.usage.output_tokens


# ── Assemble the schema-valid artifact ────────────────────────────────────────

_CONF_OK = {"high", "medium", "low"}


def _ev(x: dict) -> dict:
    """Sanitize LLM evidence to the schema-allowed {path, lines} shape (strips unknown keys)."""
    out = []
    for e in (x.get("evidence") or []):
        if isinstance(e, dict) and e.get("path"):
            item = {"path": str(e["path"])}
            if e.get("lines"):
                item["lines"] = str(e["lines"])
            out.append(item)
    return {"evidence": out} if out else {}


def _cf(x: dict) -> dict:
    c = x.get("confidence")
    return {"confidence": c} if c in _CONF_OK else {}


def assemble_artifact(raw: dict, *, repo_name: str, commit_sha: str, ref: str, feature_intent: str,
                      concepts: list[str], scanned: list[str], files_total: int, run_id: str,
                      model: str, route_names: list[str]) -> tuple[dict, list[str]]:
    minter = Minter()
    name_to_id: dict[str, str] = {}        # code name (lower) -> cbc id (entities + actors)
    events: list[dict] = []

    def reg(name: str, cbc_type: str) -> str:
        cid = minter.mint(cbc_type, name)
        name_to_id.setdefault(name.strip().lower(), cid)
        return cid

    entities = []
    for e in raw.get("entities", []):
        cid = reg(e["name"], "entity")
        events.append({"type": "minted", "cbc_id": cid, "current_name": e["name"]})
        entities.append({
            "id": cid, "name": e["name"], "exists": bool(e.get("exists", False)),
            "source": e.get("source", "none"), "description": e.get("description", ""),
            "fields": [{"name": f["name"], **({"semantic_hint": f["semantic_hint"]} if f.get("semantic_hint") else {}),
                        **({"nullable": f["nullable"]} if isinstance(f.get("nullable"), bool) else {})}
                       for f in e.get("fields", [])],
            "relationships": [],  # filled after all entities have ids
            **_cf(e), **_ev(e),
            "_rels_raw": e.get("relationships", []),
        })
    # resolve relationships to cbc ids now that every entity is minted
    for ent in entities:
        rels = []
        for r in ent.pop("_rels_raw", []):
            tid = name_to_id.get(str(r.get("to_name", "")).strip().lower())
            if tid:
                rels.append({"to": tid, "kind": r["kind"], **({"via": r["via"]} if r.get("via") else {})})
        ent["relationships"] = rels

    actors = []
    for a in raw.get("actors", []):
        cid = reg(a["name"], "actor")
        events.append({"type": "minted", "cbc_id": cid, "current_name": a["name"]})
        actors.append({"id": cid, "name": a["name"], "exists": bool(a.get("exists", False)),
                       **({"auth_role": a["auth_role"]} if a.get("auth_role") else {}),
                       **({"source": a["source"]} if a.get("source") else {}),
                       **_cf(a), **_ev(a)})

    capabilities = []
    for c in raw.get("capabilities", []):
        cid = minter.mint("capability", c["name"])
        capabilities.append({"id": cid, "name": c["name"], "description": c.get("description", ""),
                             "entities": [name_to_id[n.strip().lower()] for n in c.get("entity_names", [])
                                          if n.strip().lower() in name_to_id],
                             **_cf(c), **_ev(c)})

    domain_signals = []
    for s in raw.get("domain_signals", []):
        sc = s.get("confidence") if s.get("confidence") in _CONF_OK else "medium"
        domain_signals.append({"signal": s["signal"], "implication_hint": s["implication_hint"],
                               "confidence": sc,
                               "entities": [name_to_id[n.strip().lower()] for n in s.get("entity_names", [])
                                            if n.strip().lower() in name_to_id],
                               **_ev(s)})

    glossary = []
    for g in raw.get("glossary", []):
        mt = name_to_id.get(str(g.get("maps_to_name", "")).strip().lower())
        glossary.append({"term": g["term"], **({"aka": g["aka"]} if g.get("aka") else {}),
                         **({"maps_to": mt} if mt else {})})

    concept_resolution = []
    for cr in raw.get("concept_resolution", []):
        ids = [name_to_id[n.strip().lower()] for n in cr.get("resolved_names", []) if n.strip().lower() in name_to_id]
        concept_resolution.append({"requested_noun": cr["requested_noun"], "cbc_ids": ids,
                                   "exists": bool(cr.get("exists", bool(ids))),
                                   **({"note": cr["note"]} if cr.get("note") else {})})

    artifact = {
        "schema_version": "1.0", "artifact_type": "codebase_context",
        "artifact_id": str(uuid.uuid4()), "run_id": run_id,
        "repo": repo_name, "commit_sha": commit_sha, "ref_requested": ref,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feature_intent": feature_intent,
        "generator": {"agent": AGENT_INSTANCE, "version": DEFINITION_VERSION, "model": model},
        "inputs": {"target_key": repo_name, "ref_requested": ref, "feature_intent": feature_intent,
                   "concepts_to_check": concepts},
        "entities": entities, "actors": actors, "capabilities": capabilities,
        "domain_signals": domain_signals, "glossary": glossary,
        "concept_resolution": concept_resolution,
        "registry_events": events,
        "coverage": {"scanned_paths": scanned,
                     "omitted": ["apps/web frontend components", "functions/ (Firebase functions)",
                                 "background jobs / webhooks", "non-schema service internals"],
                     "confidence": "medium", "files_scanned": len(scanned), "files_total": files_total,
                     "note": f"Schema + roles + routes scanned; {len(route_names)} route files enumerated. "
                             "Frontend and function internals not parsed in v1."},
    }
    return artifact, [e["cbc_id"] for e in events]


# ── Markdown render ───────────────────────────────────────────────────────────

def render_md(a: dict) -> str:
    L = []
    L.append(f"# Codebase Context Summary - {a['repo']}\n")
    L.append(f"- Commit: `{a['commit_sha']}`  (ref: `{a['ref_requested']}`)")
    L.append(f"- Generated: {a['generated_at']}  by {a['generator']['agent']} ({a['generator']['model']})")
    L.append(f"- Feature intent: {a['feature_intent']}")
    cov = a["coverage"]
    L.append(f"- Coverage: {cov['files_scanned']} scanned / {cov['files_total']} total  (confidence: {cov['confidence']})\n")

    L.append("## Concept resolution (feature nouns)\n")
    L.append("| Requested | Exists | cbc identities |")
    L.append("|---|---|---|")
    for cr in a["concept_resolution"]:
        L.append(f"| {cr['requested_noun']} | {'yes' if cr['exists'] else 'NO (new)'} | {', '.join(cr['cbc_ids']) or '-'} |")
    L.append("")

    L.append("## Existing entities\n")
    for e in a["entities"]:
        flds = ", ".join(f["name"] for f in e.get("fields", [])[:12])
        L.append(f"- **{e['name']}** (`{e['id']}`) - {'exists' if e['exists'] else 'NOT in code'} - {e.get('source','')}")
        if e.get("description"):
            L.append(f"  - {e['description']}")
        if flds:
            L.append(f"  - fields: {flds}")
    L.append("")

    L.append("## Actors\n")
    for ac in a["actors"]:
        L.append(f"- **{ac['name']}** (`{ac['id']}`)" + (f" - role `{ac.get('auth_role')}`" if ac.get("auth_role") else ""))
    L.append("")

    L.append("## Domain signals (highest-value)\n")
    for s in a["domain_signals"]:
        L.append(f"- **{s['signal']}** ({s['confidence']}) -> {s['implication_hint']}")
    L.append("")

    L.append("## Glossary\n")
    for g in a["glossary"]:
        aka = f" (aka: {', '.join(g['aka'])})" if g.get("aka") else ""
        L.append(f"- {g['term']}{aka}" + (f" -> `{g['maps_to']}`" if g.get("maps_to") else ""))
    L.append("")

    L.append("## Capabilities\n")
    for c in a["capabilities"]:
        L.append(f"- **{c['name']}** (`{c['id']}`) - {c.get('description','')}")
    L.append("")

    L.append("## Coverage\n")
    L.append(f"- Scanned: {cov['files_scanned']} files. Omitted: {', '.join(cov['omitted'])}.")
    L.append(f"- {cov.get('note','')}")
    return "\n".join(L) + "\n"


# ── Persistence ───────────────────────────────────────────────────────────────

def write_agent_output(artifact: dict, run_id: str) -> str:
    url = os.environ["NEXT_PUBLIC_SUPABASE_URL"]; key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    r = requests.post(f"{url}/rest/v1/agent_outputs",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json", "Prefer": "return=representation"},
        json={"agent_id": AGENT_INSTANCE_ID, "run_id": run_id, "company_id": COMPANY_ID,
              "output_type": "codebase_context", "content": artifact}, timeout=20)
    if not r.ok:
        raise RuntimeError(f"agent_outputs write failed: {r.status_code} {r.text}")
    d = r.json()
    return (d[0] if isinstance(d, list) else d).get("id", "")


def persist_registry(artifact: dict) -> str:
    """Best-effort: mint cbc ids into platform.cbc_identity_registry via RPC. Skips if migration 025 unapplied."""
    url = os.environ["NEXT_PUBLIC_SUPABASE_URL"]; key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    sha = artifact["commit_sha"]
    rows = ([(e["id"], "entity", e["name"], e.get("source", "none"), e.get("exists", False)) for e in artifact["entities"]]
            + [(a["id"], "actor", a["name"], a.get("source", "none"), a.get("exists", False)) for a in artifact["actors"]]
            + [(c["id"], "capability", c["name"], "none", True) for c in artifact["capabilities"]])
    ok = 0
    for cid, ctype, name, source, exists in rows:
        status = "active" if exists else "provisional"
        r = requests.post(f"{url}/rest/v1/rpc/cbc_register_or_get",
            headers=h, json={"p_cbc_id": cid, "p_cbc_type": ctype, "p_name": name, "p_sha": sha,
                             "p_created_by": AGENT_INSTANCE, "p_source": source, "p_status": status}, timeout=15)
        if r.status_code == 404:
            return "skipped (migration 025 not applied)"
        if r.ok:
            ok += 1
    return f"persisted {ok}/{len(rows)} cbc identities"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="codebase-context-agent v1 (LLM-assisted, local-path)")
    p.add_argument("--repo-path", required=True, help="Path to a local checkout of the target repo")
    p.add_argument("--target-key", default="reformai-product")
    p.add_argument("--feature-intent", required=True)
    p.add_argument("--concepts-to-check", nargs="*", default=[])
    p.add_argument("--ref", default=None, help="Informational; defaults to the checkout's branch")
    p.add_argument("--model", default=os.environ.get("CCA_MODEL", "claude-opus-4-5"))
    p.add_argument("--out-dir", default=None)
    p.add_argument("--no-persist", action="store_true", help="Skip agent_outputs + registry writes")
    args = p.parse_args()

    repo = Path(args.repo_path).resolve()
    if not repo.is_dir():
        log.error("repo path not found: %s", repo); sys.exit(2)

    commit_sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    branch = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
    ref = args.ref or branch
    log.info("Target %s @ %s (ref %s)", args.target_key, commit_sha[:12], ref)

    oversight = OversightClient(
        url=os.environ.get("OVERSIGHT_URL", "https://agent-oversight.vercel.app"),
        secret=(os.environ.get("AGENT_OVERSIGHT_SECRET") or os.environ.get("OVERSIGHT_SECRET")
                or os.environ.get("INGEST_SECRET") or ""))
    run_id = str(uuid.uuid4())

    t0 = time.monotonic()
    bundle, scanned, files_total, route_names = collect_bundle(repo)
    bundle_ms = int((time.monotonic() - t0) * 1000)
    if not bundle.strip():
        log.error("empty source bundle - check INCLUDE_GLOBS against the repo layout"); sys.exit(2)
    tokens_in_hint = max(len(bundle) // 4, 500)
    complexity = "complex" if tokens_in_hint >= 25_000 else "medium" if tokens_in_hint >= 5_000 else "simple"
    log.info("Bundle: %d files, %d chars (~%d tok in), %d total repo files", len(scanned), len(bundle), tokens_in_hint, files_total)

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    with telemetry_ctx(oversight, agent_id=AGENT_INSTANCE_ID, run_id=run_id, model=args.model, provider="anthropic",
                       tokens_in_hint=tokens_in_hint, task_type_code="code_gen",
                       task_complexity_bucket=complexity) as ctx:
        ctx.step("bundle_collected", message=f"{len(scanned)} files, {len(bundle)} chars", duration_ms=bundle_ms,
                 payload={"files_scanned": len(scanned), "files_total": files_total})

        log.info("Calling %s for extraction...", args.model)
        with ctx.timer() as t:
            raw, ti, to = call_llm(args.model, bundle, args.feature_intent, args.concepts_to_check)
        cost = estimate_cost(args.model, ti, to)
        ctx.report(tokens_in=ti, tokens_out=to, cost_usd=cost)
        ctx.step("llm_extracted",
                 message=f"{len(raw.get('entities', []))} entities, {len(raw.get('domain_signals', []))} signals",
                 duration_ms=t.ms, tokens_in=ti, tokens_out=to, cost_usd=cost)

        artifact, cbc_ids = assemble_artifact(
            raw, repo_name=args.target_key, commit_sha=commit_sha, ref=ref,
            feature_intent=args.feature_intent, concepts=args.concepts_to_check,
            scanned=scanned, files_total=files_total, run_id=run_id, model=args.model, route_names=route_names)

        jsonschema.validate(artifact, schema)
        ctx.step("artifact_validated", message=f"schema-valid; {len(cbc_ids)} cbc identities minted")

        out_dir = Path(args.out_dir) if args.out_dir else (REPO_ROOT / "docs" / "codebase-context" / args.target_key)
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / f"{commit_sha[:12]}.json"
        md_path = out_dir / f"{commit_sha[:12]}.md"
        json_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        md_path.write_text(render_md(artifact), encoding="utf-8")
        ctx.step("artifact_written", message=f"{json_path.name} + {md_path.name}")

        record_id, reg_status = "(skipped)", "(skipped)"
        if not args.no_persist:
            with ctx.timer() as t:
                record_id = write_agent_output(artifact, run_id)
            ctx.step("agent_output_written", message=f"agent_outputs row {record_id}", duration_ms=t.ms)
            reg_status = persist_registry(artifact)
            ctx.step("registry_persisted", message=reg_status)

        print(f"\n{'-'*64}")
        print("  Codebase Context Complete")
        print(f"  Target  : {args.target_key} @ {commit_sha[:14]}")
        print(f"  Entities: {len(artifact['entities'])}  Actors: {len(artifact['actors'])}  "
              f"Capabilities: {len(artifact['capabilities'])}  Signals: {len(artifact['domain_signals'])}")
        print(f"  Resolved: " + "  ".join(
            f"{cr['requested_noun']}={'Y' if cr['exists'] else 'NEW'}" for cr in artifact["concept_resolution"]))
        print(f"  Cost    : ${cost:.6f}  ({ti:,} in / {to:,} out)")
        print(f"  Files   : {json_path}")
        print(f"            {md_path}")
        print(f"  Artifact: agent_outputs/{record_id}")
        print(f"  Registry: {reg_status}")
        print(f"  Run     : {run_id}")
        print(f"{'-'*64}\n")


if __name__ == "__main__":
    main()
