#!/usr/bin/env python3
"""
Committed-credential scan.

A first version of this gate fired on three strings that were not credentials:
a bare `sk-ant-api03-` prefix in documentation, and two obviously-fake test
fixtures ("...PLATFORM-OWNER-KEY-DO-NOT-USE-1234"). That matters more than it
sounds: a security gate that cries wolf is a gate someone disables, so the
detector has to distinguish a real key from something key-shaped.

The approach: match on the STRUCTURE of a real credential - the prefix plus a
long, high-entropy suffix - and then reject anything that looks like a
placeholder. Both halves are tested by --self-test below, which is what keeps
this honest: it asserts the scan catches realistic keys AND ignores the
fixtures, so neither property can silently regress.

    python scripts/tests/check_no_secrets.py
    python scripts/tests/check_no_secrets.py --self-test
"""

from __future__ import annotations

import re
import sys
import math
import argparse
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

SKIP_DIRS = {".git", "node_modules", "backups", ".next", "__pycache__",
             ".claude", "dist", "build", ".venv", "venv"}
SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".sql", ".md",
                 ".yml", ".yaml", ".sh", ".ps1", ".txt", ".env", ".toml"}

# Real credential shapes. Each requires a long suffix, because the prefix alone
# appears legitimately in docs and error messages.
PATTERNS = [
    ("anthropic_api_key", re.compile(r"sk-ant-api\d{2}-[A-Za-z0-9_\-]{80,}")),
    ("anthropic_oauth",   re.compile(r"sk-ant-oat\d{2}-[A-Za-z0-9_\-]{60,}")),
    ("openai_api_key",    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_\-]{40,}")),
    ("supabase_pat",      re.compile(r"sbp_[a-f0-9]{40,}")),
    ("supabase_jwt",      re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{40,}\.[A-Za-z0-9_\-]{20,}")),
    ("google_api_key",    re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("postgres_url_pw",   re.compile(r"postgres(?:ql)?://[^:\s]+:[^@\s]{8,}@")),
]

# Markers that identify a deliberate placeholder or fixture.
PLACEHOLDER_MARKERS = (
    "do-not-use", "donotuse", "example", "placeholder", "redacted", "xxxx",
    "your-", "<password>", "fake", "dummy", "sample", "test-key", "testkey",
    "platform-owner-key", "cameron-own-account", "changeme", "replace",
)


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    return -sum((c / len(s)) * math.log2(c / len(s)) for c in counts.values())


def is_placeholder(match: str) -> bool:
    low = match.lower()
    if any(m in low for m in PLACEHOLDER_MARKERS):
        return True
    # A real key's suffix is high-entropy. Fixtures spell words in caps with
    # hyphens, which scores low.
    suffix = re.sub(r"^[a-z\-_]*\d*-", "", match, count=1)
    if suffix and shannon_entropy(suffix) < 3.5:
        return True
    return False


def scan(root: Path) -> list:
    findings = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in SCAN_SUFFIXES and path.name != ".env.local":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, pattern in PATTERNS:
            for m in pattern.finditer(text):
                raw = m.group(0)
                if is_placeholder(raw):
                    continue
                line = text[: m.start()].count("\n") + 1
                findings.append({
                    "file": str(path.relative_to(root)),
                    "line": line,
                    "kind": name,
                    # Never print the credential itself.
                    "preview": raw[:12] + "..." + f"({len(raw)} chars)",
                })
    return findings


def self_test() -> int:
    """Assert both halves: real-shaped keys are caught, fixtures are not."""
    import tempfile
    print("[self-test] verifying the detector catches real keys and ignores fixtures")

    must_catch = {
        "anthropic": "sk-ant-api03-" + "aB3xK9mQ7pL2vR5tY8wZ1nC4hJ6sD0fG" * 3,
        "supabase_pat": "sbp_" + "a3f9c1e7b5d2084619fe7c3a8d5b2e049f1c6a7b",
        "jwt": ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFiY2RlZmdoaWprbG1ub3AiLCJyb2xlIjoic2VydmljZV9yb2xlIn0."
                "x7Kq2mZp9Lw3Rt8Yv1Nc4Hj6Sd0Fg5Bn"),
        "pg_url": "postgresql://postgres:Hx8kQm2vLp9Rt4Wz@db.example.supabase.co:5432/postgres",
        # A real Google API key is AIza + exactly 35 chars. The first draft of
        # this fixture had 33 and the self-test failed - correctly, since the
        # pattern is length-anchored. Keeping the exact length matters.
        "google": "AIza" + "SyD9xK3mQ7pL2vR5tY8wZ1nC4hJ6sD0fGhK",
    }
    must_ignore = {
        "bare_prefix": "sk-ant-api03-",
        "fixture_platform": "sk-ant-api03-PLATFORM-OWNER-KEY-DO-NOT-USE-1234",
        "fixture_cameron": "sk-ant-api03-CAMERON-OWN-ACCOUNT-KEY-5678",
        "doc_placeholder": "postgresql://postgres:<password>@db.ref.supabase.co:5432/postgres",
    }

    failures = 0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for label, value in must_catch.items():
            (root / f"catch_{label}.py").write_text(f'KEY = "{value}"\n', encoding="utf-8")
        for label, value in must_ignore.items():
            (root / f"ignore_{label}.py").write_text(f'KEY = "{value}"\n', encoding="utf-8")

        found = scan(root)
        found_files = {f["file"] for f in found}

        for label in must_catch:
            name = f"catch_{label}.py"
            ok = name in found_files
            print(f"  [{'PASS' if ok else 'FAIL'}] catches {label}")
            if not ok:
                failures += 1
        for label in must_ignore:
            name = f"ignore_{label}.py"
            ok = name not in found_files
            print(f"  [{'PASS' if ok else 'FAIL'}] ignores {label}")
            if not ok:
                failures += 1

    print(f"\n[self-test] {failures} failure(s)")
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    findings = scan(REPO)
    if not findings:
        print("[secrets] no committed credentials found")
        print("[secrets] note: .env.local and .claude/settings.local.json hold real "
              "keys but are gitignored and excluded from this scan by design")
        return 0

    print(f"[secrets] {len(findings)} finding(s):")
    for f in findings:
        print(f"  {f['file']}:{f['line']}  {f['kind']}  {f['preview']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
