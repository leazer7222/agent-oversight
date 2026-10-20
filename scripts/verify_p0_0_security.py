#!/usr/bin/env python3
"""
P0-0 security regression suite.

Proves the two halves of migration 047's claim:
  1. anon (the PUBLIC publishable key, which ships in any browser bundle) can no
     longer read internal tables, invoke privileged RPCs, or forge ledger rows.
  2. service_role - the path every API route and Python agent actually uses -
     still works, so the hardening is behaviour-neutral for the application.

Run BEFORE applying 047 to document the vulnerable baseline:
    python scripts/verify_p0_0_security.py

Run AFTER applying 047 to assert the fix:
    python scripts/verify_p0_0_security.py --expect-hardened

Exit codes: 0 = all assertions met, 1 = at least one failed, 2 = setup problem.

SAFETY
------
Default mode is strictly READ-ONLY. The forge/injection probes are WRITE attempts
and are gated behind --include-write-probes, because against an UNHARDENED
database they would SUCCEED and leave junk rows in the ledger and the job queue.
Only pass that flag after 047 is applied, when the expected outcome is rejection.
No key material is ever printed.
"""

import os
import sys
import json
import uuid
import argparse
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Objects confirmed exposed by the 2026-10-20 audit. Keep in sync with 047.
ANON_READABLE_TABLES = [
    "contractor_rows", "contractor_evidence", "contractor_approval_queue",
    "contractor_sync_log", "codebase_context_cache", "pipeline_config",
    "event_type_registry", "output_type_registry",
]
# Privileged RPCs. Read-only ones are safe to probe in either mode.
ANON_CALLABLE_RPCS_READONLY = [
    ("get_calibration_readiness", {}),
    ("get_estimation_accuracy_overview", {}),
    ("get_bucket_accuracy", {}),
    ("invariant_report", {}),
    ("cbc_resolve", {"p_noun": "Material"}),
    ("get_task_type_id", {"p_code": "code_gen"}),
]
# Ledger WRITERS. Write probes - gated.
ANON_CALLABLE_RPCS_WRITE = [
    ("write_run_started_artifacts", {
        "p_run_id": None, "p_tenant_id": None, "p_model": "claude-sonnet-4-6",
        "p_provider": "anthropic", "p_task_type_code": "code_gen",
        "p_task_complexity_bucket": "simple"}),
    ("graph_ratify_node", {
        "p_tenant": None, "p_product": "reformai-product",
        "p_node_key": "CON-0001", "p_new_status": "ratified",
        "p_ratified_by": "p0-0-security-probe"}),
]


class Result:
    def __init__(self):
        self.rows = []
        self.failed = 0

    def record(self, section, name, outcome, detail=""):
        self.rows.append((section, name, outcome, detail))
        if outcome == "FAIL":
            self.failed += 1

    def report(self):
        width = max(len(r[1]) for r in self.rows) if self.rows else 10
        section = None
        for sec, name, outcome, detail in self.rows:
            if sec != section:
                print(f"\n--- {sec} ---")
                section = sec
            tag = {"PASS": "[OK]", "FAIL": "[FAIL]", "SKIP": "[SKIP]",
                   "INFO": "[INFO]"}[outcome]
            print(f"  {tag:7} {name:<{width}}  {detail}")
        print(f"\n{len(self.rows)} checks, {self.failed} failed")


def load_env():
    """Read Supabase config from .env.local. Never echo the values."""
    env_path = REPO_ROOT / ".env.local"
    if not env_path.exists():
        # Worktrees: .env.local lives in the main checkout.
        for parent in REPO_ROOT.parents:
            cand = parent / ".env.local"
            if cand.exists():
                env_path = cand
                break
    values = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or values.get("NEXT_PUBLIC_SUPABASE_URL")
    anon = (os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
            or values.get("NEXT_PUBLIC_SUPABASE_ANON_KEY"))
    svc = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
           or values.get("SUPABASE_SERVICE_ROLE_KEY"))
    if not url or not anon:
        print("[setup] NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are required.")
        sys.exit(2)
    return url.rstrip("/"), anon, svc


