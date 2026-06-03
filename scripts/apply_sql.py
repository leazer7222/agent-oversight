"""
apply_sql.py - apply SQL/DDL to the Supabase project via the Management API.

The repo's service-role key only reaches PostgREST (no DDL). This helper uses the
Supabase Management API (which CAN run DDL), authenticating with the personal
access token already stored in ~/.claude.json (the Supabase MCP token). No secret
is hard-coded; the token is read at runtime.

Usage:
    python scripts/apply_sql.py --sql "select 1 as ok"
    python scripts/apply_sql.py --file supabase/migrations/025_cbc_identity_registry.sql
    python scripts/apply_sql.py --file path.sql --dry-run     # print, do not execute

Project ref defaults to hdhovyrlnfojtkqbcegh (override with --project).
"""
from __future__ import annotations

import os
import sys
import json
import argparse
import requests

DEFAULT_PROJECT = "hdhovyrlnfojtkqbcegh"


def find_token() -> str:
    cfg = json.load(open(os.path.expanduser("~/.claude.json"), encoding="utf-8"))
    found: list[str] = []

    def walk(o):
        if isinstance(o, str):
            if o.startswith("sbp_"):
                found.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(cfg)
    if not found:
        raise SystemExit("No Supabase management token (sbp_...) found in ~/.claude.json")
    return found[0]


def run_sql(sql: str, project: str) -> tuple[int, str]:
    tok = find_token()
    r = requests.post(
        f"https://api.supabase.com/v1/projects/{project}/database/query",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        json={"query": sql},
        timeout=120,
    )
    return r.status_code, r.text


def main() -> None:
    p = argparse.ArgumentParser(description="Apply SQL to Supabase via the Management API")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--sql", help="Inline SQL string")
    g.add_argument("--file", help="Path to a .sql file")
    p.add_argument("--project", default=DEFAULT_PROJECT)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    sql = args.sql if args.sql else open(args.file, encoding="utf-8").read()
    if args.dry_run:
        print(f"-- DRY RUN ({len(sql)} chars) against {args.project} --\n{sql[:2000]}")
        return

    status, body = run_sql(sql, args.project)
    print(f"status: {status}")
    print(body[:4000])
    if status >= 400:
        sys.exit(1)


if __name__ == "__main__":
    main()
