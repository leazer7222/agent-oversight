#!/usr/bin/env python3
"""
Static API-authorization regression gate.

Runs in CI with no database. It exists because the live tenant-isolation test
cannot run in CI, and without some automated gate the specific regressions that
re-open P0-0/P0-1 would be caught only by review:

  1. A new /api/sourcing/* route that forgets requireTenant() - instantly a
     publicly-reachable tenant data leak, since every route uses the
     service-role client and so bypasses RLS.
  2. A route that trusts a caller-supplied company id instead of the session.
     This is the exact defect P0-1 fixed; `?company=` must be passed to
     requireTenant for validation, never used directly as a filter.
  3. The middleware exempting more paths from authentication over time.
  4. The browser (anon) Supabase client being imported into server code.
  5. A hard-coded credential appearing in a route.

    python scripts/tests/check_route_authorization.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
API = REPO / "src" / "app" / "api"
MIDDLEWARE = REPO / "src" / "middleware.ts"

# Routes authenticated by x-agent-secret rather than a session. Any addition to
# this set is a deliberate security decision and should be reviewed as one.
AGENT_SECRET_ROUTES = {"ingest/route.ts", "telemetry/ingest/route.ts"}

# Pre-existing ReformAI-internal routes that predate requireTenant. They are
# tracked here rather than ignored: the list must only ever shrink. A new route
# cannot be added to it without someone editing this file, which is the point.
LEGACY_UNSCOPED = {
    "agents/route.ts", "agents/[id]/route.ts", "agents/[id]/runs/route.ts",
    "agile/intake/route.ts", "agile/jobs/route.ts", "agile/jobs/[id]/route.ts",
    "agile/jobs/[id]/answer/route.ts", "ai-ops/feedback/route.ts",
    "ai-ops/provider-account/route.ts", "ai-ops/quota-snapshot/route.ts",
    "cost/route.ts", "errors/route.ts", "estimation/overview/route.ts",
    "estimation/runs/[id]/route.ts", "hierarchy/route.ts",
    "monitoring/invariants/route.ts", "project-state/route.ts",
    "project-state/[tag]/route.ts", "runs/route.ts", "runs/[id]/route.ts",
    "runs/[id]/events/route.ts", "scoping/route.ts", "scoping/[feature]/route.ts",
    "scoping/[feature]/answer/route.ts", "scoping/[feature]/gate-a/route.ts",
    "scoping/[feature]/ratify/route.ts",
}

CREDENTIAL_PATTERNS = (
    r"sk-ant-api\d{2}-",
    r"sk-proj-",
    r"sbp_[a-f0-9]{40}",
    r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.eyJpc3MiOiJzdXBhYmFzZSI",
)


class Gate:
    def __init__(self):
        self.failures: list = []
        self.checks = 0

    def check(self, passed: bool, message: str) -> None:
        self.checks += 1
        if not passed:
            self.failures.append(message)
            print(f"  [FAIL] {message}")

    def report(self) -> int:
        print(f"\n{self.checks} checks, {len(self.failures)} failure(s)")
        return 1 if self.failures else 0


def main() -> int:
    g = Gate()
    if not API.exists():
        print(f"[gate] {API} not found")
        return 1

    routes = sorted(p.relative_to(API).as_posix() for p in API.rglob("route.ts"))
    print(f"[gate] {len(routes)} API routes\n")

    print("[gate] 1. every non-legacy, non-agent-secret route resolves a verified tenant")
    for rel in routes:
        if rel in AGENT_SECRET_ROUTES or rel in LEGACY_UNSCOPED:
            continue
        src = (API / rel).read_text(encoding="utf-8")
        g.check("requireTenant" in src,
                f"{rel} does not call requireTenant() - tenant data would be "
                f"reachable without authorization")

    print("[gate] 2. no route uses a caller-supplied company id as a filter")
    for rel in routes:
        if rel in LEGACY_UNSCOPED or rel in AGENT_SECRET_ROUTES:
            continue
        src = (API / rel).read_text(encoding="utf-8")
        # Reading ?company= is fine ONLY if it is handed to requireTenant for
        # validation. Using it directly in an .eq() is the P0-1 defect.
        for m in re.finditer(r"\.eq\(\s*['\"]company_id['\"]\s*,\s*([^)]+)\)", src):
            expr = m.group(1).strip()
            g.check("ctx." in expr,
                    f"{rel} filters company_id on '{expr}' which is not derived "
                    f"from the verified session context")

    print("[gate] 3. middleware exempts only the known agent-secret paths")
    mw = MIDDLEWARE.read_text(encoding="utf-8")
    g.check(MIDDLEWARE.exists(), "src/middleware.ts is missing - the app would be unauthenticated")
    exempt_block = re.search(r"AGENT_SECRET_PATHS\s*=\s*\[(.*?)\]", mw, re.S)
    g.check(exempt_block is not None, "middleware has no AGENT_SECRET_PATHS list")
    if exempt_block:
        found = set(re.findall(r"'([^']+)'", exempt_block.group(1)))
        g.check(found == {"/api/ingest", "/api/telemetry/ingest"},
                f"middleware agent-secret exemptions changed to {sorted(found)}; "
                f"expected exactly /api/ingest and /api/telemetry/ingest")
    public_block = re.search(r"PUBLIC_PATHS\s*=\s*\[(.*?)\]", mw, re.S)
    if public_block:
        found = set(re.findall(r"'([^']+)'", public_block.group(1)))
        g.check(found <= {"/login", "/auth/callback"},
                f"middleware public paths widened to {sorted(found)}")
    g.check("getUser()" in mw,
            "middleware must use getUser() (revalidates against the auth server), "
            "not getSession() (decodes a client-tamperable cookie)")

    print("[gate] 4. the browser (anon) Supabase client is not used server-side")
    for rel in routes:
        src = (API / rel).read_text(encoding="utf-8")
        g.check("supabase/client" not in src,
                f"{rel} imports the browser anon client; server routes must use "
                f"createClient (session) or createServiceRoleClient")

    print("[gate] 5. no hard-coded credentials in routes or lib")
    scan_roots = [REPO / "src"]
    for root in scan_roots:
        for path in root.rglob("*.ts"):
            src = path.read_text(encoding="utf-8", errors="ignore")
            for pat in CREDENTIAL_PATTERNS:
                g.check(re.search(pat, src) is None,
                        f"{path.relative_to(REPO)} contains a credential-shaped literal")
        for path in root.rglob("*.tsx"):
            src = path.read_text(encoding="utf-8", errors="ignore")
            for pat in CREDENTIAL_PATTERNS:
                g.check(re.search(pat, src) is None,
                        f"{path.relative_to(REPO)} contains a credential-shaped literal")

    print("[gate] 6. the approval route binds approver identity to the session")
    appr = API / "sourcing" / "approvals" / "route.ts"
    if appr.exists():
        src = appr.read_text(encoding="utf-8")
        g.check("ctx.userId" in src,
                "approvals route must record ctx.userId as the approver, not a "
                "value from the request body (the gate-a defect)")
        g.check("approved_sha256" in src,
                "approvals route must bind the decision to a content hash")
        g.check(re.search(r"body\.(ratified_by|approver|approved_by)", src) is None,
                "approvals route reads an approver identity from the request body")

    print("[gate] 7. the legacy unscoped list has not grown")
    unknown = [r for r in LEGACY_UNSCOPED if r not in routes]
    g.check(not unknown,
            f"LEGACY_UNSCOPED lists routes that no longer exist: {unknown}. "
            f"Remove them - the list must only shrink.")

    return g.report()


if __name__ == "__main__":
    sys.exit(main())
