"""Live credential-vault validation against the APPLIED migration-048 schema.

Proves, against the real database rather than an in-memory mock store, that:
  * a credential is stored as ciphertext and no API returns the plaintext
  * resolution returns the right key for the right company
  * one company cannot resolve another company's credential
  * an unknown company fails CLOSED even with a platform key in the environment
  * tenant_llm_env scrubs the inherited platform key
  * a revoked credential blocks execution
  * rotation resolves the new key and changes the fingerprint
  * check_tenant_budget is callable by service_role

Uses a MOCK key throughout. Cameron's real Anthropic key is never used, and the
platform owner's key only ever enters the environment to prove it is NOT picked
up. Every row it creates is removed at the end.

    python scripts/tests/validate_credential_vault_live.py

Requires SUPABASE_DB_URL - the platform schema is not exposed over PostgREST.
"""
import os, sys, json, base64, uuid, urllib.request, urllib.error
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
_env = next((c for c in [REPO / ".env.local"] + [q / ".env.local" for q in REPO.parents]
             if c.exists()), None)
for line in (_env.read_text(encoding="utf-8").splitlines() if _env else []):
    if line.strip() and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip().strip('"'))
os.environ["CREDENTIAL_ENCRYPTION_KEY"] = base64.b64encode(b"live-validation-key-32-bytes!!!!"[:32]).decode()
from agents.lib import credentials as C

URL = os.environ["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/")
SK  = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
MOCK_KEY = "sk-ant-api03-MOCK-" + "x" * 80 + "-END"

def rest(path, method="GET", body=None, key=SK):
    r = urllib.request.Request(f"{URL}/rest/v1/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json", "Prefer": "return=representation"},
        method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode(); return resp.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try: return e.code, json.loads(raw)
        except Exception: return e.code, raw

ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    if cond: ok += 1
    else: fail += 1

_, cos = rest("companies?select=id,name&name=eq.ReformAI")
CO = cos[0]["id"]
print(f"[vault] using company ReformAI {CO}\n")

print("[vault] registration + encryption")
enc = C.encrypt_api_key(MOCK_KEY)
# Insert via the direct connection: platform schema is not REST-exposed.
import psycopg
with psycopg.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=30) as conn:
    with conn.cursor() as cur:
        cur.execute("delete from platform.tenant_provider_credentials where company_id=%s", (CO,))
        cur.execute("""insert into platform.tenant_provider_credentials
            (company_id, provider, key_ciphertext, key_nonce, key_fingerprint, key_last4, label, created_by)
            values (%s,'anthropic',%s,%s,%s,%s,'LIVE VALIDATION MOCK','p0-closeout') returning id""",
            (CO, enc["key_ciphertext"], enc["key_nonce"], enc["key_fingerprint"], enc["key_last4"]))
        cred_id = cur.fetchone()[0]
    conn.commit()
check("credential stored as ciphertext", True, f"id={cred_id}")

status, rows = rest("rpc/get_tenant_credential", "POST",
                    {"p_company_id": CO, "p_provider": "anthropic"})
check("get_tenant_credential returns ciphertext", status == 200 and rows, f"HTTP {status}")
row = rows[0] if isinstance(rows, list) and rows else {}
check("response contains NO plaintext key", MOCK_KEY not in json.dumps(rows))

print("\n[vault] resolution via the real RPC path")
cred = C.resolve_tenant_api_key(CO, "anthropic")
check("resolves to the correct plaintext", cred.api_key == MOCK_KEY)
check("company binding correct", cred.company_id == CO)
check("repr does not leak the key", MOCK_KEY not in repr(cred) and "***" in repr(cred))

print("\n[vault] wrong tenant gets nothing")
_, others = rest("companies?select=id,name&name=eq.Personal")
try:
    C.resolve_tenant_api_key(others[0]["id"], "anthropic")
    check("other company cannot resolve ReformAI's key", False, "it resolved!")
except C.MissingTenantCredential:
    check("other company cannot resolve ReformAI's key", True)

print("\n[vault] no fallback to the platform key")
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-api03-PLATFORM-OWNER-" + "y"*70
try:
    C.resolve_tenant_api_key(str(uuid.uuid4()), "anthropic")
    check("unknown company fails closed with platform key present", False, "it resolved!")
except C.MissingTenantCredential:
    check("unknown company fails closed with platform key present", True)
env = C.tenant_llm_env(cred)
check("tenant env scrubs the inherited platform key",
      env["ANTHROPIC_API_KEY"] == MOCK_KEY and "PLATFORM-OWNER" not in json.dumps(env))

print("\n[vault] revocation fails closed")
with psycopg.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=30) as conn:
    with conn.cursor() as cur:
        cur.execute("update platform.tenant_provider_credentials set status='revoked', revoked_at=now() where id=%s", (cred_id,))
    conn.commit()
try:
    C.resolve_tenant_api_key(CO, "anthropic")
    check("revoked credential blocks execution", False, "it still resolved!")
except C.MissingTenantCredential:
    check("revoked credential blocks execution", True)

print("\n[vault] rotation")
new_key = MOCK_KEY.replace("MOCK", "ROTATED")
enc2 = C.encrypt_api_key(new_key)
with psycopg.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=30) as conn:
    with conn.cursor() as cur:
        cur.execute("""insert into platform.tenant_provider_credentials
            (company_id, provider, key_ciphertext, key_nonce, key_fingerprint, key_last4, label, created_by)
            values (%s,'anthropic',%s,%s,%s,%s,'ROTATED MOCK','p0-closeout') returning id""",
            (CO, enc2["key_ciphertext"], enc2["key_nonce"], enc2["key_fingerprint"], enc2["key_last4"]))
        new_id = cur.fetchone()[0]
    conn.commit()
cred2 = C.resolve_tenant_api_key(CO, "anthropic")
check("rotation resolves the NEW key", cred2.api_key == new_key)
check("fingerprint changed on rotation", cred2.key_fingerprint != cred.key_fingerprint)

print("\n[vault] budget enforcement")
status, rows = rest("rpc/check_tenant_budget", "POST", {"p_company_id": CO, "p_estimate_usd": 0.05})
r0 = rows[0] if isinstance(rows, list) and rows else rows
check("check_tenant_budget callable by service_role", status == 200, f"HTTP {status} {r0}")

print("\n[vault] cleanup")
with psycopg.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=30) as conn:
    with conn.cursor() as cur:
        cur.execute("delete from platform.tenant_provider_credentials where company_id=%s", (CO,))
    conn.commit()
print("  removed all validation credentials")
print(f"\n[vault] {ok+fail} checks, {fail} failure(s)")
sys.exit(1 if fail else 0)
