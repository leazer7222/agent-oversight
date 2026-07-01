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
import sys, re
import html as _html
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

def esc(t): return _html.escape(str(t), quote=False)

def find_page(title):
    r = httpx.get(f"{SITE}/wiki/rest/api/content",
                  params={"spaceKey": SPACE, "title": title, "type": "page", "expand": "version"},
                  headers=H, timeout=40); r.raise_for_status()
    res = r.json().get("results", [])
    return res[0] if res else None

def pick_sprints(override=None):
    """Return (review_sprint_dict, next_sprint_dict). Review = the sprint being reviewed
    (override by name, else the ACTIVE/open sprint, else latest closed) - run this while
    the sprint is still OPEN, before closing it. Next = first future sprint (planning link)."""
    vals, start = [], 0
    while True:
        pg = cycle.jget(f"/rest/agile/1.0/board/{cycle.BOARD}/sprint", {"startAt": start, "maxResults": 50})
        vals += pg.get("values", [])
        if pg.get("isLast") or start + 50 >= 1000:
            break
        start += 50
    if override:
        review = next((s for s in vals if s["name"] == override), None)
        if not review:
            raise SystemExit(f"sprint {override!r} not found on board {cycle.BOARD}")
    else:
        active = [s for s in vals if s["state"] == "active"]
        closed = [s for s in vals if s["state"] == "closed"]
        review = active[-1] if active else (closed[-1] if closed else None)
        if not review:
            raise SystemExit("no active or closed sprint found - pass --sprint")
    # next = first future sprint that is not the review sprint (for the Planning link)
    future = [s for s in vals if s["state"] == "future" and s["id"] != review["id"]]
    return review, (future[0] if future else None)

def _pagelink(title):
    return f'<ac:link><ri:page ri:content-title="{esc(title)}" /></ac:link>'

def prefill(body, review, nxt):
    """Fill the info panel (Sprint, Dates, Review/Planning links) and the Sprint Goal
    table (one row per goal component). Facilitator/Participants stay blank (human)."""
    name = review["name"]
    start = (review.get("startDate") or "")[:10]
    end = (review.get("endDate") or "")[:10]
    body = body.replace("<strong>Sprint:</strong> Sprint N</p>",
                        f"<strong>Sprint:</strong> {esc(name)}</p>")
    if start and end:
        body = body.replace("<strong>Dates:</strong> YYYY-MM-DD &ndash; YYYY-MM-DD</p>",
                            f"<strong>Dates:</strong> {start} &ndash; {end}</p>")
    body = body.replace("<strong>Review page:</strong> (link to Sprint N &mdash; Review)</p>",
                        f"<strong>Review page:</strong> {_pagelink(f'{name} - Review Analysis')}</p>")
    plan = _pagelink(f"{nxt['name']} - Planning") if nxt else "(next sprint not created yet)"
    body = body.replace("<strong>Planning page:</strong> (link to Sprint N+1 &mdash; Planning)</p>",
                        f"<strong>Planning page:</strong> {plan}</p>")
    # Sprint Goal table: one component per row (split the Jira goal on '+').
    goal = (review.get("goal") or "").strip()
    comps = [c.strip() for c in re.split(r"\s*\+\s*", goal) if c.strip()] if goal else []
    if comps:
        h = body.find("Sprint Goal</h2>")
        tstart = body.find("<table", h) if h != -1 else -1
        tend = body.find("</table>", tstart) if tstart != -1 else -1
        if tstart != -1 and tend != -1:
            table = body[tstart:tend]
            data_rows = re.findall(r"<tr\b.*?</tr>", table, re.S)[1:]  # skip header
            for i, comp in enumerate(comps):
                if i >= len(data_rows):
                    print(f"   [note] goal has {len(comps)} parts but the table has {len(data_rows)} rows; extra parts dropped")
                    break
                filled = re.sub(r'<p local-id="([^"]*)" ?/>',
                                lambda m: f'<p local-id="{m.group(1)}">{esc(comp)}</p>',
                                data_rows[i], count=1)
                body = body.replace(data_rows[i], filled, 1)
    return body, name, (start, end), comps

def copy_retro(review, nxt, dry=False):
    title = f"{review['name']} Retro"
    existing = find_page(title)
    if existing:
        print(f"   [skip] '{title}' already exists -> {SITE}/wiki/spaces/{SPACE}/pages/{existing['id']}")
        return
    tmpl = cycle.jget(f"/wiki/rest/api/content/{RETRO_TEMPLATE_ID}", {"expand": "body.storage"})
    body, name, dates, comps = prefill(tmpl["body"]["storage"]["value"], review, nxt)
    print(f"   prefill -> Sprint: {name} | Dates: {dates[0] or '?'}..{dates[1] or '?'} | "
          f"Goal rows: {len(comps)} | Planning link: {nxt['name'] if nxt else '(none)'}")
    if dry:
        print(f"   [dry-run] would create '{title}' under Sprint Reviews ({SPRINT_REVIEWS_PARENT})")
        return
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
    review, nxt = pick_sprints(override)
    print(f"== Cycle kickoff: reviewing {review['name']}{' (DRY RUN)' if dry else ''} ==\n")

    print("1) Retro page from template (pre-filled from Jira):")
    copy_retro(review, nxt, dry=dry)

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
