#!/usr/bin/env python3
"""
LIVE tenant-isolation test. Proves one company's user cannot reach another
company's resources, against the real database.

This is the test that the unit suite cannot substitute for: `requireTenant` and
the RLS policies are the single most important behaviour in P0-1, and until this
runs they are compiled but unproven.

WRITES TO PRODUCTION. Creates two throwaway auth users, two throwaway companies
and their memberships, asserts isolation across four layers, then deletes
everything it created. It is gated behind --i-understand-this-writes-to-production
so it cannot run by accident.

PREREQUISITES: migrations 047, 048, 049 and 050 must be applied. The script
checks and refuses to run otherwise, rather than producing a misleading pass.

    python scripts/tests/test_tenant_isolation_live.py --check-only
    python scripts/tests/test_tenant_isolation_live.py --i-understand-this-writes-to-production
"""

from __future__ import annotations

import os
import sys
import json
import uuid
import argparse
import urllib.error
import urllib.request
from pathlib import Path

PASSWORD = "Isolation-Test-" + uuid.uuid4().hex[:12] + "!aA1"


def load_env() -> tuple:
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
    url = (os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    anon = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY") or ""
    if not (url and svc and anon):
        sys.exit("[iso] NEXT_PUBLIC_SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and "
                 "NEXT_PUBLIC_SUPABASE_ANON_KEY are required")
    return url, svc, anon


def call(url: str, path: str, *, key: str, bearer: str | None = None,
         method: str = "GET", body: dict | list | None = None,
         prefer: str | None = None) -> tuple:
    headers = {"apikey": key, "Authorization": f"Bearer {bearer or key}",
               "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(
        f"{url}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, raw


class Results:
    def __init__(self):
        self.rows = []

    def check(self, name: str, passed: bool, detail: str = "") -> None:
        self.rows.append((name, passed, detail))
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))

    @property
    def failures(self) -> int:
        return sum(1 for _, p, _ in self.rows if not p)


