"""
Qualification scoring tests. No database, no network, no LLM.

    python agents/tests/test_qualification.py
"""

from __future__ import annotations

import sys
import unittest
import importlib.util as ilu
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = ilu.spec_from_file_location(
    "scoring", REPO / "agents" / "library" / "facility-qualification-agent" / "scoring.py")
scoring = ilu.module_from_spec(spec)
sys.modules["scoring"] = scoring
spec.loader.exec_module(scoring)


def facility(attrs, conf=None, fid="f-1"):
    return {
        "id": fid,
        "attributes": attrs,
        # `conf is not None` not `conf or ...`: an empty dict is falsy, and
        # falling back to all-verified would silently defeat the very test that
        # checks an unstated confidence is treated as unknown.
        "attributes_confidence": conf if conf is not None else {k: "verified" for k in attrs},
    }


class TestDeterminism(unittest.TestCase):
    def test_same_input_same_score(self):
        f = facility({"distance_miles": 6.0, "indoor": True, "heated": True,
                      "commercial_instruction_allowed": True})
        scores = {scoring.qualify(f).score for _ in range(25)}
        self.assertEqual(len(scores), 1, "scoring must be deterministic")

    def test_model_version_is_reported(self):
        r = scoring.qualify(facility({"distance_miles": 5.0}))
        self.assertEqual(r.model_version, scoring.MODEL_VERSION)


class TestUnknownHandling(unittest.TestCase):
    def test_unknown_attributes_are_listed_not_guessed(self):
        r = scoring.qualify(facility({"distance_miles": 5.0}))
        self.assertIn("heated", r.unknown_fields)
        self.assertIn("pool_length_m", r.unknown_fields)
        self.assertNotIn("distance_miles", r.unknown_fields)

    def test_unknown_does_not_drag_score_down(self):
        """A facility known to be good on one axis and unknown elsewhere must not
        be penalised into looking bad - that would hide real prospects."""
        sparse = scoring.qualify(facility({"commercial_instruction_allowed": True}))
        self.assertGreater(sparse.score, 90.0)
        self.assertLess(sparse.completeness, 0.3)

    def test_low_completeness_yields_needs_info_not_qualified(self):
        r = scoring.qualify(facility({"commercial_instruction_allowed": True}))
        self.assertEqual(r.status, "needs_info")

    def test_completeness_rises_with_more_known_attributes(self):
        sparse = scoring.qualify(facility({"distance_miles": 5.0}))
        rich = scoring.qualify(facility({
            "distance_miles": 5.0, "indoor": True, "heated": True,
            "commercial_instruction_allowed": True, "recurring_availability": True,
            "pool_length_m": 25.0, "depth_ft": 3.5, "hourly_rate_usd": 60.0,
            "lesson_capacity": 10}))
        self.assertGreater(rich.completeness, sparse.completeness)

    def test_value_without_stated_confidence_is_treated_as_unknown(self):
        r = scoring.qualify(facility({"heated": True}, conf={}))
        self.assertIn("heated", r.unknown_fields)

    def test_open_questions_generated_for_unknowns(self):
        r = scoring.qualify(facility({"distance_miles": 5.0}))
        asked = {q["attribute"] for q in r.open_questions}
        self.assertIn("commercial_instruction_allowed", asked)
        for q in r.open_questions:
            # Must actually ask something. Some questions carry a trailing
            # clarifying sentence, so check for a question mark anywhere rather
            # than requiring it to be the last character.
            self.assertIn("?", q["question"])


class TestConfidenceWeighting(unittest.TestCase):
    def test_inferred_scores_lower_than_verified(self):
        attrs = {"distance_miles": 5.0, "indoor": True, "heated": True}
        v = scoring.qualify(facility(attrs, {k: "verified" for k in attrs}))
        i = scoring.qualify(facility(attrs, {k: "inferred" for k in attrs}))
        self.assertGreater(v.score, i.score)

    def test_verified_and_inferred_are_reported_separately(self):
        r = scoring.qualify(facility(
            {"distance_miles": 5.0, "heated": True},
            {"distance_miles": "verified", "heated": "inferred"}))
        self.assertIn("distance_miles", r.verified_fields)
        self.assertIn("heated", r.inferred_fields)


