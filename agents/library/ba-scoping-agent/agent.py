"""
ba-scoping-agent - v1 (LLM-assisted)

Converts a feature idea into a scope-ready brief by resolving Concepts against
existing product knowledge + codebase reality, surfacing high-divergence forks as
blocking Questions, and (Pass B) capturing human answers as durable Decisions.
Scoping + decision-extraction agent. NOT a PRD generator in v1.

It NEVER reads source code. Its IS-state view is a validated codebase_context
artifact loaded via public.get_latest_codebase_context(product_key). It writes the
product graph only through public.graph_* RPCs and never mints/mutates cbc:* ids.

Pass A (scope, default): propose Feature/Concepts/Questions, compute readiness,
                         withhold the brief if not scope-ready.
Pass B (ratify):         capture human answers as Decisions, recompute, render brief.

Usage:
    python agents/library/ba-scoping-agent/agent.py \\
        --feature-intent "Add a catalogue of materials for suppliers and service providers" \\
        --product-key reformai-product --tenant ReformAI

Required env (.env.local):
    ANTHROPIC_API_KEY, NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
    OVERSIGHT_URL (default https://agent-oversight.vercel.app), AGENT_OVERSIGHT_SECRET
Optional: BA_SCOPING_MODEL (default claude-opus-4-5), BA_SCOPING_AGENT_ID
"""

from __future__ import annotations

import os
import sys
import json
import uuid
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(".env.local", usecwd=True), override=True)
except ImportError:
    pass

# Claude Code injects EMPTY ANTHROPIC_* vars into child processes -> illegal 'Bearer ' header.
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
log = logging.getLogger("ba")

# ── Identity ──────────────────────────────────────────────────────────────────
AGENT_INSTANCE_ID  = os.environ.get("BA_SCOPING_AGENT_ID", "0cc9bf15-49a5-4667-9985-77c31877490b")
AGENT_INSTANCE     = "reformai.ba-scoping-agent"
DEFINITION_VERSION = "1.0.0"
OUT_SCHEMA_PATH    = REPO_ROOT / "docs" / "schemas" / "product-graph.schema.json"
IN_SCHEMA_PATH     = REPO_ROOT / "docs" / "schemas" / "codebase-context.schema.json"

_CLAUDE_PRICING = {"claude-opus": (15.00, 75.00), "claude-sonnet": (3.00, 15.00), "claude-haiku": (0.25, 1.25)}


class NullRunCtx:
    """No-op telemetry context used when the agent is paused (ingest rejects inactive agents)."""
    def step(self, *a, **k) -> None: pass
    def report(self, *a, **k) -> None: pass
    def timer(self) -> StepTimer: return StepTimer()


@contextlib.contextmanager
def telemetry_ctx(oversight: OversightClient, **kw):
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


# ── Supabase REST helpers ─────────────────────────────────────────────────────

