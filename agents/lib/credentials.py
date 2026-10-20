"""
Tenant provider credential resolution (P0-2).

Billing isolation rule, stated once and enforced everywhere below:
a tenant's agent runs on THAT TENANT'S provider key or it does not run at all.
There is no fallback to a platform key, ever, under any failure mode.

Three things make that true rather than aspirational:

  1. resolve_tenant_api_key() raises MissingTenantCredential when no active
     credential exists. It never returns a default.
  2. tenant_llm_env() SCRUBS the inherited provider variables from the
     environment dict it builds. Without this step the Anthropic SDK would
     silently fall back to ANTHROPIC_API_KEY from the parent process - the
     platform owner's key - and the failure would be invisible: the agent would
     work, and the bill would land in the wrong account. This is the single most
     important function in this module.
  3. Nothing here ever logs, prints, or returns plaintext key material. Display
     uses last4 and a SHA-256 fingerprint.

The database side is migration 048: platform.tenant_provider_credentials plus
public.get_tenant_credential(), which returns CIPHERTEXT and is granted to
service_role only.
"""

from __future__ import annotations

import os
import json
import base64
import hashlib
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

# Provider env vars that must never leak into a tenant agent's environment.
# ANTHROPIC_BASE_URL is included because Claude Code injects a real value that
# would redirect a tenant's calls through the platform's endpoint.
_PROVIDER_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_CUSTOM_HEADERS",
    "ANTHROPIC_BASE_URL",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
)

_PROVIDER_ENV_TARGET = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GEMINI_API_KEY",
}


class CredentialError(Exception):
    """Base class. Carries an error category for telemetry."""

    category = "credential_error"


class MissingTenantCredential(CredentialError):
    """No active credential for this (company, provider). Execution must stop."""

    category = "missing_tenant_credential"


class CredentialDecryptionError(CredentialError):
    """Ciphertext present but undecryptable - wrong or rotated master key."""

    category = "credential_decryption_error"


class ProviderAuthError(CredentialError):
    """The tenant's key was rejected by the provider."""

    category = "provider_auth_error"


@dataclass(frozen=True)
class ResolvedCredential:
    company_id: str
    provider: str
    credential_id: str
    api_key: str          # plaintext - never log, never serialise
    key_last4: str
    key_fingerprint: str

    def __repr__(self) -> str:  # pragma: no cover - defensive
        # Explicit repr so an accidental print() or an exception traceback that
        # includes locals cannot expose the key.
        return (
            f"ResolvedCredential(company_id={self.company_id!r}, "
            f"provider={self.provider!r}, credential_id={self.credential_id!r}, "
            f"api_key='***{self.key_last4}', fingerprint={self.key_fingerprint[:12]!r})"
        )

    __str__ = __repr__


# ---------------------------------------------------------------------------
# Encryption: AES-256-GCM, master key from CREDENTIAL_ENCRYPTION_KEY.
# ---------------------------------------------------------------------------

def _master_key() -> bytes:
    raw = os.environ.get("CREDENTIAL_ENCRYPTION_KEY", "")
    if not raw:
        raise CredentialError(
            "CREDENTIAL_ENCRYPTION_KEY is not set. Tenant credentials cannot be "
            "encrypted or decrypted without it."
        )
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise CredentialError(
            "CREDENTIAL_ENCRYPTION_KEY must be base64-encoded 32 bytes"
        ) from exc
    if len(key) != 32:
        raise CredentialError(
            f"CREDENTIAL_ENCRYPTION_KEY must decode to 32 bytes, got {len(key)}"
        )
    return key


