"""
cache.py - read/write the commit-scoped codebase_context_cache (step 8).

Key: (product_key, repo, commit_sha, parser_version). On hit, the caller skips extraction
and reuses the inventory + coverage. agent_outputs stays the published-artifact store; this
is the reusable truth cache. Uses Supabase REST (service role); DDL lives in migration 036.
"""
from __future__ import annotations

import os
import requests
from typing import Optional


def _conn() -> tuple[str, dict]:
    url = os.environ["NEXT_PUBLIC_SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return url, {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def get_cached(product_key: str, repo: str, commit_sha: str, parser_version: str) -> Optional[dict]:
    url, h = _conn()
    params = {
        "product_key": f"eq.{product_key}", "repo": f"eq.{repo}",
        "commit_sha": f"eq.{commit_sha}", "parser_version": f"eq.{parser_version}",
        "select": "id,inventory_json,coverage_report_json,semantic_context_json,created_at", "limit": "1",
    }
    r = requests.get(f"{url}/rest/v1/codebase_context_cache", headers=h, params=params, timeout=20)
    if not r.ok:
        raise RuntimeError(f"cache read failed: {r.status_code} {r.text}")
    rows = r.json()
    return rows[0] if rows else None


def put_cache(*, tenant_id: Optional[str], product_key: str, repo: str, branch: Optional[str],
              commit_sha: str, parser_version: str, inventory_json: dict,
              coverage_report_json: dict, semantic_context_json: Optional[dict] = None) -> str:
    url, h = _conn()
    h = {**h, "Prefer": "resolution=merge-duplicates,return=representation"}
    payload = {
        "tenant_id": tenant_id, "product_key": product_key, "repo": repo, "branch": branch,
        "commit_sha": commit_sha, "parser_version": parser_version,
        "inventory_json": inventory_json, "coverage_report_json": coverage_report_json,
        "semantic_context_json": semantic_context_json,
    }
    r = requests.post(
        f"{url}/rest/v1/codebase_context_cache?on_conflict=product_key,repo,commit_sha,parser_version",
        headers=h, json=payload, timeout=30)
    if not r.ok:
        raise RuntimeError(f"cache write failed: {r.status_code} {r.text}")
    d = r.json()
    return (d[0] if isinstance(d, list) else d).get("id", "")
