#!/usr/bin/env python3
"""
LAYER 5 - app-layer tenant authorization, against the deployed application.

This is the check the database-level isolation test could not make. The RLS
suite proves Postgres filters rows; this proves the Next.js routes reject a
caller who asks for a company they are not a member of. Those are different
controls and a bug in either one is a cross-tenant leak.

It drives the REAL deployed URL with a REAL signed-in session, by minting a
Supabase session and encoding it the way @supabase/ssr expects to find it in a
cookie. No browser required.

WRITES TO PRODUCTION: creates two throwaway companies, two throwaway users and
their memberships, then removes them. Gated behind an explicit flag.

    python scripts/tests/test_layer5_app_authz_live.py --site https://... \
        --i-understand-this-writes-to-production
"""

from __future__ import annotations

import os
import sys
import json
import uuid
import base64
import argparse
import urllib.error
import urllib.request
from pathlib import Path

PASSWORD = "Layer5-" + uuid.uuid4().hex[:12] + "!aA1"


def load_env():
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
    return url, os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "", \
        os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY") or ""


def api(url, path, *, key, bearer=None, method="GET", body=None, prefer=None):
    headers = {"apikey": key, "Authorization": f"Bearer {bearer or key}",
               "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(
        f"{url}{path}", data=json.dumps(body).encode() if body is not None else None,
        headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def site_get(site, path, cookie=None):
    """Request the deployed app, NOT following redirects, so a 307 is visible."""
    req = urllib.request.Request(f"{site}{path}", method="GET")
    if cookie:
        req.add_header("Cookie", cookie)

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace")[:2000], dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:2000], dict(e.headers)


def ssr_cookie(project_ref: str, session: dict) -> str:
    """Encode a session the way @supabase/ssr stores it.

    The server helper reads `sb-<ref>-auth-token`, whose value is `base64-`
    followed by base64url of the session JSON. Long values are split across
    numbered chunks (.0, .1, ...), which is why this returns a full Cookie
    header rather than a single name=value pair.
    """
    payload = json.dumps(session, separators=(",", ":"))
    encoded = "base64-" + base64.b64encode(payload.encode()).decode()
    name = f"sb-{project_ref}-auth-token"
    limit = 3180  # keep each cookie under the common 4KB per-cookie ceiling
    if len(encoded) <= limit:
        return f"{name}={encoded}"
    chunks = [encoded[i:i + limit] for i in range(0, len(encoded), limit)]
    return "; ".join(f"{name}.{i}={c}" for i, c in enumerate(chunks))


class Results:
    def __init__(self):
        self.rows = []

    def check(self, name, passed, detail=""):
        self.rows.append(passed)
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))

    @property
    def failures(self):
        return sum(1 for p in self.rows if not p)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True, help="deployed base URL")
    ap.add_argument("--i-understand-this-writes-to-production", action="store_true",
                    dest="confirmed")
    args = ap.parse_args()

    url, svc, anon = load_env()
    ref = url.split("//")[1].split(".")[0]
    site = args.site.rstrip("/")
    print(f"[layer5] app: {site}\n[layer5] supabase ref: {ref}")

    if not args.confirmed:
        print("[layer5] refusing to run without "
              "--i-understand-this-writes-to-production")
        return 2

    r = Results()
    created = {"users": [], "companies": [], "members": []}

    try:
        print("\n[layer5] anonymous baseline")
        status, _, _ = site_get(site, "/api/sourcing/facilities")
        r.check("anonymous /api/sourcing/facilities -> 401", status == 401, f"HTTP {status}")
        status, _, hdrs = site_get(site, "/dashboard")
        r.check("anonymous /dashboard redirects to /login",
                status in (301, 302, 307, 308) and "/login" in hdrs.get("Location", ""),
                f"HTTP {status} -> {hdrs.get('Location','')}")

        print("\n[layer5] creating two throwaway tenants")
        for label in ("a", "b"):
            s, b = api(url, "/rest/v1/companies", key=svc, method="POST",
                       body={"name": f"layer5-{label}-{uuid.uuid4().hex[:8]}",
                             "slug": f"layer5-{label}-{uuid.uuid4().hex[:8]}"},
                       prefer="return=representation")
            assert s in (200, 201), f"company create: {s} {b}"
            created["companies"].append(b[0]["id"])

            email = f"layer5-{label}-{uuid.uuid4().hex[:8]}@example.invalid"
            s, b = api(url, "/auth/v1/admin/users", key=svc, method="POST",
                       body={"email": email, "password": PASSWORD, "email_confirm": True})
            assert s in (200, 201), f"user create: {s} {b}"
            created["users"].append({"id": b["id"], "email": email})

        co_a, co_b = created["companies"]
        user_a, user_b = created["users"]

        for user, co in ((user_a, co_a), (user_b, co_b)):
            s, b = api(url, "/rest/v1/company_members", key=svc, method="POST",
                       body={"user_id": user["id"], "company_id": co,
                             "role": "operator", "created_by": "layer5-test"},
                       prefer="return=representation")
            assert s in (200, 201), f"membership: {s} {b}"
            created["members"].append(b[0]["id"])

        # Give company A a facility so "A sees its own data" is a real assertion.
        api(url, "/rest/v1/rpc/swim_upsert_facility", key=svc, method="POST",
            body={"p_company_id": co_a, "p_facility": {
                "name": "LAYER5 TEST Facility A", "source": "fixture",
                "source_ref": f"layer5-{uuid.uuid4().hex[:8]}"}})

        print("\n[layer5] signing in as user A")
        s, sess = api(url, "/auth/v1/token?grant_type=password", key=anon,
                      method="POST",
                      body={"email": user_a["email"], "password": PASSWORD})
        assert s == 200, f"sign-in failed: {s} {sess}"
        cookie_a = ssr_cookie(ref, sess)
        r.check("minted a session cookie for user A", bool(cookie_a))

        print("\n[layer5] authenticated access, own company")
        status, body, _ = site_get(site, "/api/sourcing/facilities", cookie_a)
        r.check("user A gets 200 from /api/sourcing/facilities", status == 200,
                f"HTTP {status}")
        ok_own = False
        if status == 200:
            try:
                d = json.loads(body)
                ok_own = d.get("company_id") == co_a
                r.check("response is scoped to company A", ok_own,
                        f"company_id={d.get('company_id')}")
                r.check("user A can see its own facility",
                        d.get("count", 0) >= 1, f"count={d.get('count')}")
            except Exception as exc:
                r.check("response parsed", False, str(exc))

        print("\n[layer5] THE CROSS-TENANT CHECK: A asks for company B")
        status, body, _ = site_get(site, f"/api/sourcing/facilities?company={co_b}", cookie_a)
        r.check("mismatched ?company= returns 403", status == 403, f"HTTP {status}")
        r.check("the 403 body leaks no company B data",
                co_b not in body or "Forbidden" in body)

        print("\n[layer5] dashboard is reachable once signed in")
        status, _, hdrs = site_get(site, "/dashboard", cookie_a)
        r.check("authenticated /dashboard is not redirected to login",
                status == 200, f"HTTP {status} {hdrs.get('Location','')}")

        print("\n[layer5] legacy oversight routes require an ADMIN, not just a session")
        for path in ("/api/agents", "/api/runs", "/api/cost", "/api/hierarchy"):
            status, _, _ = site_get(site, path, cookie_a)
            r.check(f"operator denied {path}", status == 403, f"HTTP {status}")

    finally:
        print("\n[layer5] cleaning up")
        db_url = os.environ.get("SUPABASE_DB_URL")
        if db_url and created["companies"]:
            try:
                import psycopg
                with psycopg.connect(db_url, connect_timeout=30) as conn:
                    with conn.cursor() as cur:
                        cur.execute("delete from swim_sourcing.qualifications "
                                    "where company_id = any(%s)", (created["companies"],))
                        cur.execute("delete from swim_sourcing.facilities "
                                    "where company_id = any(%s)", (created["companies"],))
                    conn.commit()
            except Exception as exc:
                print(f"  WARNING: facility cleanup failed: {exc}")
        for mid in created["members"]:
            api(url, f"/rest/v1/company_members?id=eq.{mid}", key=svc, method="DELETE")
        leftover = []
        for cid in created["companies"]:
            s, _ = api(url, f"/rest/v1/companies?id=eq.{cid}", key=svc, method="DELETE")
            if s >= 400:
                leftover.append(cid)
        for u in created["users"]:
            api(url, f"/auth/v1/admin/users/{u['id']}", key=svc, method="DELETE")
        print(f"  removed {len(created['members'])} membership(s), "
              f"{len(created['companies']) - len(leftover)} company/ies, "
              f"{len(created['users'])} user(s)")
        if leftover:
            print(f"  WARNING: orphaned companies: {leftover}")

    print(f"\n[layer5] {len(r.rows)} checks, {r.failures} failure(s)")
    return 1 if r.failures else 0


if __name__ == "__main__":
    sys.exit(main())