def fingerprint(api_key: str) -> str:
    """Stable identifier for a key without revealing it. Used for equality
    checks and for confirming a rotation actually changed the key."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def encrypt_api_key(api_key: str) -> dict:
    """Returns the fields migration 048 stores. Plaintext is not retained."""
    if not api_key or not api_key.strip():
        raise CredentialError("refusing to encrypt an empty api key")
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:  # pragma: no cover
        raise CredentialError(
            "the 'cryptography' package is required for credential encryption "
            "(pip install cryptography)"
        ) from exc

    nonce = os.urandom(12)
    ciphertext = AESGCM(_master_key()).encrypt(nonce, api_key.encode("utf-8"), None)
    return {
        "key_ciphertext": ciphertext,
        "key_nonce": nonce,
        "key_fingerprint": fingerprint(api_key),
        "key_last4": api_key[-4:],
    }


def decrypt_api_key(ciphertext: bytes, nonce: bytes) -> str:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:  # pragma: no cover
        raise CredentialError("the 'cryptography' package is required") from exc
    try:
        return AESGCM(_master_key()).decrypt(nonce, ciphertext, None).decode("utf-8")
    except Exception as exc:
        raise CredentialDecryptionError(
            "stored credential could not be decrypted - CREDENTIAL_ENCRYPTION_KEY "
            "may have changed since it was written"
        ) from exc


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def _rpc_fetcher(company_id: str, provider: str) -> Optional[dict]:
    """Default fetcher: calls public.get_tenant_credential via PostgREST using
    the service role key. Returns None when no active credential exists."""
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise CredentialError(
            "NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required "
            "to resolve tenant credentials"
        )
    req = urllib.request.Request(
        f"{url}/rest/v1/rpc/get_tenant_credential",
        data=json.dumps({"p_company_id": company_id, "p_provider": provider}).encode(),
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            rows = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise CredentialError(
            f"credential lookup failed (HTTP {exc.code})"
        ) from exc
    if not rows:
        return None
    row = rows[0] if isinstance(rows, list) else rows
    # PostgREST returns bytea as a hex string prefixed with \x
    def _unhex(v):
        if isinstance(v, str) and v.startswith("\\x"):
            return bytes.fromhex(v[2:])
        if isinstance(v, str):
            return base64.b64decode(v)
        return v
    return {
        "credential_id": row["credential_id"],
        "key_ciphertext": _unhex(row["key_ciphertext"]),
        "key_nonce": _unhex(row["key_nonce"]),
        "key_fingerprint": row["key_fingerprint"],
        "key_last4": row["key_last4"],
    }


def resolve_tenant_api_key(
    company_id: str,
    provider: str = "anthropic",
    *,
    fetcher: Callable[[str, str], Optional[dict]] = _rpc_fetcher,
) -> ResolvedCredential:
    """Resolve a tenant's provider key. FAILS CLOSED.

    Raises MissingTenantCredential when the tenant has no active credential.
    Never returns a platform-owned key as a fallback - that is the whole point
    of this module, and the test suite asserts it even when a platform key is
    present in the environment.
    """
    if not company_id:
        raise MissingTenantCredential("company_id is required to resolve a credential")
    if provider not in _PROVIDER_ENV_TARGET:
        raise CredentialError(f"unsupported provider: {provider!r}")

    row = fetcher(company_id, provider)
    if not row:
        raise MissingTenantCredential(
            f"no active {provider} credential for company {company_id}. "
            f"Execution stops here by design: there is no platform-key fallback."
        )

    api_key = decrypt_api_key(row["key_ciphertext"], row["key_nonce"])

    stored = row.get("key_fingerprint")
    if stored and fingerprint(api_key) != stored:
        raise CredentialDecryptionError(
            "decrypted credential does not match its stored fingerprint"
        )

    return ResolvedCredential(
        company_id=company_id,
        provider=provider,
        credential_id=row["credential_id"],
        api_key=api_key,
        key_last4=row["key_last4"],
        key_fingerprint=stored or fingerprint(api_key),
    )


def tenant_llm_env(cred: ResolvedCredential, base_env: Optional[dict] = None) -> dict:
    """Build an environment for a tenant agent subprocess or SDK client.

    Scrubs EVERY inherited provider variable before injecting the tenant's key.
    This is what prevents silent cross-tenant billing: if the tenant key were
    merely added on top of an inherited ANTHROPIC_API_KEY, SDK precedence or an
    explicit-arg omission anywhere downstream could quietly use the wrong one.
    """
    env = dict(os.environ if base_env is None else base_env)
    for var in _PROVIDER_ENV_VARS:
        env.pop(var, None)
    env[_PROVIDER_ENV_TARGET[cred.provider]] = cred.api_key
    env["OVERSIGHT_TENANT_COMPANY_ID"] = cred.company_id
    env["OVERSIGHT_CREDENTIAL_ID"] = cred.credential_id
    return env


def scrub_platform_provider_env() -> list:
    """Remove inherited provider vars from THIS process. Call at the top of any
    tenant-scoped worker before constructing SDK clients. Returns the names
    removed, for telemetry - never the values."""
    removed = []
    for var in _PROVIDER_ENV_VARS:
        if var in os.environ:
            del os.environ[var]
            removed.append(var)
    return removed


def check_tenant_budget(company_id: str, estimate_usd: float = 0.0) -> dict:
    """Fail-closed spend ceiling (P0-3) via public.check_tenant_budget."""
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise CredentialError("supabase config required for budget check")
    req = urllib.request.Request(
        f"{url}/rest/v1/rpc/check_tenant_budget",
        data=json.dumps({"p_company_id": company_id, "p_estimate_usd": estimate_usd}).encode(),
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        rows = json.loads(resp.read().decode())
    row = (rows[0] if isinstance(rows, list) and rows else rows) or {}
    return {
        "allowed": bool(row.get("allowed", False)),
        "reason": row.get("reason", "unknown"),
        "spent_usd": row.get("spent_usd"),
        "limit_usd": row.get("limit_usd"),
    }
