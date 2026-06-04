"""
pipeline.py - CCA P1 truth-service orchestrator (deterministic; LLM optional, label-only).

Flow: acquire (local path) -> build_inventory (drizzle snapshot + source scan) -> coverage
-> cache.put -> resolve concepts -> [optional label-only semantic domain_signals] -> compose
BA view -> schema-validate -> publish codebase_context + concept_resolution to agent_outputs
-> register deterministic cbc:* identities (entity/actor/capability) -> telemetry.

The deterministic parser is the authoritative cbc minter (C1). Routes/integrations live in the
cache inventory only (registry constraint 025 = entity|actor|capability).
"""
from __future__ import annotations

import os
import sys
import json
import uuid
import time
import argparse
import logging
import subprocess
import contextlib
from pathlib import Path
from types import SimpleNamespace

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(".env.local", usecwd=True), override=True)
except ImportError:
    pass
for _k in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS"):
    if os.environ.get(_k, None) == "":
        os.environ.pop(_k, None)

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT / "python-sdk"))

import requests          # noqa: E402
import jsonschema        # noqa: E402
import inventory as inventory_mod   # noqa: E402
import coverage as coverage_mod     # noqa: E402
import resolve as resolve_mod       # noqa: E402
import compose as compose_mod       # noqa: E402
import cache as cache_mod           # noqa: E402
from oversight import OversightClient, OversightError, StepTimer  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("cca-p1")

AGENT_INSTANCE_ID = os.environ.get("CODEBASE_CONTEXT_AGENT_ID", "b118d9e1-c3ff-49c3-bb8b-f3c1bb985d2a")
COMPANY_ID = "1021c018-fe0e-4ae8-a972-7487521cc3d9"
SCHEMA_PATH = REPO_ROOT / "docs" / "schemas" / "codebase-context.schema.json"


class NullCtx:
    def step(self, *a, **k): pass
    def report(self, *a, **k): pass
    def timer(self): return StepTimer()


@contextlib.contextmanager
def telemetry_ctx(ov, **kw):
    try:
        with ov.run(**kw) as c:
            yield c
        return
    except OversightError as e:
        log.warning("telemetry degraded (%s)", str(e)[:120])
        yield NullCtx()


def _inventory_json(inv) -> dict:
    return {"parser_version": inv.parser_version, "snapshot_tag": inv.snapshot_tag,
            "entities": inv.entities, "actors": inv.actors, "routes": inv.routes,
            "capabilities": inv.capabilities, "integrations": inv.integrations, "enums": inv.enums}


def _inv_from_cache(ij: dict):
    """Rebuild a resolve/compose-compatible inventory view from cached JSON (no schema_inv/src)."""
    return SimpleNamespace(
        parser_version=ij.get("parser_version"), snapshot_tag=ij.get("snapshot_tag"),
        entities=ij.get("entities", []), actors=ij.get("actors", []), routes=ij.get("routes", []),
        capabilities=ij.get("capabilities", []), integrations=ij.get("integrations", []),
        enums=ij.get("enums", []), schema_inv=None, src=None)


