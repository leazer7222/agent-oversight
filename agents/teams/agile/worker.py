#!/usr/bin/env python3
"""
Agile intake worker (Phase 1b execution mechanism).

Polls public.agile_intake_jobs for queued jobs, runs the PCA intake pipeline
(pca.run_intake), and writes result pointers back. Supabase is the bus between the
dashboard (which ENQUEUES jobs) and this worker (which EXECUTES them).

Run locally per work session:
    python agents/teams/agile/worker.py            # poll loop (Ctrl-C to stop)
    python agents/teams/agile/worker.py --once     # claim+process one job, then exit (testing)

Same artifact contracts as the CLI path - only the trigger differs. To move to a hosted
worker later, run this exact script on a server/cron; no other change.
"""

import os
import sys
import time
import uuid
import signal
import importlib.util as ilu
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "python-sdk"))

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(".env.local", usecwd=True), override=True)
except ImportError:
    pass
for _k in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS"):
    if os.environ.get(_k, None) == "":
        os.environ.pop(_k, None)

import requests  # noqa: E402
from oversight import OversightClient  # noqa: E402

POLL_SECONDS = float(os.environ.get("AGILE_WORKER_POLL_SECONDS", "5"))
MODEL = os.environ.get("PCA_MODEL", "claude-sonnet-4-6")
# The worker is the orchestrator's execution arm: it emits an orchestrator run per job under the
# agile-team-orchestrator identity and threads parent_run_id into the PCA child run (same as run.py).
ORCH_AGENT_ID = os.environ.get("AGILE_ORCHESTRATOR_AGENT_ID", "b2c3d4e5-f6a7-8901-bcde-f12345678901")
_STATUS = {"proceed_direct": "done", "clarify": "clarify", "block": "blocked"}
_NEXT_STATE = {"proceed_direct": "context_scanning", "clarify": "clarification_blocked",
               "block": "clarification_blocked"}


def _load(alias: str, rel: str):
    spec = ilu.spec_from_file_location(alias, REPO_ROOT / rel)
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pca = _load("pca_agent", "agents/library/product-clarification-agent/agent.py")
ba = _load("ba_agent", "agents/library/ba-scoping-agent/agent.py")


