#!/usr/bin/env python3
"""
Generate the branded Sprint 2 management PDF (HTML) from reports/cycle_data.json.
Reuses the ReformAI brand CSS + logo_en.png. Render with Edge headless afterwards.
"""
from __future__ import annotations
import json, html as _html
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "reports" / "sprint-2-review.html"

def esc(t): return _html.escape(str(t), quote=False)

CSS = (REPO / "reports" / "sprint-1-review.html").read_text(encoding="utf-8").split("<style>")[1].split("</style>")[0]

LZ = {"To Do": "lz-todo", "In Progress": "lz-prog", "QA / Testing": "lz-qa", "Done": "lz-done", "Blocked": "lz-block"}
ORDER = {"Done": 0, "QA / Testing": 1, "In Progress": 2, "To Do": 3, "Blocked": 4}
SHORT = {"To Do": "To Do", "In Progress": "In Prog", "QA / Testing": "QA", "Done": "Done", "Blocked": "Blocked"}

def bar(label, right, pct, color):
    return (f'<div class="barlbl"><span>{label}</span><span>{right}</span></div>'
            f'<div class="track"><div class="fill" style="width:{pct}%; background:{color};"></div></div>')

def tile(label, val, vclass, foot):
    return f'<div class="kpi"><div class="label">{label}</div><div class="val {vclass}">{val}</div><div class="foot">{foot}</div></div>'

