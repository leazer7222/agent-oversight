#!/usr/bin/env python3
"""
Author the Sprint Review Analysis + next-Sprint Planning Confluence pages from
reports/cycle_data.json, via Confluence REST (token auth, no MCP). Wrapped in
oversight telemetry so the cycle is a tracked agent run.

Page titles + framework are data-driven off the sprint names in cycle_data.json.
The per-cycle narrative (goal grading, highlights, recommendations) is authored
below for THIS cycle (Sprint 3 review / Sprint 4 planning) and marked DRAFT.
"""
from __future__ import annotations
import base64, json, sys, uuid
from pathlib import Path
import httpx

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "python-sdk"))
from oversight import OversightClient  # noqa

SITE = "https://reform-ai-team.atlassian.net"
SPACE = "RAPD"
INSTANCE_AGENT_ID = "5544edd7-fe39-4340-9063-f9f71aef85b9"
DEFAULT_OVERSIGHT_URL = "https://agent-oversight.vercel.app"
BROWSE = "https://reform-ai-team.atlassian.net/browse/"

# ---- per-cycle human judgment (edit each cycle) ------------------------------
# Sprint 3 goal graded part-by-part (confirmed with the product owner).
GOAL_GRADING = [
    ("Complete the Wompi switch to the ReformAI account", "Complete", "Green"),
    ("Productionize the operational health dashboard", "Complete", "Green"),
    ("Add Google Cloud health monitoring", "Complete", "Green"),
    ("Stand up code review", "Complete", "Green"),
    ("Jira / GitHub integration", "Partial", "Yellow"),
    ("User feature: create a project from a visualization", "Partial", "Yellow"),
]
GOAL_HEALTH = ("GREEN", "Green")  # 4 of 6 pillars complete, 2 in progress, none missed.
# Prior sprint delivered-by-size baseline, for the velocity trend note.
PRIOR = {"name": "Sprint 2", "by_size": {"XS": 10, "S": 6, "M": 3, "Spike": 2}, "sized": 21}

def env() -> dict:
    e = {}
    for line in (REPO / ".env.local").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1); e[k.strip()] = v.strip()
    return e
E = env()
AUTH = base64.b64encode(f"{E['ATLASSIAN_EMAIL']}:{E['ATLASSIAN_API_TOKEN']}".encode()).decode()
HJSON = {"Authorization": f"Basic {AUTH}", "Accept": "application/json", "Content-Type": "application/json"}

# ---- storage-format helpers --------------------------------------------------
import html as _html
def esc(t): return _html.escape(str(t), quote=False)
def status(title, colour): return (f'<ac:structured-macro ac:name="status"><ac:parameter ac:name="title">{esc(title)}</ac:parameter>'
                                   f'<ac:parameter ac:name="colour">{colour}</ac:parameter></ac:structured-macro>')
def panel(kind, inner): return f'<ac:structured-macro ac:name="{kind}"><ac:rich-text-body>{inner}</ac:rich-text-body></ac:structured-macro>'
def expand(title, inner): return (f'<ac:structured-macro ac:name="expand"><ac:parameter ac:name="title">{esc(title)}</ac:parameter>'
                                  f'<ac:rich-text-body>{inner}</ac:rich-text-body></ac:structured-macro>')
def link(key): return f'<a href="{BROWSE}{key}">{key}</a>'
def th(*cells): return "<tr>" + "".join(f"<th><p>{c}</p></th>" for c in cells) + "</tr>"
def td(*cells): return "<tr>" + "".join(f"<td><p>{c}</p></td>" for c in cells) + "</tr>"
def table(header, rows): return "<table><tbody>" + th(*header) + "".join(rows) + "</tbody></table>"

STATUS_COLOUR = {"To Do": "Grey", "In Progress": "Yellow", "QA / Testing": "Blue", "Done": "Green", "Blocked": "Red"}
def st_lozenge(s): return status(s, STATUS_COLOUR.get(s, "Grey"))
ORDER = {"Done": 0, "QA / Testing": 1, "In Progress": 2, "To Do": 3, "Blocked": 4}

# ---- Confluence REST upsert --------------------------------------------------
def find_page(title):
    # Direct content lookup by exact title (NOT the CQL search index, which lags for new pages).
    r = httpx.get(f"{SITE}/wiki/rest/api/content",
                  params={"spaceKey": SPACE, "title": title, "type": "page", "expand": "version"},
                  headers=HJSON, timeout=40); r.raise_for_status()
    res = r.json().get("results", [])
    return res[0] if res else None

