#!/usr/bin/env python3
"""
Generate the branded Sprint 2 management report (HTML) from reports/cycle_data.json,
in English and Spanish. Reuses the ReformAI brand CSS + the localized logo. Render
each with Edge headless afterwards.

Framework + agent-authored narrative are translated; Jira ticket titles and verbatim
retro content stay in their source language (data, not chrome).
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
            ".hlcard{padding:11px 13px;} .track{margin-bottom:9px;}")

LZ = {"To Do": "lz-todo", "In Progress": "lz-prog", "QA / Testing": "lz-qa", "Done": "lz-done", "Blocked": "lz-block"}
ORDER = {"Done": 0, "QA / Testing": 1, "In Progress": 2, "To Do": 3, "Blocked": 4}

STR = {
 "en": {
  "logo": "logo_en.png", "meta": "Sprint Review", "out": "sprint-2-review.html",
  "eyebrow1": "Sprint 2 &middot; Jun 2026", "h1": "Sprint 2<br>Review",
  "sub": "Goal: switch Wompi billing to the ReformAI account and ship the 3 user dashboards.",
  "badge": "SPRINT HEALTH: GREEN &middot; GOAL PARTIAL",
  "kpi": [("Sprint Goal","Partial","amber","Dashboards yes; Wompi pending"),
          ("Completion","{pct}%","teal","{done} of {committed} items"),
          ("Carried Over","{carry}","","Roll into Sprint 3"),
          ("Best Yet","{pct}%","green","Highest completion to date")],
  "s_headline": "The Headline",
  "headline": ("<strong>Strongest sprint to date - {done} of {committed} done ({pct}%).</strong> "
               "The 3 user dashboards shipped. The Wompi account switch is still pending on Wompi's side - an external "
               "dependency, not a team miss (the CEO met Wompi and the switch carries into Sprint 3). "
               "<strong>Standout:</strong> analytics was scoped only as a research task; the team found PostHog and fully "
               "implemented it in-sprint, ahead of plan."),
  "s_delivery": "Delivery at a Glance", "byinit": "By initiative",
  "bytype": "<strong>By type:</strong> Bugs {bd} / {bt} done &middot; Stories {sd} / {st} done. Tech Debt slipped (0 of 2).",
  "complete": "{done} of {committed} complete",
  "s_shipped": "What We Shipped &amp; Why It Matters",
  "cards": [("DASHBOARDS","3 user dashboards live","Goal"),
            ("POSTHOG","Analytics found + shipped in-sprint","Ahead of plan"),
            ("OPS HEALTH","New operational health dashboard","Infrastructure"),
            ("EMAIL","Notification templates for every user type","Visuals this sprint"),
            ("ADMIN LOGS","User activity logs in the admin module","Product"),
            ("PLATFORM","Landing pages live + email notifications","Product")],
  "s_story": "The Story Behind the Numbers",
  "story": ["<strong>Cloudflare fallout -&gt; a new dashboard.</strong> Old account references left from the Sprint 1 infra migration broke production images and took major unplanned effort to fix. That pain inspired the operational health dashboard - now being handed to Kay to productionize.",
            "<strong>Google-registration bug</strong> was a significant time sink (fix expected end of day) - a real driver of the carryover.",
            "<strong>Seller module (from UAT)</strong> is blocked on CEO input: broker-agreement update + white-glove service pricing. It keeps rolling over until that decision lands."],
  "s_velocity": "Velocity - Completed by Size", "v_baseline": "First sized baseline",
  "v_text": ("The team delivered <strong>{sized} sized items</strong> ({xs} XS, {s} S, {m} M, {spk} Spike) plus {un} "
             "unsized carryover. <strong>No L or larger</strong> was completed. This is the first throughput baseline; it sharpens each fully-sized sprint."),
  "s_selfcorr": "How We're Self-Correcting", "fromretro": "From the retro", "actions": "Actions next sprint",
  "action_items": ["Unblock the seller module (CEO: broker agreement + white-glove pricing)",
                   "Protect tech-debt capacity (slipped 0/2 this sprint)", "Dedicated production-bug time"],
  "ahead": "Looking ahead", "h1_plan": "Sprint 3 Planning", "plan_eyebrow": "Technical hardening sprint",
  "plan_goal": ('Complete the Wompi switch, productionize the ops health dashboard, add GCP health, '
                'stand up code review + Jira/GitHub - plus ship "create a project from a visualization".'),
  "kpi_plan": [("Committed","{committed}","teal","{carry} carry &middot; {new} new"),
               ("Readiness","Ready","green","gate passed"),
               ("Sized","{committed}/{committed}","green","all sized"),
               ("Goal","Set","green","Wompi + technical")],
  "s_scope": "Committed Scope", "bysize": "By size", "s_capacity": "Capacity vs Last Sprint",
  "cap_text": ("<strong>Capacity watch.</strong> Sprint 3 commits {m} M and {l} L items; Sprint 2 delivered "
               "{dm} M and {dl} L. The committed mix is heavier than proven throughput - confirm capacity or trim the larger items before locking. "
               "Velocity baseline is one sprint old and partly unsized, so treat as directional."),
  "eyebrow3": "Sprint 3", "h1_scope": "What's in Scope",
  "scope_intro": 'All {committed} committed items. <span class="cotag">CO</span> = carryover from Sprint 2.',
  "cols": ["Key","Type","Size","Status","Owner","","Summary"],
  "st": {"To Do":"To Do","In Progress":"In Prog","QA / Testing":"QA","Done":"Done","Blocked":"Blocked"},
  "cat": {"Business Design":"Business Design","Product":"Product","Tech Debt":"Tech Debt","Infrastructure":"Infrastructure"},
  "footer": "Reform-A.i &middot; Sprint 2 Review", "conf": "Confidential",
 },
 "es": {
  "logo": "logo_es.png", "meta": "Revisión de Sprint", "out": "sprint-2-review-es.html",
  "eyebrow1": "Sprint 2 &middot; Jun 2026", "h1": "Revisión<br>Sprint 2",
  "sub": "Objetivo: cambiar la facturación de Wompi a la cuenta de ReformAI y entregar los 3 tableros de usuario.",
  "badge": "ESTADO DEL SPRINT: VERDE &middot; OBJETIVO PARCIAL",
  "kpi": [("Objetivo","Parcial","amber","Tableros sí; Wompi pendiente"),
          ("Completado","{pct}%","teal","{done} de {committed} ítems"),
          ("Trasladado","{carry}","","Pasan al Sprint 3"),
          ("Mejor a la fecha","{pct}%","green","Mayor completado hasta ahora")],
  "s_headline": "Lo Más Importante",
  "headline": ("<strong>El sprint más fuerte hasta la fecha - {done} de {committed} ({pct}%).</strong> "
               "Los 3 tableros de usuario se entregaron. El cambio de la cuenta Wompi sigue pendiente por parte de Wompi - una "
               "dependencia externa, no una falla del equipo (el CEO se reunió con Wompi y el cambio pasa al Sprint 3). "
               "<strong>Destacado:</strong> el análisis estaba previsto solo como tarea de investigación; el equipo encontró PostHog "
               "y lo implementó por completo dentro del sprint, adelantándose al plan."),
  "s_delivery": "Entrega de un Vistazo", "byinit": "Por iniciativa",
  "bytype": "<strong>Por tipo:</strong> Bugs {bd} / {bt} &middot; Historias {sd} / {st}. La deuda técnica se quedó atrás (0 de 2).",
  "complete": "{done} de {committed} completados",
  "s_shipped": "Lo Que Entregamos y Por Qué Importa",
  "cards": [("TABLEROS","3 tableros de usuario en vivo","Objetivo"),
            ("POSTHOG","Análisis encontrado + implementado en el sprint","Adelanta el plan"),
            ("SALUD OPS","Nuevo tablero de salud operativa","Infraestructura"),
            ("CORREOS","Plantillas de notificación para cada tipo de usuario","Diseño este sprint"),
            ("LOGS ADMIN","Registros de actividad de usuario en el módulo admin","Producto"),
            ("PLATAFORMA","Páginas de aterrizaje en vivo + notificaciones por correo","Producto")],
  "s_story": "La Historia Detrás de los Números",
  "story": ["<strong>Secuela de Cloudflare -&gt; un nuevo tablero.</strong> Referencias de cuentas antiguas que quedaron de la migración de infraestructura del Sprint 1 dañaron las imágenes en producción y costaron un esfuerzo no planeado significativo. Ese dolor inspiró el tablero de salud operativa - ahora se entrega a Kay para llevarlo a producción.",
            "<strong>El bug de registro con Google</strong> consumió mucho tiempo (corrección esperada para fin de día) - un motor real del trabajo trasladado.",
            "<strong>El módulo de vendedor (de UAT)</strong> está bloqueado esperando decisión del CEO: actualización del acuerdo de corretaje + precios del servicio White-Glove. Seguirá trasladándose hasta que esa decisión llegue."],
  "s_velocity": "Velocidad - Completado por Tamaño", "v_baseline": "Primera línea base con tamaños",
  "v_text": ("El equipo entregó <strong>{sized} ítems con tamaño</strong> ({xs} XS, {s} S, {m} M, {spk} Spike) más {un} "
             "trasladados sin tamaño. <strong>No se completó ningún L o mayor</strong>. Esta es la primera línea base de rendimiento; se afina con cada sprint totalmente dimensionado."),
  "s_selfcorr": "Cómo Nos Auto-Corregimos", "fromretro": "De la retro", "actions": "Acciones próximo sprint",
  "action_items": ["Desbloquear el módulo de vendedor (CEO: acuerdo de corretaje + precios White-Glove)",
                   "Proteger capacidad para deuda técnica (0/2 este sprint)", "Tiempo dedicado a bugs de producción"],
  "ahead": "Mirando hacia adelante", "h1_plan": "Planeación Sprint 3", "plan_eyebrow": "Sprint de fortalecimiento técnico",
  "plan_goal": ('Completar el cambio de Wompi, llevar a producción el tablero de salud operativa, agregar salud de GCP, '
                'montar revisión de código + Jira/GitHub - y entregar "crear un proyecto desde una visualización".'),
  "kpi_plan": [("Comprometido","{committed}","teal","{carry} traslado &middot; {new} nuevos"),
               ("Preparación","Listo","green","filtro aprobado"),
               ("Dimensionado","{committed}/{committed}","green","todo con tamaño"),
               ("Objetivo","Definido","green","Wompi + técnico")],
  "s_scope": "Alcance Comprometido", "bysize": "Por tamaño", "s_capacity": "Capacidad vs Sprint Anterior",
  "cap_text": ("<strong>Alerta de capacidad.</strong> El Sprint 3 compromete {m} M y {l} L; el Sprint 2 entregó "
               "{dm} M y {dl} L. La mezcla comprometida es más pesada que el rendimiento comprobado - confirme la capacidad o reduzca los ítems grandes antes de cerrar. "
               "La línea base de velocidad tiene un sprint de antigüedad y está parcialmente sin tamaños, trátela como referencial."),
  "eyebrow3": "Sprint 3", "h1_scope": "Qué Está en el Alcance",
  "scope_intro": 'Los {committed} ítems comprometidos. <span class="cotag">CO</span> = trasladado del Sprint 2.',
  "cols": ["Clave","Tipo","Tamaño","Estado","Responsable","","Resumen"],
  "st": {"To Do":"Por Hacer","In Progress":"En Curso","QA / Testing":"QA","Done":"Hecho","Blocked":"Bloqueado"},
  "cat": {"Business Design":"Diseño de Negocio","Product":"Producto","Tech Debt":"Deuda Técnica","Infrastructure":"Infraestructura"},
  "footer": "Reform-A.i &middot; Revisión Sprint 2", "conf": "Confidencial",
 },
}

def bar(label, right, pct, color):
    return (f'<div class="barlbl"><span>{label}</span><span>{right}</span></div>'
            f'<div class="track"><div class="fill" style="width:{pct}%; background:{color};"></div></div>')
def tile(label, val, vclass, foot):
    return f'<div class="kpi"><div class="label">{label}</div><div class="val {vclass}">{val}</div><div class="foot">{foot}</div></div>'

COLORS = {"Product":"var(--orange)","Infrastructure":"var(--green)","Business Design":"var(--blue)","Tech Debt":"var(--amber)"}

def build(lang, d):
    S = STR[lang]
    r, p, retro = d["review"], d["planning"], d["retro"]
    bi = r["by_initiative"]; cbs = r["completed_by_size"]; bt = r["by_type"]
    pct = r["completion_pct"]; dash = round(502.6*pct/100, 1)
    F = dict(pct=pct, done=r["completed"], committed=r["committed"], carry=r["carryover"],
             new=p["committed"]-p["carryover"])
    foot = f'<div class="footer"><span>{S["footer"]}</span><span>{S["conf"]}</span></div>'
    H = []

    # PAGE 1
    H.append('<div class="page">')
    H.append(f'<div class="topbar"><div class="brand"><img class="logo" src="{S["logo"]}" alt="Reform-A.i"></div>'
             f'<div class="meta">{S["meta"]}<br>Sprint 2</div></div>')
    H.append(f'<div class="hero"><div class="eyebrow">{S["eyebrow1"]}</div><h1>{S["h1"]}</h1>'
             f'<div class="sub">{S["sub"]}</div><div class="healthbadge"><span class="dot"></span> {S["badge"]}</div></div>')
    H.append('<div class="kpis">' + "".join(tile(l, v.format(**F), c, ft.format(**F)) for l, v, c, ft in S["kpi"]) + '</div>')
    H.append(f'<h2 class="sec"><span class="bar"></span>{S["s_headline"]}</h2><div class="panel-goal">{S["headline"].format(**F)}</div>')
    cats = sorted(bi.items(), key=lambda x: -x[1]["total"]); maxt = max(v["total"] for _, v in cats)
    bars = "".join(bar(S["cat"][k], f'{v["done"]} / {v["total"]}', round(100*v["total"]/maxt), COLORS.get(k, "var(--teal)")) for k, v in cats)
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

    # PAGE 4: Sprint 3 planning
    pby = p["by_initiative"]; psz = p["sizes"]
    H.append(f'<div class="page"><div class="eyebrow">{S["ahead"]}</div><h1 style="font-size:32px; margin-top:6px;">{S["h1_plan"]}</h1>')
    H.append(f'<div class="panel-goal" style="border-left-color:var(--teal); background:#f0fbfb; margin-top:14px;">'
             f'<div class="eyebrow" style="color:var(--teal);">{S["plan_eyebrow"]}</div>'
             f'<strong style="font-size:14px; display:block; margin-top:4px;">{S["plan_goal"]}</strong></div>')
    H.append('<div class="kpis" style="margin-top:16px;">' + "".join(tile(l, v.format(**F), c, ft.format(**F)) for l, v, c, ft in S["kpi_plan"]) + '</div>')
    pmax = max(v["total"] for v in pby.values())
    pbars = "".join(bar(S["cat"][k], v["total"], round(100*v["total"]/pmax), COLORS.get(k, "var(--teal)")) for k, v in sorted(pby.items(), key=lambda x:-x[1]["total"]))
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
                     f'<td>{esc(i["owner"])}</td><td>{co}</td><td>{esc(i["summary"])}</td></tr>')
        cols = "".join(f"<th>{c2}</th>" for c2 in S["cols"])
        H.append(f'<table class="scope"><thead><tr>{cols}</tr></thead><tbody>{rows}</tbody></table>')
    H.append(foot + '</div>')
    return "".join(H)

def main():
    d = json.loads((REPO / "reports" / "cycle_data.json").read_text(encoding="utf-8"))
    head = ('<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><title>Reform-A.i - Sprint 2 Review (ES/EN)</title>'
            '<link href="https://fonts.googleapis.com/css2?family=Red+Hat+Display:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
            f'<style>{CSS}</style><style>{OVERRIDE}</style></head><body>')
    # Spanish section first, then English section, in one document.
    html = head + build("es", d) + build("en", d) + "</body></html>"
    out = REPO / "reports" / "sprint-2-review.html"
    out.write_text(html, encoding="utf-8")
    print("wrote", out, "(ES + EN, one document)")

if __name__ == "__main__":
    main()
