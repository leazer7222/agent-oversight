#!/usr/bin/env python3
"""
Token-based sprint cycle runner (no MCP). Uses the Atlassian API token (Basic auth)
to read Jira + Confluence and author the Confluence pages + PDF via REST.

Stages (default: gather only, prints summary + writes reports/cycle_data.json):
  --gather-only   read Jira (closed + future sprint) + retro page; print + save JSON
Author stages are added once the gathered data is validated.

ENV (.env.local): ATLASSIAN_EMAIL, ATLASSIAN_API_TOKEN, ATLASSIAN_CLOUD_ID (optional).
"""
from __future__ import annotations
import base64, json, sys
from pathlib import Path
import httpx

REPO = Path(__file__).resolve().parents[3]
SITE = "https://reform-ai-team.atlassian.net"
BOARD = 3
SPACE_KEY = "RAPD"
# Retro page is auto-discovered by title ("<closed sprint name> Retro") in SPACE_KEY.
# Override per-run with RETRO_PAGE_ID_OVERRIDE if the page uses a non-standard title.
RETRO_PAGE_ID_OVERRIDE = None

EPIC_CAT = {  # parent epic key -> initiative
    "RAI-629": "Business Design",
    "RAI-558": "Tech Debt",
    "RAI-161": "Infrastructure",
    "RAI-159": "Infrastructure",
}

def env() -> dict:
    e = {}
    for line in (REPO / ".env.local").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1); e[k.strip()] = v.strip()
    return e

E = env()
AUTH = base64.b64encode(f"{E['ATLASSIAN_EMAIL']}:{E['ATLASSIAN_API_TOKEN']}".encode()).decode()
H = {"Authorization": f"Basic {AUTH}", "Accept": "application/json"}

def jget(path: str, params: dict | None = None) -> dict:
    r = httpx.get(f"{SITE}{path}", params=params or {}, headers=H, timeout=40)
    r.raise_for_status()
    return r.json()

def cat(parent_key: str | None) -> str:
    if not parent_key:
        return "Uncategorized"
    return EPIC_CAT.get(parent_key, "Product")

def sprint_issues(sprint_id: int) -> list[dict]:
    """All non-subtask issues in a sprint, with normalized fields."""
    out, start = [], 0
    while True:
        page = jget(f"/rest/agile/1.0/sprint/{sprint_id}/issue",
                    {"fields": "summary,status,issuetype,parent,customfield_10225,assignee",
                     "startAt": start, "maxResults": 50})
        for i in page.get("issues", []):
            f = i["fields"]
            if f["issuetype"]["name"] == "Sub-task":
                continue
            parent = f.get("parent")
            out.append({
                "key": i["key"],
                "type": f["issuetype"]["name"],
                "status": f["status"]["name"],
                "done": f["status"]["statusCategory"]["key"] == "done",
                "epic_key": parent["key"] if parent else None,
                "epic": parent["fields"]["summary"] if parent else None,
                "cat": cat(parent["key"] if parent else None),
                "size": (f["customfield_10225"]["value"] if f.get("customfield_10225") else None),
                "owner": (f["assignee"]["displayName"].split()[0] if f.get("assignee") else "Unassigned"),
                "summary": f["summary"],
            })
        if start + 50 >= page.get("total", 0):
            break
        start += 50
    return out

def scope_changes(sprint_id: int) -> dict:
    """Issues added or removed AFTER the sprint started. The Agile REST API cannot
    express this; the GreenHopper sprint report can, and the token can read it.
    rapidViewId == board id here (3)."""
    try:
        d = jget("/rest/greenhopper/1.0/rapid/charts/sprintreport",
                 {"rapidViewId": BOARD, "sprintId": sprint_id})
    except Exception as ex:
        print(f"[WARN] sprint report unavailable for {sprint_id}: {ex}")
        return {"added": [], "removed": []}
    c = d.get("contents", {})
    return {
        "added": list(c.get("issueKeysAddedDuringSprint", {}).keys()),
        "removed": [i.get("key") for i in c.get("puntedIssues", [])],
    }

