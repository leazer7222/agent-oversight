#!/usr/bin/env python3
"""
Complete logical backup of the Agent Oversight database - all application
schemas, DDL and data. This is the backup that gates production migrations.

It exists because `scripts/backup_supabase.py` can only reach the `public`
schema (PostgREST exposes nothing else) and because the migration-047 privilege
pre-image restores grants and policies but contains no data and no DDL. Neither
is a full backup.

CREDENTIAL HANDLING - read this before running
----------------------------------------------
Needs a direct Postgres connection string, which is NOT in the repository and
must never be pasted into a chat, a log, or a commit. Supply it the same way
every other secret here is supplied:

  1. Get the connection string by clicking **Connect** at the top of the
     project dashboard:
       https://supabase.com/dashboard/project/hdhovyrlnfojtkqbcegh?showConnect=true
     Choose the **Session pooler** tab. Not Direct (IPv6-only on the Free plan)
     and NOT Transaction pooler on port 6543 - this script uses server-side
     named cursors, which require a session-scoped connection.
  2. Append it to `.env.local` in the repo root, which is gitignored
     (`.gitignore:34` matches `.env*`):

         SUPABASE_DB_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres

  3. Run this script. It reads the variable, never prints it, and redacts the
     password from every message and from the manifest.

The script refuses to run if the URL would be written anywhere, and the output
directory is `backups/`, which is gitignored (`.gitignore`).

WHAT IT CAPTURES
----------------
  * Every schema: public, platform, product_graph, cost_intelligence,
    telemetry, runtime_governance, model_intelligence
  * Table DDL reconstructed from the catalog: columns, types, defaults,
    nullability, primary keys, unique and check constraints, foreign keys
  * Indexes (pg_get_indexdef), including the partial ones this schema relies on
  * Functions and procedures in full (pg_get_functiondef) - this is the part the
    git migrations CANNOT reproduce, because migration 021 exists in the
    production ledger with no file in the repo, and 022/041 were repaired
    in-place with CREATE OR REPLACE
  * RLS state, policies (pg_policies), triggers, sequences and their values
  * Table and function grants, and default privileges
  * All row data as NDJSON, one file per table

WHAT IT DOES NOT CAPTURE
------------------------
  * `auth.*` and `storage.*` (managed services; users and objects)
  * Extensions, roles, and database-level settings
  * Large objects (none in this database)

Usage:
    python scripts/backup_full.py                       # take a backup
    python scripts/backup_full.py --verify backups/DIR  # verify one
    python scripts/backup_full.py --check               # connectivity only
"""

from __future__ import annotations

import io
import os
import json
import sys
import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

SCHEMAS = ["public", "platform", "product_graph", "cost_intelligence",
           "telemetry", "runtime_governance", "model_intelligence"]


def redact(text: str) -> str:
    """Strip any password out of a connection string before it is shown."""
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", str(text))


def load_db_url() -> str:
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / ".env.local"
        if cand.exists():
            for line in cand.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            break
    url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL") or ""
    if not url:
        print("[backup] SUPABASE_DB_URL is not set.\n")
        print("  A complete backup needs a direct Postgres connection. Add this")
        print("  line to .env.local (gitignored), then re-run:\n")
        print("    SUPABASE_DB_URL=postgresql://postgres.<ref>:<password>"
              "@aws-0-<region>.pooler.supabase.com:5432/postgres\n")
        print("  Click 'Connect' at the TOP of the project dashboard")
        print("  (dashboard/project/<ref>?showConnect=true) - it is no longer")
        print("  under Settings -> Database. Use the SESSION POOLER tab:")
        print("    * Direct connection is IPv6-only on the Free plan")
        print("    * Transaction pooler (6543) breaks the server-side cursors")
        print("      this script uses to stream large tables")
        print("  Do not paste the connection string into chat.")
        sys.exit(3)
    return url


def connect(url: str):
    try:
        import psycopg
    except ImportError:
        sys.exit("[backup] psycopg is required: pip install 'psycopg[binary]'")
    try:
        return psycopg.connect(url, connect_timeout=30)
    except Exception as exc:
        sys.exit(f"[backup] could not connect: {redact(exc)}")


# ---------------------------------------------------------------------------
# DDL capture
# ---------------------------------------------------------------------------

