#!/usr/bin/env python3
"""
quota_sync.py — Reads quota from Claude and Codex, posts snapshots to Agent Oversight.
Runs every 4 hours via Windows Task Scheduler.

Credential files read (never written except for token refresh):
  Claude : %USERPROFILE%\.claude\.credentials.json
  Codex  : %USERPROFILE%\.codex\auth.json
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
import json
import time
import base64
import datetime

import requests

sdk_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../python-sdk"))
if sdk_dir not in sys.path:
    sys.path.append(sdk_dir)
from oversight import OversightClient

AGENT_ID         = os.environ.get("QUOTA_SYNC_AGENT_ID", "17ad33d5-7de1-4aa1-b81c-4f654e524ae0")
OVERSIGHT_URL    = os.environ.get("OVERSIGHT_URL", "https://agentoversight.netlify.app")
OVERSIGHT_SECRET = os.environ.get("OVERSIGHT_SECRET") or os.environ.get("INGEST_SECRET", "")
SUPABASE_URL     = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "https://hdhovyrlnfojtkqbcegh.supabase.co")
SUPABASE_KEY     = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
COMPANY_ID       = "87fb6e0d-ebff-4344-9b75-07c1a1a213ac"  # Personal

_PROFILE = os.environ.get("USERPROFILE", os.path.expanduser("~"))


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _decode_jwt_exp(token: str) -> int:
    """Return the exp claim from a JWT payload without verifying signature."""
    try:
        segment = token.split(".")[1]
        segment += "=" * (4 - len(segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode(segment))
        return int(payload.get("exp", 0))
    except Exception:
        return 0


def _hours_until(iso_or_epoch) -> float | None:
    """Return hours from now until a reset time given as ISO string or Unix epoch."""
    if iso_or_epoch is None:
        return None
    try:
        if isinstance(iso_or_epoch, str):
            dt = datetime.datetime.fromisoformat(iso_or_epoch.replace("Z", "+00:00"))
            return (dt - datetime.datetime.now(datetime.timezone.utc)).total_seconds() / 3600
        else:
            return (float(iso_or_epoch) - time.time()) / 3600
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# Claude
# ─────────────────────────────────────────────────────────────

_CLAUDE_CREDS = os.path.join(_PROFILE, ".claude", ".credentials.json")
_CLAUDE_REFRESH_URL = "https://claude.ai/api/oauth/token"


def get_claude_token() -> str | None:
    if not os.path.exists(_CLAUDE_CREDS):
        print("[Claude] .credentials.json not found — using API key auth, quota API unavailable")
        return None

    with open(_CLAUDE_CREDS, "r") as f:
        creds = json.load(f)

    oauth = creds.get("claudeAiOauth", {})
    access_token  = oauth.get("accessToken")
    refresh_token = oauth.get("refreshToken")
    expires_at_ms = oauth.get("expiresAt", 0)

    # Refresh if within 60 seconds of expiry
    if time.time() * 1000 > expires_at_ms - 60_000:
        print("[Claude] Token expired — refreshing...")
        try:
            r = requests.post(_CLAUDE_REFRESH_URL, json={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }, timeout=10)
            r.raise_for_status()
            data = r.json()
            oauth["accessToken"]  = data["access_token"]
            oauth["refreshToken"] = data.get("refresh_token", refresh_token)
            oauth["expiresAt"]    = int(time.time() * 1000) + data.get("expires_in", 3600) * 1000
            creds["claudeAiOauth"] = oauth
            with open(_CLAUDE_CREDS, "w") as f:
                json.dump(creds, f, indent=2)
            access_token = oauth["accessToken"]
            print("[Claude] Token refreshed.")
        except Exception as e:
            print(f"[Claude] Refresh failed: {e}")
            return None

    return access_token


def fetch_claude_quota(token: str) -> dict | None:
    try:
        r = requests.get(
            "https://api.anthropic.com/api/oauth/usage",
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": "oauth-2025-04-20",
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

        five_hour = data.get("five_hour")
        seven_day = data.get("seven_day")

        if not five_hour and not seven_day:
            print("[Claude] No quota windows in response — may not apply to this plan")
            return None

        # Use whichever window is more constrained (lower remaining)
        remaining_5h = round(100 - five_hour.get("utilization", 0), 1) if five_hour else 100.0
        remaining_7d = round(100 - seven_day.get("utilization", 0), 1) if seven_day else 100.0
        remaining_pct = min(remaining_5h, remaining_7d)

        # Report the reset time for whichever window is more constrained
        binding_window = five_hour if remaining_5h <= remaining_7d else seven_day
        hours_until_reset = _hours_until(binding_window.get("resets_at")) if binding_window else None

        print(f"[Claude] 5h: {remaining_5h}% | 7d: {remaining_7d}% | binding: {remaining_pct}%, resets in {hours_until_reset:.1f}h")
        return {
            "provider": "anthropic",
            "quota_remaining_pct": remaining_pct,
            "hours_until_reset": round(hours_until_reset, 2) if hours_until_reset is not None else None,
        }
    except Exception as e:
        print(f"[Claude] Quota fetch failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# Codex
# ─────────────────────────────────────────────────────────────

_CODEX_CREDS = os.path.join(_PROFILE, ".codex", "auth.json")
_CODEX_REFRESH_URL = "https://auth.openai.com/oauth/token"


def get_codex_token() -> tuple[str | None, str | None]:
    """Returns (access_token, account_id)."""
    if not os.path.exists(_CODEX_CREDS):
        print("[Codex] auth.json not found — skipping")
        return None, None

    with open(_CODEX_CREDS, "r") as f:
        creds = json.load(f)

    tokens        = creds.get("tokens", {})
    access_token  = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    account_id    = tokens.get("account_id")

    # Refresh if JWT is expired
    exp = _decode_jwt_exp(access_token) if access_token else 0
    if time.time() > exp - 60:
        print("[Codex] Token expired — refreshing...")
        try:
            r = requests.post(_CODEX_REFRESH_URL, json={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            }, timeout=10)
            r.raise_for_status()
            data = r.json()
            tokens["access_token"]  = data["access_token"]
            tokens["refresh_token"] = data.get("refresh_token", refresh_token)
            if "account_id" in data:
                account_id = data["account_id"]
                tokens["account_id"] = account_id
            creds["tokens"] = tokens
            with open(_CODEX_CREDS, "w") as f:
                json.dump(creds, f, indent=2)
            access_token = tokens["access_token"]
            print("[Codex] Token refreshed.")
        except Exception as e:
            print(f"[Codex] Refresh failed: {e}")
            return None, None

    # Extract account_id from JWT payload if missing from file
    if not account_id and access_token:
        try:
            segment = access_token.split(".")[1]
            segment += "=" * (4 - len(segment) % 4)
            payload = json.loads(base64.urlsafe_b64decode(segment))
            account_id = payload.get("https://api.openai.com/auth", {}).get("chatgpt_account_id")
        except Exception:
            pass

    return access_token, account_id


def fetch_codex_quota(token: str, account_id: str | None) -> dict | None:
    try:
        headers = {"Authorization": f"Bearer {token}"}
        if account_id:
            headers["chatgpt-account-id"] = account_id

        r = requests.get(
            "https://chatgpt.com/backend-api/codex/usage",
            headers=headers,
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

        primary = data.get("rate_limit", {}).get("primary_window")
        if not primary:
            print("[Codex] No primary_window in response")
            return None

        remaining_pct    = round(100 - primary.get("used_percent", 0), 1)
        hours_until_reset = _hours_until(primary.get("reset_at"))

        print(f"[Codex] {remaining_pct}% remaining, resets in {hours_until_reset:.1f}h")
        return {
            "provider": "openai",
            "quota_remaining_pct": remaining_pct,
            "hours_until_reset": round(hours_until_reset, 2) if hours_until_reset is not None else None,
        }
    except Exception as e:
        print(f"[Codex] Quota fetch failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# Write to Supabase directly
# ─────────────────────────────────────────────────────────────

def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

def post_snapshot(provider: str, remaining_pct: float) -> bool:
    try:
        # 1. Get or create provider_account
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/provider_accounts",
            headers=_sb_headers(),
            params={"company_id": f"eq.{COMPANY_ID}", "provider": f"eq.{provider}", "select": "id"},
            timeout=10,
        )
        r.raise_for_status()
        rows = r.json()
        if rows:
            account_id = rows[0]["id"]
        else:
            r2 = requests.post(
                f"{SUPABASE_URL}/rest/v1/provider_accounts",
                headers=_sb_headers(),
                json={"company_id": COMPANY_ID, "provider": provider, "account_type": "subscription"},
                timeout=10,
            )
            r2.raise_for_status()
            account_id = r2.json()[0]["id"]

        # 2. Insert quota snapshot (expires in 4h for api source)
        expires_at = (datetime.datetime.utcnow() + datetime.timedelta(hours=4)).isoformat() + "Z"
        r2 = requests.post(
            f"{SUPABASE_URL}/rest/v1/provider_quota_snapshots",
            headers=_sb_headers(),
            json={
                "provider_account_id": account_id,
                "quota_remaining_pct": remaining_pct,
                "snapshot_source": "api",
                "confidence": "high",
                "expires_at": expires_at,
                "notes": f"quota-sync-agent auto-sync",
            },
            timeout=10,
        )
        r2.raise_for_status()
        print(f"[{provider}] Snapshot written to Supabase: {remaining_pct}% remaining")
        return True
    except Exception as e:
        print(f"[{provider}] Supabase write failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

def main():
    synced = []

    # ── Claude ──
    token = get_claude_token()
    if token:
        quota = fetch_claude_quota(token)
        if quota:
            ok = post_snapshot("anthropic", quota["quota_remaining_pct"])
            if ok:
                synced.append("anthropic")

    # ── Codex ──
    token, account_id = get_codex_token()
    if token:
        quota = fetch_codex_quota(token, account_id)
        if quota:
            ok = post_snapshot("openai", quota["quota_remaining_pct"])
            if ok:
                synced.append("openai")

    print(f"\nDone. Providers synced: {synced or 'none'}")

    # ── Oversight telemetry (best-effort) ──
    try:
        client = OversightClient(url=OVERSIGHT_URL, secret=OVERSIGHT_SECRET)
        with client.run(agent_id=AGENT_ID) as run:
            run.step("quota_sync", message=f"Synced {len(synced)} providers",
                     payload={"providers": synced})
            run.report(tokens_in=0, tokens_out=0, cost_usd=0.0)
    except Exception as e:
        print(f"[telemetry] Skipped: {e}")


if __name__ == "__main__":
    main()
