#!/usr/bin/env python3
"""
Seed (or inspect, or tear down) the pool-acquisition PROTOTYPE tenant.

Idempotent: re-running changes nothing that already exists. Everything it
creates is unmistakably labelled PROTOTYPE so it can never be confused with a
real business tenant, and everything hangs off ONE company_id so cleanup is
"find the company, act on its rows".

Creates, if absent:
  public.companies            Cameron Swim School (PROTOTYPE), cost_limit_usd = 5.00
  public.projects             facility-sourcing-prototype
  public.agent_definitions    facility-acquisition-controller / facility-researcher /
                              partnership-coordinator  (tenant-neutral library rows)
  public.agents               swimschool.facility-acquisition-controller (orchestrator)
                              swimschool.facility-researcher               (worker, child)
                              swimschool.partnership-coordinator           (worker, child)
                              all status='active' so /api/ingest accepts their telemetry
  platform.tenant_provider_credentials
                              ONE 'anthropic' credential for the prototype company,
                              encrypted with CREDENTIAL_ENCRYPTION_KEY via
                              agents/lib/credentials.encrypt_api_key().

BILLING DISCLOSURE: by instruction, the credential stored is the PLATFORM
ANTHROPIC_API_KEY from .env.local, so prototype LLM spend bills to the platform
account. Replace it with the business's own key before any real campaign.
The row is labelled accordingly.

    python scripts/seed_prototype.py            # create / confirm
    python scripts/seed_prototype.py --status   # print ids and counts, change nothing
    python scripts/seed_prototype.py --teardown # pause agents, cancel queued jobs

Teardown note: swim_sourcing.outreach_messages is append-only by trigger and
approvals are immutable, so prototype correspondence is not deleted - it is
isolated by company_id and the agents are paused. That is the designed
behaviour of the ledger, not an omission.
"""

from __future__ import annotations

import os
import sys
import json
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv, find_dotenv  # noqa: E402
load_dotenv(find_dotenv(".env.local", usecwd=True), override=True)

import psycopg  # noqa: E402
from agents.lib import credentials as CRED  # noqa: E402

TENANT_PREFIX = os.environ.get("SWIM_TENANT_PREFIX", "swimschool")

COMPANY = {
    "name": "Cameron Swim School (PROTOTYPE)",
    "slug": "cameron-swim-school-prototype",
    "description": (
        "PROTOTYPE tenant for the pool-acquisition demonstration (2026-10-20). "
        "All facilities are recorded fixtures, all inbound mail is simulated, "
        "nothing is sent. Safe to pause or ignore; see scripts/seed_prototype.py."
    ),
    "cost_limit_usd": 5.00,
    "cost_limit_period": "monthly",
}
PROJECT = {"name": "facility-sourcing-prototype",
           "description": "PROTOTYPE: pool facility discovery, research, drafting, simulated replies"}

DEFINITIONS = [
    ("facility-acquisition-controller", "Facility Acquisition Controller",
     "Deterministic, event-driven controller: reads goal state, enqueues stage jobs, "
     "prints objective progress. Makes no LLM calls in the prototype.",
     ["controller", "scheduling", "policy"], None),
    ("facility-researcher", "Facility Researcher",
     "Discovery (Places or labelled fixtures), evidence-bound enrichment, deterministic "
     "triage and prioritisation. Never invents a facility, fact or contact.",
     ["discovery", "enrichment", "qualification"], "claude-haiku-5-5"),
    ("partnership-coordinator", "Partnership Coordinator",
     "Templated outreach drafts with one LLM-written sentence behind an anti-fabrication "
     "gate; inbound classification into proposals; deterministic escalation. Holds no "
     "send capability.",
     ["outreach", "classification", "escalation"], "claude-sonnet-5-5"),
]


def _conn():
    url = os.environ.get("SUPABASE_DB_URL", "")
    if not url:
        print("[seed] SUPABASE_DB_URL is not set")
        sys.exit(3)
    return psycopg.connect(url, autocommit=False)