class TestDisqualifiers(unittest.TestCase):
    def test_too_far_is_disqualified(self):
        r = scoring.qualify(facility({"distance_miles": 40.0, "indoor": True,
                                      "heated": True, "pool_length_m": 25.0}))
        self.assertEqual(r.status, "disqualified")
        self.assertTrue(any("distance" in d for d in r.disqualifiers))

    def test_commercial_instruction_forbidden_is_absolute(self):
        """Perfect on every other axis; still disqualified. The business cannot
        operate where lessons are not permitted."""
        r = scoring.qualify(facility({
            "distance_miles": 1.0, "indoor": True, "heated": True,
            "pool_length_m": 50.0, "depth_ft": 4.0, "hourly_rate_usd": 10.0,
            "lesson_capacity": 20, "recurring_availability": True,
            "commercial_instruction_allowed": False}))
        self.assertEqual(r.status, "disqualified")
        self.assertIn("facility does not permit outside commercial instruction",
                      r.disqualifiers)

    def test_rate_above_ceiling_disqualifies(self):
        r = scoring.qualify(facility({"hourly_rate_usd": 400.0, "distance_miles": 2.0}))
        self.assertTrue(any("hourly rate" in d for d in r.disqualifiers))

    def test_pool_too_short_disqualifies(self):
        r = scoring.qualify(facility({"pool_length_m": 8.0, "distance_miles": 2.0}))
        self.assertTrue(any("pool length" in d for d in r.disqualifiers))


class TestQualifiedPath(unittest.TestCase):
    def test_strong_complete_facility_qualifies(self):
        r = scoring.qualify(facility({
            "distance_miles": 4.0, "indoor": True, "heated": True,
            "commercial_instruction_allowed": True, "recurring_availability": True,
            "pool_length_m": 25.0, "depth_ft": 3.5, "hourly_rate_usd": 45.0,
            "lesson_capacity": 12, "insurance_required": True,
            "revenue_share_possible": False}))
        self.assertEqual(r.status, "qualified")
        self.assertGreater(r.score, 60.0)
        self.assertEqual(r.disqualifiers, [])

    def test_breakdown_explains_every_scored_criterion(self):
        r = scoring.qualify(facility({"distance_miles": 4.0, "indoor": True}))
        scored = {k for k, v in r.score_breakdown.items() if v["status"] == "scored"}
        self.assertIn("distance", scored)
        self.assertIn("indoor", scored)
        for key, entry in r.score_breakdown.items():
            self.assertIn("note", entry, f"{key} must explain itself")

    def test_closer_facility_outranks_further_one(self):
        base = {"indoor": True, "heated": True, "commercial_instruction_allowed": True}
        near = scoring.qualify(facility({**base, "distance_miles": 2.0}))
        far = scoring.qualify(facility({**base, "distance_miles": 14.0}))
        self.assertGreater(near.score, far.score)

    def test_config_overrides_change_the_verdict(self):
        """Weights are configuration, so a second business reuses this module."""
        f = facility({"distance_miles": 20.0, "commercial_instruction_allowed": True})
        default = scoring.qualify(f)
        relaxed = scoring.qualify(f, {"max_distance_miles": 30.0})
        self.assertEqual(default.status, "disqualified")
        self.assertNotEqual(relaxed.status, "disqualified")


class TestPayload(unittest.TestCase):
    def test_payload_shape_matches_the_rpc_contract(self):
        r = scoring.qualify(facility({"distance_miles": 4.0}))
        p = r.to_payload(run_id="00000000-0000-0000-0000-000000000001")
        for key in ("facility_id", "run_id", "model_version", "score", "status",
                    "completeness", "score_breakdown", "verified_fields",
                    "inferred_fields", "unknown_fields", "open_questions",
                    "disqualifiers"):
            self.assertIn(key, p)
        self.assertLessEqual(p["score"], 100.0)
        self.assertGreaterEqual(p["score"], 0.0)
        self.assertLessEqual(p["completeness"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