def request(url, key, path, method="GET", body=None, timeout=25):
    """Returns (status, short_body). Never raises on HTTP error status."""
    req = urllib.request.Request(
        f"{url}/rest/v1/{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(300).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(300).decode("utf-8", "replace")
    except Exception as exc:  # network/DNS
        return 0, f"{type(exc).__name__}: {exc}"


def denied(status):
    """True only when PostgREST actually refused the request.

    Deliberately strict. An earlier version of this check also treated
    `200 []` as denied, on the theory that RLS had filtered every row - but an
    EMPTY table returns exactly the same thing, so a table that was still wide
    open would have scored a false PASS purely because it held no rows.

    Migration 047 REVOKEs the table grants, so after it is applied PostgREST
    returns 401/403 ("permission denied for table"), not 200. Anything that
    still answers 200 is reachable, whether or not rows come back.
    """
    return status in (401, 403, 404)


def describe(status, body):
    if denied(status):
        return "denied"
    if status == 200 and body.strip() in ("[]", ""):
        return "REACHABLE (empty - grant still present)"
    return "REACHABLE (returns data)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expect-hardened", action="store_true",
                    help="Assert 047 is applied: anon access must be denied.")
    ap.add_argument("--include-write-probes", action="store_true",
                    help="Attempt anonymous ledger forgery and job injection. "
                         "Only safe AFTER 047 is applied - these WRITE if unhardened.")
    args = ap.parse_args()

    url, anon_key, svc_key = load_env()
    r = Result()
    mode = "expect hardened (post-047)" if args.expect_hardened else "baseline report (pre-047)"
    print(f"P0-0 security verification - {mode}")
    print(f"target: {url}   anon key: {len(anon_key)} chars (public)   "
          f"service key: {'present' if svc_key else 'ABSENT'}")

    # ---- 1. anon table reads -------------------------------------------------
    for table in ANON_READABLE_TABLES:
        status, body = request(url, anon_key, f"{table}?select=*&limit=1")
        if args.expect_hardened:
            r.record("anon table reads (must be denied)", table,
                     "PASS" if denied(status) else "FAIL",
                     f"HTTP {status} - {describe(status, body)}")
        else:
            r.record("anon table reads (baseline)", table,
                     "INFO", f"HTTP {status} - {describe(status, body)}")

    # ---- 2. anon RPC invocation (read-only) ---------------------------------
    for fn, payload in ANON_CALLABLE_RPCS_READONLY:
        status, body = request(url, anon_key, f"rpc/{fn}", method="POST", body=payload)
        if args.expect_hardened:
            r.record("anon RPC (must be denied)", fn,
                     "PASS" if denied(status) else "FAIL", f"HTTP {status}")
        else:
            r.record("anon RPC (baseline)", fn, "INFO",
                     f"HTTP {status} {'denied' if denied(status) else 'CALLABLE'}")

    # ---- 3. anon ledger forgery + job injection (gated) --------------------
    if args.include_write_probes:
        if not args.expect_hardened:
            r.record("anon write probes", "refused to run", "SKIP",
                     "write probes require --expect-hardened (they mutate if unhardened)")
        else:
            for fn, payload in ANON_CALLABLE_RPCS_WRITE:
                body_payload = dict(payload)
                for k, v in body_payload.items():
                    if v is None:
                        body_payload[k] = str(uuid.uuid4())
                status, _ = request(url, anon_key, f"rpc/{fn}", method="POST",
                                    body=body_payload)
                r.record("anon ledger forgery (must be denied)", fn,
                         "PASS" if denied(status) else "FAIL", f"HTTP {status}")

            status, _ = request(url, anon_key, "agile_intake_jobs", method="POST", body={
                "company_id": str(uuid.uuid4()), "product_key": "p0-0-probe",
                "intake": [{"source_type": "probe", "text": "security probe"}]})
            r.record("anon job injection (must be denied)", "agile_intake_jobs INSERT",
                     "PASS" if denied(status) else "FAIL", f"HTTP {status}")
    else:
        r.record("anon write probes", "not run", "SKIP",
                 "pass --include-write-probes AFTER applying 047")

    # ---- 4. service_role must still work (no regression) -------------------
    if not svc_key:
        r.record("service_role regression", "all checks", "SKIP",
                 "SUPABASE_SERVICE_ROLE_KEY not available")
    else:
        for table in ["companies", "agents", "runs", "agent_events", "agent_outputs",
                      "agile_intake_jobs", "contractor_rows", "codebase_context_cache"]:
            status, _ = request(url, svc_key, f"{table}?select=*&limit=1")
            r.record("service_role reads (must still work)", table,
                     "PASS" if status == 200 else "FAIL", f"HTTP {status}")
        for fn, payload in ANON_CALLABLE_RPCS_READONLY:
            status, _ = request(url, svc_key, f"rpc/{fn}", method="POST", body=payload)
            r.record("service_role RPC (must still work)", fn,
                     "PASS" if status == 200 else "FAIL", f"HTTP {status}")
        for view in ["agent_cost_summary", "project_cost_summary", "company_cost_summary"]:
            status, _ = request(url, svc_key, f"{view}?select=*&limit=1")
            r.record("service_role cost views (must still work)", view,
                     "PASS" if status == 200 else "FAIL", f"HTTP {status}")

    r.report()
    if not args.expect_hardened:
        print("\nBaseline mode: INFO rows are observations, not assertions. "
              "Re-run with --expect-hardened after applying migration 047.")
    return 1 if r.failed else 0


if __name__ == "__main__":
    sys.exit(main())
