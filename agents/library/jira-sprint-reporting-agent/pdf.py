#!/usr/bin/env python3
"""
Generate the branded management report (HTML) for the current cycle from
reports/cycle_data.json, English only. Reuses the ReformAI brand CSS + logo.
Render to PDF afterwards with Edge headless (--print-to-pdf).

Narrative (headline, cards, story, actions) is authored per-cycle for THIS cycle
(Sprint 3 review / Sprint 4 planning). Ticket titles + retro text stay verbatim.
"""
from __future__ import annotations
import json, html as _html
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

def esc(t): return _html.escape(str(t), quote=False)

CSS = (REPO / "reports" / "sprint-1-review.html").read_text(encoding="utf-8").split("<style>")[1].split("</style>")[0]
OVERRIDE = ("body{font-size:12.5px;}"
            ".hero{margin-top:14px;} .hero h1{font-size:34px; line-height:1.04;} .hero .sub{font-size:14px; margin-top:6px;}"
            ".healthbadge{margin-top:12px; font-size:13px; padding:7px 14px;}"
            ".kpis{margin-top:16px;} .kpi .val{font-size:23px;}"
            "h2.sec{margin:16px 0 9px; font-size:18px;} .panel-goal{padding:12px 16px;}"
            ".hlcard{padding:11px 13px;} .track{margin-bottom:9px;}"
            "table.scope{font-size:8.6px;} table.scope th{padding:2px 5px;} table.scope td{padding:1.5px 5px; white-space:nowrap;}"
            " .grp{margin:8px 0 2px; font-size:11px;}")

def trunc(s, n=70):
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"

LZ = {"To Do": "lz-todo", "In Progress": "lz-prog", "QA / Testing": "lz-qa", "Done": "lz-done", "Blocked": "lz-block"}
ORDER = {"Done": 0, "QA / Testing": 1, "In Progress": 2, "To Do": 3, "Blocked": 4}