def _sb():
    url = os.environ["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return url, {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def claim_job():
    url, h = _sb()
    r = requests.post(f"{url}/rest/v1/rpc/claim_intake_job", headers=h, json={"p_worker": "local"}, timeout=20)
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def patch_job(job_id: str, fields: dict) -> None:
    url, h = _sb()
    fields["updated_at"] = _now()
    r = requests.patch(f"{url}/rest/v1/agile_intake_jobs?id=eq.{job_id}",
                       headers={**h, "Prefer": "return=minimal"}, json=fields, timeout=20)
    if not r.ok:
        print(f"[warn] patch job {job_id[:8]} failed: {r.status_code} {r.text}", file=sys.stderr)


def _client() -> OversightClient:
    return OversightClient(
        url=os.environ.get("OVERSIGHT_URL", "https://agent-oversight.vercel.app"),
        secret=(os.environ.get("AGENT_OVERSIGHT_SECRET") or os.environ.get("OVERSIGHT_SECRET")
                or os.environ.get("INGEST_SECRET") or ""))


def _emit(client: OversightClient, **kw) -> None:
    try:
        client.emit(**kw)
    except Exception as e:  # telemetry must never break the worker
        print(f"[warn] worker telemetry: {str(e)[:120]}", file=sys.stderr)


# Sonnet is reliable + cheap for the auto-chain scoping step; override with AGILE_BA_MODEL.
BA_MODEL = os.environ.get("AGILE_BA_MODEL", "claude-sonnet-4-6")


def process(job: dict, client: OversightClient) -> None:
    """One orchestrator run per job. PCA (clarifying) -> on proceed_direct auto-chain to BA
    (scoping) reusing the latest codebase_context -> park at scope_review (Gate A). PCA child
    and BA child both link to this orchestrator run via parent_run_id."""
    jid = job["id"]
    orch_run_id = str(uuid.uuid4())
    _emit(client, agent_id=ORCH_AGENT_ID, event="run_started", run_id=orch_run_id, team_id="agile",
          metadata={"stage": "clarifying", "trigger": "worker", "job_id": jid,
                    "product_key": job["product_key"], "workspace_id": job["workspace_id"], "pass": job["pass"]})
    print(f"[run]  job {jid[:8]} pass={job['pass']} product={job['product_key']} "
          f"sources={len(job.get('intake') or [])}  orch_run={orch_run_id[:8]}")

    # ---- Stage 1: clarifying (PCA) ----
    try:
        grounding = pca.load_grounding(job["workspace_id"])
        entries = [f"{s['source_type']}:{s['text']}" for s in (job.get("intake") or [])]
        sources, sources_text = pca.build_sources(entries, None)
        result = pca.run_intake(
            sources=sources, sources_text=sources_text, product_key=job["product_key"],
            tenant=job["company_id"], workspace_id=job["workspace_id"], grounding=grounding,
            model=MODEL, pass_=job["pass"], answers=job.get("answers"), no_persist=False,
            parent_run_id=orch_run_id)
    except Exception as exc:
        _emit(client, agent_id=ORCH_AGENT_ID, event="run_failed", run_id=orch_run_id,
              error=f"[worker_error] pca: {exc}", metadata={"team_id": "agile", "stage": "clarifying", "job_id": jid})
        raise

    decision = result["decision"]
    patch_job(jid, {"decision": decision, "assessment_id": result.get("assessment_id"),
                    "brief_id": result.get("brief_id"), "pca_run_id": result.get("run_id"), "stage": "clarifying"})

    # clarify / block -> stop at the clarifying stage (no BA)
    if decision != "proceed_direct":
        patch_job(jid, {"status": _STATUS.get(decision, "error"), "finished_at": _now()})
        _emit(client, agent_id=ORCH_AGENT_ID, event="run_completed", run_id=orch_run_id,
              metadata={"team_id": "agile", "stage": "clarifying", "job_id": jid, "decision": decision,
                        "next_state": _NEXT_STATE.get(decision),
                        "intake_assessment_artifact_id": result.get("assessment_id"),
                        "clarification_brief_artifact_id": result.get("brief_id"),
                        "pca_run_id": result.get("run_id")})
        print(f"[done] job {jid[:8]} decision={decision} (no BA)")
        return

    # ---- Stage 2: scoping (BA), auto-chained. Reuses the latest codebase_context. ----
    handoff = result.get("handoff") or {}
    feature_intent = handoff.get("feature_intent") or (result.get("brief") or {}).get("restated_goal") or ""
    patch_job(jid, {"status": "scoping", "stage": "scoping"})
    print(f"[scope] job {jid[:8]} -> BA scoping (reusing codebase_context)...")
    try:
        ba_res = ba.scope_feature(
            feature_intent=feature_intent, product_key=job["product_key"], tenant=job["company_id"],
            model=BA_MODEL, clarification_artifact_id=result.get("brief_id"), parent_run_id=orch_run_id)
    except Exception as exc:
        msg = f"BA scoping failed ({type(exc).__name__}): {str(exc)[:300]}"
        patch_job(jid, {"status": "error", "stage": "scoping", "error": msg, "finished_at": _now()})
        _emit(client, agent_id=ORCH_AGENT_ID, event="run_failed", run_id=orch_run_id,
              error=f"[worker_error] {msg}", metadata={"team_id": "agile", "stage": "scoping", "job_id": jid})
        print(f"[error] job {jid[:8]} {msg}", file=sys.stderr)
        return  # handled here; don't let main() overwrite the error

    scope_artifact = ba_res.get("artifact_id")
    patch_job(jid, {"status": "scoped", "stage": "scope_review", "feature_key": ba_res["feature_key"],
                    "scope_artifact_id": scope_artifact if scope_artifact and scope_artifact != "(skipped)" else None,
                    "scope_ready": ba_res["scope_ready"], "finished_at": _now()})
    _emit(client, agent_id=ORCH_AGENT_ID, event="run_completed", run_id=orch_run_id,
          metadata={"team_id": "agile", "stage": "scope_review", "job_id": jid, "decision": decision,
                    "next_state": "scope_review", "feature_key": ba_res["feature_key"],
                    "scope_ready": ba_res["scope_ready"],
                    "clarification_brief_artifact_id": result.get("brief_id"),
                    "product_graph_scope_artifact_id": scope_artifact,
                    "pca_run_id": result.get("run_id"), "ba_run_id": ba_res.get("run_id")})
    print(f"[done] job {jid[:8]} scoped -> {ba_res['feature_key']} "
          f"(scope_ready={ba_res['scope_ready']}, {ba_res['n_questions']} questions)")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    once = "--once" in sys.argv
    stop = {"v": False}
    try:
        signal.signal(signal.SIGINT, lambda *a: stop.__setitem__("v", True))
    except Exception:
        pass

    client = _client()
    print(f"agile worker online (model={MODEL}, poll={POLL_SECONDS}s){' [--once]' if once else ''}. "
          "Ctrl-C to stop.")
    while not stop["v"]:
        try:
            job = claim_job()
        except Exception as e:
            print(f"[warn] claim failed: {str(e)[:140]}", file=sys.stderr)
            if once:
                break
            time.sleep(POLL_SECONDS)
            continue
        if not job:
            if once:
                print("no queued jobs.")
                break
            time.sleep(POLL_SECONDS)
            continue
        try:
            process(job, client)
        except Exception as e:
            patch_job(job["id"], {"status": "error", "error": str(e)[:500], "finished_at": _now()})
            print(f"[error] job {job['id'][:8]}: {str(e)[:180]}", file=sys.stderr)
        if once:
            break
    print("worker stopped.")


if __name__ == "__main__":
    main()