def _sb():
    url = os.environ["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    return url, h


def sb_rpc(fn: str, payload: dict):
    url, h = _sb()
    r = requests.post(f"{url}/rest/v1/rpc/{fn}", headers=h, json=payload, timeout=30)
    if not r.ok:
        raise RuntimeError(f"rpc {fn} failed: {r.status_code} {r.text}")
    if r.status_code == 204 or not r.text.strip():
        return None
    return r.json()


def resolve_tenant(name_or_id: str) -> str:
    """Resolve company by exact name or explicit UUID. Never LIMIT 1."""
    try:
        uuid.UUID(name_or_id)
        return name_or_id
    except ValueError:
        pass
    url, h = _sb()
    r = requests.get(f"{url}/rest/v1/companies", headers=h,
                     params={"name": f"eq.{name_or_id}", "select": "id,name"}, timeout=20)
    r.raise_for_status()
    rows = r.json()
    if len(rows) != 1:
        raise RuntimeError(f"tenant '{name_or_id}' resolved to {len(rows)} companies (need exactly 1)")
    return rows[0]["id"]


def load_codebase_context(product_key: str) -> dict | None:
    rows = sb_rpc("get_latest_codebase_context", {"p_target_key": product_key})
    if not rows:
        return None
    row = rows[0] if isinstance(rows, list) else rows
    return row


def write_agent_output(artifact: dict, run_id: str, company_id: str) -> str:
    url, h = _sb()
    r = requests.post(f"{url}/rest/v1/agent_outputs",
        headers={**h, "Prefer": "return=representation"},
        json={"agent_id": AGENT_INSTANCE_ID, "run_id": run_id, "company_id": company_id,
              "output_type": "product_graph_scope", "content": artifact}, timeout=25)
    if not r.ok:
        raise RuntimeError(f"agent_outputs write failed: {r.status_code} {r.text}")
    d = r.json()
    return (d[0] if isinstance(d, list) else d).get("id", "")


# ── Compact the IS-state artifact for the LLM ─────────────────────────────────

def compact_context(ctx: dict) -> tuple[str, dict, dict]:
    """Return (prompt_text, name_to_cbc, noun_to_cbc).

    noun_to_cbc (requested_noun -> [cbc_ids]) is the AUTHORITATIVE mapping source per the
    CCA/BA contract; name_to_cbc (code entity/actor name -> cbc id) is a secondary fallback.
    The BA never infers cbc ids - it reads them from the artifact.
    """
    name_to_cbc: dict[str, str] = {}
    for e in ctx.get("entities", []):
        if e.get("name") and e.get("id"):
            name_to_cbc[e["name"].strip().lower()] = e["id"]
    for a in ctx.get("actors", []):
        if a.get("name") and a.get("id"):
            name_to_cbc[a["name"].strip().lower()] = a["id"]
    noun_to_cbc: dict[str, list] = {}
    for cr in ctx.get("concept_resolution", []):
        noun = str(cr.get("requested_noun", "")).strip().lower()
        if noun and cr.get("cbc_ids"):
            noun_to_cbc[noun] = list(cr["cbc_ids"])

    lines = []
    lines.append("## Entities (code reality)")
    for e in ctx.get("entities", []):
        flds = ", ".join(f.get("name", "") for f in e.get("fields", [])[:10])
        lines.append(f"- {e['name']} [{'exists' if e.get('exists') else 'NOT in code'}] {e.get('source','')}"
                     + (f" :: {e.get('description','')}" if e.get("description") else "")
                     + (f" | fields: {flds}" if flds else ""))
    lines.append("\n## Actors")
    for a in ctx.get("actors", []):
        lines.append(f"- {a['name']}" + (f" (role {a.get('auth_role')})" if a.get("auth_role") else "")
                     + f" [{'exists' if a.get('exists') else 'NOT in code'}]")
    lines.append("\n## Domain signals (highest value - may REFUTE assumptions)")
    for s in ctx.get("domain_signals", []):
        lines.append(f"- {s.get('signal')} ({s.get('confidence')}) -> {s.get('implication_hint')}")
    lines.append("\n## Concept resolution (feature nouns already checked against code)")
    for cr in ctx.get("concept_resolution", []):
        lines.append(f"- {cr.get('requested_noun')}: {'EXISTS' if cr.get('exists') else 'NEW'} "
                     f"-> code names {cr.get('cbc_ids')}")
    lines.append("\n## Capabilities")
    for c in ctx.get("capabilities", []):
        lines.append(f"- {c.get('name')}: {c.get('description','')}")
    return "\n".join(lines), name_to_cbc, noun_to_cbc


# ── LLM scoping tool ──────────────────────────────────────────────────────────

_SCOPE_TOOL = {
    "name": "submit_feature_scope",
    "description": "Submit the scoping result: the product Concepts the feature touches, the BLOCKING "
                   "high-divergence Questions that must be answered before scoping, and low-divergence "
                   "notes/confirmed constraints. Do NOT write requirements or decisions. Do NOT invent "
                   "cbc identities - reference existing code by its code name in cbc_refs.",
    "input_schema": {
        "type": "object",
        "required": ["concepts", "questions", "feature_notes"],
        "properties": {
            "concepts": {"type": "array", "items": {"type": "object",
                "required": ["title", "kind"], "properties": {
                    "title": {"type": "string", "description": "product noun, e.g. 'Supplier', 'Material'"},
                    "kind": {"type": "string", "description": "actor | entity | workflow | event | integration"},
                    "cbc_refs": {"type": "array", "items": {"type": "string"},
                                 "description": "code names (entity/actor names from the context) this concept maps to; empty = net-new"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "note": {"type": "string"}}}},
            "questions": {"type": "array", "items": {"type": "object",
                "required": ["text", "blocking", "divergence"], "properties": {
                    "text": {"type": "string"},
                    "blocking": {"type": "boolean"},
                    "divergence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "addresses": {"type": "array", "items": {"type": "string"},
                                  "description": "concept titles this question bears on"}}}},
            "feature_notes": {"type": "array", "items": {"type": "string"},
                "description": "low-divergence assumptions AND confirmed constraints from domain_signals "
                               "(e.g. 'single-market Colombia; market-scoping refuted')"},
        },
    },
}

SYSTEM_PROMPT = """You are the BA Scoping Agent. You convert a feature idea into a scope-ready graph by
resolving Concepts against existing product knowledge and codebase reality, and surfacing only the
forks that actually matter. You are NOT a PRD generator. You never write requirements or decisions.

Method:
- Resolve the feature's nouns to Concepts. If a noun already exists in code (see concept_resolution /
  entities / actors), map it via cbc_refs using the CODE NAME; if it is net-new, leave cbc_refs empty.
- A domain signal can REFUTE an assumption. If the code shows single-market/single-currency, do NOT ask
  'is it market-scoped' - record the confirmed constraint in feature_notes instead. Only ask what the
  code cannot answer.
- Generate Questions ONLY for BLOCKING + HIGH-divergence forks: ones where different answers produce
  incompatible data models or workflows. Everything else is a feature_note, not a question. Asking
  twenty questions defeats the purpose; surface the few that change the design.
- If a material/catalog/etc already exists in code, the feature is a RECONCILIATION, not greenfield -
  the central question is usually how the new thing relates to the existing one.
Call submit_feature_scope exactly once."""


def call_llm(model: str, feature_intent: str, context_text: str) -> tuple[dict, int, int]:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model=model, max_tokens=8000,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        tools=[_SCOPE_TOOL], tool_choice={"type": "tool", "name": "submit_feature_scope"},
        messages=[{"role": "user", "content": [
            {"type": "text", "text": f"# IS-state codebase context\n\n{context_text}",
             "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": f"# Feature intent\n{feature_intent}\n\n"
             "Scope it: resolve Concepts (cbc_refs by code name), raise only blocking high-divergence "
             "Questions, and put confirmed constraints / low-divergence assumptions in feature_notes. "
             "Call submit_feature_scope."}]}],
    )
    block = next((b for b in resp.content if b.type == "tool_use"), None)
    if block is None:
        raise RuntimeError("LLM did not call submit_feature_scope: " + str([b.type for b in resp.content]))
    return block.input, resp.usage.input_tokens, resp.usage.output_tokens


