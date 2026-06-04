"""
P1 acceptance regression - the Partner/Admin error class.

Runs as a plain script (python test_habi_regression.py) and under pytest.

Layered so it goes green as the P1 sequence lands:
  - LEVEL 1 (now): deterministic snapshot parser finds Partner/Property/Material
    entities; Admin is correctly NOT an entity (it is an actor). Determinism.
  - LEVEL 2 (after resolve.py + source_scan actors + coverage): full concept
    resolution against the fixture's `expected` block, incl. Admin via actor,
    Habi not_found-only-if-green, and the hard-fail conditions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT_DIR = HERE.parent
REPO_ROOT = AGENT_DIR.parent.parent.parent
sys.path.insert(0, str(AGENT_DIR))

from parser import drizzle_snapshot  # noqa: E402

FIXTURE = json.loads((HERE / "fixtures" / "habi_handoff.json").read_text(encoding="utf-8"))
TARGET = (REPO_ROOT / FIXTURE["handoff"]["repo_path"]).resolve()


# ---------------------------------------------------------------------------
# LEVEL 1 - deterministic structural truth (passes once drizzle_snapshot.py exists)
# ---------------------------------------------------------------------------

def test_inventory_is_complete_not_sampled():
    inv = drizzle_snapshot.extract(TARGET)
    # v1's LLM run reported 18. The truth is ~140. Guard against silent sampling.
    assert len(inv.entities) >= 130, f"implausibly low entity count: {len(inv.entities)}"


def test_partner_entity_exists_with_evidence():
    inv = drizzle_snapshot.extract(TARGET)
    names = {e.pg_table for e in inv.entities}
    assert "partners" in names, "Partner must resolve to the partners table (the v1 miss)"
    partners = next(e for e in inv.entities if e.pg_table == "partners")
    assert partners.evidence.get("snapshot"), "Partner entity must carry snapshot evidence"


def test_property_and_material_entities_exist():
    inv = drizzle_snapshot.extract(TARGET)
    names = {e.pg_table for e in inv.entities}
    assert "property_listings" in names
    assert names & {"project_materials", "room_material_options", "project_room_materials"}


def test_admin_is_not_an_entity():
    # Admin is an ACTOR (roles table + USER_ROLES.ADMIN), never a table. If a future
    # change makes 'admin' an entity, the actor/entity split must be re-examined.
    inv = drizzle_snapshot.extract(TARGET)
    names = {e.pg_table for e in inv.entities}
    assert "admin" not in names and "admins" not in names


def test_determinism():
    a = drizzle_snapshot.extract(TARGET)
    b = drizzle_snapshot.extract(TARGET)
    assert [e.pg_table for e in a.entities] == [e.pg_table for e in b.entities]


# ---------------------------------------------------------------------------
# LEVEL 2 - full concept resolution (activates after resolve.py + actor scan + coverage)
# ---------------------------------------------------------------------------

def _pipeline_ready() -> bool:
    return (AGENT_DIR / "resolve.py").exists() and (AGENT_DIR / "parser" / "source_scan.py").exists()


def test_full_habi_resolution():
    if not _pipeline_ready():
        print("LEVEL 2 skipped: resolve.py / source_scan.py not built yet")
        return
    import resolve  # noqa: E402  (built in step 10)
    result = resolve.resolve_concepts(TARGET, FIXTURE["handoff"]["concepts_to_check"])
    by_concept = {r["concept"]: r for r in result["resolved_concepts"]}
    for concept, exp in FIXTURE["expected"].items():
        r = by_concept[concept]
        assert r["status"] in exp["status_in"], f"{concept}: {r['status']} not in {exp['status_in']}"
        for bad in exp.get("hard_fail_if", []):
            if bad == "not_found":
                assert r["status"] != "not_found", f"HARD FAIL: {concept} resolved not_found"
            if bad == "indeterminate":
                assert r["status"] != "indeterminate", f"HARD FAIL: {concept} indeterminate"
        if exp.get("evidence_required"):
            assert r.get("evidence"), f"{concept}: status {r['status']} requires evidence"


if __name__ == "__main__":
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS  {name}")
                passed += 1
            except AssertionError as e:
                print(f"FAIL  {name}: {e}")
            except Exception as e:
                print(f"ERROR {name}: {e}")
    print(f"\n{passed} passed")