# ---- per-cycle English narrative (Sprint 3 review / Sprint 4 planning) --------
S = {
  "logo": "logo_en.png", "meta": "Sprint Review", "out": "sprint-3-review.html",
  "eyebrow1": "Sprint 3 &middot; Jul 2026", "h1": "Sprint 3<br>Review",
  "sub": "Goal: technical hardening - Wompi switch, ops health + Google Cloud monitoring, code review, and create-a-project-from-a-visualization.",
  "badge": "SPRINT HEALTH: GREEN &middot; GOAL MET",
  "kpi": [("Sprint Goal","Met","green","4 of 6 pillars done"),
          ("Completion","{pct}%","teal","{done} of {committed} items"),
          ("Committed Work","{cstart_pct}%","green","{cstart_done} of {cstart} committed-at-start"),
          ("Carried Over","{carry}","","Roll into Sprint 4")],
  "s_headline": "The Headline",
  "headline": ("<strong>The Wompi switch landed - {done} of {committed} done ({pct}%).</strong> "
               "Of the {cstart} items committed at sprint start, {cstart_done} shipped ({cstart_pct}%); the team also absorbed "
               "{added} items added mid-sprint and finished {added_done} of them. The Sprint 2 external blocker is resolved, "
               "code review is stood up in GitHub, and the operational health dashboard is in production with Google Cloud "
               "monitoring added. Four of six goal pillars are complete; the other two are in progress, not missed."),
  "s_delivery": "Delivery at a Glance", "byinit": "By initiative",
  "bytype": "<strong>By type:</strong> Bugs {bd} / {bt} done &middot; Stories {sd} / {st} done.",
  "complete": "{done} of {committed} complete",
  "s_shipped": "What We Shipped &amp; Why It Matters",
  "cards": [("WOMPI","Account switched to the ReformAI bank account","Goal"),
            ("CODE REVIEW","Stood up in GitHub","Goal"),
            ("OPS HEALTH","Operational health dashboard productionized","Goal"),
            ("GCP MONITORING","Google Cloud health monitoring added","Goal"),
            ("ASSET PIPELINE","Asset Discovery Pipeline shipped","Product"),
            ("TEAMS","Team member functionality delivered","Product")],
  "s_story": "The Story Behind the Numbers",
  "story": ["<strong>Scope grew mid-sprint.</strong> 7 items were added after the sprint started; the team completed 4. The 3 that carried over are all reactive homeowner-registration bugs - the reason a <strong>Production Bugs bucket</strong> now exists in Sprint 4.",
            "<strong>Prod regressions from hotfixes.</strong> Flagged in the retro; it motivates a per-build test suite and standard user-checks across all tabs and pages.",
            "<strong>Supplier Catalog is hard to design</strong> without enough client catalogs to generalize from. It carries into Sprint 4 and needs unblocking (sample catalogs, or a research spike) before more design effort.",
            "<strong>Venezuela new-market design</strong> pulled focus from sprint initiatives."],
  "s_velocity": "Velocity - Completed by Size", "v_baseline": "M throughput doubled",
  "v_text": ("The team delivered <strong>{sized} sized items</strong> ({xs} XS, {s} S, {m} M, {spk} Spike) plus {un} "
             "unsized. Mid-size (M) throughput <strong>doubled versus Sprint 2</strong> (3 &rarr; {m}). <strong>No L or larger</strong> "
             "was completed - the second sprint running - which is the key input to Sprint 4 capacity."),
  "s_selfcorr": "How We're Self-Correcting", "fromretro": "From the retro", "actions": "Actions next sprint",
  "action_items": ["Unblock Supplier Catalog before designing it (sample catalogs, or a spike)",
                   "Stand up a per-build test suite to catch prod regressions",
                   "Track ad-hoc bugs against the new Production Bugs bucket"],
  "ahead": "Looking ahead", "h1_plan": "Sprint 4 Planning", "plan_eyebrow": "Infrastructure + Partner UI",
  "plan_goal": "Compiled Infrastructure Report + GCP Visualization Insight + Partner Projects UI Overhaul.",
  "kpi_plan": [("Committed","{pcommitted}","teal","{pcarry} carry &middot; {new} new"),
               ("Readiness","Ready","green","gate passed"),
               ("Bugs","Bucketed","amber","unsized by design"),
               ("Goal","Set","green","infra + partner UI")],
  "s_scope": "Committed Scope", "bysize": "By size", "s_capacity": "Capacity vs Last Sprint",
  "cap_text": ("<strong>Capacity watch.</strong> Sprint 4 commits {m} M and {l} L items; Sprint 3 delivered "
               "{dm} M and {dl} L (zero L). The committed mix is heavier than proven throughput - confirm capacity or "
               "trim/split the larger items before locking. The two carryover L's are Business Design (owner-acknowledged); "
               "RAI-546 (Supplier Catalog) is the one to watch, as the retro flagged it blocked."),
  "eyebrow3": "Sprint 4", "h1_scope": "What's in Scope",
  "scope_intro": 'All {pcommitted} committed items. <span class="cotag">CO</span> = carryover from Sprint 3.',
  "cols": ["Key","Type","Size","Status","Owner","","Summary"],
  "st": {"To Do":"To Do","In Progress":"In Prog","QA / Testing":"QA","Done":"Done","Blocked":"Blocked"},
  "cat": {"Business Design":"Business Design","Product":"Product","Tech Debt":"Tech Debt","Infrastructure":"Infrastructure"},
  "footer": "Reform-A.i &middot; Sprint 3 Review", "conf": "Confidential",
}

def bar(label, right, pct, color):
    return (f'<div class="barlbl"><span>{label}</span><span>{right}</span></div>'
            f'<div class="track"><div class="fill" style="width:{pct}%; background:{color};"></div></div>')
def tile(label, val, vclass, foot):
    return f'<div class="kpi"><div class="label">{label}</div><div class="val {vclass}">{val}</div><div class="foot">{foot}</div></div>'

COLORS = {"Product":"var(--orange)","Infrastructure":"var(--green)","Business Design":"var(--blue)","Tech Debt":"var(--amber)"}