# ── Graph writes ──────────────────────────────────────────────────────────────

def scope_to_graph(raw: dict, *, tenant: str, product: str, feature_intent: str, commit_sha: str,
                   name_to_cbc: dict, noun_to_cbc: dict, created_by: str,
                   clarification_artifact_id: str | None = None) -> tuple[str, list[dict], list[dict]]:
    """Write Feature + Concepts + Questions + edges. Returns (feature_key, nodes[], edges[])."""
    nodes: list[dict] = []
    edges: list[dict] = []

    notes = [n for n in raw.get("feature_notes", []) if isinstance(n, str)]
    # clarification_brief_artifact_id is the field the Scoping dashboard reads to surface the PCA panel.
    feat_attrs = {"scoped_against_commit": commit_sha,
                  **({"notes": notes} if notes else {}),
                  **({"clarification_brief_artifact_id": clarification_artifact_id} if clarification_artifact_id else {})}
    fk = sb_rpc("graph_next_key", {"p_product": product, "p_node_type": "feature"})
    sb_rpc("graph_upsert_node", {"p_tenant": tenant, "p_product": product, "p_node_type": "feature",
        "p_node_key": fk, "p_title": feature_intent, "p_status": "scoping", "p_created_by": created_by,
        "p_node_attributes": feat_attrs})
    nodes.append({"node_key": fk, "node_type": "feature", "title": feature_intent, "status": "scoping",
                  "created_by": created_by, "node_attributes": feat_attrs})

    title_to_key: dict[str, str] = {}
    for c in raw.get("concepts", []):
        title = c["title"].strip()
        kind = c.get("kind", "entity").strip() or "entity"
        aliases = [a for a in c.get("aliases", []) if isinstance(a, str)]
        # Authoritative: concept_resolution by noun (title + aliases). Fallback: LLM cbc_refs by code name.
        ids: set[str] = set()
        for key in [title.lower(), *(a.strip().lower() for a in aliases)]:
            ids.update(noun_to_cbc.get(key, []))
        for ref in c.get("cbc_refs", []):
            r = str(ref).strip().lower()
            if r in noun_to_cbc:
                ids.update(noun_to_cbc[r])
            elif name_to_cbc.get(r):
                ids.add(name_to_cbc[r])
        cbc_ids = sorted(ids)

        existing = sb_rpc("graph_resolve_concept", {"p_tenant": tenant, "p_product": product, "p_noun": title})
        if existing:
            ck = existing[0]["node_key"]
        else:
            ck = sb_rpc("graph_next_key", {"p_product": product, "p_node_type": "concept"})
            sb_rpc("graph_upsert_node", {"p_tenant": tenant, "p_product": product, "p_node_type": "concept",
                "p_node_key": ck, "p_title": title, "p_status": "proposed", "p_created_by": created_by,
                "p_kind": kind, "p_maps_to_codebase": cbc_ids, "p_aliases": aliases})
            nodes.append({"node_key": ck, "node_type": "concept", "title": title, "status": "proposed",
                          "kind": kind, "maps_to_codebase": cbc_ids, "aliases": aliases, "created_by": created_by})
        title_to_key[title.lower()] = ck
        nature = "touches" if cbc_ids else "creates"
        sb_rpc("graph_add_edge", {"p_tenant": tenant, "p_product": product, "p_edge_type": "references",
            "p_src_key": fk, "p_dst_key": ck, "p_created_by": created_by, "p_edge_attributes": {"nature": nature}})
        edges.append({"edge_type": "references", "src_key": fk, "dst_key": ck, "created_by": created_by,
                      "edge_attributes": {"nature": nature}})

    for q in raw.get("questions", []):
        qk = sb_rpc("graph_next_key", {"p_product": product, "p_node_type": "question"})
        blocking = bool(q.get("blocking", True))
        divergence = q.get("divergence", "high")
        sb_rpc("graph_upsert_node", {"p_tenant": tenant, "p_product": product, "p_node_type": "question",
            "p_node_key": qk, "p_title": q["text"], "p_status": "open", "p_created_by": created_by,
            "p_blocking": blocking, "p_divergence": divergence})
        nodes.append({"node_key": qk, "node_type": "question", "title": q["text"], "status": "open",
                      "blocking": blocking, "divergence": divergence, "created_by": created_by})
        sb_rpc("graph_add_edge", {"p_tenant": tenant, "p_product": product, "p_edge_type": "derived_from",
            "p_src_key": qk, "p_dst_key": fk, "p_created_by": created_by, "p_edge_attributes": {}})
        edges.append({"edge_type": "derived_from", "src_key": qk, "dst_key": fk, "created_by": created_by,
                      "edge_attributes": {}})
        for addr in q.get("addresses", []):
            ck = title_to_key.get(str(addr).strip().lower())
            if ck:
                sb_rpc("graph_add_edge", {"p_tenant": tenant, "p_product": product, "p_edge_type": "references",
                    "p_src_key": qk, "p_dst_key": ck, "p_created_by": created_by, "p_edge_attributes": {}})
                edges.append({"edge_type": "references", "src_key": qk, "dst_key": ck,
                              "created_by": created_by, "edge_attributes": {}})

    return fk, nodes, edges