def _supabase():
    url = os.environ["NEXT_PUBLIC_SUPABASE_URL"]; key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return url, {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _post_retry(url, headers, payload, timeout, attempts=4):
    """POST with retry on transient network errors (Supabase resets/timeouts)."""
    last = None
    for i in range(attempts):
        try:
            return requests.post(url, headers=headers, json=payload, timeout=timeout)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


def publish_artifact(output_type: str, content: dict, run_id: str) -> str:
    url, h = _supabase()
    h = {**h, "Prefer": "return=representation"}
    r = _post_retry(f"{url}/rest/v1/agent_outputs", h, {
        "agent_id": AGENT_INSTANCE_ID, "run_id": run_id, "company_id": COMPANY_ID,
        "output_type": output_type, "content": content}, timeout=60)
    if not r.ok:
        raise RuntimeError(f"publish {output_type} failed: {r.status_code} {r.text}")
    d = r.json()
    return (d[0] if isinstance(d, list) else d).get("id", "")


def register_identities(inv, commit_sha: str) -> str:
    """Register deterministic entity/actor/capability cbc ids (idempotent). Registry = 025 types only."""
    url, h = _supabase()
    rows = ([(e["cbc_id"], "entity", e["name"], "drizzle_table") for e in inv.entities]
            + [(a["cbc_id"], "actor", a["name"], "role") for a in inv.actors]
            + [(c["cbc_id"], "capability", c["slug"], "route_group") for c in inv.capabilities])
    ok = 0
    for cid, ctype, name, source in rows:
        r = _post_retry(f"{url}/rest/v1/rpc/cbc_register_or_get", h, {
            "p_cbc_id": cid, "p_cbc_type": ctype, "p_name": name, "p_sha": commit_sha,
            "p_created_by": "reformai.codebase-context-agent", "p_source": source, "p_status": "active"}, timeout=45)
        if r.status_code == 404:
            return "skipped (registry 025 not applied)"
        if r.ok:
            ok += 1
    return f"registered {ok}/{len(rows)} (entity/actor/capability)"


def main():
    p = argparse.ArgumentParser(description="CCA P1 truth-service pipeline")
    p.add_argument("--repo-path", required=True)
    p.add_argument("--target-key", default="reformai-product")
    p.add_argument("--feature-intent", required=True)
    p.add_argument("--concepts-to-check", nargs="*", default=[])
    p.add_argument("--ref", default=None)
    p.add_argument("--semantic", action="store_true", help="run the label-only LLM domain_signals pass")
    p.add_argument("--no-persist", action="store_true")
    p.add_argument("--force", action="store_true", help="bypass the cache and re-extract")
    args = p.parse_args()

    repo = Path(args.repo_path).resolve()
    commit_sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    branch = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
    ref = args.ref or branch
    run_id = str(uuid.uuid4())
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    ov = OversightClient(url=os.environ.get("OVERSIGHT_URL", "https://agent-oversight.vercel.app"),
                         secret=(os.environ.get("AGENT_OVERSIGHT_SECRET") or os.environ.get("OVERSIGHT_SECRET")
                                 or os.environ.get("INGEST_SECRET") or ""))

    with telemetry_ctx(ov, agent_id=AGENT_INSTANCE_ID, run_id=run_id, model="deterministic",
                       provider="none", tokens_in_hint=500, task_type_code="code_gen",
                       task_complexity_bucket="simple") as ctx:
        # --- commit-keyed cache short-circuit: same (commit_sha, parser_version) -> reuse, skip extraction ---
        cached = None
        if not args.force and not args.no_persist:
            try:
                cached = cache_mod.get_cached(args.target_key, args.target_key, commit_sha, inventory_mod.PARSER_VERSION)
            except Exception as e:
                log.warning("cache read failed (%s); extracting fresh", str(e)[:120])

        cache_hit = bool(cached)
        if cached:
            inv = _inv_from_cache(cached["inventory_json"])
            cov = cached["coverage_report_json"]
            cached_semantic = cached.get("semantic_context_json")
            cache_id = cached["id"]
            ctx.step("cache_hit", message=f"reused {cache_id}: {len(inv.entities)} entities, "
                     f"parser {inv.parser_version} (extraction skipped)")
            log.info("CACHE HIT %s - extraction skipped (%d entities)", cache_id, len(inv.entities))
        else:
            with ctx.timer() as t:
                inv = inventory_mod.build_inventory(repo)
            ctx.step("inventory_built", message=f"{len(inv.entities)} entities, {len(inv.actors)} actors, "
                     f"{len(inv.routes)} routes, {len(inv.integrations)} integrations", duration_ms=t.ms)
            cov = coverage_mod.build_coverage(repo, inv.schema_inv, inv.src)
            ctx.step("coverage_built", message=f"coverage={cov['coverage_status']}")
            cached_semantic = None
            cache_id = "(skipped)"
            if not args.no_persist:
                cache_id = cache_mod.put_cache(
                    tenant_id=None, product_key=args.target_key, repo=args.target_key, branch=branch,
                    commit_sha=commit_sha, parser_version=inv.parser_version,
                    inventory_json=_inventory_json(inv), coverage_report_json=cov)
                ctx.step("cache_written", message=f"codebase_context_cache {cache_id}")

        resolution = resolve_mod.resolve_concepts(repo, args.concepts_to_check, inv=inv, cov=cov)

        semantic = cached_semantic
        if args.semantic and not semantic:
            import semantic as semantic_mod  # lazy: only import (and pay LLM) when asked
            with ctx.timer() as t:
                semantic, ti, to, cost = semantic_mod.label(inv, args.feature_intent)
            ctx.report(tokens_in=ti, tokens_out=to, cost_usd=cost)
            ctx.step("semantic_labeled", message=f"{len(semantic.get('domain_signals', []))} signals", duration_ms=t.ms)
            # persist semantic back into the cache row so future runs reuse it (no LLM)
            if not args.no_persist:
                cache_mod.put_cache(tenant_id=None, product_key=args.target_key, repo=args.target_key,
                                    branch=branch, commit_sha=commit_sha, parser_version=inv.parser_version,
                                    inventory_json=_inventory_json(inv), coverage_report_json=cov,
                                    semantic_context_json=semantic)
        elif args.semantic and semantic:
            ctx.step("semantic_cache_hit", message=f"reused cached semantic ({len(semantic.get('domain_signals', []))} signals)")

        cc = compose_mod.compose(inventory=inv, coverage=cov, resolution=resolution, repo=args.target_key,
                                 commit_sha=commit_sha, ref=ref, feature_intent=args.feature_intent,
                                 concepts=args.concepts_to_check, run_id=run_id, semantic=semantic)
        jsonschema.validate(cc, schema)
        ctx.step("composed_validated", message=f"BA codebase_context schema-valid ({len(cc['entities'])} entities)")

        cc_id = cr_id = reg = "(skipped)"
        if not args.no_persist:
            cc_id = publish_artifact("codebase_context", cc, run_id)
            cr_id = publish_artifact("concept_resolution", resolution, run_id)
            # cbc ids are commit-scoped: already registered when the cache row was first written.
            reg = "skipped (cache hit; already registered)" if cache_hit else register_identities(inv, commit_sha)
            ctx.step("published", message=f"codebase_context {cc_id} | concept_resolution {cr_id} | {reg}")

    print(f"\n{'-'*64}")
    print("  CCA P1 truth-service run complete")
    print(f"  Target   : {args.target_key} @ {commit_sha[:14]}  parser {inv.parser_version}")
    print(f"  Inventory: {len(inv.entities)} entities  {len(inv.actors)} actors  "
          f"{len(inv.routes)} routes  {len(inv.capabilities)} caps  {len(inv.integrations)} integ")
    print(f"  Coverage : {cov['coverage_status']}  (" + ", ".join(f"{k}:{v['status']}" for k, v in cov['layers'].items()) + ")")
    print("  Resolved : " + "  ".join(f"{r['concept']}={r['status']}" for r in resolution["resolved_concepts"]))
    print(f"  Cache    : {cache_id}")
    print(f"  Artifact : codebase_context={cc_id}  concept_resolution={cr_id}")
    print(f"  Registry : {reg}")
    print(f"  Run      : {run_id}")
    print(f"{'-'*64}\n")


if __name__ == "__main__":
    main()
