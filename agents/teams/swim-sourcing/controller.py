#!/usr/bin/env python3
"""
Facility Acquisition Controller - deterministic, event-driven.

The controller is a PROCESS, not a job type. It reads goal state, decides by
rule which stage jobs to enqueue, optionally drives the worker until the queue
drains, and prints an objective-progress summary. It makes no LLM calls. It
opens its own run under the controller identity so its decisions are in the
ledger like everything else.

Stage gating is deterministic and reads only database state:

  discover        always, when requested (refresh)
  enrich          facilities exist that have no extracted facts yet
  qualify         facilities exist
  draft_outreach  contact-first facilities exist with no thread yet
  poll_inbox      threads exist with a draft and no reply   (PROTOTYPE: simulated inbox)
  classify_reply  replies exist that have not been classified

Policy evaluation (prototype subset of the decision matrix in
docs/reviews/pool-acquisition-final-design.md, section C):

  saturation      new-unique rate of the last discovery run below 5 percent
  replenishment   contactable-uncontacted below 2 x the daily initial cap
  radius expansion to the pre-authorised 30-mile ceiling is RECOMMENDED when both
                  hold; the prototype records the decision and does not act on it,
                  because discovery is fixture-driven and there is no campaign.

    python agents/teams/swim-sourcing/controller.py --drive                 # all stages
    python agents/teams/swim-sourcing/controller.py --stages discover,enrich --drive
    python agents/teams/swim-sourcing/controller.py --summary               # read-only
"""

from __future__ import annotations

import os
import sys
import json
import uuid
import argparse
import importlib.util as ilu
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-sdk"))
sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(".env.local", usecwd=True), override=True)
except ImportError:
    pass


def _load_worker():
    spec = ilu.spec_from_file_location("swim_worker", HERE / "worker.py")
    mod = ilu.module_from_spec(spec)
    sys.modules["swim_worker"] = mod
    spec.loader.exec_module(mod)
    return mod


W = _load_worker()

DEFAULT_OBJECTIVE = ("Secure one commercially viable, recurring pool partnership for private "
                     "swimming lessons (children eight and under) within 60 days; initial market "
                     "Katy, Texas, 15 miles, expandable to 30.")
STAGES = ["discover", "enrich", "qualify", "draft_outreach", "poll_inbox", "classify_reply"]
PROTOTYPE_SLUG = "cameron-swim-school-prototype"
DAILY_INITIAL_CAP = 8          # pilot value; policy maximum is 15
SATURATION_THRESHOLD = 0.05


def company_id_for(slug: str) -> str:
    rows = W.rest_get("companies", {"slug": f"eq.{slug}", "select": "id,name"})
    if not rows:
        raise SystemExit(f"no company with slug {slug}; run scripts/seed_prototype.py first")
    return rows[0]["id"]


def progress(company_id: str) -> dict:
    return W.rpc("swim_objective_progress", {"p_company_id": company_id}) or {}


def next_actions(company_id: str) -> list:
    return W.rpc("swim_next_actions", {"p_company_id": company_id}) or []


def should_run(stage: str, p: dict, actions: list) -> tuple[bool, str]:
    total = int(p.get("facilities_total") or 0)
    if stage == "discover":
        return True, "refresh requested"
    if stage == "enrich":
        n = total - int(p.get("enriched") or 0)
        return n > 0, f"{n} facilities without extracted facts"
    if stage == "qualify":
        return total > 0, f"{total} facilities to triage"
    if stage == "draft_outreach":
        n = sum(1 for a in actions if a.get("action_type") == "prepare_outreach")
        return n > 0, f"{n} contact-first facilities without a draft"
    if stage == "poll_inbox":
        n = int(p.get("threads") or 0) - int(p.get("replies") or 0)
        return n > 0, f"{n} threads awaiting a (simulated) reply"
    if stage == "classify_reply":
        n = int(p.get("replies") or 0) - int(p.get("classified") or 0)
        return n > 0, f"{n} replies not yet classified"
    return False, "unknown stage"


def evaluate_policies(before: dict, after: dict, discovery_result: dict | None) -> list:
    """Deterministic policy decisions. Returns a list of decision records."""
    decisions = []
    if discovery_result:
        found = int(discovery_result.get("found") or 0)
        inserted = int(discovery_result.get("inserted") or 0)
        rate = (inserted / found) if found else 0.0
        saturated = found > 0 and rate < SATURATION_THRESHOLD
        decisions.append({"rule": "saturation", "new_unique_rate": round(rate, 3),
                          "saturated": saturated, "tier": "T1"})
        contactable_uncontacted = int(after.get("contact_first") or 0) - int(after.get("threads") or 0)
        low = contactable_uncontacted < 2 * DAILY_INITIAL_CAP
        decisions.append({"rule": "replenishment_floor",
                          "contactable_uncontacted": contactable_uncontacted,
                          "floor": 2 * DAILY_INITIAL_CAP, "below_floor": low, "tier": "T1"})
        if saturated and low:
            decisions.append({"rule": "expand_radius", "to_miles": 30, "tier": "T1",
                              "action": "recommended_only_in_prototype",
                              "reason": "market saturated and contactable supply below floor; "
                                        "30 miles is pre-authorised, but discovery is fixture-driven "
                                        "and no campaign exists, so the prototype records rather than acts"})
    return decisions


