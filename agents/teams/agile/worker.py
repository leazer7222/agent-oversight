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

POLL_SECONDS = float(os.environ.get("AGILE_WORKER_POLL_SECONDS", "5"))
MODEL = os.environ.get("PCA_MODEL", "claude-sonnet-4-6")
_STATUS = {"proceed_direct": "done", "clarify": "clarify", "block": "blocked"}


def _load_pca():
    spec = ilu.spec_from_file_location(
        "pca_agent", REPO_ROOT / "agents/library/product-clarification-agent/agent.py")
    mod = ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pca = _load_pca()


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


def process(job: dict) -> None:
    jid = job["id"]
    print(f"[run]  job {jid[:8]} pass={job['pass']} product={job['product_key']} "
          f"sources={len(job.get('intake') or [])}")
    grounding = pca.load_grounding(job["workspace_id"])
    entries = [f"{s['source_type']}:{s['text']}" for s in (job.get("intake") or [])]
    sources, sources_text = pca.build_sources(entries, None)
    result = pca.run_intake(
        sources=sources, sources_text=sources_text, product_key=job["product_key"],
        tenant=job["company_id"], workspace_id=job["workspace_id"], grounding=grounding,
        model=MODEL, pass_=job["pass"], answers=job.get("answers"), no_persist=False)
    patch_job(jid, {
        "status": _STATUS.get(result["decision"], "error"),
        "decision": result["decision"], "assessment_id": result.get("assessment_id"),
        "brief_id": result.get("brief_id"), "pca_run_id": result.get("run_id"),
        "finished_at": _now()})
    print(f"[done] job {jid[:8]} decision={result['decision']} "
          f"assessment={result.get('assessment_id')} brief={result.get('brief_id')}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    once = "--once" in sys.argv
    stop = {"v": False}
    try:
        signal.signal(signal.SIGINT, lambda *a: stop.__setitem__("v", True))
    except Exception:
        pass

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
            process(job)
        except Exception as e:
            patch_job(job["id"], {"status": "error", "error": str(e)[:500], "finished_at": _now()})
            print(f"[error] job {job['id'][:8]}: {str(e)[:180]}", file=sys.stderr)
        if once:
            break
    print("worker stopped.")


if __name__ == "__main__":
    main()