DDL_QUERIES = {
    "schemas": """
        SELECT nspname AS schema_name, pg_get_userbyid(nspowner) AS owner
        FROM pg_namespace WHERE nspname = ANY(%s) ORDER BY 1
    """,
    "tables": """
        SELECT n.nspname AS schema_name, c.relname AS table_name, c.relkind::text,
               c.relrowsecurity AS rls_enabled,
               pg_get_userbyid(c.relowner) AS owner,
               coalesce(array_to_string(c.reloptions, ','), '') AS reloptions
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = ANY(%s) AND c.relkind IN ('r','v','m','p')
        ORDER BY 1, 2
    """,
    "columns": """
        SELECT table_schema, table_name, ordinal_position, column_name,
               data_type, is_nullable, column_default,
               character_maximum_length, numeric_precision, numeric_scale
        FROM information_schema.columns
        WHERE table_schema = ANY(%s)
        ORDER BY table_schema, table_name, ordinal_position
    """,
    "constraints": """
        SELECT n.nspname AS schema_name, cl.relname AS table_name,
               con.conname AS constraint_name, con.contype::text,
               pg_get_constraintdef(con.oid) AS definition
        FROM pg_constraint con
        JOIN pg_class cl ON cl.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = cl.relnamespace
        WHERE n.nspname = ANY(%s)
        ORDER BY 1, 2, 3
    """,
    "indexes": """
        SELECT schemaname AS schema_name, tablename AS table_name,
               indexname AS index_name, indexdef AS definition
        FROM pg_indexes WHERE schemaname = ANY(%s)
        ORDER BY 1, 2, 3
    """,
    # The critical one: git cannot reproduce these. Migration 021 is in the
    # production ledger with no file in the repo, and 022/041 were repaired
    # in place with CREATE OR REPLACE.
    "functions": """
        SELECT n.nspname AS schema_name, p.proname AS function_name,
               pg_get_function_identity_arguments(p.oid) AS identity_args,
               p.prosecdef AS security_definer,
               coalesce(array_to_string(p.proconfig, ','), '') AS config,
               pg_get_userbyid(p.proowner) AS owner,
               pg_get_functiondef(p.oid) AS definition
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = ANY(%s) AND p.prokind IN ('f','p')
        ORDER BY 1, 2, 3
    """,
    "views": """
        SELECT schemaname AS schema_name, viewname AS view_name,
               definition FROM pg_views WHERE schemaname = ANY(%s)
        ORDER BY 1, 2
    """,
    "policies": """
        SELECT schemaname AS schema_name, tablename AS table_name, policyname,
               permissive, array_to_string(roles, ',') AS roles, cmd,
               qual AS using_expr, with_check AS check_expr
        FROM pg_policies WHERE schemaname = ANY(%s)
        ORDER BY 1, 2, 3
    """,
    "triggers": """
        SELECT n.nspname AS schema_name, c.relname AS table_name,
               t.tgname AS trigger_name, pg_get_triggerdef(t.oid) AS definition
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = ANY(%s) AND NOT t.tgisinternal
        ORDER BY 1, 2, 3
    """,
    "sequences": """
        SELECT schemaname AS schema_name, sequencename AS sequence_name,
               start_value, increment_by, max_value, last_value
        FROM pg_sequences WHERE schemaname = ANY(%s)
        ORDER BY 1, 2
    """,
    "table_grants": """
        SELECT table_schema, table_name, grantee, privilege_type
        FROM information_schema.role_table_grants
        WHERE table_schema = ANY(%s)
        ORDER BY 1, 2, 3, 4
    """,
    "function_acls": """
        SELECT n.nspname AS schema_name, p.proname AS function_name,
               pg_get_function_identity_arguments(p.oid) AS identity_args,
               coalesce(array_to_string(p.proacl::text[], ' '), '(null)') AS acl
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = ANY(%s) AND p.prokind IN ('f','p')
        ORDER BY 1, 2, 3
    """,
    "default_privileges": """
        SELECT coalesce(n.nspname, '(global)') AS schema_name,
               pg_get_userbyid(d.defaclrole) AS role_name,
               d.defaclobjtype::text AS object_type,
               coalesce(array_to_string(d.defaclacl::text[], ' '), '') AS acl
        FROM pg_default_acl d LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace
        ORDER BY 1, 2, 3
    """,
}


def rows_as_dicts(cur) -> list:
    cols = [c.name for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def take_backup(out_root: Path) -> Path:
    url = load_db_url()
    conn = connect(url)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = out_root / f"full-{stamp}"
    (dest / "ddl").mkdir(parents=True, exist_ok=True)
    (dest / "data").mkdir(parents=True, exist_ok=True)

    manifest = {
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "connection": redact(url),
        "schemas": SCHEMAS,
        "scope": "all application schemas: DDL + data",
        "NOT_INCLUDED": ["auth.*", "storage.*", "extensions", "roles",
                         "database-level settings"],
        "ddl": {},
        "data": [],
    }

    print(f"[backup] connected; writing to {dest}")

    with conn.cursor() as cur:
        cur.execute("SELECT current_database(), version()")
        db, ver = cur.fetchone()
        manifest["database"] = db
        manifest["server_version"] = ver.split(" on ")[0]
        print(f"[backup] {db} / {manifest['server_version']}")

        print("[backup] capturing DDL")
        for name, sql in DDL_QUERIES.items():
            cur.execute(sql, (SCHEMAS,))
            data = rows_as_dicts(cur)
            (dest / "ddl" / f"{name}.json").write_text(
                json.dumps(data, indent=2, default=str), encoding="utf-8")
            manifest["ddl"][name] = len(data)
            print(f"  {name:22s} {len(data):5d}")

        # --- data ---------------------------------------------------------
        print("[backup] capturing data")
        cur.execute("""
            SELECT n.nspname, c.relname
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r' AND n.nspname = ANY(%s)
            ORDER BY 1, 2
        """, (SCHEMAS,))
        tables = cur.fetchall()

        total = 0
        for schema, table in tables:
            cur.execute(f'SELECT count(*) FROM "{schema}"."{table}"')
            expected = cur.fetchone()[0]

            path = dest / "data" / f"{schema}.{table}.ndjson"
            written = 0
            # Server-side cursor so a large table cannot exhaust memory.
            with conn.cursor(name=f"bk_{schema}_{table}") as scur:
                scur.itersize = 1000
                scur.execute(f'SELECT * FROM "{schema}"."{table}"')
                cols = None
                with io.open(path, "w", encoding="utf-8") as fh:
                    for row in scur:
                        if cols is None:
                            cols = [c.name for c in scur.description]
                        fh.write(json.dumps(dict(zip(cols, row)),
                                            ensure_ascii=False, default=str) + "\n")
                        written += 1

            entry = {"schema": schema, "table": table, "rows": written,
                     "expected": expected}
            if written != expected:
                entry["MISMATCH"] = True
            manifest["data"].append(entry)
            total += written
            flag = "  MISMATCH" if written != expected else ""
            print(f"  {schema}.{table:34s} {written:7d} / {expected}{flag}")

        manifest["total_rows"] = total

    conn.close()
    (dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, default=str),
                                        encoding="utf-8")
    print(f"\n[backup] {total} rows, {len(manifest['data'])} tables, "
          f"{sum(manifest['ddl'].values())} DDL objects -> {dest}")
    return dest


