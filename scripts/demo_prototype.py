#!/usr/bin/env python3
"""
Drive the pool-acquisition PROTOTYPE end to end and print each checkpoint.

What this exercises, for real: the durable queue, three registered identities
in one worker, preflight (kill switch, budget, tenant credential), real LLM
calls for enrichment / drafting / classification, the evidence rule, the
anti-fabrication gate, deterministic escalation, telemetry to Agent Oversight,
and the dashboard reads. What is simulated, and labelled as such: Google Places
(recorded fixtures, source='fixture') and inbound mail ([SIMULATED] subjects).
Nothing is sent.

    python scripts/demo_prototype.py                 # full run with a fresh campaign id
    python scripts/demo_prototype.py --pause-demo    # also prove the per-identity kill switch
    python scripts/demo_prototype.py --dry-run       # print the sequence only

Prerequisites: scripts/seed_prototype.py has been run; .env.local carries
OVERSIGHT_URL, AGENT_OVERSIGHT_SECRET, CREDENTIAL_ENCRYPTION_KEY, SUPABASE_*.
"""

from __future__ import annotations

import os
import sys
import json
import uuid
import argparse
import subprocess
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv, find_dotenv  # noqa: E402
load_dotenv(find_dotenv(".env.local", usecwd=True), override=True)

sys.stdout.reconfigure(line_buffering=True)   # keep banners in order with subprocess output
PY = sys.executable
CONTROLLER = REPO / "agents" / "teams" / "swim-sourcing" / "controller.py"
WORKER = REPO / "agents" / "teams" / "swim-sourcing" / "worker.py"
SLUG = "cameron-swim-school-prototype"
OVERSIGHT_URL = os.environ.get("OVERSIGHT_URL", "https://agent-oversight.vercel.app").rstrip("/")


def _sb(method: str, path: str, body: dict | None = None):
    url = os.environ["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    req = urllib.request.Request(f"{url}/rest/v1/{path}",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"apikey": key, "Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json",
                                          "Prefer": "return=representation"},
                                 method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else None


def company_id() -> str:
    rows = _sb("GET", f"companies?slug=eq.{SLUG}&select=id")
    if not rows:
        raise SystemExit("prototype company missing - run scripts/seed_prototype.py first")
    return rows[0]["id"]


def banner(title: str) -> None:
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def run(cmd: list, dry: bool) -> int:
    print("$ " + " ".join(str(c) for c in cmd))
    if dry:
        return 0
    return subprocess.call([str(c) for c in cmd], cwd=str(REPO))


def pause_demo(cid: str, dry: bool) -> None:
    banner("CHECKPOINT: independent kill switch (pause the coordinator, research keeps running)")
    coord = _sb("GET", f"agents?company_id=eq.{cid}&name=eq.swimschool.partnership-coordinator&select=id,status")[0]
    if dry:
        print("(dry run) would pause the coordinator, enqueue a draft job and a qualify job, drain, un-pause")
        return
    _sb("PATCH", f"agents?id=eq.{coord['id']}", {"status": "paused", "paused_reason": "demo: kill switch"})
    print("[demo] coordinator paused")
    _sb("POST", "rpc/swim_enqueue_job", {"p_company_id": cid, "p_job_type": "draft_outreach",
                                          "p_payload": {"limit": 1, "campaign_id": str(uuid.uuid4())}})
    _sb("POST", "rpc/swim_enqueue_job", {"p_company_id": cid, "p_job_type": "qualify", "p_payload": {}})
    run([PY, WORKER, "--drain"], dry)
    _sb("PATCH", f"agents?id=eq.{coord['id']}", {"status": "active", "paused_at": None, "paused_reason": None})
    print("[demo] coordinator re-activated. Expected above: draft_outreach BLOCKED [agent_paused], qualify done.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pause-demo", action="store_true")
    ap.add_argument("--only-pause", action="store_true", help="run just the kill-switch demonstration")
    ap.add_argument("--campaign-id", default=None, help="defaults to a fresh uuid per demo run")
    args = ap.parse_args()
    dry = args.dry_run

    cid = company_id() if not dry else "<company-id>"
    campaign = args.campaign_id or str(uuid.uuid4())

    if args.only_pause:
        pause_demo(cid, dry)
        return 0

    banner("PROTOTYPE DEMO - pool acquisition")
    print(f"company: {cid}\ncampaign (prototype id, no campaigns table yet, nothing is sent): {campaign}")
    print("fixtures: facilities from recorded Places responses (source='fixture'); replies scripted ([SIMULATED])")
    print("re-runs are idempotent: discovery dedups on place id, and a facility already drafted is never drafted again")

    banner("CHECKPOINT 1 + 2: controller -> discover (dedup) -> enrich -> triage")
    rc = run([PY, CONTROLLER, "--company-id", cid, "--stages", "discover,enrich,qualify", "--drive"], dry)
    if rc:
        return rc

    banner("CHECKPOINT 3: drafts -> simulated replies -> classification -> next actions")
    rc = run([PY, CONTROLLER, "--company-id", cid, "--stages", "draft_outreach,poll_inbox,classify_reply",
              "--drive", "--campaign-id", campaign], dry)
    if rc:
        return rc

    if args.pause_demo:
        pause_demo(cid, dry)

    banner("WHERE TO LOOK")
    print(f"dashboard : {OVERSIGHT_URL}/dashboard/sourcing?company={cid}")
    print(f"runs      : {OVERSIGHT_URL}/dashboard/runs")
    print(f"costs     : {OVERSIGHT_URL}/dashboard/costs")
    print("status    : python scripts/seed_prototype.py --status")
    print("teardown  : python scripts/seed_prototype.py --teardown")
    return 0


if __name__ == "__main__":
    sys.exit(main())