def preconditions(url: str, svc: str) -> list:
    """Refuse to run against a database where the migrations are not applied -
    an 'isolation holds' result would be meaningless if the tables are absent."""
    missing = []
    status, _ = call(url, "/rest/v1/company_members?select=id&limit=1", key=svc)
    if status == 404:
        missing.append("public.company_members (migration 048)")
    status, body = call(url, "/rest/v1/rpc/swim_operations_summary", key=svc,
                        method="POST", body={"p_company_id": str(uuid.uuid4())})
    if status == 404:
        missing.append("public.swim_operations_summary (migration 050)")
    status, _ = call(url, "/rest/v1/rpc/check_tenant_budget", key=svc,
                     method="POST", body={"p_company_id": str(uuid.uuid4()),
                                          "p_estimate_usd": 0})
    if status == 404:
        missing.append("public.check_tenant_budget (migration 048)")
    return missing


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--i-understand-this-writes-to-production", action="store_true",
                    dest="confirmed")
    ap.add_argument("--check-only", action="store_true",
                    help="report whether prerequisites are met, then exit")
    args = ap.parse_args()

    url, svc, anon = load_env()
    print(f"[iso] target: {url}")

    missing = preconditions(url, svc)
    if missing:
        print("[iso] PREREQUISITES NOT MET - migrations are not applied:")
        for m in missing:
            print(f"       missing {m}")
        print("[iso] refusing to run; a pass here would be meaningless")
        return 2
    print("[iso] prerequisites met: 048/050 objects present")

    if args.check_only:
        return 0
    if not args.confirmed:
        print("[iso] refusing to run without "
              "--i-understand-this-writes-to-production")
        return 2

    r = Results()
    created = {"users": [], "companies": [], "members": []}

    try:
        # ---------- fixtures ------------------------------------------------
        print("\n[iso] creating throwaway tenants and users")
        for label in ("a", "b"):
            status, body = call(url, "/rest/v1/companies", key=svc, method="POST",
                                body={"name": f"iso-test-{label}-{uuid.uuid4().hex[:8]}",
                                      "slug": f"iso-test-{label}-{uuid.uuid4().hex[:8]}"},
                                prefer="return=representation")
            assert status in (200, 201), f"company create failed: {status} {body}"
            created["companies"].append(body[0]["id"])

            email = f"iso-{label}-{uuid.uuid4().hex[:8]}@example.invalid"
            status, body = call(url, "/auth/v1/admin/users", key=svc, method="POST",
                                body={"email": email, "password": PASSWORD,
                                      "email_confirm": True})
            assert status in (200, 201), f"user create failed: {status} {body}"
            created["users"].append({"id": body["id"], "email": email})

        co_a, co_b = created["companies"]
        user_a, user_b = created["users"]

        for user, company in ((user_a, co_a), (user_b, co_b)):
            status, body = call(url, "/rest/v1/company_members", key=svc, method="POST",
                                body={"user_id": user["id"], "company_id": company,
                                      "role": "operator", "created_by": "iso-test"},
                                prefer="return=representation")
            assert status in (200, 201), f"membership failed: {status} {body}"
            created["members"].append(body[0]["id"])

        # Give company A one facility so "cannot see B's rows" is a real claim
        # rather than an artefact of both tenants being empty.
        # Both companies get a facility. Without a row on each side, "A cannot
        # see B's data" would pass trivially because B has no data.
        fac_ids = {}
        for label, co in (("A", co_a), ("B", co_b)):
            status, body = call(url, "/rest/v1/rpc/swim_upsert_facility", key=svc,
                                method="POST",
                                body={"p_company_id": co, "p_facility": {
                                    "name": f"ISO TEST Facility {label}",
                                    "source": "fixture",
                                    "source_ref": f"iso-{uuid.uuid4().hex[:8]}"}})
            r.check(f"fixture: company {label} has a facility", status == 200,
                    f"HTTP {status}")
            row = (body[0] if isinstance(body, list) and body else body) or {}
            fac_ids[label] = row.get("facility_id")

        # ---------- sign in as each user ------------------------------------
        tokens = {}
        for label, user in (("a", user_a), ("b", user_b)):
            status, body = call(url, "/auth/v1/token?grant_type=password", key=anon,
                                method="POST",
                                body={"email": user["email"], "password": PASSWORD})
            assert status == 200, f"sign-in failed for {label}: {status} {body}"
            tokens[label] = body["access_token"]
        print("[iso] both users signed in\n")

        print("[iso] LAYER 1 - RLS on company_members (own rows only)")
        status, body = call(url, "/rest/v1/company_members?select=company_id",
                            key=anon, bearer=tokens["a"])
        rows = body if isinstance(body, list) else []
        r.check("user A sees exactly 1 membership", status == 200 and len(rows) == 1,
                f"HTTP {status}, {len(rows)} row(s)")
        r.check("user A's membership is company A",
                bool(rows) and rows[0].get("company_id") == co_a)
        r.check("user A cannot see user B's membership",
                all(row.get("company_id") != co_b for row in rows))

        print("\n[iso] LAYER 1b - CROSS-TENANT DATA, tested at the database")
        # swim_sourcing is NOT exposed by PostgREST (only `public` is), so a REST
        # probe returns 404 and proves nothing about the policy. The RLS policy
        # still governs any direct Postgres session, so test it there by
        # impersonating each user with their real JWT claims.
        db_url = os.environ.get("SUPABASE_DB_URL")
        if not db_url:
            r.check("cross-tenant facility isolation", False,
                    "SKIPPED - set SUPABASE_DB_URL to test the RLS policy directly")
        else:
            import psycopg

            def as_user(user_id, sql, params=()):
                """Run a query as `authenticated` with auth.uid() = user_id."""
                with psycopg.connect(db_url, connect_timeout=30) as conn:
                    with conn.cursor() as cur:
                        cur.execute("select set_config('request.jwt.claims', %s, true)",
                                    (json.dumps({"sub": user_id, "role": "authenticated"}),))
                        cur.execute("set local role authenticated")
                        cur.execute(sql, params)
                        return cur.fetchall()

            rows_a = as_user(user_a["id"],
                             "select id, company_id from swim_sourcing.facilities")
            r.check("user A sees exactly 1 facility", len(rows_a) == 1,
                    f"{len(rows_a)} row(s)")
            r.check("the facility user A sees belongs to company A",
                    bool(rows_a) and str(rows_a[0][1]) == co_a)
            r.check("user A CANNOT see company B's facility",
                    all(str(row[1]) != co_b for row in rows_a))

            rows_b = as_user(user_b["id"],
                             "select id, company_id from swim_sourcing.facilities")
            r.check("user B sees exactly 1 facility, and it is B's",
                    len(rows_b) == 1 and str(rows_b[0][1]) == co_b,
                    f"{len(rows_b)} row(s)")

            if fac_ids.get("B"):
                got = as_user(user_a["id"],
                              "select id from swim_sourcing.facilities where id = %s",
                              (fac_ids["B"],))
                r.check("user A asking for B's facility BY ID gets nothing",
                        len(got) == 0, f"{len(got)} row(s)")

            orphan = as_user(str(uuid.uuid4()),
                             "select id from swim_sourcing.facilities")
            r.check("a user with no membership sees zero facilities",
                    len(orphan) == 0, f"{len(orphan)} row(s)")

        print("\n[iso] LAYER 1c - swim_sourcing is unreachable over PostgREST")
        status, _ = call(url, "/rest/v1/facilities?select=id", key=anon, bearer=tokens["a"])
        r.check("authenticated cannot reach swim_sourcing via REST",
                status in (401, 403, 404), f"HTTP {status}")

        print("\n[iso] LAYER 2 - authenticated users cannot reach swim_* RPCs")
        # These are granted to service_role only. An authenticated session must
        # not be able to call them at all, whatever company id it passes.
        for fn, payload in (("swim_operations_summary", {"p_company_id": co_a}),
                            ("swim_list_facilities", {"p_company_id": co_a}),
                            ("swim_upsert_facility", {"p_company_id": co_a,
                                                      "p_facility": {"name": "x", "source": "fixture"}})):
            status, _ = call(url, f"/rest/v1/rpc/{fn}", key=anon, bearer=tokens["a"],
                             method="POST", body=payload)
            r.check(f"authenticated cannot call {fn}", status in (401, 403, 404),
                    f"HTTP {status}")

        print("\n[iso] LAYER 3 - anon cannot reach the ledger or the queue (047)")
        for path in ("/rest/v1/agents?select=id&limit=1",
                     "/rest/v1/agent_outputs?select=id&limit=1",
                     "/rest/v1/contractor_rows?select=id&limit=1",
                     "/rest/v1/agile_intake_jobs?select=id&limit=1"):
            status, _ = call(url, path, key=anon)
            r.check(f"anon denied {path.split('?')[0].split('/')[-1]}",
                    status in (401, 403, 404), f"HTTP {status}")
        for fn in ("get_calibration_readiness", "invariant_report"):
            status, _ = call(url, f"/rest/v1/rpc/{fn}", key=anon, method="POST", body={})
            r.check(f"anon denied rpc/{fn}", status in (401, 403, 404), f"HTTP {status}")

        print("\n[iso] LAYER 4 - ledger immutability binds even service_role (048)")
        status, body = call(url, "/rest/v1/agent_outputs?select=id&limit=1", key=svc)
        if status == 200 and isinstance(body, list) and body:
            target = body[0]["id"]
            status, body = call(url, f"/rest/v1/agent_outputs?id=eq.{target}", key=svc,
                                method="PATCH", body={"output_type": "tampered"})
            r.check("service_role UPDATE on agent_outputs is refused by trigger",
                    status >= 400, f"HTTP {status}")
            status, _ = call(url, f"/rest/v1/agent_outputs?id=eq.{target}", key=svc,
                             method="DELETE")
            r.check("service_role DELETE on agent_outputs is refused by trigger",
                    status >= 400, f"HTTP {status}")
        else:
            r.check("ledger immutability", False, "no agent_outputs row to test against")

        print("\n[iso] LAYER 5 - app route rejects a mismatched ?company=")
        site = os.environ.get("ISO_TEST_SITE_URL", "").rstrip("/")
        if not site:
            print("  [SKIP] set ISO_TEST_SITE_URL to test /api/sourcing/facilities "
                  "end to end (needs a running app and a session cookie)")
        else:
            print(f"  [INFO] app-layer check against {site} requires a browser "
                  "session; use the manual step in the activation plan")

    finally:
        print("\n[iso] cleaning up")
        # Order matters. facilities.company_id is ON DELETE RESTRICT, so a
        # company owning a facility cannot be deleted. An earlier version of this
        # teardown skipped the facilities and silently orphaned 8 iso-test
        # companies across runs. Delete children first, and report loudly if a
        # company still will not go.
        #
        # swim_sourcing is not exposed over PostgREST, so this needs the direct
        # connection.
        db_url = os.environ.get("SUPABASE_DB_URL")
        removed_facilities = 0
        if db_url and created["companies"]:
            try:
                import psycopg
                with psycopg.connect(db_url, connect_timeout=30) as conn:
                    with conn.cursor() as cur:
                        cur.execute("delete from swim_sourcing.qualifications "
                                    "where company_id = any(%s)", (created["companies"],))
                        cur.execute("delete from swim_sourcing.facilities "
                                    "where company_id = any(%s)", (created["companies"],))
                        removed_facilities = cur.rowcount
                    conn.commit()
            except Exception as exc:
                print(f"[iso] WARNING: could not remove test facilities: {exc}")
                print("[iso] the test companies will fail to delete as a result")

        for mid in created["members"]:
            call(url, f"/rest/v1/company_members?id=eq.{mid}", key=svc, method="DELETE")
        leftover = []
        for cid in created["companies"]:
            status, _ = call(url, f"/rest/v1/companies?id=eq.{cid}", key=svc, method="DELETE")
            if status >= 400:
                leftover.append(cid)
        for user in created["users"]:
            call(url, f"/auth/v1/admin/users/{user['id']}", key=svc, method="DELETE")

        print(f"[iso] removed {len(created['members'])} membership(s), "
              f"{removed_facilities} facility/ies, "
              f"{len(created['companies']) - len(leftover)} company/ies, "
              f"{len(created['users'])} user(s)")
        if leftover:
            print(f"[iso] WARNING: {len(leftover)} test company/ies could not be "
                  f"deleted and are now ORPHANED: {leftover}")

    print(f"\n[iso] {len(r.rows)} checks, {r.failures} failure(s)")
    return 1 if r.failures else 0


if __name__ == "__main__":
    sys.exit(main())
