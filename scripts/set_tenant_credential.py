"""
Store or rotate a tenant's LLM provider key in the credential vault.

    python scripts/set_tenant_credential.py --company-slug cameron-swim-school-prototype \
        --from-env NEW_ANTHROPIC_API_KEY --label "Suit Up - Cameron's own Anthropic key"

How the key gets in WITHOUT passing through a chat window or a shell history:
  1. Put the key in `.env.local` on ONE line, under the name you pass to --from-env
     (e.g. NEW_ANTHROPIC_API_KEY=sk-ant-...).
  2. Run this script. It reads that variable, checks the key against the provider
     (a free model-list call, no tokens billed), encrypts it with
     CREDENTIAL_ENCRYPTION_KEY (AES-256-GCM, agents/lib/credentials.py), inserts
     the new row as 'active' and marks the previous active row 'revoked'.
  3. Delete the line from `.env.local` again. The vault is the only copy.

Nothing here prints, logs or returns the key. Output is last4 + fingerprint.
Rotation is a new row plus a revoke, never an UPDATE of the ciphertext, so the
audit trail of which key was active when is kept (migration 048).

Requires SUPABASE_DB_URL (the platform schema is not exposed over PostgREST)
and CREDENTIAL_ENCRYPTION_KEY - the SAME master key the worker uses, or the
worker will not be able to decrypt what this stores.
"""
from __future__ import annotations

import os
import sys
import json
import argparse
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv, find_dotenv  # noqa: E402
load_dotenv(find_dotenv(".env.local", usecwd=True), override=True)

import psycopg  # noqa: E402
from agents.lib import credentials as CRED  # noqa: E402

PROVIDERS = ("anthropic", "openai", "google")


def _validate_anthropic(api_key: str) -> str | None:
    """GET /v1/models - authenticates the key without spending tokens.
    Returns None on success, else a short error string."""
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/models?limit=1",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            json.loads(resp.read().decode())
        return None
    except urllib.error.HTTPError as exc:
        return f"provider returned HTTP {exc.code}"
    except Exception as exc:  # network
        return f"could not reach provider: {type(exc).__name__}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--company-slug", help="public.companies.slug")
    g.add_argument("--company-id", help="public.companies.id")
    ap.add_argument("--provider", default="anthropic", choices=PROVIDERS)
    ap.add_argument("--from-env", required=True, metavar="VAR",
                    help="environment variable holding the new key (set it in .env.local, then remove it)")
    ap.add_argument("--label", default=None, help="human label stored with the row (never the key)")
    ap.add_argument("--no-validate", action="store_true", help="skip the provider check (anthropic only is checked)")
    ap.add_argument("--dry-run", action="store_true", help="validate and encrypt, write nothing")
    args = ap.parse_args()

    api_key = os.environ.get(args.from_env, "").strip()
    if not api_key:
        print(f"[cred] {args.from_env} is empty or unset. Put the key in .env.local under that name and re-run.")
        return 2
    if args.provider == "anthropic" and not api_key.startswith("sk-ant-"):
        print("[cred] that does not look like an Anthropic key (expected sk-ant-...). Refusing.")
        return 2

    db_url = os.environ.get("SUPABASE_DB_URL", "")
    if not db_url:
        print("[cred] SUPABASE_DB_URL is not set")
        return 3

    if args.provider == "anthropic" and not args.no_validate:
        err = _validate_anthropic(api_key)
        if err:
            print(f"[cred] the key was rejected: {err}. Nothing stored.")
            return 4
        print("[cred] provider accepted the key (model-list call, no tokens billed)")

    enc = CRED.encrypt_api_key(api_key)
    new_fp = enc["key_fingerprint"]
    print(f"[cred] encrypted: last4 {enc['key_last4']}, fingerprint {new_fp[:12]}...")

    with psycopg.connect(db_url, autocommit=False) as conn, conn.cursor() as cur:
        if args.company_id:
            cur.execute("select id, name from public.companies where id = %s", (args.company_id,))
        else:
            cur.execute("select id, name from public.companies where slug = %s", (args.company_slug,))
        row = cur.fetchone()
        if not row:
            print("[cred] company not found")
            return 3
        company_id, company_name = str(row[0]), row[1]

        cur.execute("select id, key_last4, key_fingerprint, label from platform.tenant_provider_credentials "
                    "where company_id = %s and provider = %s and status = 'active'",
                    (company_id, args.provider))
        current = cur.fetchone()
        if current:
            print(f"[cred] current active {args.provider} key for {company_name}: last4 {current[1]}, "
                  f"label {current[3]!r}")
            if current[2] == new_fp:
                print("[cred] the new key is identical to the active one (same fingerprint). Nothing to do.")
                return 0
        else:
            print(f"[cred] no active {args.provider} key for {company_name} yet")

        if args.dry_run:
            print("[cred] dry run - nothing written")
            conn.rollback()
            return 0

        if current:
            cur.execute("update platform.tenant_provider_credentials set status = 'revoked', revoked_at = now() "
                        "where id = %s", (current[0],))
        cur.execute(
            "insert into platform.tenant_provider_credentials (company_id, provider, key_ciphertext, key_nonce, "
            "key_fingerprint, key_last4, status, label, created_by, validated_at) values "
            "(%s, %s, %s, %s, %s, %s, 'active', %s, %s, case when %s then now() else null end) returning id",
            (company_id, args.provider, enc["key_ciphertext"], enc["key_nonce"], new_fp, enc["key_last4"],
             args.label or f"{company_name} - own {args.provider} key",
             "scripts/set_tenant_credential.py", not args.no_validate and args.provider == "anthropic"))
        new_id = cur.fetchone()[0]
        conn.commit()

    # Prove the worker will resolve it: decrypt through the same path the worker uses.
    resolved = CRED.resolve_tenant_api_key(company_id, args.provider)
    ok = resolved.key_fingerprint == new_fp and resolved.credential_id == str(new_id)
    print(f"[cred] stored {new_id} as active; worker resolution {'OK' if ok else 'MISMATCH'} "
          f"(last4 {resolved.key_last4})")
    if current:
        print(f"[cred] previous key {current[0]} marked revoked (kept for audit)")
    print(f"[cred] now remove {args.from_env} from .env.local")
    return 0 if ok else 5


if __name__ == "__main__":
    sys.exit(main())