def _one(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchone()


def ensure_company(cur) -> str:
    row = _one(cur, "select id from public.companies where slug = %s", (COMPANY["slug"],))
    if row:
        cur.execute("update public.companies set cost_limit_usd = %s, cost_limit_period = %s "
                    "where id = %s and (cost_limit_usd is null or cost_limit_period is null)",
                    (COMPANY["cost_limit_usd"], COMPANY["cost_limit_period"], row[0]))
        return str(row[0])
    row = _one(cur,
               "insert into public.companies (name, slug, description, cost_limit_usd, cost_limit_period) "
               "values (%s, %s, %s, %s, %s) returning id",
               (COMPANY["name"], COMPANY["slug"], COMPANY["description"],
                COMPANY["cost_limit_usd"], COMPANY["cost_limit_period"]))
    print("[seed] created company")
    return str(row[0])


def ensure_project(cur, company_id: str) -> str:
    row = _one(cur, "select id from public.projects where company_id = %s and name = %s",
               (company_id, PROJECT["name"]))
    if row:
        return str(row[0])
    row = _one(cur, "insert into public.projects (name, company_id, description, status) "
                    "values (%s, %s, %s, 'active') returning id",
               (PROJECT["name"], company_id, PROJECT["description"]))
    print("[seed] created project")
    return str(row[0])


def ensure_definition(cur, name, display, desc, tags, model) -> str:
    row = _one(cur, "select id from public.agent_definitions where name = %s", (name,))
    if row:
        return str(row[0])
    row = _one(cur,
               "insert into public.agent_definitions (name, display_name, description, capability_tags, "
               "default_model, source_path) values (%s, %s, %s, %s, %s, %s) returning id",
               (name, display, desc, tags, model, f"agents/library/{name}/"))
    print(f"[seed] created definition {name}")
    return str(row[0])


def ensure_agent(cur, company_id, project_id, definition_id, capability, agent_type,
                 parent_id, depth, model, cost_limit) -> str:
    name = f"{TENANT_PREFIX}.{capability}"
    row = _one(cur, "select id, status from public.agents where company_id = %s and name = %s",
               (company_id, name))
    if row:
        if row[1] != "active":
            cur.execute("update public.agents set status = 'active', paused_at = null, "
                        "paused_reason = null where id = %s", (row[0],))
            print(f"[seed] re-activated {name}")
        return str(row[0])
    metadata = {"prototype": True, "runtime_implemented": True,
                "entry_point": ("agents/teams/swim-sourcing/controller.py"
                                if agent_type == "orchestrator"
                                else "agents/teams/swim-sourcing/worker.py"),
                "note": "PROTOTYPE identity: one worker process, three identities, no "
                        "inter-agent protocol. See docs/reviews/pool-acquisition-final-design.md B.5"}
    row = _one(cur,
               "insert into public.agents (name, company_id, project_id, definition_id, agent_type, "
               "parent_agent_id, depth, platform, model, trigger_type, status, cost_limit_usd, "
               "cost_limit_period, tags, metadata) values "
               "(%s, %s, %s, %s, %s, %s, %s, 'python', %s, 'manual', 'active', %s, 'monthly', %s, %s) "
               "returning id",
               (name, company_id, project_id, definition_id, agent_type, parent_id, depth, model,
                cost_limit, ["prototype", "swim-sourcing"], json.dumps(metadata)))
    print(f"[seed] created agent {name} ({agent_type})")
    return str(row[0])


def ensure_credential(cur, company_id: str) -> str:
    row = _one(cur, "select id, key_last4, label from platform.tenant_provider_credentials "
                    "where company_id = %s and provider = 'anthropic' and status = 'active'",
               (company_id,))
    if row:
        return f"{row[0]} (last4 {row[1]}, label {row[2]!r})"
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[seed] ANTHROPIC_API_KEY is not set; cannot seed the prototype credential")
        sys.exit(3)
    enc = CRED.encrypt_api_key(api_key)
    cipher = enc.get("key_ciphertext", enc.get("ciphertext"))
    nonce = enc.get("key_nonce", enc.get("nonce"))
    fp = enc.get("key_fingerprint", enc.get("fingerprint"))
    last4 = enc.get("key_last4", enc.get("last4"))
    row = _one(cur,
               "insert into platform.tenant_provider_credentials (company_id, provider, key_ciphertext, "
               "key_nonce, key_fingerprint, key_last4, status, label, created_by) values "
               "(%s, 'anthropic', %s, %s, %s, %s, 'active', %s, %s) returning id",
               (company_id, cipher, nonce, fp, last4,
                "PROTOTYPE: platform Anthropic key stored by instruction 2026-10-20 - "
                "REPLACE with the business's own key before any real campaign",
                "scripts/seed_prototype.py"))
    print(f"[seed] stored prototype credential (last4 {last4})")
    return f"{row[0]} (last4 {last4})"


def status(cur, company_id: str) -> None:
    cur.execute("select name, agent_type, status, cost_limit_usd from public.agents "
                "where company_id = %s order by depth, name", (company_id,))
    agents = cur.fetchall()
    cur.execute("select count(*) from platform.tenant_provider_credentials "
                "where company_id = %s and status = 'active'", (company_id,))
    creds = cur.fetchone()[0]
    cur.execute("select public.swim_objective_progress(%s)", (company_id,))
    progress = cur.fetchone()[0]
    print(json.dumps({
        "company_id": company_id,
        "agents": [{"name": a[0], "type": a[1], "status": a[2], "cost_limit_usd": float(a[3] or 0)}
                   for a in agents],
        "active_credentials": creds,
        "progress": progress,
    }, indent=2, default=str))


def teardown(cur, company_id: str) -> None:
    cur.execute("update public.agents set status = 'paused', paused_at = now(), "
                "paused_reason = 'prototype teardown' where company_id = %s and status <> 'paused'",
                (company_id,))
    paused = cur.rowcount
    cur.execute("update swim_sourcing.jobs set status = 'cancelled', finished_at = now(), "
                "error = 'prototype teardown' where company_id = %s and status in ('queued','blocked')",
                (company_id,))
    cancelled = cur.rowcount
    cur.execute("update swim_sourcing.jobs set cancel_requested = true "
                "where company_id = %s and status = 'running'", (company_id,))
    print(f"[teardown] paused {paused} agent(s), cancelled {cancelled} queued job(s); "
          f"running jobs asked to stop. Rows remain (ledger is append-only by design).")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--teardown", action="store_true")
    args = ap.parse_args()

    with _conn() as conn, conn.cursor() as cur:
        if args.status or args.teardown:
            row = _one(cur, "select id from public.companies where slug = %s", (COMPANY["slug"],))
            if not row:
                print("[seed] prototype company does not exist")
                return 1
            company_id = str(row[0])
            if args.teardown:
                teardown(cur, company_id)
                conn.commit()
            status(cur, company_id)
            return 0

        company_id = ensure_company(cur)
        project_id = ensure_project(cur, company_id)
        defs = {d[0]: ensure_definition(cur, *d) for d in DEFINITIONS}

        controller = ensure_agent(cur, company_id, project_id, defs["facility-acquisition-controller"],
                                  "facility-acquisition-controller", "orchestrator", None, 0,
                                  None, 1.00)
        researcher = ensure_agent(cur, company_id, project_id, defs["facility-researcher"],
                                  "facility-researcher", "worker", controller, 1,
                                  "claude-haiku-5-5", 2.00)
        coordinator = ensure_agent(cur, company_id, project_id, defs["partnership-coordinator"],
                                   "partnership-coordinator", "worker", controller, 1,
                                   "claude-sonnet-5-5", 2.00)
        cur.execute("update public.projects set orchestrator_id = %s where id = %s and orchestrator_id is null",
                    (controller, project_id))
        cred = ensure_credential(cur, company_id)
        conn.commit()

        print(json.dumps({
            "company_id": company_id, "project_id": project_id,
            "controller_agent_id": controller, "researcher_agent_id": researcher,
            "coordinator_agent_id": coordinator, "credential": cred,
            "dashboard": f"https://agent-oversight.vercel.app/dashboard/sourcing?company={company_id}",
        }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