def find_sprints():
    """Return (review_sprint, next_sprint) dicts for the board.

    Review = the sprint being reviewed = the ACTIVE (open) sprint if one exists,
    else the latest closed. This supports reviewing a sprint BEFORE it is closed
    (the team runs the review while the sprint is still open, then closes it).
    Next = first future sprint (the planning target)."""
    vals, start = [], 0
    while True:
        page = jget(f"/rest/agile/1.0/board/{BOARD}/sprint", {"startAt": start, "maxResults": 50})
        vals += page.get("values", [])
        if page.get("isLast") or start + 50 >= 1000:
            break
        start += 50
    active = [s for s in vals if s["state"] == "active"]
    closed = [s for s in vals if s["state"] == "closed"]
    future = [s for s in vals if s["state"] == "future"]
    review = active[-1] if active else (closed[-1] if closed else None)
    return review, (future[0] if future else None)

def find_retro_page_id(sprint_name: str) -> str | None:
    """Locate the retro Confluence page for a sprint by title in SPACE_KEY.
    Uses the direct content API (?title=), NOT CQL search (search index lags for
    just-published pages). Tries '<name> Retro' then '<name> - Retro'."""
    for title in (f"{sprint_name} Retro", f"{sprint_name} - Retro"):
        res = jget("/wiki/rest/api/content",
                   {"title": title, "spaceKey": SPACE_KEY, "limit": 5})
        for r in res.get("results", []):
            return r["id"]
    return None

def parse_retro(page_id: str) -> dict:
    """Read a retro page storage and extract Good/Bad/Ideas + actions count."""
    import re, html
    data = jget(f"/wiki/rest/api/content/{page_id}", {"expand": "body.storage"})
    s = data["body"]["storage"]["value"]
    def section(name: str, nxt: str) -> list[str]:
        m = re.search(rf"<h2[^>]*>{name}</h2>(.*?)<h2", s, re.S) or \
            re.search(rf"<h2[^>]*>{name}</h2>(.*)", s, re.S)
        if not m:
            return []
        chunk = m.group(1)
        items = re.findall(r"<p[^>]*>(.*?)</p>", chunk, re.S)
        clean = []
        for it in items:
            t = re.sub(r"<[^>]+>", "", it).strip()
            t = html.unescape(t)
            if t and t.lower() not in ("what went well this sprint",
                                       "what didn't go well / friction points"):
                clean.append(t)
        return clean
    return {
        "good": section("Good", "Bad"),
        "bad": section("Bad / could be better", "Ideas"),
        "ideas": section("Ideas", "Actions"),
        "page_id": page_id,
    }

def summarize(issues: list[dict]) -> dict:
    done = [i for i in issues if i["done"]]
    by_type = {}
    for i in issues:
        by_type.setdefault(i["type"], {"total": 0, "done": 0})
        by_type[i["type"]]["total"] += 1
        if i["done"]:
            by_type[i["type"]]["done"] += 1
    by_init = {}
    for i in issues:
        by_init.setdefault(i["cat"], {"total": 0, "done": 0})
        by_init[i["cat"]]["total"] += 1
        if i["done"]:
            by_init[i["cat"]]["done"] += 1
    SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL", "Spike", "Unsized"]
    sizes, completed_by_size = {}, {}
    for i in issues:
        s = i["size"] or "Unsized"
        sizes[s] = sizes.get(s, 0) + 1
        if i["done"]:
            completed_by_size[s] = completed_by_size.get(s, 0) + 1
    order = lambda d: {k: d[k] for k in SIZE_ORDER if k in d}
    return {
        "committed": len(issues),
        "completed": len(done),
        "carryover": len(issues) - len(done),
        "completion_pct": round(100.0 * len(done) / len(issues)) if issues else 0,
        "by_type": by_type, "by_initiative": by_init,
        "sizes": order(sizes), "completed_by_size": order(completed_by_size),
    }

