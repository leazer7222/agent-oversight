"""
Discovery agent tests. No network; replays recorded Places-shaped fixtures.

The fixtures use deliberately synthetic names prefixed "FIXTURE" so that a row
originating here could never be mistaken for a real business someone might email.

    python agents/tests/test_discovery.py
"""

from __future__ import annotations

import json
import sys
import unittest
import importlib.util as ilu
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
AGENT_DIR = REPO / "agents" / "library" / "facility-discovery-agent"
spec = ilu.spec_from_file_location("discovery", AGENT_DIR / "discovery.py")
D = ilu.module_from_spec(spec)
sys.modules["discovery"] = D
spec.loader.exec_module(D)

FIXTURES = json.loads((AGENT_DIR / "fixtures" / "katy_tx_places.json").read_text(encoding="utf-8"))


class TestNoFabrication(unittest.TestCase):
    """The central safety property: the agent reports nothing it was not given."""

    def test_empty_api_response_yields_zero_facilities(self):
        facilities, stats = D.discover(
            D.SearchConfig(queries=("no results query",)),
            transport=D.fixture_transport(FIXTURES))
        self.assertEqual(facilities, [])
        self.assertEqual(stats.accepted, 0)

    def test_unknown_query_invents_nothing(self):
        facilities, _ = D.discover(
            D.SearchConfig(queries=("a query with no recorded response",)),
            transport=D.fixture_transport(FIXTURES))
        self.assertEqual(facilities, [])

    def test_missing_api_key_refuses_rather_than_improvising(self):
        import os
        saved = os.environ.pop("GOOGLE_PLACES_API_KEY", None)
        try:
            with self.assertRaises(D.PlacesConfigError):
                D.discover(D.SearchConfig(queries=("indoor swimming pool",)))
        finally:
            if saved is not None:
                os.environ["GOOGLE_PLACES_API_KEY"] = saved

    def test_result_without_stable_id_is_rejected_not_patched(self):
        facilities, stats = D.discover(
            D.SearchConfig(queries=("indoor swimming pool",)),
            transport=D.fixture_transport(FIXTURES))
        self.assertGreaterEqual(stats.rejected_no_id, 1)
        for f in facilities:
            self.assertTrue(f["source_ref"])


class TestProvenance(unittest.TestCase):
    def test_every_facility_carries_a_verifiable_source(self):
        facilities, _ = D.discover(D.SearchConfig(), transport=D.fixture_transport(FIXTURES))
        self.assertGreater(len(facilities), 0)
        for f in facilities:
            self.assertEqual(f["source"], "google_places")
            self.assertTrue(f["source_ref"])
            self.assertIn("place_id:", f["source_url"])

    def test_pool_specifics_are_declared_unknown_not_assumed(self):
        """Places does not know whether a pool is heated or permits lessons.
        Claiming otherwise is what would mislead Cameron."""
        facilities, _ = D.discover(D.SearchConfig(), transport=D.fixture_transport(FIXTURES))
        f = facilities[0]
        for attr in ("heated", "indoor", "pool_length_m", "depth_ft",
                     "commercial_instruction_allowed", "hourly_rate_usd"):
            self.assertIn(attr, f["unknown_fields"])
            self.assertNotIn(attr, f["attributes"])

    def test_distance_is_computed_and_marked_verified(self):
        facilities, _ = D.discover(D.SearchConfig(), transport=D.fixture_transport(FIXTURES))
        f = facilities[0]
        self.assertIsNotNone(f["attributes"]["distance_miles"])
        self.assertEqual(f["attributes_confidence"]["distance_miles"], "verified")


class TestFiltering(unittest.TestCase):
    def test_radius_is_enforced_because_places_only_biases(self):
        facilities, stats = D.discover(
            D.SearchConfig(radius_miles=15.0), transport=D.fixture_transport(FIXTURES))
        self.assertGreaterEqual(stats.rejected_out_of_radius, 1)
        for f in facilities:
            self.assertLessEqual(f["distance_miles"], 15.0)

    def test_permanently_closed_is_excluded(self):
        facilities, stats = D.discover(
            D.SearchConfig(), transport=D.fixture_transport(FIXTURES))
        self.assertGreaterEqual(stats.rejected_closed, 1)
        self.assertNotIn("FIXTURE Facility 900", [f["name"][:20] for f in facilities])

    def test_configurable_radius(self):
        wide, _ = D.discover(D.SearchConfig(radius_miles=60.0),
                             transport=D.fixture_transport(FIXTURES))
        narrow, _ = D.discover(D.SearchConfig(radius_miles=5.0),
                               transport=D.fixture_transport(FIXTURES))
        self.assertGreater(len(wide), len(narrow))

    def test_results_sorted_nearest_first(self):
        facilities, _ = D.discover(D.SearchConfig(), transport=D.fixture_transport(FIXTURES))
        dists = [f["distance_miles"] for f in facilities]
        self.assertEqual(dists, sorted(dists))