def upsert(title, body):
    existing = find_page(title)
    if existing:
        ver = existing["version"]["number"] + 1
        payload = {"id": existing["id"], "type": "page", "title": title,
                   "space": {"key": SPACE}, "version": {"number": ver},
                   "body": {"storage": {"value": body, "representation": "storage"}}}
        r = httpx.put(f"{SITE}/wiki/rest/api/content/{existing['id']}", json=payload, headers=HJSON, timeout=60)
    else:
        payload = {"type": "page", "title": title, "space": {"key": SPACE},
                   "body": {"storage": {"value": body, "representation": "storage"}}}
        r = httpx.post(f"{SITE}/wiki/rest/api/content", json=payload, headers=HJSON, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"upsert {title} failed {r.status_code}: {r.text[:400]}")
    d = r.json()
    return d["id"], f"{SITE}/wiki/spaces/{SPACE}/pages/{d['id']}"

# ---- page builders -----------------------------------------------------------
def build_review(d):
    r = d["review"]; retro = d["retro"]
    sprint = r["sprint"]
    done = [i for i in r["issues"] if i["done"]]
    not_done = [i for i in r["issues"] if not i["done"]]
    bi = r["by_initiative"]; bt = r["by_type"]
    sc = r["scope"]; cs = sc["committed_at_start"]; am = sc["added_mid_sprint"]
    added_carry = [i for i in not_done if i.get("added_after_start")]
    out = []
    out.append(panel("note", f"<p><strong>DRAFT - agent-generated (token runtime, no MCP).</strong> Source: Jira {esc(sprint)} (id {r['id']}), generated via cycle.py. Sub-tasks excluded. Human review pending.</p>"))
    out.append("<h1>Executive Summary</h1>")
    out.append(panel("tip",
        f"<p><strong>Sprint Health: </strong>{status(*GOAL_HEALTH)}</p>"
        f"<p><strong>{r['completed']} of {r['committed']} items completed ({r['completion_pct']}%)</strong> &middot; {r['carryover']} carried over.</p>"
        f"<p><strong>The headline: the Wompi switch landed.</strong> The external blocker that held Sprint 2 to a partial goal is done - the account is switched to ReformAI. Alongside it, the team stood up code review, productionized the operational health dashboard, and added Google Cloud health monitoring. Four of the six goal pillars are complete; the remaining two (Jira/GitHub integration, project-from-a-visualization) are in progress, not missed - so health is {GOAL_HEALTH[0]}.</p>"
        f"<p><strong>Beneath the raw {r['completion_pct']}%:</strong> of {cs['count']} items committed at sprint start, {cs['done']} shipped ({cs['pct']}%). The team also absorbed {am['count']} items added mid-sprint and completed {am['done']} of them.</p>"))
    out.append("<h2>Sprint Outcome</h2>")
    out.append(table(["Metric", "Result"], [
        td("Committed (final)", r["committed"]), td("Completed", f"<strong>{r['completed']}</strong>"),
        td("Completion rate", status(f"{r['completion_pct']}%", "Green")),
        td("Carried over", f"{r['carryover']}")]))
    # scope decomposition - the true story of what was planned vs added
    out.append("<h2>Scope: Committed vs Added Mid-Sprint</h2>")
    out.append("<p>Point-in-time counts hide mid-sprint additions. Pulled from the Jira sprint report:</p>")
    out.append(table(["Bucket", "Count", "Completed", "Carryover", "Rate"], [
        td("<strong>Committed at start</strong>", cs["count"], cs["done"], cs["carryover"], status(f"{cs['pct']}%", "Green")),
        td("<strong>Added mid-sprint</strong>", am["count"], am["done"], am["carryover"], f"{am['pct']}%"),
        td("Removed after start", len(sc["removed"]), "-", "-", "-")]))
    if added_carry:
        out.append(panel("note", f"<p>The {len(added_carry)} added items that carried over are all reactive production/registration bugs (" +
                   ", ".join(link(i["key"]) for i in added_carry) + "). Late, unplanned bug work is exactly what the new <strong>Production Bugs bucket</strong> is designed to absorb in Sprint 4.</p>"))
    out.append("<p><strong>By initiative</strong> (completed / total):</p>")
    out.append(table(["Initiative", "Completed", "Total"],
        [td(k, v["done"], v["total"]) for k, v in sorted(bi.items(), key=lambda x: -x[1]["total"])]))
    out.append("<p><strong>By work type</strong>:</p>")
    out.append(table(["Type", "Completed", "Total"],
        [td(k, v["done"], v["total"]) for k, v in sorted(bt.items(), key=lambda x: -x[1]["total"])]))
    cbs = r.get("completed_by_size", {})
    sized_total = sum(v for k, v in cbs.items() if k != "Unsized")
    out.append("<h2>Velocity - Completed by Size</h2>")
    out.append("<p>What the team actually delivered, by t-shirt size:</p>")
    out.append(table(list(cbs.keys()), [td(*[cbs[k] for k in cbs])]))
    out.append(panel("note",
        f"<p>Sized velocity sample: <strong>{sized_total} items</strong> ({cbs.get('Unsized',0)} completed items were unsized). "
        f"This is only the second sprint with sizing, so treat it as <strong>baseline data, not a trend</strong> - a defensible "
        f"velocity trend needs roughly 5-6 fully-sized sprints. One point to carry forward: <strong>no L or larger completed</strong> "
        f"in either sprint.</p>"))
    out.append("<h2>Goal Assessment</h2>")
    out.append(panel("tip", f"<p><strong>Overall: </strong>{status(*GOAL_HEALTH)} - goal substantially met.</p>"))
    out.append(f"<p><em>Jira goal:</em> {esc(r['goal'] or 'not set')}</p>")
    out.append(table(["Goal component", "Outcome"],
        [td(esc(name), status(verdict, colour)) for name, verdict, colour in GOAL_GRADING]))
    out.append("<h2>Highlights</h2>")
    out.append("<ul>"
               "<li><strong>Wompi account switched over.</strong> The Sprint 2 external blocker is resolved - billing now runs on the ReformAI account.</li>"
               "<li><strong>Health monitoring implemented.</strong> Operational health dashboard productionized and Google Cloud monitoring added (retro flags a few gaps still to close).</li>"
               "<li><strong>Code review stood up</strong> in GitHub, with Jira/GitHub integration in progress.</li>"
               "<li><strong>Asset Discovery Pipeline</strong> and the <strong>Airbnb Investor Landing Page</strong> shipped.</li>"
               "<li><strong>Project creation from a visualization</strong> (partial) is now Sprint 4's top goal - currently in the QA environment.</li>"
               "</ul>")
    out.append("<h2>Watch Items (from the retro)</h2>")
    out.append("<ul>"
               "<li><strong>Prod regressions from hotfixes.</strong> Directly motivated the Production Bugs bucket + a per-build test-suite idea for Sprint 4.</li>"
               "<li><strong>Operational Health still missing some things</strong> - follow-up scope.</li>"
               "<li><strong>Service Providers' projects not showing up</strong> - now filed as a Sprint 4 bug.</li>"
               "<li><strong>Supplier Catalog moved to a research spike.</strong> Retro flagged it hard to design without enough client catalogs; for Sprint 4 it converts from a large story to a spike to de-risk it while sample catalogs are gathered.</li>"
               "<li><strong>Venezuela new-market design pulled focus</strong> from sprint initiatives.</li>"
               "</ul>")
    out.append("<h2>Work Completed</h2>")
    out.append(expand(f"Show all {len(done)} completed items",
        table(["Key", "Type", "Initiative", "Summary"],
              [td(link(i["key"]), i["type"], i["cat"], esc(i["summary"])) for i in done])))
    out.append(f"<h2>Carry-Over ({len(not_done)} items)</h2>")
    out.append(expand(f"Show all {len(not_done)} carry-over items",
        table(["Key", "Type", "Status", "Summary"],
              [td(link(i["key"]), i["type"], st_lozenge(i["status"]), esc(i["summary"]))
               for i in sorted(not_done, key=lambda x: ORDER.get(x["status"], 9))])))
    out.append("<h2>Retro Summary</h2>")
    out.append(f'<p>Pulled from <a href="{SITE}/wiki/spaces/{SPACE}/pages/{retro["page_id"]}">{esc(sprint)} Retro</a>.</p>')
    out.append(panel("tip", "<p><strong>What went well</strong></p><ul>" + "".join(f"<li>{esc(x)}</li>" for x in retro["good"]) + "</ul>"))
    out.append(panel("warning", "<p><strong>Could be better</strong></p><ul>" + "".join(f"<li>{esc(x)}</li>" for x in retro["bad"]) + "</ul>"))
    out.append(panel("info", "<p><strong>Ideas</strong></p><ul>" + "".join(f"<li>{esc(x)}</li>" for x in retro["ideas"]) + "</ul>"))
    out.append("<h2>Recommendations</h2>")
    recs = [
        "<li><strong>Pull the Seller Module (RAI-437) from the application</strong> if the CEO broker-agreement and white-glove pricing decisions are not settled - do not expose seller functionality without the legal and pricing terms in place. RAI-622 is the decision gate; both have carried since UAT.</li>",
        "<li><strong>Supplier Catalog converted to a research spike (done).</strong> RAI-546 moves from a large story to a spike for Sprint 4; gather sample client catalogs to design against before committing full design effort.</li>",
        "<li><strong>Stand up a per-build test suite.</strong> Retro idea; directly targets the prod regressions from hotfixes.</li>",
        "<li><strong>Add standard user-checks across all tabs/pages.</strong> Retro idea; catches the class of bugs (service-provider projects, homeowner registration) that leaked to prod.</li>",
        "<li><strong>Track ad-hoc bugs against the new Production Bugs bucket.</strong> The 3 late-added homeowner-registration bugs that carried over show why the reserved bucket matters.</li>",
        f"<li><strong>Right-size Sprint 4's top end.</strong> {r['carryover']} items carried in; committed mix runs heavier at M/L than proven throughput (0 L delivered two sprints running).</li>",
    ]
    out.append("<ul>" + "".join(recs) + "</ul>")
    out.append("<hr/><p><strong>Cross-links:</strong> " +
               f'<a href="{SITE}/wiki/spaces/{SPACE}/pages/{retro["page_id"]}">{esc(sprint)} Retro</a> &middot; '
               f'{esc(d["planning"]["sprint"])} - Planning (this cycle)</p>')
    return "".join(out)

