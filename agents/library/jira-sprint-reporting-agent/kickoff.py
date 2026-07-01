#!/usr/bin/env python3
"""
Cycle kickoff - run at the START of each review/planning session.

Does the three session-opening steps:
  1. Copy the "SPRINT RETRO - TEMPLATE" into "<review sprint> Retro" under the
     Sprint Reviews folder (idempotent - skips if the page already exists).
  2. Copy over information from the Jira sprint (runs the gather ->
     reports/cycle_data.json + prints the sprint summary).
  3. Print the 1-hour-before pre-meeting checklist.

Order matters: CLOSE the sprint in Jira first, so the gather reviews it and the
retro is named for it. Then run this.

Run:
  python agents/library/jira-sprint-reporting-agent/kickoff.py
  python agents/library/jira-sprint-reporting-agent/kickoff.py --sprint "Sprint 4"
  python agents/library/jira-sprint-reporting-agent/kickoff.py --dry-run   # no writes
"""
from __future__ import annotations
import sys
from pathlib import Path
import httpx

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cycle  # sibling module: SITE, SPACE_KEY, BOARD, jget, find_sprints, H, REPO, main

SITE = cycle.SITE
SPACE = cycle.SPACE_KEY
H = cycle.H
HJSON = {**H, "Content-Type": "application/json"}
SPRINT_REVIEWS_PARENT = "164921346"   # RAPD > Reform AI Product Documentation > Sprint Reviews
RETRO_TEMPLATE_ID = "166297602"       # SPRINT RETRO - TEMPLATE

def find_page(title):
    r = httpx.get(f"{SITE}/wiki/rest/api/content",
                  params={"spaceKey": SPACE, "title": title, "type": "page", "expand": "version"},
                  headers=H, timeout=40); r.raise_for_status()
    res = r.json().get("results", [])
    return res[0] if res else None

def review_sprint_name(override=None):
    if override:
        return override
    closed, _future = cycle.find_sprints()  # review target = latest closed (matches the gather)
    if not closed:
        raise SystemExit("no closed sprint found - close the sprint in Jira first, or pass --sprint")
    return closed["name"]

def copy_retro(sprint_name, dry=False):
    title = f"{sprint_name} Retro"
    existing = find_page(title)
    if existing:
        print(f"   [skip] '{title}' already exists -> {SITE}/wiki/spaces/{SPACE}/pages/{existing['id']}")
        return
    if dry:
        print(f"   [dry-run] would create '{title}' under Sprint Reviews ({SPRINT_REVIEWS_PARENT}) from template {RETRO_TEMPLATE_ID}")
        return
    tmpl = cycle.jget(f"/wiki/rest/api/content/{RETRO_TEMPLATE_ID}", {"expand": "body.storage"})
    body = tmpl["body"]["storage"]["value"]
    payload = {"type": "page", "title": title, "space": {"key": SPACE},
               "ancestors": [{"id": SPRINT_REVIEWS_PARENT}],
               "body": {"storage": {"value": body, "representation": "storage"}}}
    r = httpx.post(f"{SITE}/wiki/rest/api/content", json=payload, headers=HJSON, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"create '{title}' failed {r.status_code}: {r.text[:300]}")
    print(f"   [created] '{title}' -> {SITE}/wiki/spaces/{SPACE}/pages/{r.json()['id']}")

def print_checklist():
    print((HERE / "PRE_MEETING_CHECKLIST.md").read_text(encoding="utf-8"))

def main():
    dry = "--dry-run" in sys.argv
    override = None
    if "--sprint" in sys.argv:
        override = sys.argv[sys.argv.index("--sprint") + 1]
    name = review_sprint_name(override)
    print(f"== Cycle kickoff: reviewing {name}{' (DRY RUN)' if dry else ''} ==\n")

    print("1) Retro page from template:")
    copy_retro(name, dry=dry)

    print("\n2) Copy over Jira sprint info (gather):")
    if dry:
        print("   [dry-run] would run cycle.py gather -> reports/cycle_data.json")
    else:
        cycle.main()

    print("\n3) Pre-meeting checklist (1 hour before the review):")
    print("=" * 70)
    print_checklist()

if __name__ == "__main__":
    main()
