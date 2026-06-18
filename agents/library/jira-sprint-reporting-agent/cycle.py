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
RETRO_PAGE_ID = "170721281"          # Sprint 2 Retro
SPACE_KEY = "RAPD"

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

def find_sprints():
    """Return (closed_latest, future_next) sprint dicts for the board."""
    vals, start = [], 0
    while True:
        page = jget(f"/rest/agile/1.0/board/{BOARD}/sprint", {"startAt": start, "maxResults": 50})
        vals += page.get("values", [])
        if page.get("isLast") or start + 50 >= 1000:
            break
        start += 50
    closed = [s for s in vals if s["state"] == "closed"]
    future = [s for s in vals if s["state"] == "future"]
    return (closed[-1] if closed else None), (future[0] if future else None)

def parse_retro() -> dict:
    """Read the Sprint 2 retro page storage and extract Good/Bad/Ideas + actions count."""
    import re, html
    data = jget(f"/wiki/rest/api/content/{RETRO_PAGE_ID}", {"expand": "body.storage"})
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
        "page_id": RETRO_PAGE_ID,
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
    sizes = {}
    for i in issues:
        sizes[i["size"] or "Unsized"] = sizes.get(i["size"] or "Unsized", 0) + 1
    return {
        "committed": len(issues),
        "completed": len(done),
        "carryover": len(issues) - len(done),
        "completion_pct": round(100.0 * len(done) / len(issues)) if issues else 0,
        "by_type": by_type, "by_initiative": by_init, "sizes": sizes,
    }

def main():
    closed, future = find_sprints()
    print(f"closed sprint: {closed['name']} (id {closed['id']})")
    print(f"future sprint: {future['name']} (id {future['id']})" if future else "no future sprint")

    s2 = sprint_issues(closed["id"])
    s3 = sprint_issues(future["id"]) if future else []
    s2_keys = {i["key"] for i in s2}
    for i in s3:
        i["carryover"] = i["key"] in s2_keys

    retro = parse_retro()
    data = {
        "review": {"sprint": closed["name"], "id": closed["id"],
                   "goal": closed.get("goal", ""), **summarize(s2), "issues": s2},
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
    print(f"  by initiative: {json.dumps(r['by_initiative'])}")
    print(f"  by type: {json.dumps(r['by_type'])}")
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
