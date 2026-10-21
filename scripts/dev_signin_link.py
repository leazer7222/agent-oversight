#!/usr/bin/env python3
"""
Mint a one-time sign-in link for an EXISTING user without sending an email.

Why: Supabase's built-in SMTP rate-limits magic-link emails (a handful per
hour). The Auth admin API can generate the same single-use token directly;
this script turns it into a link to THIS app's callback, which verifies the
token hash server-side (src/app/auth/callback/route.ts). Nothing is weakened:
the token is Supabase-issued, single-use and expires like the emailed one.

Requires the service-role key, so it only ever runs on an operator machine.
The link is printed ONCE to stdout and nowhere else. Treat it like a password.

    python scripts/dev_signin_link.py --email you@example.com [--base http://localhost:3000] [--next /dashboard/sourcing]
"""

from __future__ import annotations

import os
import sys
import json
import argparse
import urllib.parse
import urllib.request
import urllib.error

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(".env.local", usecwd=True), override=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--next", dest="next_path", default="/dashboard/sourcing")
    args = ap.parse_args()

    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        print("NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required", file=sys.stderr)
        return 2

    body = {"type": "magiclink", "email": args.email,
            "options": {"redirect_to": f"{args.base}/auth/callback"}}
    req = urllib.request.Request(
        f"{url}/auth/v1/admin/generate_link",
        data=json.dumps(body).encode(),
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(f"generate_link failed: HTTP {exc.code} {exc.read(300).decode('utf-8', 'replace')}", file=sys.stderr)
        return 1

    props = data.get("properties") or data
    token_hash = props.get("hashed_token")
    if not token_hash:
        print("no hashed_token in response", file=sys.stderr)
        return 1

    qs = urllib.parse.urlencode({"token_hash": token_hash, "type": "magiclink", "next": args.next_path})
    print(f"{args.base}/auth/callback?{qs}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
