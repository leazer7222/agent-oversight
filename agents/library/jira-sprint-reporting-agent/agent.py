#!/usr/bin/env python3
"""
Jira Sprint Reporting Agent - telemetry-emitting runtime.

Emits run_started / run_completed (run_failed on error) to the Agent Oversight
ingest endpoint via the oversight SDK, around a real unit of work.

Modes:
  --smoke   Telemetry + config validation only. No Atlassian calls. Proves the
            telemetry loop end-to-end (use for the registration smoke test).
  (default) Pull the latest CLOSED sprint from Jira and compute count-based
            metrics (committed / completed / carryover). Requires an Atlassian
            API token in the environment (see ENV below).

ENV (read from .env.local, no dotenv dependency):
  AGENT_OVERSIGHT_SECRET      required - ingest auth
  OVERSIGHT_URL               optional - defaults to the Vercel production URL
  ATLASSIAN_EMAIL             required for live mode - Atlassian account email
  ATLASSIAN_API_TOKEN         required for live mode - id.atlassian.com API token
  ATLASSIAN_CLOUD_ID          optional - defaults to the ReformAI cloud id
  JIRA_BOARD_ID               optional - defaults to 3

This runtime makes NO LLM calls, so it reports zero tokens / zero cost (honest:
deterministic API work). It is read-only against Jira.
"""
from __future__ import annotations

import os
import sys
import uuid
import base64
import json
from pathlib import Path

# --- locate repo root + SDK ---------------------------------------------------
HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[3]  # agents/library/<agent>/agent.py -> repo root
sys.path.insert(0, str(REPO_ROOT / "python-sdk"))

from oversight import OversightClient  # noqa: E402

# --- constants ----------------------------------------------------------------
INSTANCE_AGENT_ID = "5544edd7-fe39-4340-9063-f9f71aef85b9"  # reformai.jira-sprint-reporting-agent
DEFAULT_OVERSIGHT_URL = "https://agent-oversight.vercel.app"
DEFAULT_CLOUD_ID = "6c97a9a2-291e-4c35-89da-b7c3d245e386"
DEFAULT_BOARD_ID = "3"


def load_env() -> dict:
    """Parse .env.local from the repo root into a dict (no dotenv dependency)."""
    env: dict = {}
    env_path = REPO_ROOT / ".env.local"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    # process env wins for anything explicitly set
    for k in ("AGENT_OVERSIGHT_SECRET", "OVERSIGHT_URL", "ATLASSIAN_EMAIL",
              "ATLASSIAN_API_TOKEN", "ATLASSIAN_CLOUD_ID", "JIRA_BOARD_ID"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def _atlassian_get(env: dict, path: str, params: dict | None = None) -> dict:
    """GET against the Atlassian Cloud REST API with basic (email:token) auth."""
    import httpx
    cloud = env.get("ATLASSIAN_CLOUD_ID", DEFAULT_CLOUD_ID)
    email = env["ATLASSIAN_EMAIL"]
    token = env["ATLASSIAN_API_TOKEN"]
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    url = f"https://api.atlassian.com/ex/jira/{cloud}{path}"
    resp = httpx.get(url, params=params or {},
                     headers={"Authorization": f"Basic {auth}", "Accept": "application/json"},
                     timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def pull_sprint_metrics(env: dict, run) -> dict:
    """Pull the latest closed sprint and compute count-based metrics."""
    board = env.get("JIRA_BOARD_ID", DEFAULT_BOARD_ID)

    with run.timer() as t:
        sprints = _atlassian_get(env, f"/rest/agile/1.0/board/{board}/sprint",
                                  {"state": "closed"})
    closed = sprints.get("values", [])
    if not closed:
        raise RuntimeError("validation: no closed sprints found on board")
    sprint = closed[-1]  # most recently created closed sprint
    run.step("closed_sprint_resolved",
             message=f"Sprint {sprint['name']} (id {sprint['id']})", duration_ms=t.ms)

    issues, start_at = [], 0
    with run.timer() as t:
        while True:
            page = _atlassian_get(env, f"/rest/agile/1.0/sprint/{sprint['id']}/issue",
                                  {"fields": "status,issuetype", "startAt": start_at,
                                   "maxResults": 50})
            issues.extend(page.get("issues", []))
            if start_at + 50 >= page.get("total", 0):
                break
            start_at += 50
    run.step("issues_pulled", message=f"{len(issues)} issues", duration_ms=t.ms)

    top = [i for i in issues if i["fields"]["issuetype"]["name"] != "Sub-task"]
    done = [i for i in top if i["fields"]["status"]["statusCategory"]["key"] == "done"]
    total = len(top)
    completion = round(100.0 * len(done) / total) if total else 0
    metrics = {
        "sprint": sprint["name"],
        "sprint_id": sprint["id"],
        "committed": total,
        "completed": len(done),
        "carryover": total - len(done),
        "completion_pct": completion,
    }
    run.step("metrics_computed", message=json.dumps(metrics), payload=metrics)
    return metrics


def run_smoke(env: dict, run) -> dict:
    """Config-validation unit of work; no Atlassian calls. Proves the telemetry loop."""
    checks = {
        "template_exists": (REPO_ROOT / "reports" / "sprint-1-review.html").exists(),
        "design_spec_exists": (REPO_ROOT / "docs" / "agent-jira-sprint-reporting.md").exists(),
        "atlassian_token_present": bool(env.get("ATLASSIAN_API_TOKEN")),
        "cloud_id": env.get("ATLASSIAN_CLOUD_ID", DEFAULT_CLOUD_ID),
    }
    run.step("smoke_validate", message="config validation", payload=checks,
             severity="info" if checks["template_exists"] else "warning")
    return checks


def main() -> int:
    smoke = "--smoke" in sys.argv
    env = load_env()
    secret = env.get("AGENT_OVERSIGHT_SECRET")
    url = env.get("OVERSIGHT_URL") or DEFAULT_OVERSIGHT_URL
    if not secret:
        print("FATAL: AGENT_OVERSIGHT_SECRET missing", file=sys.stderr)
        return 1

    client = OversightClient(url=url, secret=secret)
    run_id = str(uuid.uuid4())
    print(f"agent_id={INSTANCE_AGENT_ID} run_id={run_id} mode={'smoke' if smoke else 'live'} url={url}")

    with client.run(agent_id=INSTANCE_AGENT_ID, run_id=run_id,
                    metadata={"mode": "smoke" if smoke else "live",
                              "capability": "sprint_reporting"}) as run:
        result = run_smoke(env, run) if smoke else pull_sprint_metrics(env, run)
        # No LLM calls -> deterministic API work -> zero token cost (reported explicitly).
        run.report(tokens_in=0, tokens_out=0, cost_usd=0.0,
                   metadata={"result": result})

    print("RESULT:", json.dumps(result, indent=2))
    print("telemetry: run_started + run_completed emitted OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
