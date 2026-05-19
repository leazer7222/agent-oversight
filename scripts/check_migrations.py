#!/usr/bin/env python3
"""
Migration Schema Enforcement Linter
Adaptive Cost Risk Engine — Phase 0 CI Enforcement

Checks Supabase migration files for schema evolution violations defined in RFC-009.
Run in CI before any migration is merged.

Usage:
  python scripts/check_migrations.py [--file path/to/migration.sql] [--dir supabase/migrations]
  python scripts/check_migrations.py  # checks all migrations in supabase/migrations/

Exit codes:
  0 — all checks pass
  1 — hard failures detected (block merge)
  2 — warnings detected (flag for review; do not block)

RFC reference: RFC-009 §11
"""

import re
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Class I (immutable artifact) table names
# When these tables appear in a migration, ON DELETE CASCADE is prohibited.
# ---------------------------------------------------------------------------
CLASS_I_TABLES = {
    "estimate_artifacts",
    "evaluation_artifacts",
    "recommendation_artifacts",
    "pricing_table_versions",
    "calibration_snapshots",
    "calibration_buckets",
    "calibration_observations",
    "task_taxonomy_versions",
    "task_types",
    "model_performance_profiles",
    "profile_snapshots",
    "quality_signals",
    "correction_records",
    "budget_reservations",
    "settlement_records",
    "budget_corrections",
    "raw_events",
    "schema_registry",
}

@dataclass
class CheckResult:
    hard_failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_failure(self, msg: str):
        self.hard_failures.append(msg)

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    @property
    def has_failures(self) -> bool:
        return len(self.hard_failures) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


def check_migration(path: Path) -> CheckResult:
    result = CheckResult()
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        # Skip comments
        if stripped.startswith("--"):
            continue
        loc = f"{path.name}:{i}"

        # ------------------------------------------------------------------
        # HARD FAILURE: TIMESTAMP without TZ
        # Allow TIMESTAMPTZ, reject plain TIMESTAMP
        # ------------------------------------------------------------------
        if re.search(r"\bTIMESTAMP\b(?!\s*WITH\s+TIME\s+ZONE)(?!Z)", stripped, re.IGNORECASE):
            # Exclude TIMESTAMPTZ (already handled by the regex above as it
            # matches the TZ suffix) and comments
            if "TIMESTAMPTZ" not in stripped.upper():
                result.add_failure(
                    f"[HARD] {loc}: TIMESTAMP without timezone. Use TIMESTAMPTZ. (RFC-009 §8.2)"
                )

        # ------------------------------------------------------------------
        # HARD FAILURE: SERIAL or BIGSERIAL primary key
        # ------------------------------------------------------------------
        if re.search(r"\b(SERIAL|BIGSERIAL)\b", stripped, re.IGNORECASE):
            result.add_failure(
                f"[HARD] {loc}: SERIAL/BIGSERIAL primary key. Use UUID DEFAULT gen_random_uuid(). (RFC-009 §8.1)"
            )

        # ------------------------------------------------------------------
        # HARD FAILURE: uuid_generate_v1()
        # ------------------------------------------------------------------
        if re.search(r"uuid_generate_v1\(\)", stripped, re.IGNORECASE):
            result.add_failure(
                f"[HARD] {loc}: uuid_generate_v1() leaks MAC address. Use gen_random_uuid(). (RFC-009 §8.1)"
            )

        # ------------------------------------------------------------------
        # HARD FAILURE: ON DELETE CASCADE on Class I tables
        # ------------------------------------------------------------------
        if re.search(r"ON\s+DELETE\s+CASCADE", stripped, re.IGNORECASE):
            # Check if any Class I table name appears nearby (within 10 lines)
            context_start = max(0, i - 10)
            context = "\n".join(lines[context_start:i]).lower()
            for table in CLASS_I_TABLES:
                if table in context:
                    result.add_failure(
                        f"[HARD] {loc}: ON DELETE CASCADE near Class I table '{table}'. "
                        f"Use ON DELETE RESTRICT. (RFC-009 §9)"
                    )
                    break

        # ------------------------------------------------------------------
        # HARD FAILURE: PostgreSQL ENUM type creation
        # ------------------------------------------------------------------
        if re.search(r"\bCREATE\s+TYPE\b.+\bAS\s+ENUM\b", stripped, re.IGNORECASE):
            result.add_failure(
                f"[HARD] {loc}: PostgreSQL ENUM type. Use CHECK constraints instead. (RFC-009 §7.3)"
            )

        # ------------------------------------------------------------------
        # WARNING: VARCHAR with explicit length limit
        # ------------------------------------------------------------------
        if re.search(r"\bVARCHAR\s*\(\d+\)", stripped, re.IGNORECASE):
            result.add_warning(
                f"[WARN] {loc}: VARCHAR with length limit. Use TEXT. (RFC-009 §8.3)"
            )

        # ------------------------------------------------------------------
        # WARNING: FLOAT on financial column
        # ------------------------------------------------------------------
        if re.search(r"\b(FLOAT|REAL|DOUBLE PRECISION)\b", stripped, re.IGNORECASE):
            if any(word in stripped.lower() for word in ["usd", "cost", "amount", "price", "budget", "reserved", "consumed"]):
                result.add_warning(
                    f"[WARN] {loc}: FLOAT type on financial column. Use NUMERIC. (RFC-009 §8.2)"
                )

        # ------------------------------------------------------------------
        # WARNING: JSONB column with a generic, undescriptive name
        # Only flag truly generic names — not all JSONB columns.
        # Descriptive names (corrected_fields, trigger_config, etc.) are fine.
        # ------------------------------------------------------------------
        jsonb_col = re.search(r"(\w+)\s+JSONB", stripped, re.IGNORECASE)
        if jsonb_col:
            col_name = jsonb_col.group(1).lower()
            generic_names = {"data", "json", "jsonb", "extra", "info", "misc", "stuff"}
            if col_name in generic_names:
                result.add_warning(
                    f"[WARN] {loc}: JSONB column '{col_name}' is too generic. "
                    f"Use a descriptive name (_snapshot, _definition, _data, _payload). (RFC-009 §8.4)"
                )

    # ------------------------------------------------------------------
    # Table-level checks: new tables must have created_at
    # ------------------------------------------------------------------
    table_matches = re.finditer(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\S+)\s*\(",
        content, re.IGNORECASE
    )
    for match in table_matches:
        table_name = match.group(1)
        # Extract table body (rough heuristic: content between opening paren and matching close)
        start = match.end()
        depth = 1
        pos = start
        while pos < len(content) and depth > 0:
            if content[pos] == "(":
                depth += 1
            elif content[pos] == ")":
                depth -= 1
            pos += 1
        table_body = content[start:pos].lower()

        if "created_at" not in table_body:
            result.add_failure(
                f"[HARD] {path.name}: Table '{table_name}' missing "
                f"created_at TIMESTAMPTZ NOT NULL DEFAULT now(). (RFC-009 §8.2)"
            )

    return result