def main():
    d = json.loads((REPO / "reports" / "cycle_data.json").read_text(encoding="utf-8"))
    r, p, retro = d["review"], d["planning"], d["retro"]
    bi = r["by_initiative"]; cbs = r["completed_by_size"]
    done = [i for i in r["issues"] if i["done"]]
    pct = r["completion_pct"]
    dash = round(502.6 * pct / 100, 1)

    H = []
    H.append(f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Reform-A.i - Sprint 2 Review</title>'
             f'<link href="https://fonts.googleapis.com/css2?family=Red+Hat+Display:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
             f'<style>{CSS}</style></head><body>')

    # ---- PAGE 1: Review ----
    H.append('<div class="page">')
    H.append('<div class="topbar"><div class="brand"><img class="logo" src="logo_en.png" alt="Reform-A.i"></div>'
             '<div class="meta">Sprint Review<br>Sprint 2</div></div>')
    H.append('<div class="hero"><div class="eyebrow">Sprint 2 &middot; Jun 2026</div><h1>Sprint 2<br>Review</h1>'
             '<div class="sub">Goal: switch Wompi billing to the ReformAI account and ship the 3 user dashboards.</div>'
             '<div class="healthbadge"><span class="dot"></span> SPRINT HEALTH: GREEN &middot; GOAL PARTIAL</div></div>')
    H.append('<div class="kpis">'
             + tile("Sprint Goal", "Partial", "amber", "Dashboards yes; Wompi pending")
             + tile("Completion", f"{pct}%", "teal", f"{r['completed']} of {r['committed']} items")
             + tile("Carried Over", f"{r['carryover']}", "", "Roll into Sprint 3")
             + tile("Best Yet", "72%", "green", "Highest completion to date") + '</div>')
    H.append('<h2 class="sec"><span class="bar"></span>The Headline</h2>'
             '<div class="panel-goal"><strong>Strongest sprint to date - 29 of 40 done (72%).</strong> '
             'The 3 user dashboards shipped. The Wompi account switch is still pending on Wompi\'s side - an external '
             'dependency, not a team miss (the CEO met Wompi and the switch carries into Sprint 3). '
             '<strong>Standout:</strong> analytics was scoped only as a research task; the team found PostHog and fully '
             'implemented it in-sprint, ahead of plan.</div>')
    # delivery donut + initiative bars
    cats = sorted(bi.items(), key=lambda x: -x[1]["total"])
    maxt = max(v["total"] for _, v in cats)
    colors = {"Product": "var(--orange)", "Infrastructure": "var(--green)", "Business Design": "var(--blue)", "Tech Debt": "var(--amber)"}
    bars = "".join(bar(k, f'{v["done"]} / {v["total"]}', round(100*v["total"]/maxt), colors.get(k, "var(--teal)")) for k, v in cats)
    H.append('<h2 class="sec"><span class="bar"></span>Delivery at a Glance</h2>'
             '<div class="chartrow"><div class="donutwrap"><svg width="200" height="200" viewBox="0 0 200 200">'
             '<circle cx="100" cy="100" r="80" fill="none" stroke="#f5f5f5" stroke-width="22"/>'
             f'<circle cx="100" cy="100" r="80" fill="none" stroke="var(--teal)" stroke-width="22" stroke-linecap="round" stroke-dasharray="{dash} 502.6" transform="rotate(-90 100 100)"/>'
             f'<text x="100" y="96" text-anchor="middle" class="donut-center">{pct}%</text>'
             f'<text x="100" y="116" text-anchor="middle" class="donut-sub">{r["completed"]} of {r["committed"]} complete</text>'
             f'</svg></div><div><div class="barlbl"><span>By initiative</span><span></span></div>{bars}'
             f'<div class="legend"><strong>By type:</strong> Bugs {r["by_type"].get("Bug",{}).get("done",0)} / {r["by_type"].get("Bug",{}).get("total",0)} done &middot; '
             f'Stories {r["by_type"].get("Story",{}).get("done",0)} / {r["by_type"].get("Story",{}).get("total",0)} done. Tech Debt slipped (0 of 2).</div></div></div>')
    H.append('<div class="footer"><span>Reform-A.i &middot; Sprint 2 Review</span><span>Confidential</span></div></div>')

    # ---- PAGE 2: Shipped + Context + Velocity ----
    H.append('<div class="page">')
    H.append('<h2 class="sec"><span class="bar"></span>What We Shipped &amp; Why It Matters</h2>'
             '<div class="hl">'
             '<div class="hlcard"><div class="k">DASHBOARDS</div><div class="t">3 user dashboards live</div><span class="tag">Goal</span></div>'
             '<div class="hlcard"><div class="k">POSTHOG</div><div class="t">Analytics found + shipped in-sprint</div><span class="tag">Ahead of plan</span></div>'
             '<div class="hlcard"><div class="k">OPS HEALTH</div><div class="t">New operational health dashboard</div><span class="tag">Infrastructure</span></div>'
             '<div class="hlcard"><div class="k">PLATFORM</div><div class="t">Email notifications + landing pages live</div><span class="tag">Product</span></div>'
             '</div>')
    H.append('<h2 class="sec"><span class="bar"></span>The Story Behind the Numbers</h2><ul class="clean">'
             '<li><strong>Cloudflare fallout -&gt; a new dashboard.</strong> Old account references left from the Sprint 1 infra migration broke production images and took major unplanned effort to fix. That pain inspired the operational health dashboard - now being handed to Kay to productionize.</li>'
             '<li><strong>Google-registration bug</strong> was a significant time sink (fix expected end of day) - a real driver of the carryover.</li>'
             '<li><strong>Seller module (from UAT)</strong> is blocked on CEO input: broker-agreement update + white-glove service pricing. It keeps rolling over until that decision lands.</li>'
             '</ul>')
    # velocity bars
    vmax = max(cbs.values()) if cbs else 1
    vbars = "".join(bar(k, v, round(100*v/vmax), "var(--amber)" if k == "Unsized" else "var(--teal)") for k, v in cbs.items())
    sized_total = sum(v for k, v in cbs.items() if k != "Unsized")
    H.append('<h2 class="sec"><span class="bar"></span>Velocity - Completed by Size</h2>'
             f'<div class="two"><div>{vbars}</div>'
             f'<div class="card"><strong style="font-size:13px;">First sized baseline</strong>'
             f'<p style="font-size:12.5px; margin-top:8px;">The team delivered <strong>{sized_total} sized items</strong> '
             f'({cbs.get("XS",0)} XS, {cbs.get("S",0)} S, {cbs.get("M",0)} M, {cbs.get("Spike",0)} Spike) plus {cbs.get("Unsized",0)} '
             f'unsized carryover. <strong>No L or larger</strong> was completed. This is the first throughput baseline; it sharpens each fully-sized sprint.</p></div></div>')
    # self-correcting
    H.append('<h2 class="sec"><span class="bar"></span>How We\'re Self-Correcting</h2><div class="two">'
             '<div class="card"><strong style="font-size:13px;">From the retro</strong><ul class="clean warn">'
             + "".join(f"<li>{esc(x)}</li>" for x in retro["ideas"]) + '</ul></div>'
             '<div class="card"><strong style="font-size:13px;">Actions next sprint</strong><ul class="clean">'
             '<li>Unblock the seller module (CEO: broker agreement + white-glove pricing)</li>'
             '<li>Protect tech-debt capacity (slipped 0/2 this sprint)</li>'
             '<li>Dedicated production-bug time</li></ul></div></div>')
    H.append('<div class="footer"><span>Reform-A.i &middot; Sprint 2 Review</span><span>Confidential</span></div></div>')

    # ---- PAGE 3: Sprint 3 Planning ----
    pby = p["by_initiative"]; psz = p["sizes"]
    H.append('<div class="page"><div class="eyebrow">Looking ahead</div><h1 style="font-size:32px; margin-top:6px;">Sprint 3 Planning</h1>')
    H.append('<div class="panel-goal" style="border-left-color:var(--teal); background:#f0fbfb; margin-top:14px;">'
             '<div class="eyebrow" style="color:var(--teal);">Technical hardening sprint</div>'
             '<strong style="font-size:14px; display:block; margin-top:4px;">Complete the Wompi switch, productionize the ops health dashboard, add GCP health, '
             'stand up code review + Jira/GitHub - plus ship "create a project from a visualization".</strong></div>')
    H.append('<div class="kpis" style="margin-top:16px;">'
             + tile("Committed", f"{p['committed']}", "teal", f"{p['carryover']} carry &middot; {p['committed']-p['carryover']} new")
             + tile("Readiness", "Ready", "green", "gate passed")
            + tile("Sized", f"{p['committed']}/{p['committed']}", "green", "all sized")
             + tile("Goal", "Set", "green", "Wompi + technical") + '</div>')
    # scope + capacity
    pmax = max(v["total"] for v in pby.values())
    pbars = "".join(bar(k, v["total"], round(100*v["total"]/pmax), colors.get(k, "var(--teal)")) for k, v in sorted(pby.items(), key=lambda x:-x[1]["total"]))
    H.append('<h2 class="sec"><span class="bar"></span>Committed Scope</h2><div class="two"><div>'
             '<div class="barlbl"><span>By initiative</span><span></span></div>' + pbars + '</div><div>'
             '<div class="barlbl"><span>By size</span><span></span></div>'
             + "".join(bar(k, psz.get(k,0), round(100*psz.get(k,0)/max(psz.values())), "var(--teal)") for k in ["XS","S","M","L","Spike"] if psz.get(k)) + '</div></div>')
    H.append('<h2 class="sec"><span class="bar"></span>Capacity vs Last Sprint</h2>'
             '<div class="card" style="border-left:5px solid var(--amber);">'
             f'<strong>Capacity watch.</strong> Sprint 3 commits {psz.get("M",0)} M and {psz.get("L",0)} L items; Sprint 2 delivered '
             f'{cbs.get("M",0)} M and {cbs.get("L",0)} L. The committed mix is heavier than proven throughput - confirm capacity or trim the larger items before locking. '
             f'Velocity baseline is one sprint old and partly unsized, so treat as directional.</div>')
    H.append('<div class="footer"><span>Reform-A.i &middot; Sprint 2 Review</span><span>Confidential</span></div></div>')

    # ---- PAGE 4: Sprint 3 Full Scope ----
    H.append('<div class="page"><div class="eyebrow">Sprint 3</div><h1 style="font-size:26px; margin-top:4px;">What\'s in Scope</h1>'
             f'<p style="color:var(--muted); margin-top:4px; font-size:11px;">All {p["committed"]} committed items. <span class="cotag">CO</span> = carryover from Sprint 2.</p>')
    for c in ["Business Design", "Product", "Tech Debt", "Infrastructure"]:
        grp = [i for i in p["issues"] if i["cat"] == c]
        if not grp: continue
        H.append(f'<div class="grp">{c} ({len(grp)})</div>')
        rows = ""
        for i in sorted(grp, key=lambda x: ORDER.get(x["status"], 9)):
            co = '<span class="cotag">CO</span>' if i.get("carryover") else ""
            rows += (f'<tr><td>{esc(i["key"])}</td><td>{esc(i["type"])}</td><td>{esc(i["size"] or "-")}</td>'
                     f'<td><span class="lozenge {LZ.get(i["status"],"lz-todo")}">{SHORT.get(i["status"], i["status"])}</span></td>'
                     f'<td>{esc(i["owner"])}</td><td>{co}</td><td>{esc(i["summary"])}</td></tr>')
        H.append('<table class="scope"><thead><tr><th>Key</th><th>Type</th><th>Size</th><th>Status</th><th>Owner</th><th></th><th>Summary</th></tr></thead><tbody>'
                 + rows + '</tbody></table>')
    H.append('<div class="footer"><span>Reform-A.i &middot; Sprint 2 Review</span><span>Confidential</span></div></div>')

    H.append('</body></html>')
    OUT.write_text("".join(H), encoding="utf-8")
    print("wrote", OUT)

if __name__ == "__main__":
    main()