def print_summary(objective: str, p: dict, actions: list, decisions: list) -> None:
    print("\n=== OBJECTIVE ===")
    print(objective)
    print("\n=== PROGRESS (counts with denominators) ===")
    keys = ["facilities_total", "facilities_fixture", "facilities_live", "enriched", "with_contact",
            "triaged", "contact_first", "research_further", "not_currently_suitable", "disqualified",
            "open_questions_total", "threads", "drafts", "sent", "replies", "classified",
            "escalated", "opted_out", "secured", "target_partnerships"]
    for k in keys:
        print(f"  {k:24s} {p.get(k)}")
    print(f"  {'jobs':24s} {json.dumps(p.get('jobs'))}")
    print("\n=== POLICY DECISIONS ===")
    for d in decisions or [{"rule": "none evaluated (no discovery this run)"}]:
        print("  " + json.dumps(d))
    print("\n=== NEXT ACTIONS (top 12) ===")
    for a in actions[:12]:
        print(f"  [{a.get('priority')}] {a.get('action_type'):22s} {a.get('facility_name')[:44]:44s} {a.get('detail')[:60]}")
    print(f"\n  total next actions: {len(actions)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--company-id", default=os.environ.get("SWIM_COMPANY_ID", ""))
    ap.add_argument("--slug", default=PROTOTYPE_SLUG)
    ap.add_argument("--objective", default=DEFAULT_OBJECTIVE)
    ap.add_argument("--stages", default="all", help="comma list or 'all'")
    ap.add_argument("--drive", action="store_true", help="run the worker in-process after each enqueue")
    ap.add_argument("--summary", action="store_true", help="print progress only; enqueue nothing")
    ap.add_argument("--campaign-id", default="00000000-0000-4000-8000-00000000c0de",
                    help="prototype campaign id (no campaigns table exists yet; nothing is sent)")
    ap.add_argument("--no-fixtures", action="store_true", help="require a live Places key for discovery")
    ap.add_argument("--draft-limit", type=int, default=DAILY_INITIAL_CAP)
    args = ap.parse_args()

    company_id = args.company_id or company_id_for(args.slug)
    stages = STAGES if args.stages == "all" else [s.strip() for s in args.stages.split(",") if s.strip()]

    if args.summary:
        p = progress(company_id)
        print_summary(args.objective, p, next_actions(company_id), [])
        return 0

    W.CRED.scrub_platform_provider_env()
    controller = W.resolve_agent(company_id, "facility-acquisition-controller")
    run_id = str(uuid.uuid4())
    decisions: list = []
    discovery_result = None

    with W.oversight().run(agent_id=controller["id"], run_id=run_id,
                           metadata={"objective": args.objective, "stages": stages,
                                     "company_id": company_id, "prototype": True}) as ctx:
        before = progress(company_id)
        ctx.step("goal_state_read", payload={k: before.get(k) for k in
                                             ("facilities_total", "enriched", "contact_first",
                                              "threads", "replies", "classified")})
        for stage in stages:
            p = progress(company_id)
            actions = next_actions(company_id)
            run, why = should_run(stage, p, actions)
            if not run:
                print(f"[controller] skip {stage}: {why}")
                ctx.step(f"skip_{stage}", message=why)
                continue
            payload: dict = {}
            if stage == "discover":
                payload = {"use_fixtures": not args.no_fixtures, "radius_miles": 15, "max_requests": 8}
            elif stage == "draft_outreach":
                payload = {"limit": args.draft_limit, "campaign_id": args.campaign_id}
            job_id = W.rpc("swim_enqueue_job", {"p_company_id": company_id, "p_job_type": stage,
                                                "p_payload": payload})
            print(f"[controller] enqueued {stage} ({why}) -> job {job_id}")
            ctx.step(f"enqueue_{stage}", message=why, payload={"job_id": job_id, "payload": payload})
            if args.drive:
                n = W.drain()
                print(f"[controller] drove {n} job(s)")
                if stage == "discover":
                    # Read the discovery result back (via the run ledger) for the saturation rule.
                    discovery_result = _last_job_result(company_id, "discover")

        after = progress(company_id)
        decisions = evaluate_policies(before, after, discovery_result)
        actions = next_actions(company_id)
        ctx.step("policy_evaluation", payload={"decisions": decisions})
        ctx.report(tokens_in=0, tokens_out=0, cost_usd=0.0,
                   metadata={"outcome": "done", "progress": after, "decisions": decisions,
                             "next_actions": len(actions), "prototype": True})
        print_summary(args.objective, after, actions, decisions)
    return 0


def _last_job_result(company_id: str, job_type: str) -> dict | None:
    """The worker reports each job's summary on its run_completed metadata;
    PostgREST cannot read swim_sourcing.jobs directly, so read it from the ledger."""
    rows = W.rest_get("runs", {"select": "metadata,started_at,agents!inner(company_id)",
                               "agents.company_id": f"eq.{company_id}",
                               "order": "started_at.desc", "limit": "20"})
    for r in rows or []:
        md = r.get("metadata") or {}
        if md.get("job_type") == job_type:
            s = md.get("summary") or {}
            if "found" in s:
                return s
    return None


if __name__ == "__main__":
    sys.exit(main())