def render_provisional_brief(feature_intent: str, nodes: list[dict], readiness: dict) -> str:
    qs = [n for n in nodes if n["node_type"] == "question" and n.get("status") == "open"]
    L = [f"> PROVISIONAL - NOT SCOPE READY. {readiness.get('gate_open_blocking_questions', len(qs))} "
         "blocking question(s) open. Decisions are not final.\n",
         f"# Feature Scope Brief (provisional): {feature_intent}\n", "## Open questions"]
    for q in qs:
        flag = "[BLOCKING] " if q.get("blocking") else ""
        L.append(f"- {flag}{q['title']} ({q['node_key']}, divergence: {q.get('divergence')})")
    return "\n".join(L) + "\n"


# ── Main ──────────────────────────────────────────────────────────────────────

def scope_feature(*, feature_intent: str, product_key: str, tenant: str, model: str,
                  clarification_artifact_id: str | None = None, parent_run_id: str | None = None,
                  no_persist: bool = False) -> dict:
    """Scope a feature against the latest codebase_context (reads no source code). Returns a
    structured result. Callable by the CLI (main) and by the agile orchestrator/worker auto-chain."""
    ctx_row = load_codebase_context(product_key)
    if not ctx_row:
        raise RuntimeError(f"no codebase_context artifact for product_key={product_key} (run the CCA first)")
    content = ctx_row["content"] if isinstance(ctx_row.get("content"), dict) else json.loads(ctx_row["content"])
    commit_sha = ctx_row.get("commit_sha") or content.get("commit_sha", "unknown")
    cc_artifact_id = ctx_row.get("artifact_id", "")
    log.info("loaded codebase context @ %s (artifact %s)", commit_sha[:12], cc_artifact_id)

    try:
        jsonschema.validate(content, json.loads(IN_SCHEMA_PATH.read_text(encoding="utf-8")))
    except jsonschema.ValidationError as e:
        log.warning("consumed codebase_context not strictly schema-valid: %s", str(e)[:160])

    out_schema = json.loads(OUT_SCHEMA_PATH.read_text(encoding="utf-8"))
    context_text, name_to_cbc, noun_to_cbc = compact_context(content)
    tokens_in_hint = max(len(context_text) // 4, 500)

    oversight = OversightClient(
        url=os.environ.get("OVERSIGHT_URL", "https://agent-oversight.vercel.app"),
        secret=(os.environ.get("AGENT_OVERSIGHT_SECRET") or os.environ.get("OVERSIGHT_SECRET")
                or os.environ.get("INGEST_SECRET") or ""))
    run_id = str(uuid.uuid4())
    tkw = dict(agent_id=AGENT_INSTANCE_ID, run_id=run_id, model=model, provider="anthropic",
               tokens_in_hint=tokens_in_hint, task_type_code="orchestration", task_complexity_bucket="medium")
    if parent_run_id:
        tkw["parent_run_id"] = parent_run_id

    record_id = "(skipped)"
    with telemetry_ctx(oversight, **tkw) as tctx:
        tctx.step("context_loaded", message=f"codebase context @ {commit_sha[:12]}",
                  payload={"entities": len(content.get("entities", [])),
                           "signals": len(content.get("domain_signals", []))})
        log.info("calling %s for scoping...", model)
        with tctx.timer() as t:
            raw, ti, to = call_llm(model, feature_intent, context_text)
        cost = estimate_cost(model, ti, to)
        tctx.report(tokens_in=ti, tokens_out=to, cost_usd=cost)
        tctx.step("scoped", message=f"{len(raw.get('concepts', []))} concepts, "
                  f"{len(raw.get('questions', []))} questions", duration_ms=t.ms,
                  tokens_in=ti, tokens_out=to, cost_usd=cost)

        fk, nodes, edges = scope_to_graph(raw, tenant=tenant, product=product_key,
            feature_intent=feature_intent, commit_sha=commit_sha,
            name_to_cbc=name_to_cbc, noun_to_cbc=noun_to_cbc, created_by=AGENT_INSTANCE,
            clarification_artifact_id=clarification_artifact_id)
        tctx.step("graph_written", message=f"{len(nodes)} nodes, {len(edges)} edges, feature {fk}")

        readiness = sb_rpc("graph_feature_readiness",
            {"p_tenant": tenant, "p_product": product_key, "p_feature_key": fk})
        scope_ready = bool(readiness.get("scope_ready"))
        tctx.step("readiness_evaluated", message=f"scope_ready={scope_ready}", payload=readiness)

        brief_md = None if scope_ready else render_provisional_brief(feature_intent, nodes, readiness)
        artifact = {
            "schema_version": "1.0", "artifact_type": "product_graph_scope",
            "artifact_id": str(uuid.uuid4()), "run_id": run_id,
            "product_key": product_key, "tenant_id": tenant,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "feature_key": fk,
            "scoped_against": {"repo": product_key, "commit_sha": commit_sha,
                               **({"codebase_context_artifact_id": cc_artifact_id} if cc_artifact_id else {})},
            "generator": {"agent": AGENT_INSTANCE, "version": DEFINITION_VERSION, "model": model},
            "inputs": {"product_key": product_key, "feature_intent": feature_intent},
            "nodes": nodes, "edges": edges, "readiness": readiness,
            **({"brief_markdown": brief_md} if brief_md else {}),
        }
        jsonschema.validate(artifact, out_schema)
        tctx.step("artifact_validated", message="product_graph_scope schema-valid")
        if not no_persist:
            with tctx.timer() as t:
                record_id = write_agent_output(artifact, run_id, tenant)
            tctx.step("artifact_written", message=f"agent_outputs/{record_id}", duration_ms=t.ms)

    return {"feature_key": fk, "scope_ready": scope_ready, "artifact_id": record_id, "run_id": run_id,
            "readiness": readiness, "n_concepts": sum(1 for n in nodes if n["node_type"] == "concept"),
            "n_questions": sum(1 for n in nodes if n["node_type"] == "question"), "n_edges": len(edges),
            "cost": cost, "tokens_in": ti, "tokens_out": to, "commit_sha": commit_sha}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="ba-scoping-agent v1 (Pass A scope)")
    p.add_argument("--feature-intent", required=True)
    p.add_argument("--product-key", default="reformai-product")
    p.add_argument("--tenant", default="ReformAI", help="company name or explicit UUID")
    p.add_argument("--model", default=os.environ.get("BA_SCOPING_MODEL", "claude-opus-4-5"))
    p.add_argument("--clarification-artifact-id", default=None,
                   help="link this feature to a PCA clarification_brief artifact (stamped on the feature node; surfaced in the Scoping dashboard)")
    p.add_argument("--no-persist", action="store_true", help="skip the agent_outputs artifact write")
    args = p.parse_args()

    tenant = resolve_tenant(args.tenant)
    log.info("tenant %s -> %s", args.tenant, tenant)
    try:
        r = scope_feature(feature_intent=args.feature_intent, product_key=args.product_key, tenant=tenant,
                          model=args.model, clarification_artifact_id=args.clarification_artifact_id,
                          no_persist=args.no_persist)
    except RuntimeError as e:
        log.error("%s", e)
        sys.exit(2)

    print(f"\n{'-'*64}")
    print("  BA Scoping Complete (Pass A)")
    print(f"  Feature : {r['feature_key']}  ({args.feature_intent})")
    print(f"  Concepts: {r['n_concepts']}  Questions: {r['n_questions']}  Edges: {r['n_edges']}")
    print(f"  Ready   : {r['scope_ready']}  (blocking={r['readiness'].get('gate_open_blocking_questions')}, "
          f"high_div={r['readiness'].get('gate_open_high_divergence')})")
    print(f"  Cost    : ${r['cost']:.6f}  ({r['tokens_in']:,} in / {r['tokens_out']:,} out)")
    print(f"  Artifact: agent_outputs/{r['artifact_id']}")
    print(f"  Run     : {r['run_id']}")
    print(f"{'-'*64}\n")


if __name__ == "__main__":
    main()
