#!/usr/bin/env python3
"""
Apply one migration file over a direct Postgres connection and RECORD it in
supabase_migrations.schema_migrations.

Why this exists: scripts/apply_sql.py goes through the Management API, which
does not write a migration record (that is how 024-046 went missing from the
ledger), and the stored Management API token is invalid. A direct connection
via SUPABASE_DB_URL applies the SQL and records it in one place.

The migration file is expected to carry its own BEGIN/COMMIT (every file in
this repo does), so a failing statement rolls the whole file back server-side.
The ledger row is written only after the file applied successfully.

    python scripts/apply_migration_db.py --file supabase/migrations/053_swim_prototype_rpcs.sql
    python scripts/apply_migration_db.py --file ... --check-only   # connectivity + ledger state

Never prints the connection string.
"""

from __future__ import annotations

import os
import re
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(".env.local", usecwd=True), override=True)
except ImportError:
    pass

try:
    import psycopg
except ImportError:
    print("[apply] psycopg is required: pip install 'psycopg[binary]'")
    sys.exit(2)


def _version_for(path: Path) -> str:
    """A ledger version in the same shape Supabase uses (YYYYMMDDHHMMSS)."""
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--no-record", action="store_true",
                    help="apply without writing a ledger row (not recommended)")
    args = ap.parse_args()

    url = os.environ.get("SUPABASE_DB_URL", "")
    if not url:
        print("[apply] SUPABASE_DB_URL is not set in the environment / .env.local")
        return 3

    path = Path(args.file)
    if not path.exists():
        print(f"[apply] file not found: {path}")
        return 2
    sql = path.read_text(encoding="utf-8")
    name = path.stem
    m = re.match(r"^(\d{3})_", name)
    if not m:
        print(f"[apply] file name must start with NNN_: {name}")
        return 2

    with psycopg.connect(url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("select current_database(), version()")
            db, ver = cur.fetchone()
            print(f"[apply] connected to {db}: {ver.split(',')[0]}")
            cur.execute(
                "select version, name from supabase_migrations.schema_migrations "
                "where name = %s", (name,))
            existing = cur.fetchall()
            if existing:
                print(f"[apply] ledger already records {name}: {existing}")
                if not args.check_only:
                    print("[apply] refusing to re-apply a recorded migration")
                    return 4
            else:
                print(f"[apply] ledger has no row for {name}")

            if args.check_only:
                return 0

            print(f"[apply] applying {path} ({len(sql)} chars) ...")
            # No parameters -> simple query protocol -> the file's own
            # BEGIN/COMMIT delimit the transaction.
            cur.execute(sql)
            print("[apply] applied")

            if not args.no_record:
                version = _version_for(path)
                cur.execute(
                    "insert into supabase_migrations.schema_migrations (version, name, statements) "
                    "values (%s, %s, %s)",
                    (version, name, [sql]))
                print(f"[apply] recorded in ledger as version {version} name {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
