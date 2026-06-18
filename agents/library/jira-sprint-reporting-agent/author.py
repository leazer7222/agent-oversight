#!/usr/bin/env python3
"""
Author Sprint 2 Review Analysis + Sprint 3 Planning Confluence pages from
reports/cycle_data.json, via Confluence REST (token auth, no MCP). Wrapped in
oversight telemetry so the cycle is a tracked agent run.
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
    cql = f'space={SPACE} and title="{title}" and type=page'
    r = httpx.get(f"{SITE}/wiki/rest/api/content/search", params={"cql": cql, "expand": "version"},
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
    done = [i for i in r["issues"] if i["done"]]
    not_done = [i for i in r["issues"] if not i["done"]]
    bi = r["by_initiative"]; bt = r["by_type"]
    out = []
    out.append(panel("note", f"<p><strong>DRAFT - agent-generated (token runtime, no MCP).</strong> Source: Jira {r['sprint']} (id {r['id']}), generated via cycle.py. Sub-tasks excluded.</p>"))
    out.append("<h1>Executive Summary</h1>")
    out.append(panel("tip",
        f"<p><strong>Sprint Health: </strong>{status('GREEN','Green')} <em>[HUMAN: confirm vs goal]</em></p>"
        f"<p><strong>Goal:</strong> {esc(r['goal'] or 'not set in Jira')}</p>"
        f"<p><strong>{r['completed']} of {r['committed']} work items completed ({r['completion_pct']}%)</strong> &middot; {r['carryover']} carried over</p>"
        f"<p>Strongest sprint to date by completion. Wins from the retro: dashboards, PostHog analytics, email notifications, landing pages live.</p>"))
    out.append("<h2>Sprint Outcome</h2>")
    out.append(table(["Metric", "Result"], [
        td("Committed", r["committed"]), td("Completed", f"<strong>{r['completed']}</strong>"),
        td("Completion rate", status(f"{r['completion_pct']}%", "Green")),
        td("Carried over", f"{r['carryover']}")]))
    out.append("<p><strong>By initiative</strong> (completed / total):</p>")
    out.append(table(["Initiative", "Completed", "Total"],
        [td(k, v["done"], v["total"]) for k, v in sorted(bi.items(), key=lambda x: -x[1]["total"])]))
    out.append("<p><strong>By work type</strong>:</p>")
    out.append(table(["Type", "Completed", "Total"],
        [td(k, v["done"], v["total"]) for k, v in sorted(bt.items(), key=lambda x: -x[1]["total"])]))
    out.append("<h2>Goal Assessment</h2>")
    out.append(f"<p><em>[HUMAN: was the Wompi + Dashboards goal achieved? Mark Achieved / Partial and add business impact.]</em></p>")
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
    out.append(f'<p>Pulled from <a href="{SITE}/wiki/spaces/{SPACE}/pages/{retro["page_id"]}">Sprint 2 Retro</a>.</p>')
    out.append(panel("tip", "<p><strong>What went well</strong></p><ul>" + "".join(f"<li>{esc(x)}</li>" for x in retro["good"]) + "</ul>"))
    out.append(panel("warning", "<p><strong>Could be better</strong></p><ul>" + "".join(f"<li>{esc(x)}</li>" for x in retro["bad"]) + "</ul>"))
    out.append(panel("info", "<p><strong>Ideas</strong></p><ul>" + "".join(f"<li>{esc(x)}</li>" for x in retro["ideas"]) + "</ul>"))
    out.append("<h2>Recommendations</h2>")
    recs = ["<li><strong>Tech Debt slipped (0 of 2 done).</strong> Protect explicit tech-debt capacity in Sprint 3 or it keeps deferring.</li>",
            "<li><strong>Evaluate the 2-week sprint idea from retro.</strong> 1-week cadence ran long this sprint (ended after the planned Mon 18th); 2-week sprints with weekly releases + hotfixes is worth trying.</li>",
            "<li><strong>Allocate dedicated prod-bug time.</strong> Retro flagged production bugs (R2, Google registration) as friction.</li>",
            f"<li><strong>{r['carryover']} items carried into Sprint 3.</strong> Right-size Sprint 3 around that backlog before adding new scope.</li>"]
    out.append("<ul>" + "".join(recs) + "</ul>")
    out.append("<hr/><p><strong>Cross-links:</strong> " +
               f'<a href="{SITE}/wiki/spaces/{SPACE}/pages/{retro["page_id"]}">Sprint 2 Retro</a></p>')
    return "".join(out)

def build_planning(d):
    p = d["planning"]
    issues = p["issues"]
    sized_active = [i for i in issues if not i["size"] and not i["done"]]
    out = []
    out.append(panel("note", f"<p><strong>DRAFT - agent-generated planning (token runtime, no MCP).</strong> Source: Jira {p['sprint']} (id {p['id']}). Sub-tasks excluded. Carryover = also in Sprint 2.</p>"))
    out.append(f"<h1>{esc(p['sprint'])} - Planning</h1>")
    goal_txt = esc(p["goal"]) if p["goal"] else "NOT SET - " + "set a sprint goal in Jira before starting the sprint."
    out.append(panel("info", f"<p><strong>Goal:</strong> {goal_txt}</p>"
                             + ("" if p["goal"] else "<p><em>[HUMAN: set the Sprint 3 goal on the sprint in the Jira board, then re-run.]</em></p>")))
    # readiness
    sized_ok = p["unsized"] == 0
    own_ok = p["unassigned"] == 0
    out.append("<h2>Readiness Gate</h2>")
    gate_ready = (p["no_epic"] == 0 and sized_ok and own_ok and bool(p["goal"]))
    out.append(panel("tip" if gate_ready else "warning",
        f"<p><strong>Gate: {'READY' if gate_ready else 'NOT READY'}.</strong> "
        f"{'All checks pass.' if gate_ready else 'Resolve the ACTION items below before starting.'}</p>"))
    out.append(table(["Check", "Status", "Detail"], [
        td("Epics linked", status("PASS" if p["no_epic"]==0 else "ACTION", "Green" if p["no_epic"]==0 else "Yellow"), f"{p['committed']-p['no_epic']}/{p['committed']} linked"),
        td("T-shirt sized", status("PASS" if sized_ok else "ACTION", "Green" if sized_ok else "Yellow"), f"{p['unsized']} active items unsized"),
        td("Owners assigned", status("PASS" if own_ok else "ACTION", "Green" if own_ok else "Yellow"), f"{p['unassigned']} unassigned"),
        td("Sprint goal", status("PASS" if p["goal"] else "ACTION", "Green" if p["goal"] else "Yellow"), "set" if p["goal"] else "not set in Jira"),
    ]))
    # scope summary
    out.append("<h2>Committed Scope</h2>")
    out.append(f"<p><strong>{p['committed']} items</strong> &middot; {p['carryover']} carryover &middot; {p['committed']-p['carryover']} net-new</p>")
    out.append("<p><strong>By initiative:</strong></p>")
    out.append(table(["Initiative", "Items"], [td(k, v["total"]) for k, v in sorted(p["by_initiative"].items(), key=lambda x: -x[1]["total"])]))
    out.append("<p><strong>By size:</strong></p>")
    out.append(table(list(p["sizes"].keys()), [td(*[p["sizes"][k] for k in p["sizes"]])]))
    if sized_active:
        out.append("<h2>Needs Estimate</h2>")
        out.append(table(["Key", "Status", "Epic", "Owner", "Summary"],
            [td(link(i["key"]), st_lozenge(i["status"]), esc(i["epic"] or "-"), i["owner"], esc(i["summary"])) for i in sized_active]))
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
    out.append("<hr/><p><strong>Cross-links:</strong> Sprint 2 Review Analysis (this cycle)</p>")
    return "".join(out)

# ---- main --------------------------------------------------------------------
def main():
    d = json.loads((REPO / "reports" / "cycle_data.json").read_text(encoding="utf-8"))
    client = OversightClient(url=E.get("OVERSIGHT_URL") or DEFAULT_OVERSIGHT_URL,
                             secret=E["AGENT_OVERSIGHT_SECRET"])
    run_id = str(uuid.uuid4())
    print(f"run_id={run_id}")
    with client.run(agent_id=INSTANCE_AGENT_ID, run_id=run_id,
                    metadata={"mode": "cycle", "review": d["review"]["sprint"],
                              "planning": d["planning"]["sprint"]}) as run:
        with run.timer() as t:
            rid, rurl = upsert("Sprint 2 - Review Analysis", build_review(d))
        run.step("review_authored", message=rurl, duration_ms=t.ms)
        print("Sprint 2 Review ->", rurl)
        with run.timer() as t:
            pid, purl = upsert("Sprint 3 - Planning", build_planning(d))
        run.step("planning_authored", message=purl, duration_ms=t.ms)
        print("Sprint 3 Planning ->", purl)
        run.report(tokens_in=0, tokens_out=0, cost_usd=0.0,
                   metadata={"review_url": rurl, "planning_url": purl})
    print("telemetry: run_started + run_completed emitted OK")

if __name__ == "__main__":
    main()