def build_planning(d):
    p = d["planning"]
    issues = p["issues"]
    review_sprint = d["review"]["sprint"]
    # Bugs are intentionally left unsized (bucketed under the Production Bugs story); the
    # readiness gate for sizing considers only non-Bug items.
    unsized_stories = [i for i in issues if not i["size"] and not i["done"] and i["type"] != "Bug"]
    unsized_bugs = [i for i in issues if not i["size"] and i["type"] == "Bug"]
    out = []
    out.append(panel("note", f"<p><strong>DRAFT - agent-generated planning (token runtime, no MCP).</strong> Source: Jira {esc(p['sprint'])} (id {p['id']}). Sub-tasks excluded. Carryover = also in {esc(review_sprint)}.</p>"))
    out.append(f"<h1>{esc(p['sprint'])} - Planning</h1>")
    goal_txt = esc(p["goal"]) if p["goal"] else "NOT SET - set a sprint goal in Jira before starting the sprint."
    out.append(panel("info", f"<p><strong>Goal:</strong> {goal_txt}</p>"))
    # readiness (bug-aware)
    sized_ok = len(unsized_stories) == 0
    own_ok = p["unassigned"] == 0
    epic_ok = p["no_epic"] == 0
    gate_ready = epic_ok and sized_ok and own_ok and bool(p["goal"])
    out.append("<h2>Readiness Gate</h2>")
    out.append(panel("tip" if gate_ready else "warning",
        f"<p><strong>Gate: {'READY' if gate_ready else 'NOT READY'}.</strong> "
        f"{'All checks pass. Bugs are intentionally unsized (bucketed).' if gate_ready else 'Resolve the ACTION items below before starting.'}</p>"))
    out.append(table(["Check", "Status", "Detail"], [
        td("Epics linked", status("PASS" if epic_ok else "ACTION", "Green" if epic_ok else "Yellow"), f"{p['committed']-p['no_epic']}/{p['committed']} linked"),
        td("Stories sized", status("PASS" if sized_ok else "ACTION", "Green" if sized_ok else "Yellow"), f"{len(unsized_stories)} non-bug items unsized"),
        td("Owners assigned", status("PASS" if own_ok else "ACTION", "Green" if own_ok else "Yellow"), f"{p['unassigned']} unassigned"),
        td("Sprint goal", status("PASS" if p["goal"] else "ACTION", "Green" if p["goal"] else "Yellow"), "set" if p["goal"] else "not set in Jira"),
        td("Bugs (bucketed)", status("INFO", "Blue"), f"{len(unsized_bugs)} unsized by design; capacity held in the Production Bugs story"),
    ]))
    # scope summary
    out.append("<h2>Committed Scope</h2>")
    out.append(f"<p><strong>{p['committed']} items</strong> &middot; {p['carryover']} carryover &middot; {p['committed']-p['carryover']} net-new</p>")
    out.append("<p><strong>By initiative:</strong></p>")
    out.append(table(["Initiative", "Items"], [td(k, v["total"]) for k, v in sorted(p["by_initiative"].items(), key=lambda x: -x[1]["total"])]))
    out.append("<p><strong>By size:</strong></p>")
    out.append(table(list(p["sizes"].keys()), [td(*[p["sizes"][k] for k in p["sizes"]])]))
    # capacity vs last sprint's actual throughput
    cbs = d["review"].get("completed_by_size", {})
    def big(d2): return d2.get("M", 0) + d2.get("L", 0) + d2.get("XL", 0) + d2.get("XXL", 0)
    out.append("<h2>Capacity vs Last Sprint</h2>")
    out.append(table(["Size", f"{p['sprint']} committed", f"{review_sprint} delivered"],
        [td(s, p["sizes"].get(s, 0), cbs.get(s, 0)) for s in ["XS", "S", "M", "L", "XL", "Spike"]]))
    out.append(panel("warning",
        f"<p><strong>Capacity watch:</strong> {p['sprint']} commits {big(p['sizes'])} items at M or larger; "
        f"{review_sprint} delivered {big(cbs)} that big (and zero L). Top-end load eased: Supplier Catalog (RAI-546) "
        f"was converted from a large story to a research spike, so the remaining L's are the infrastructure report "
        f"(RAI-677) and Moodboard Design (RAI-654). On M the plan commits more than last sprint delivered - but with only "
        f"two sized sprints there is no defensible velocity yet, so treat this as a planning sanity check, not a hard ceiling.</p>"))
    if unsized_stories:
        out.append("<h2>Needs Estimate (non-bug)</h2>")
        out.append(table(["Key", "Status", "Epic", "Owner", "Summary"],
            [td(link(i["key"]), st_lozenge(i["status"]), esc(i["epic"] or "-"), i["owner"], esc(i["summary"])) for i in unsized_stories]))
    if unsized_bugs:
        out.append("<h2>Bugs (unsized by design)</h2>")
        out.append("<p>Tracked against the Production Bugs bucket; not individually sized.</p>")
        out.append(table(["Key", "Status", "Owner", "Summary"],
            [td(link(i["key"]), st_lozenge(i["status"]), i["owner"], esc(i["summary"])) for i in unsized_bugs]))
    # full scope grouped by initiative, Business Design first
    out.append("<h2>Full Committed Scope</h2>")
    cats = ["Business Design", "Product", "Tech Debt", "Infrastructure"]
    for c in cats:
        grp = [i for i in issues if i["cat"] == c]
        if not grp: continue
        out.append(f"<h3>{c} ({len(grp)})</h3>")
        rows = []
        for i in sorted(grp, key=lambda x: ORDER.get(x["status"], 9)):
            co = status("Carryover", "Purple") if i.get("carryover") else ""
            rows.append(td(link(i["key"]), i["type"], i["size"] or "-", st_lozenge(i["status"]), i["owner"], co, esc(i["summary"])))
        out.append(table(["Key", "Type", "Size", "Status", "Owner", "Carryover", "Summary"], rows))
    out.append(f"<hr/><p><strong>Cross-links:</strong> {esc(review_sprint)} - Review Analysis (this cycle)</p>")
    return "".join(out)