def build(d):
    r, p, retro = d["review"], d["planning"], d["retro"]
    bi = r["by_initiative"]; cbs = r["completed_by_size"]; bt = r["by_type"]
    sc = r["scope"]; cstart = sc["committed_at_start"]; added = sc["added_mid_sprint"]
    pct = r["completion_pct"]; dash = round(502.6*pct/100, 1)
    F = dict(pct=pct, done=r["completed"], committed=r["committed"], carry=r["carryover"],
             new=p["committed"]-p["carryover"], pcommitted=p["committed"], pcarry=p["carryover"],
             cstart=cstart["count"], cstart_done=cstart["done"], cstart_pct=cstart["pct"],
             added=added["count"], added_done=added["done"])
    foot = f'<div class="footer"><span>{S["footer"]}</span><span>{S["conf"]}</span></div>'
    H = []

    # PAGE 1
    H.append('<div class="page">')
    H.append(f'<div class="topbar"><div class="brand"><img class="logo" src="{S["logo"]}" alt="Reform-A.i"></div>'
             f'<div class="meta">{S["meta"]}<br>{esc(r["sprint"])}</div></div>')
    H.append(f'<div class="hero"><div class="eyebrow">{S["eyebrow1"]}</div><h1>{S["h1"]}</h1>'
             f'<div class="sub">{S["sub"]}</div><div class="healthbadge"><span class="dot"></span> {S["badge"]}</div></div>')
    H.append('<div class="kpis">' + "".join(tile(l, v.format(**F), c, ft.format(**F)) for l, v, c, ft in S["kpi"]) + '</div>')
    H.append(f'<h2 class="sec"><span class="bar"></span>{S["s_headline"]}</h2><div class="panel-goal">{S["headline"].format(**F)}</div>')
    cats = sorted(bi.items(), key=lambda x: -x[1]["total"]); maxt = max(v["total"] for _, v in cats)
    bars = "".join(bar(S["cat"].get(k, k), f'{v["done"]} / {v["total"]}', round(100*v["total"]/maxt), COLORS.get(k, "var(--teal)")) for k, v in cats)
    bytype = S["bytype"].format(bd=bt.get("Bug",{}).get("done",0), bt=bt.get("Bug",{}).get("total",0),
                                sd=bt.get("Story",{}).get("done",0), st=bt.get("Story",{}).get("total",0))
    H.append(f'<h2 class="sec"><span class="bar"></span>{S["s_delivery"]}</h2><div class="chartrow"><div class="donutwrap">'
             '<svg width="200" height="200" viewBox="0 0 200 200"><circle cx="100" cy="100" r="80" fill="none" stroke="#f5f5f5" stroke-width="22"/>'
             f'<circle cx="100" cy="100" r="80" fill="none" stroke="var(--teal)" stroke-width="22" stroke-linecap="round" stroke-dasharray="{dash} 502.6" transform="rotate(-90 100 100)"/>'
             f'<text x="100" y="96" text-anchor="middle" class="donut-center">{pct}%</text>'
             f'<text x="100" y="116" text-anchor="middle" class="donut-sub">{S["complete"].format(**F)}</text></svg></div>'
             f'<div><div class="barlbl"><span>{S["byinit"]}</span><span></span></div>{bars}<div class="legend">{bytype}</div></div></div>')
    H.append(foot + '</div>')

    # PAGE 2
    H.append('<div class="page">')
    H.append(f'<h2 class="sec"><span class="bar"></span>{S["s_shipped"]}</h2><div class="hl">'
             + "".join(f'<div class="hlcard"><div class="k">{k}</div><div class="t">{t}</div><span class="tag">{tag}</span></div>' for k, t, tag in S["cards"]) + '</div>')
    H.append(f'<h2 class="sec"><span class="bar"></span>{S["s_story"]}</h2><ul class="clean">'
             + "".join(f"<li>{x}</li>" for x in S["story"]) + '</ul>')
    H.append(foot + '</div>')

    # PAGE 3: velocity + self-correcting
    H.append('<div class="page">')
    vmax = max(cbs.values()) if cbs else 1
    vbars = "".join(bar(k, v, round(100*v/vmax), "var(--amber)" if k == "Unsized" else "var(--teal)") for k, v in cbs.items())
    sized = sum(v for k, v in cbs.items() if k != "Unsized")
    vtext = S["v_text"].format(sized=sized, xs=cbs.get("XS",0), s=cbs.get("S",0), m=cbs.get("M",0), spk=cbs.get("Spike",0), un=cbs.get("Unsized",0))
    H.append(f'<h2 class="sec"><span class="bar"></span>{S["s_velocity"]}</h2><div class="two"><div>{vbars}</div>'
             f'<div class="card"><strong style="font-size:13px;">{S["v_baseline"]}</strong><p style="font-size:12.5px; margin-top:8px;">{vtext}</p></div></div>')
    retro_ideas = "".join(f"<li>{esc(x)}</li>" for x in retro["ideas"])
    acts = "".join(f"<li>{x}</li>" for x in S["action_items"])
    H.append(f'<h2 class="sec"><span class="bar"></span>{S["s_selfcorr"]}</h2><div class="two">'
             f'<div class="card"><strong style="font-size:13px;">{S["fromretro"]}</strong><ul class="clean warn">{retro_ideas}</ul></div>'
             f'<div class="card"><strong style="font-size:13px;">{S["actions"]}</strong><ul class="clean">{acts}</ul></div></div>')
    H.append(foot + '</div>')

    # PAGE 4: planning
    pby = p["by_initiative"]; psz = p["sizes"]
    H.append(f'<div class="page"><div class="eyebrow">{S["ahead"]}</div><h1 style="font-size:32px; margin-top:6px;">{S["h1_plan"]}</h1>')
    H.append(f'<div class="panel-goal" style="border-left-color:var(--teal); background:#f0fbfb; margin-top:14px;">'
             f'<div class="eyebrow" style="color:var(--teal);">{S["plan_eyebrow"]}</div>'
             f'<strong style="font-size:14px; display:block; margin-top:4px;">{S["plan_goal"]}</strong></div>')
    H.append('<div class="kpis" style="margin-top:16px;">' + "".join(tile(l, v.format(**F), c, ft.format(**F)) for l, v, c, ft in S["kpi_plan"]) + '</div>')
    pmax = max(v["total"] for v in pby.values())
    pbars = "".join(bar(S["cat"].get(k, k), v["total"], round(100*v["total"]/pmax), COLORS.get(k, "var(--teal)")) for k, v in sorted(pby.items(), key=lambda x:-x[1]["total"]))
    smax = max(psz.values())
    sbars = "".join(bar(k, psz.get(k,0), round(100*psz.get(k,0)/smax), "var(--teal)") for k in ["XS","S","M","L","Spike"] if psz.get(k))
    H.append(f'<h2 class="sec"><span class="bar"></span>{S["s_scope"]}</h2><div class="two"><div>'
             f'<div class="barlbl"><span>{S["byinit"]}</span><span></span></div>{pbars}</div><div>'
             f'<div class="barlbl"><span>{S["bysize"]}</span><span></span></div>{sbars}</div></div>')
    cap = S["cap_text"].format(m=psz.get("M",0), l=psz.get("L",0), dm=cbs.get("M",0), dl=cbs.get("L",0))
    H.append(f'<h2 class="sec"><span class="bar"></span>{S["s_capacity"]}</h2><div class="card" style="border-left:5px solid var(--amber);">{cap}</div>')
    H.append(foot + '</div>')

    # PAGE 5: scope
    H.append(f'<div class="page"><div class="eyebrow">{S["eyebrow3"]}</div><h1 style="font-size:26px; margin-top:4px;">{S["h1_scope"]}</h1>'
             f'<p style="color:var(--muted); margin-top:4px; font-size:11px;">{S["scope_intro"].format(**F)}</p>')
    for c in ["Business Design", "Product", "Tech Debt", "Infrastructure"]:
        grp = [i for i in p["issues"] if i["cat"] == c]
        if not grp: continue
        H.append(f'<div class="grp">{S["cat"][c]} ({len(grp)})</div>')
        rows = ""
        for i in sorted(grp, key=lambda x: ORDER.get(x["status"], 9)):
            co = '<span class="cotag">CO</span>' if i.get("carryover") else ""
            rows += (f'<tr><td>{esc(i["key"])}</td><td>{esc(i["type"])}</td><td>{esc(i["size"] or "-")}</td>'
                     f'<td><span class="lozenge {LZ.get(i["status"],"lz-todo")}">{S["st"].get(i["status"], i["status"])}</span></td>'
                     f'<td>{esc(i["owner"])}</td><td>{co}</td><td>{esc(trunc(i["summary"]))}</td></tr>')
        cols = "".join(f"<th>{c2}</th>" for c2 in S["cols"])
        H.append(f'<table class="scope"><thead><tr>{cols}</tr></thead><tbody>{rows}</tbody></table>')
    H.append(foot + '</div>')
    return "".join(H)

def main():
    d = json.loads((REPO / "reports" / "cycle_data.json").read_text(encoding="utf-8"))
    head = ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>Reform-A.i - Sprint 3 Review</title>'
            '<link href="https://fonts.googleapis.com/css2?family=Red+Hat+Display:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
            f'<style>{CSS}</style><style>{OVERRIDE}</style></head><body>')
    html = head + build(d) + "</body></html>"
    out = REPO / "reports" / S["out"]
    out.write_text(html, encoding="utf-8")
    print("wrote", out, "(EN)")

if __name__ == "__main__":
    main()
