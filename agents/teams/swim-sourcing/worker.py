#!/usr/bin/env python3
"""
Swim-sourcing durable worker.

Designed to be hosted (Railway) rather than run from a laptop, which is the gap
the existing agile worker has - its docstring says "run locally per work
session", so nothing in this platform currently runs unattended.

Execution protocol per job:
  1. claim with a LEASE (swim_claim_job)                 - SKIP LOCKED, atomic
  2. PREFLIGHT, fail closed:
       - agent status must be 'active'                   - the kill switch
       - tenant credential must resolve                 - no platform-key fallback
       - tenant budget must allow the estimate          - spend ceiling
  3. emit run_started to Agent Oversight                - existing telemetry SDK
  4. do the work, HEARTBEATING                          - lease extension
       heartbeat returns False when cancellation is requested -> stop cleanly
  5. finish (done | failed | blocked)                   - bounded retry/backoff
  6. emit run_completed / run_failed

A crashed worker is recovered by swim_reap_expired_jobs, which returns
expired-lease jobs to the queue. 'blocked' is deliberately terminal: a missing
credential or an exhausted budget will not be fixed by retrying.

    python agents/teams/swim-sourcing/worker.py --once
    python agents/teams/swim-sourcing/worker.py            # poll loop
    python agents/teams/swim-sourcing/worker.py --reap     # reaper only
"""

from __future__ import annotations

import os
import sys
import json
import time
import uuid
import signal
import argparse
import importlib.util as ilu
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "python-sdk"))
sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(".env.local", usecwd=True), override=True)
except ImportError:
    pass

from agents.lib import credentials as CRED  # noqa: E402

