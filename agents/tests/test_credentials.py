"""
Billing-isolation tests (P0-2). Runs with no database and no network.

The test that matters most is test_fails_closed_even_with_platform_key_present:
it asserts that a tenant run dies rather than quietly spending the platform
owner's money. Everything else here is supporting detail.

    python -m pytest agents/tests/test_credentials.py -v
    python agents/tests/test_credentials.py          # no pytest needed
"""

from __future__ import annotations

import os
import sys
import base64
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agents.lib import credentials as C  # noqa: E402

PLATFORM_KEY = "sk-ant-api03-PLATFORM-OWNER-KEY-DO-NOT-USE-1234"
CAMERON_KEY = "sk-ant-api03-CAMERON-OWN-ACCOUNT-KEY-5678"
CAMERON_CO = "11111111-1111-1111-1111-111111111111"
OTHER_CO = "22222222-2222-2222-2222-222222222222"


class CredentialTestBase(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in C._PROVIDER_ENV_VARS}
        os.environ["CREDENTIAL_ENCRYPTION_KEY"] = base64.b64encode(b"k" * 32).decode()

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    @staticmethod
    def _store(keys: dict) -> callable:
        """Build a fetcher backed by an in-memory encrypted store."""
        rows = {}
        for (company, provider), plaintext in keys.items():
            enc = C.encrypt_api_key(plaintext)
            rows[(company, provider)] = {
                "credential_id": f"cred-{company[:8]}-{provider}",
                **enc,
            }

        def fetcher(company_id, provider):
            return rows.get((company_id, provider))

        return fetcher


class TestEncryption(CredentialTestBase):
    def test_round_trip(self):
        enc = C.encrypt_api_key(CAMERON_KEY)
        self.assertEqual(C.decrypt_api_key(enc["key_ciphertext"], enc["key_nonce"]),
                         CAMERON_KEY)

    def test_ciphertext_does_not_contain_plaintext(self):
        enc = C.encrypt_api_key(CAMERON_KEY)
        self.assertNotIn(CAMERON_KEY.encode(), enc["key_ciphertext"])

    def test_nonce_differs_per_encryption(self):
        a, b = C.encrypt_api_key(CAMERON_KEY), C.encrypt_api_key(CAMERON_KEY)
        self.assertNotEqual(a["key_nonce"], b["key_nonce"])
        self.assertNotEqual(a["key_ciphertext"], b["key_ciphertext"])

    def test_only_last4_and_fingerprint_are_disclosable(self):
        enc = C.encrypt_api_key(CAMERON_KEY)
        self.assertEqual(enc["key_last4"], CAMERON_KEY[-4:])
        self.assertEqual(len(enc["key_fingerprint"]), 64)
        self.assertNotIn(CAMERON_KEY, enc["key_fingerprint"])

    def test_wrong_master_key_fails_loudly(self):
        enc = C.encrypt_api_key(CAMERON_KEY)
        os.environ["CREDENTIAL_ENCRYPTION_KEY"] = base64.b64encode(b"x" * 32).decode()
        with self.assertRaises(C.CredentialDecryptionError):
            C.decrypt_api_key(enc["key_ciphertext"], enc["key_nonce"])

    def test_refuses_empty_key(self):
        with self.assertRaises(C.CredentialError):
            C.encrypt_api_key("   ")

    def test_master_key_must_be_32_bytes(self):
        os.environ["CREDENTIAL_ENCRYPTION_KEY"] = base64.b64encode(b"short").decode()
        with self.assertRaises(C.CredentialError):
            C.encrypt_api_key(CAMERON_KEY)