def main():
    parser = argparse.ArgumentParser(description="Migration schema enforcement linter (RFC-009)")
    parser.add_argument("--file", type=Path, help="Check a single migration file")
    parser.add_argument("--dir", type=Path, default=Path("supabase/migrations"),
                        help="Directory of migration files (default: supabase/migrations)")
    parser.add_argument("--warn-only", action="store_true",
                        help="Treat hard failures as warnings (for reporting only)")
    parser.add_argument("--from-migration", type=str, default=None,
                        help="Only check migrations at or after this prefix (e.g. '012'). "
                             "Use to skip pre-RFC historical migrations.")
    args = parser.parse_args()

    if args.file:
        files = [args.file]
    else:
        files = sorted(args.dir.glob("*.sql"))
        if args.from_migration:
            files = [f for f in files if f.name >= args.from_migration]

    if not files:
        print("No migration files found.")
        sys.exit(0)

    all_results: dict[Path, CheckResult] = {}
    for f in files:
        all_results[f] = check_migration(f)

    total_failures = 0
    total_warnings = 0

    for path, result in all_results.items():
        if result.has_failures or result.has_warnings:
            print(f"\n=== {path.name} ===")
        for msg in result.hard_failures:
            print(f"  {msg}")
            total_failures += 1
        for msg in result.warnings:
            print(f"  {msg}")
            total_warnings += 1

    print(f"\n{'='*60}")
    print(f"Files checked:  {len(files)}")
    print(f"Hard failures:  {total_failures}")
    print(f"Warnings:       {total_warnings}")

    if total_failures == 0 and total_warnings == 0:
        print("\nAll checks passed.")

    if total_failures > 0 and not args.warn_only:
        print("\nHard failures detected. Merge blocked.")
        print("  Waivers require an RFC amendment -- not an inline suppression.")
        print("  See RFC-009 §11.")
        sys.exit(1)
    elif total_warnings > 0:
        print("\nWarnings detected. Flag for reviewer attention.")
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