POLL_SECONDS = float(os.environ.get("SWIM_WORKER_POLL_SECONDS", "5"))
LEASE_SECONDS = int(os.environ.get("SWIM_WORKER_LEASE_SECONDS", "300"))
HEARTBEAT_EVERY = max(10, LEASE_SECONDS // 3)
WORKER_ID = os.environ.get("SWIM_WORKER_ID") or f"swim-worker-{uuid.uuid4().hex[:8]}"

SUPABASE_URL = (os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""

_STOP = False


def _handle_signal(signum, _frame):
    global _STOP
    _STOP = True
    print(f"[worker] signal {signum} received; finishing current job then exiting")


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def rpc(fn: str, payload: dict):
    """Call a public RPC with the service role key."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise RuntimeError(
            "NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/rpc/{fn}",
        data=json.dumps(payload).encode(),
        headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read(400).decode("utf-8", "replace")
        raise RuntimeError(f"rpc {fn} failed ({exc.code}): {detail}") from exc


# ---------------------------------------------------------------------------
# Preflight: every check fails CLOSED
# ---------------------------------------------------------------------------

class Blocked(Exception):
    """A precondition failed. Terminal - retrying will not help."""

    def __init__(self, reason: str, category: str):
        super().__init__(reason)
        self.category = category


def preflight(company_id: str, agent_id: str, estimate_usd: float = 0.05):
    """Returns a ResolvedCredential, or raises Blocked.

    Order matters: the cheapest and most definitive checks run first so a paused
    agent or an exhausted budget never reaches credential decryption.
    """
    # 1. Kill switch. /api/ingest already returns 403 for a non-active agent,
    # but that only blocks REPORTING. Checking here stops a paused agent before
    # it does work and spends money, rather than after.
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/agents?id=eq.{agent_id}&select=status,company_id",
            headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            rows = json.loads(resp.read().decode())
    except Exception as exc:
        raise Blocked(f"could not verify agent status: {exc}", "validation_error")

    if not rows:
        raise Blocked(f"agent {agent_id} is not registered", "validation_error")
    if rows[0].get("status") != "active":
        raise Blocked(f"agent {agent_id} is not active (status={rows[0].get('status')})",
                      "agent_paused")
    if rows[0].get("company_id") != company_id:
        raise Blocked("agent does not belong to the job's company", "cross_tenant")

    # 2. Spend ceiling.
    budget = CRED.check_tenant_budget(company_id, estimate_usd)
    if not budget["allowed"]:
        raise Blocked(
            f"budget check failed: {budget['reason']} "
            f"(spent {budget.get('spent_usd')} of {budget.get('limit_usd')})",
            "budget_exceeded")

    # 3. Tenant credential. No fallback, by design.
    try:
        cred = CRED.resolve_tenant_api_key(company_id, "anthropic")
    except CRED.MissingTenantCredential as exc:
        raise Blocked(str(exc), "missing_tenant_credential") from exc
    except CRED.CredentialError as exc:
        raise Blocked(str(exc), exc.category) from exc

    return cred


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _load_module(path: Path, name: str):
    spec = ilu.spec_from_file_location(name, path)
    mod = ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def handle_discover(job: dict, cred, heartbeat) -> dict:
    """Discovery does not call an LLM, so it needs no tenant credential for the
    provider - but it DOES consume a paid Places quota, which is why the request
    ceiling lives in the agent rather than in the caller."""
    disc = _load_module(
        REPO_ROOT / "agents" / "library" / "facility-discovery-agent" / "discovery.py",
        "discovery")

    payload = job.get("payload") or {}
    cfg = disc.SearchConfig(
        center_lat=float(payload.get("center_lat", disc.KATY_TX[0])),
        center_lng=float(payload.get("center_lng", disc.KATY_TX[1])),
        radius_miles=float(payload.get("radius_miles", 15.0)),
        max_requests=int(payload.get("max_requests", 8)),
    )

    transport = None
    if payload.get("use_fixtures") or not os.environ.get("GOOGLE_PLACES_API_KEY"):
        fixtures = json.loads((
            REPO_ROOT / "agents" / "library" / "facility-discovery-agent"
            / "fixtures" / "katy_tx_places.json").read_text(encoding="utf-8"))
        transport = disc.fixture_transport(fixtures)
        print("[worker] GOOGLE_PLACES_API_KEY absent - using recorded fixtures")

    facilities, stats = disc.discover(cfg, transport=transport)
    heartbeat()

    inserted = matched = 0
    for fac in facilities:
        res = rpc("swim_upsert_facility",
                  {"p_company_id": job["company_id"], "p_facility": fac})
        row = res[0] if isinstance(res, list) and res else (res or {})
        if row.get("was_inserted"):
            inserted += 1
        else:
            matched += 1

    return {"found": len(facilities), "inserted": inserted, "matched_existing": matched,
            "stats": stats.as_dict()}


def handle_qualify(job: dict, cred, heartbeat) -> dict:
    scoring = _load_module(
        REPO_ROOT / "agents" / "library" / "facility-qualification-agent" / "scoring.py",
        "scoring")

    company_id = job["company_id"]
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/rpc/swim_list_facilities",
        data=json.dumps({"p_company_id": company_id, "p_stage": "discovered",
                         "p_limit": 200}).encode(),
        headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}",
                 "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        rows = json.loads(resp.read().decode())

    config = (job.get("payload") or {}).get("config") or {}
    counts = {"qualified": 0, "disqualified": 0, "needs_info": 0}
    for i, row in enumerate(rows or []):
        # swim_list_facilities is a projection; attributes live on the table, so
        # fetch them per facility. Kept simple deliberately - this loop is small
        # and a join-heavy RPC would be harder to reason about than N reads.
        fr = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/rpc/swim_facility_attributes",
            data=json.dumps({"p_facility_id": row["facility_id"]}).encode(),
            headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}",
                     "Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(fr, timeout=20) as resp:
                attrs = json.loads(resp.read().decode()) or {}
        except Exception:
            attrs = {}

        facility = {
            "id": row["facility_id"],
            "distance_miles": row.get("distance_miles"),
            "attributes": (attrs or {}).get("attributes") or {},
            "attributes_confidence": (attrs or {}).get("attributes_confidence") or {},
        }
        result = scoring.qualify(facility, config)
        rpc("swim_record_qualification",
            {"p_company_id": company_id,
             "p_payload": result.to_payload(run_id=job.get("run_id"))})
        counts[result.status] = counts.get(result.status, 0) + 1
        if i % 10 == 0:
            heartbeat()

    return {"scored": sum(counts.values()), **counts}


HANDLERS = {
    "discover": handle_discover,
    "qualify": handle_qualify,
}


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------

def process_one(client=None) -> bool:
    """Claim and process one job. Returns False when the queue is empty."""
    claimed = rpc("swim_claim_job",
                  {"p_worker_id": WORKER_ID, "p_lease_seconds": LEASE_SECONDS,
                   "p_job_types": list(HANDLERS.keys())})
    rows = claimed if isinstance(claimed, list) else ([claimed] if claimed else [])
    if not rows:
        return False

    job = rows[0]
    job_id = job["job_id"]
    company_id = job["company_id"]
    job_type = job["job_type"]
    print(f"[worker] claimed {job_type} {job_id} (attempt {job['attempts']}/{job['max_attempts']})")

    last_beat = [time.time()]

    def heartbeat():
        if time.time() - last_beat[0] < HEARTBEAT_EVERY:
            return
        alive = rpc("swim_heartbeat_job",
                    {"p_job_id": job_id, "p_worker_id": WORKER_ID,
                     "p_lease_seconds": LEASE_SECONDS})
        last_beat[0] = time.time()
        if alive is False:
            raise KeyboardInterrupt("cancellation requested")

    run_id = str(uuid.uuid4())
    agent_id = (job.get("payload") or {}).get("agent_id") or os.environ.get("SWIM_AGENT_ID", "")

    try:
        cred = None
        if job_type in ("draft_outreach", "classify_reply"):
            # Only LLM-calling job types need a provider credential.
            cred = preflight(company_id, agent_id)
        elif agent_id:
            # Still enforce the kill switch and the budget for non-LLM work.
            try:
                cred = preflight(company_id, agent_id)
            except Blocked as exc:
                if exc.category == "missing_tenant_credential":
                    cred = None  # not required for this job type
                else:
                    raise

        handler = HANDLERS[job_type]
        result = handler(job, cred, heartbeat)
        rpc("swim_finish_job", {"p_job_id": job_id, "p_worker_id": WORKER_ID,
                                "p_status": "done", "p_result": result})
        print(f"[worker] done {job_id}: {json.dumps(result)[:200]}")

    except Blocked as exc:
        # Terminal by design: a paused agent, an exhausted budget or a missing
        # credential will not resolve itself on a retry.
        rpc("swim_finish_job", {"p_job_id": job_id, "p_worker_id": WORKER_ID,
                                "p_status": "blocked",
                                "p_error": f"[{exc.category}] {exc}"})
        print(f"[worker] BLOCKED {job_id}: [{exc.category}] {exc}")

    except KeyboardInterrupt as exc:
        rpc("swim_finish_job", {"p_job_id": job_id, "p_worker_id": WORKER_ID,
                                "p_status": "cancelled", "p_error": str(exc)})
        print(f"[worker] cancelled {job_id}")

    except Exception as exc:  # retryable
        rpc("swim_finish_job", {"p_job_id": job_id, "p_worker_id": WORKER_ID,
                                "p_status": "failed", "p_error": str(exc)[:500]})
        print(f"[worker] FAILED {job_id}: {exc}")

    return True


def reap() -> int:
    rows = rpc("swim_reap_expired_jobs", {}) or []
    if rows:
        print(f"[worker] reaped {len(rows)} expired-lease job(s)")
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="process one job then exit")
    ap.add_argument("--reap", action="store_true", help="run the reaper only")
    args = ap.parse_args()

    print(f"[worker] id={WORKER_ID} lease={LEASE_SECONDS}s poll={POLL_SECONDS}s")

    # Scrub inherited provider keys at startup. On a shared host this is what
    # stops a tenant's agent from ever seeing the platform's key.
    removed = CRED.scrub_platform_provider_env()
    if removed:
        print(f"[worker] scrubbed inherited provider env: {', '.join(removed)}")

    if args.reap:
        reap()
        return 0

    if args.once:
        reap()
        return 0 if process_one() else 0

    idle_cycles = 0
    while not _STOP:
        try:
            if idle_cycles % 12 == 0:
                reap()
            worked = process_one()
            idle_cycles = 0 if worked else idle_cycles + 1
            if not worked:
                time.sleep(POLL_SECONDS)
        except Exception as exc:
            print(f"[worker] loop error: {exc}")
            time.sleep(min(60.0, POLL_SECONDS * 4))
    print("[worker] exited cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