class TestBillingIsolation(CredentialTestBase):
    def test_resolves_the_tenants_own_key(self):
        fetcher = self._store({(CAMERON_CO, "anthropic"): CAMERON_KEY})
        cred = C.resolve_tenant_api_key(CAMERON_CO, "anthropic", fetcher=fetcher)
        self.assertEqual(cred.api_key, CAMERON_KEY)
        self.assertEqual(cred.company_id, CAMERON_CO)

    def test_fails_closed_even_with_platform_key_present(self):
        """THE billing-isolation test.

        A platform key sits in the environment, exactly as it does inside a real
        Claude Code session or on a shared worker host. Cameron has no stored
        credential. The resolver must raise rather than fall back.
        """
        os.environ["ANTHROPIC_API_KEY"] = PLATFORM_KEY
        fetcher = self._store({})  # Cameron has nothing stored

        with self.assertRaises(C.MissingTenantCredential) as ctx:
            C.resolve_tenant_api_key(CAMERON_CO, "anthropic", fetcher=fetcher)

        # And the platform key must not appear in the failure message.
        self.assertNotIn(PLATFORM_KEY, str(ctx.exception))
        self.assertEqual(ctx.exception.category, "missing_tenant_credential")

    def test_one_tenants_credential_is_not_visible_to_another(self):
        fetcher = self._store({(CAMERON_CO, "anthropic"): CAMERON_KEY})
        with self.assertRaises(C.MissingTenantCredential):
            C.resolve_tenant_api_key(OTHER_CO, "anthropic", fetcher=fetcher)

    def test_env_scrubs_inherited_platform_key(self):
        """The subtle failure this prevents: tenant key added on top of an
        inherited platform key, letting SDK precedence pick the wrong one."""
        os.environ["ANTHROPIC_API_KEY"] = PLATFORM_KEY
        os.environ["ANTHROPIC_AUTH_TOKEN"] = ""
        os.environ["ANTHROPIC_BASE_URL"] = "https://platform.example.invalid"

        fetcher = self._store({(CAMERON_CO, "anthropic"): CAMERON_KEY})
        cred = C.resolve_tenant_api_key(CAMERON_CO, "anthropic", fetcher=fetcher)
        env = C.tenant_llm_env(cred)

        self.assertEqual(env["ANTHROPIC_API_KEY"], CAMERON_KEY)
        self.assertNotIn("ANTHROPIC_AUTH_TOKEN", env)
        self.assertNotIn("ANTHROPIC_BASE_URL", env)
        self.assertNotIn(PLATFORM_KEY, env.values())
        self.assertEqual(env["OVERSIGHT_TENANT_COMPANY_ID"], CAMERON_CO)

    def test_scrub_platform_provider_env_clears_this_process(self):
        os.environ["ANTHROPIC_API_KEY"] = PLATFORM_KEY
        os.environ["OPENAI_API_KEY"] = "sk-openai-platform"
        removed = C.scrub_platform_provider_env()
        self.assertIn("ANTHROPIC_API_KEY", removed)
        self.assertIn("OPENAI_API_KEY", removed)
        self.assertNotIn("ANTHROPIC_API_KEY", os.environ)

    def test_no_company_id_fails_closed(self):
        with self.assertRaises(C.MissingTenantCredential):
            C.resolve_tenant_api_key("", "anthropic", fetcher=self._store({}))

    def test_unsupported_provider_rejected(self):
        with self.assertRaises(C.CredentialError):
            C.resolve_tenant_api_key(CAMERON_CO, "cohere", fetcher=self._store({}))

    def test_fingerprint_mismatch_is_detected(self):
        fetcher = self._store({(CAMERON_CO, "anthropic"): CAMERON_KEY})
        original = fetcher(CAMERON_CO, "anthropic")

        def tampered(company_id, provider):
            row = dict(original)
            row["key_fingerprint"] = "0" * 64
            return row

        with self.assertRaises(C.CredentialDecryptionError):
            C.resolve_tenant_api_key(CAMERON_CO, "anthropic", fetcher=tampered)


class TestNoLeakage(CredentialTestBase):
    def test_repr_and_str_do_not_expose_the_key(self):
        fetcher = self._store({(CAMERON_CO, "anthropic"): CAMERON_KEY})
        cred = C.resolve_tenant_api_key(CAMERON_CO, "anthropic", fetcher=fetcher)
        for rendered in (repr(cred), str(cred), f"{cred}"):
            self.assertNotIn(CAMERON_KEY, rendered)
            self.assertIn("***", rendered)

    def test_rotation_changes_the_fingerprint(self):
        old = C.fingerprint(CAMERON_KEY)
        new = C.fingerprint(CAMERON_KEY + "-rotated")
        self.assertNotEqual(old, new)


if __name__ == "__main__":
    unittest.main(verbosity=2)