def main():
    closed, future = find_sprints()
    print(f"review sprint: {closed['name']} (id {closed['id']}, state {closed['state']})")
    print(f"future sprint: {future['name']} (id {future['id']})" if future else "no future sprint")

    s2 = sprint_issues(closed["id"])
    s3 = sprint_issues(future["id"]) if future else []
    s2_keys = {i["key"] for i in s2}
    for i in s3:
        i["carryover"] = i["key"] in s2_keys

    # Scope change on the review sprint: what was added/removed after it started.
    sc = scope_changes(closed["id"])
    added_keys = set(sc["added"])
    for i in s2:
        i["added_after_start"] = i["key"] in added_keys
    def _decomp(items):
        dn = sum(1 for i in items if i["done"])
        return {"count": len(items), "done": dn, "carryover": len(items) - dn,
                "pct": round(100.0 * dn / len(items)) if items else 0}
    scope = {
        "committed_at_start": _decomp([i for i in s2 if not i["added_after_start"]]),
        "added_mid_sprint": _decomp([i for i in s2 if i["added_after_start"]]),
        "removed": sc["removed"],
    }

    retro_id = RETRO_PAGE_ID_OVERRIDE or find_retro_page_id(closed["name"])
    if retro_id:
        retro = parse_retro(retro_id)
    else:
        print(f"[WARN] no retro page found for {closed['name']!r} in {SPACE_KEY} "
              f"(is it published, not a draft?)")
        retro = {"good": [], "bad": [], "ideas": [], "page_id": None}
    data = {
        "review": {"sprint": closed["name"], "id": closed["id"],
                   "goal": closed.get("goal", ""), **summarize(s2),
                   "scope": scope, "issues": s2},
        "planning": {"sprint": future["name"], "id": future["id"],
                     "goal": future.get("goal", ""),
                     "committed": len(s3),
                     "carryover": sum(1 for i in s3 if i["carryover"]),
                     "unsized": sum(1 for i in s3 if not i["size"] and not i["done"]),
                     "unassigned": sum(1 for i in s3 if i["owner"] == "Unassigned" and not i["done"]),
                     "no_epic": sum(1 for i in s3 if not i["epic_key"]),
                     "sizes": summarize(s3)["sizes"],
                     "by_initiative": summarize(s3)["by_initiative"],
                     "issues": s3} if future else {},
        "retro": retro,
    }
    (REPO / "reports" / "cycle_data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    r = data["review"]
    print(f"\n=== {r['sprint']} REVIEW ===")
    print(f"  committed {r['committed']} | completed {r['completed']} | carryover {r['carryover']} | {r['completion_pct']}%")
    sc = r["scope"]
    cs, am = sc["committed_at_start"], sc["added_mid_sprint"]
    print(f"  SCOPE: committed-at-start {cs['count']} (done {cs['done']}, {cs['pct']}%) | "
          f"added mid-sprint {am['count']} (done {am['done']}) | removed {len(sc['removed'])}")
    print(f"  by initiative: {json.dumps(r['by_initiative'])}")
    print(f"  by type: {json.dumps(r['by_type'])}")
    print(f"  VELOCITY - completed by size: {json.dumps(r['completed_by_size'])}")
    if future:
        p = data["planning"]
        print(f"\n=== {p['sprint']} PLANNING ===")
        print(f"  committed {p['committed']} | carryover {p['carryover']} | unsized {p['unsized']} | unassigned {p['unassigned']} | no_epic {p['no_epic']}")
        print(f"  goal: {p['goal']!r}")
        print(f"  sizes: {json.dumps(p['sizes'])} | by initiative: {json.dumps(p['by_initiative'])}")
    print(f"\n=== RETRO ===")
    print(f"  good({len(retro['good'])}): {retro['good']}")
    print(f"  bad({len(retro['bad'])}): {retro['bad']}")
    print(f"  ideas({len(retro['ideas'])}): {retro['ideas']}")
    print("\nsaved -> reports/cycle_data.json")

if __name__ == "__main__":
    main()
