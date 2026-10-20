#!/usr/bin/env python3
"""
Logical data backup of the PUBLIC schema, plus restore verification.

READ THIS BEFORE RELYING ON IT
------------------------------
This is a PARTIAL backup and must not be mistaken for a full one.

What it captures: every row of every table PostgREST exposes, which is the
`public` schema only - 29 objects as of 2026-10-20.

What it does NOT capture:
  * The six private schemas - platform, product_graph, cost_intelligence,
    telemetry, runtime_governance, model_intelligence. PostgREST does not expose
    them, so no service-role HTTP client can read them. These hold the cost
    artifacts, estimation history, product graph and raw telemetry.
  * Schema DDL, functions, policies, grants, triggers, sequences, extensions.
  * auth.* (users), storage.* (objects).

Why it is limited: a complete backup needs `pg_dump`, which needs a direct
Postgres connection string. There is none in `.env.local`, and the stored
Supabase management PAT is invalid, so one cannot be fetched. Getting a complete
backup requires the operator to supply the database password - see
docs/p0-activation-plan.md for the exact commands.

The P0-0 privilege pre-image is a different artifact again: it restores grants
and policies, not data. Neither it nor this script is a substitute for pg_dump.

Usage:
    python scripts/backup_supabase.py --out backups/            # take a backup
    python scripts/backup_supabase.py --verify backups/<dir>    # verify it
"""

from __future__ import annotations

import os
import io
import json
import sys
import argparse
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PAGE = 1000


def load_env() -> tuple:
    here = Path(__file__).resolve()
    for parent in [here.parent.parent] + list(here.parents):
        cand = parent / ".env.local"
        if cand.exists():
            for line in cand.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break
    url = (os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not url or not key:
        sys.exit("[backup] NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    if len(key) < 150 and not key.startswith("sb_secret"):
        sys.exit(f"[backup] SUPABASE_SERVICE_ROLE_KEY looks wrong ({len(key)} chars); "
                 "the anon key cannot read all rows and would produce a SILENTLY "
                 "INCOMPLETE backup")
    return url, key


def req(url: str, key: str, path: str, extra_headers: dict | None = None):
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    headers.update(extra_headers or {})
    r = urllib.request.Request(f"{url}/rest/v1/{path}", headers=headers)
    with urllib.request.urlopen(r, timeout=60) as resp:
        return resp.read().decode(), dict(resp.headers)


def discover_tables(url: str, key: str) -> list:
    body, _ = req(url, key, "")
    spec = json.loads(body)
    out = []
    for p, defn in spec.get("paths", {}).items():
        name = p.lstrip("/")
        if not name or name.startswith("rpc/"):
            continue
        # Views cannot be restored by insert; record them but mark as such.
        out.append(name)
    return sorted(out)


def table_count(url: str, key: str, table: str) -> int | None:
    try:
        _, headers = req(url, key, f"{table}?select=*&limit=1",
                         {"Prefer": "count=exact", "Range-Unit": "items", "Range": "0-0"})
        cr = headers.get("Content-Range", "")
        if "/" in cr:
            total = cr.split("/")[-1]
            return None if total == "*" else int(total)
    except urllib.error.HTTPError:
        return None
    return None


def dump_table(url: str, key: str, table: str, dest: Path) -> dict:
    rows_written = 0
    offset = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with io.open(dest, "w", encoding="utf-8") as fh:
        while True:
            try:
                body, _ = req(url, key, f"{table}?select=*&limit={PAGE}&offset={offset}")
            except urllib.error.HTTPError as exc:
                return {"table": table, "rows": rows_written, "error": f"HTTP {exc.code}"}
            batch = json.loads(body)
            if not isinstance(batch, list):
                return {"table": table, "rows": rows_written, "error": "unexpected payload"}
            for row in batch:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            rows_written += len(batch)
            if len(batch) < PAGE:
                break
            offset += PAGE
    return {"table": table, "rows": rows_written}


def take_backup(out_root: Path) -> Path:
    url, key = load_env()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = out_root / f"public-schema-{stamp}"
    dest.mkdir(parents=True, exist_ok=True)

    tables = discover_tables(url, key)
    print(f"[backup] {len(tables)} exposed objects; writing to {dest}")

    manifest = {
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "project_url": url,
        "scope": "public schema only (PostgREST-exposed)",
        "NOT_INCLUDED": [
            "private schemas: platform, product_graph, cost_intelligence, "
            "telemetry, runtime_governance, model_intelligence",
            "schema DDL, functions, policies, grants, triggers, sequences",
            "auth.* and storage.*",
        ],
        "tables": [],
    }

    total = 0
    for t in tables:
        expected = table_count(url, key, t)
        result = dump_table(url, key, t, dest / f"{t}.ndjson")
        result["expected_count"] = expected
        # A mismatch means the dump is incomplete - surface it rather than
        # letting a short read look like an empty table.
        if expected is not None and result.get("rows") != expected:
            result["MISMATCH"] = True
        manifest["tables"].append(result)
        total += result.get("rows", 0)
        flag = " MISMATCH" if result.get("MISMATCH") else ""
        err = f" ERROR={result['error']}" if result.get("error") else ""
        print(f"  {t:34s} {result.get('rows', 0):7d} rows"
              f" (expected {expected}){flag}{err}")

    manifest["total_rows"] = total
    (dest / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")

    bad = [t for t in manifest["tables"] if t.get("MISMATCH") or t.get("error")]
    print(f"\n[backup] {total} rows across {len(tables)} objects -> {dest}")
    if bad:
        print(f"[backup] WARNING: {len(bad)} object(s) incomplete or errored:")
        for b in bad:
            print(f"  - {b['table']}: rows={b.get('rows')} "
                  f"expected={b.get('expected_count')} {b.get('error','')}")
    return dest


def verify_backup(backup_dir: Path) -> int:
    """Verification, which is the half people skip.

    Checks three things: the manifest parses, every table file exists and holds
    exactly the row count the manifest claims, and every line is valid JSON. The
    third matters because a truncated write produces a file that LOOKS fine until
    you try to restore from it.
    """
    manifest_path = backup_dir / "MANIFEST.json"
    if not manifest_path.exists():
        print(f"[verify] FAIL: no MANIFEST.json in {backup_dir}")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    failures = 0
    checked = 0
    for entry in manifest["tables"]:
        table = entry["table"]
        path = backup_dir / f"{table}.ndjson"
        if not path.exists():
            print(f"[verify] FAIL {table}: file missing")
            failures += 1
            continue
        lines = 0
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"[verify] FAIL {table}: line {i} is not valid JSON ({exc})")
                failures += 1
                break
            lines += 1
        if lines != entry.get("rows"):
            print(f"[verify] FAIL {table}: {lines} lines but manifest claims {entry.get('rows')}")
            failures += 1
        checked += 1

    print(f"\n[verify] {checked} objects checked, {failures} failure(s)")
    print(f"[verify] total rows: {manifest.get('total_rows')}")
    print("[verify] REMINDER: public schema only. The six private schemas, all "
          "DDL, and auth/storage are NOT in this backup.")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="backups", help="directory to write a new backup into")
    ap.add_argument("--verify", metavar="DIR", help="verify an existing backup directory")
    args = ap.parse_args()

    if args.verify:
        return verify_backup(Path(args.verify))
    dest = take_backup(Path(args.out))
    print()
    return verify_backup(dest)


if __name__ == "__main__":
    sys.exit(main())