class TestDeduplication(unittest.TestCase):
    def test_duplicate_place_id_collapses(self):
        facilities, stats = D.discover(
            D.SearchConfig(queries=("indoor swimming pool",)),
            transport=D.fixture_transport(FIXTURES))
        ids = [f["source_ref"] for f in facilities]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(stats.deduped, 1)

    def test_repeat_run_produces_identical_set(self):
        """Idempotency at the agent layer, mirroring the DB unique indexes."""
        a, _ = D.discover(D.SearchConfig(), transport=D.fixture_transport(FIXTURES))
        b, _ = D.discover(D.SearchConfig(), transport=D.fixture_transport(FIXTURES))
        self.assertEqual([f["source_ref"] for f in a], [f["source_ref"] for f in b])

    def test_name_and_address_collision_is_caught(self):
        dup = {
            "q": {"places": [
                {"id": "ID_A", "displayName": {"text": "Same Pool"},
                 "formattedAddress": "1 A St, Katy, TX 77494, USA",
                 "location": {"latitude": 29.79, "longitude": -95.82},
                 "primaryType": "swimming_pool", "businessStatus": "OPERATIONAL"},
                {"id": "ID_B", "displayName": {"text": "same pool"},
                 "formattedAddress": "1 a st, katy, TX 77494, USA",
                 "location": {"latitude": 29.79, "longitude": -95.82},
                 "primaryType": "swimming_pool", "businessStatus": "OPERATIONAL"},
            ]}
        }
        facilities, stats = D.discover(D.SearchConfig(queries=("q",)),
                                       transport=D.fixture_transport(dup))
        self.assertEqual(len(facilities), 1)
        self.assertEqual(stats.deduped, 1)


class TestCostControl(unittest.TestCase):
    def test_request_ceiling_is_structural(self):
        """A loop bug must not be able to run up a Places bill."""
        calls = {"n": 0}
        base = D.fixture_transport(FIXTURES)

        def counting(body):
            calls["n"] += 1
            return base(body)

        cfg = D.SearchConfig(queries=tuple(f"q{i}" for i in range(500)), max_requests=3)
        _, stats = D.discover(cfg, transport=counting)
        self.assertEqual(calls["n"], 3)
        self.assertEqual(stats.requests_made, 3)

    def test_stats_report_the_denominator(self):
        _, stats = D.discover(D.SearchConfig(), transport=D.fixture_transport(FIXTURES))
        d = stats.as_dict()
        self.assertEqual(
            d["accepted"] + d["deduped"] + d["rejected_no_id"]
            + d["rejected_out_of_radius"] + d["rejected_closed"],
            d["raw_results"])


class TestVolume(unittest.TestCase):
    def test_yields_at_least_20_distinct_facilities_from_fixtures(self):
        """Acceptance criterion, exercised against fixtures. The equivalent
        assertion against LIVE Places data is pending an API key."""
        facilities, _ = D.discover(D.SearchConfig(radius_miles=20.0),
                                   transport=D.fixture_transport(FIXTURES))
        self.assertGreaterEqual(len(facilities), 20, f"got {len(facilities)}")
        self.assertEqual(len({f["source_ref"] for f in facilities}), len(facilities))

    def test_facility_payload_matches_the_upsert_contract(self):
        facilities, _ = D.discover(D.SearchConfig(), transport=D.fixture_transport(FIXTURES))
        required = {"name", "facility_type", "source", "source_ref", "source_url",
                    "attributes", "attributes_confidence", "unknown_fields"}
        for f in facilities:
            self.assertTrue(required.issubset(f.keys()))
            self.assertNotIn("_business_status", f)  # internal field stripped


class TestGeo(unittest.TestCase):
    def test_haversine_against_known_distance(self):
        # Katy TX to downtown Houston is roughly 26 miles.
        d = D.haversine_miles(29.7858, -95.8245, 29.7604, -95.3698)
        self.assertGreater(d, 24.0)
        self.assertLess(d, 29.0)

    def test_zero_distance(self):
        self.assertAlmostEqual(D.haversine_miles(29.78, -95.82, 29.78, -95.82), 0.0, places=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