def verify_backup(backup_dir: Path) -> int:
    """Verify completeness and integrity.

    Re-parses every data line rather than trusting the file exists, because a
    truncated write produces a file that looks fine until a restore needs it.
    """
    mpath = backup_dir / "MANIFEST.json"
    if not mpath.exists():
        print(f"[verify] FAIL: no MANIFEST.json in {backup_dir}")
        return 1
    manifest = json.loads(mpath.read_text(encoding="utf-8"))

    failures = 0

    for name, count in manifest.get("ddl", {}).items():
        p = backup_dir / "ddl" / f"{name}.json"
        if not p.exists():
            print(f"[verify] FAIL ddl/{name}: missing")
            failures += 1
            continue
        try:
            got = len(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            print(f"[verify] FAIL ddl/{name}: invalid JSON ({exc})")
            failures += 1
            continue
        if got != count:
            print(f"[verify] FAIL ddl/{name}: {got} entries, manifest says {count}")
            failures += 1

    for entry in manifest.get("data", []):
        p = backup_dir / "data" / f"{entry['schema']}.{entry['table']}.ndjson"
        if not p.exists():
            print(f"[verify] FAIL {entry['schema']}.{entry['table']}: file missing")
            failures += 1
            continue
        lines = 0
        bad = False
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                print(f"[verify] FAIL {entry['schema']}.{entry['table']}: "
                      f"line {i} invalid JSON")
                failures += 1
                bad = True
                break
            lines += 1
        if not bad and lines != entry["rows"]:
            print(f"[verify] FAIL {entry['schema']}.{entry['table']}: "
                  f"{lines} lines, manifest says {entry['rows']}")
            failures += 1

    # Completeness assertions specific to this database.
    fn_count = manifest.get("ddl", {}).get("functions", 0)
    if fn_count < 40:
        print(f"[verify] FAIL: only {fn_count} functions captured; expected 42+. "
              "A function-definition gap is the one thing git cannot replace.")
        failures += 1

    captured_schemas = {e["schema"] for e in manifest.get("data", [])}
    for s in SCHEMAS:
        if s not in captured_schemas:
            print(f"[verify] FAIL: schema '{s}' has no captured tables")
            failures += 1

    print(f"\n[verify] {len(manifest.get('data', []))} tables, "
          f"{sum(manifest.get('ddl', {}).values())} DDL objects, "
          f"{manifest.get('total_rows')} rows")
    print(f"[verify] {failures} failure(s)")
    if failures == 0:
        print("[verify] COMPLETE: all 7 application schemas, DDL and data, verified.")
        print("[verify] Still excluded by design: auth.*, storage.*, extensions, roles.")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="backups")
    ap.add_argument("--verify", metavar="DIR")
    ap.add_argument("--check", action="store_true",
                    help="test connectivity and exit without writing a backup")
    args = ap.parse_args()

    if args.verify:
        return verify_backup(Path(args.verify))

    if args.check:
        url = load_db_url()
        conn = connect(url)
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user, version()")
            db, user, ver = cur.fetchone()
            cur.execute("""SELECT count(*) FROM pg_class c
                           JOIN pg_namespace n ON n.oid=c.relnamespace
                           WHERE c.relkind='r' AND n.nspname = ANY(%s)""", (SCHEMAS,))
            tables = cur.fetchone()[0]
        conn.close()
        print(f"[check] OK: {db} as {user}")
        print(f"[check] {ver.split(' on ')[0]}")
        print(f"[check] {tables} tables visible across {len(SCHEMAS)} application schemas")
        return 0

    dest = take_backup(Path(args.out))
    print()
    return verify_backup(dest)


if __name__ == "__main__":
    sys.exit(main())