# ---- main --------------------------------------------------------------------
def main():
    d = json.loads((REPO / "reports" / "cycle_data.json").read_text(encoding="utf-8"))
    review_title = f"{d['review']['sprint']} - Review Analysis"
    planning_title = f"{d['planning']['sprint']} - Planning"
    client = OversightClient(url=E.get("OVERSIGHT_URL") or DEFAULT_OVERSIGHT_URL,
                             secret=E["AGENT_OVERSIGHT_SECRET"])
    run_id = str(uuid.uuid4())
    print(f"run_id={run_id}")
    with client.run(agent_id=INSTANCE_AGENT_ID, run_id=run_id,
                    metadata={"mode": "cycle", "review": d["review"]["sprint"],
                              "planning": d["planning"]["sprint"]}) as run:
        with run.timer() as t:
            rid, rurl = upsert(review_title, build_review(d))
        run.step("review_authored", message=rurl, duration_ms=t.ms)
        print(f"{review_title} ->", rurl)
        with run.timer() as t:
            pid, purl = upsert(planning_title, build_planning(d))
        run.step("planning_authored", message=purl, duration_ms=t.ms)
        print(f"{planning_title} ->", purl)
        run.report(tokens_in=0, tokens_out=0, cost_usd=0.0,
                   metadata={"review_url": rurl, "planning_url": purl})
    print("telemetry: run_started + run_completed emitted OK")

if __name__ == "__main__":
    main()
