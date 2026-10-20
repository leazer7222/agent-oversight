"""
Prototype pipeline tests, offline: no database, no network, no LLM.

What these prove: the evidence rule rejects anything not on the page; triage
is deterministic and gates win; the draft composer refuses unsupported claims;
classification escalates by rule even when the model proposes otherwise; the
injection scenario produces an escalation and never an action.

    python -m pytest agents/tests/test_prototype_e2e.py -q
"""

from __future__ import annotations

import sys
import json
import unittest
import importlib.util as ilu
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "agents" / "library"
sys.path.insert(0, str(LIB / "outreach-agent"))
sys.path.insert(0, str(REPO))


def _load(path: Path, name: str):
    spec = ilu.spec_from_file_location(name, path)
    mod = ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SCORE = _load(LIB / "facility-qualification-agent" / "scoring.py", "scoring")
ENRICH = _load(LIB / "facility-researcher" / "enrich.py", "enrich")
TRIAGE = _load(LIB / "facility-researcher" / "triage.py", "triage")
DRAFT = _load(LIB / "partnership-coordinator" / "draft.py", "draft")
CLASSIFY = _load(LIB / "partnership-coordinator" / "classify.py", "classify")
REPLIES = json.loads((LIB / "partnership-coordinator" / "fixtures" / "replies.json").read_text(encoding="utf-8"))

PAGE_HTML = (
    "<html><head><title>FIXTURE: Pool</title></head><body>"
    "<!-- FIXTURE PAGE -->"
    "<p>Our indoor heated pool is open year-round. The pool is 20 metres long.</p>"
    "<p>Contact Dana Whitfield, Director of Operations, at dana.whitfield@fixture.example.com.</p>"
    "</body></html>")
PAGE = {"url": "https://fixture.example.com", "html": PAGE_HTML, "text": ENRICH.html_to_text(PAGE_HTML)}


def stub_llm(response: dict):
    def _call(system, user, tool, max_tokens=8000):
        return response, {"model": "stub", "tokens_in": 1, "tokens_out": 1, "cost_usd": 0.0}
    return _call


class TestEvidenceRule(unittest.TestCase):
    def test_found_snippet_is_accepted(self):
        proposal = {"attributes": [{"attribute": "indoor", "value": "true", "confidence": "verified",
                                    "evidence_snippet": "Our indoor heated pool is open year-round."}],
                    "contacts": [], "notes": ""}
        r = ENRICH.validate(proposal, PAGE["text"])
        self.assertEqual(r["attributes"], {"indoor": True})
        self.assertEqual(r["evidence_rejected"], 0)

    def test_mutated_snippet_is_rejected(self):
        proposal = {"attributes": [{"attribute": "heated", "value": "true", "confidence": "verified",
                                    "evidence_snippet": "Our indoor UNHEATED pool is open year-round."}],
                    "contacts": [], "notes": ""}
        r = ENRICH.validate(proposal, PAGE["text"])
        self.assertEqual(r["attributes"], {})
        self.assertEqual(r["evidence_rejected"], 1)

    def test_guessed_email_is_rejected_even_with_a_real_snippet(self):
        proposal = {"attributes": [], "notes": "",
                    "contacts": [{"full_name": "Dana Whitfield", "role_title": "Director",
                                  "email": "d.whitfield@fixture.example.com", "phone": None,
                                  "evidence_snippet": "Contact Dana Whitfield, Director of Operations"}]}
        r = ENRICH.validate(proposal, PAGE["text"])
        self.assertEqual(r["contacts"], [])
        self.assertEqual(r["evidence_rejected"], 1)

    def test_on_page_email_is_accepted(self):
        proposal = {"attributes": [], "notes": "",
                    "contacts": [{"full_name": "Dana Whitfield", "role_title": "Director of Operations",
                                  "email": "dana.whitfield@fixture.example.com", "phone": None,
                                  "evidence_snippet": "Contact Dana Whitfield, Director of Operations"}]}
        r = ENRICH.validate(proposal, PAGE["text"])
        self.assertEqual(len(r["contacts"]), 1)
        self.assertTrue(r["contacts"][0]["is_primary"])

    def test_extract_runs_through_the_injected_llm(self):
        llm = stub_llm({"attributes": [{"attribute": "pool_length_m", "value": "20", "confidence": "verified",
                                         "evidence_snippet": "The pool is 20 metres long."}],
                        "contacts": [], "notes": "says nothing about rates"})
        r, usage = ENRICH.extract({"name": "Pool", "facility_type": "hotel"}, PAGE, llm)
        self.assertEqual(r["attributes"], {"pool_length_m": 20.0})
        self.assertEqual(usage["model"], "stub")


class TestTriage(unittest.TestCase):
    def _fac(self, attrs, contacts=None, ftype="hotel", phone=None):
        conf = {k: "verified" for k in attrs}
        result = SCORE.qualify({"id": "f", "attributes": attrs, "attributes_confidence": conf})
        fac = {"facility_type": ftype, "attributes": attrs, "contacts": contacts or [], "phone": phone}
        return TRIAGE.triage(result, fac)

    def test_prohibited_instruction_is_a_gate(self):
        t = self._fac({"commercial_instruction_allowed": False, "indoor": True, "heated": True},
                      contacts=[{"email": "a@b.example"}])
        self.assertEqual(t["triage_state"], "disqualified")
        self.assertEqual(t["breakdown_extra"]["gates"]["commercial_instruction"], "fail")

    def test_email_contact_means_contact_first(self):
        t = self._fac({"indoor": True}, contacts=[{"email": "a@b.example"}])
        self.assertEqual(t["triage_state"], "contact_first")
        self.assertEqual(t["channel_recommended"], "email")

    def test_no_route_means_research_further(self):
        t = self._fac({"indoor": True}, contacts=[], ftype="school")
        self.assertEqual(t["triage_state"], "research_further")
        self.assertEqual(t["channel_recommended"], "none")

    def test_application_process_for_municipal(self):
        t = self._fac({"facility_use_application_url": "https://city.example/apply"}, ftype="recreation_center")
        self.assertEqual(t["channel_recommended"], "facility_use_application")
        self.assertEqual(t["triage_state"], "contact_first")

    def test_competitor_is_not_currently_suitable(self):
        t = self._fac({"indoor": True}, contacts=[{"email": "a@b.example"}], ftype="swim_school")
        self.assertEqual(t["triage_state"], "not_currently_suitable")
        self.assertEqual(t["status_legacy"], "disqualified")

    def test_safety_is_never_inferred(self):
        t = self._fac({"indoor": True, "heated": True, "depth_ft": 3.5}, contacts=[{"email": "a@b.example"}])
        self.assertEqual(t["breakdown_extra"]["gates"]["safety_site_visit"], "unknown")


class TestDraft(unittest.TestCase):
    FAC = {"name": "FIXTURE Hotel", "facility_type": "hotel", "distance_miles": 4.2,
           "attributes": {"indoor": True, "heated": True},
           "contacts": [{"contact_id": "c1", "full_name": "Dana Whitfield", "email": "dana@fixture.example.com",
                         "is_primary": True}],
           "latest_qualification": {"open_questions": [
               {"attribute": "commercial_instruction_allowed", "question": "x"},
               {"attribute": "hourly_rate_usd", "question": "y"}]}}

    def test_clean_sentence_yields_a_draft_with_the_facilitys_questions(self):
        d, _ = DRAFT.compose(self.FAC, DRAFT.PROTOTYPE_BUSINESS_FACTS,
                             stub_llm({"sentence": "Your indoor, heated pool looks like a wonderful place for young beginners."}))
        self.assertIsNotNone(d)
        self.assertIn("outside instructors", d["body"])
        self.assertIn("charge per hour", d["body"])
        self.assertIn("[PROTOTYPE DRAFT - not sent]", d["body"])
        self.assertEqual(d["body_sha256"], DRAFT.body_sha256(d["body"]))

    def test_sentence_claiming_experience_is_refused(self):
        with self.assertRaises(DRAFT.FabricationError):
            DRAFT.compose(self.FAC, DRAFT.PROTOTYPE_BUSINESS_FACTS,
                          stub_llm({"sentence": "With 10 years of experience we are fully insured and certified instructors."}))

    def test_no_email_contact_means_no_draft(self):
        fac = {**self.FAC, "contacts": [{"phone": "(281) 555-0100"}]}
        d, _ = DRAFT.compose(fac, DRAFT.PROTOTYPE_BUSINESS_FACTS, stub_llm({"sentence": "ok"}))
        self.assertIsNone(d)


class TestClassification(unittest.TestCase):
    THREAD = {"thread_id": "t", "facility_name": "FIXTURE Pool", "subject": "Recurring swim lesson space"}

    def _scenario(self, sid):
        return next(s for s in REPLIES["scenarios"] if s["id"] == sid)

    def test_injection_escalates_and_never_acts(self):
        s = self._scenario("injection_attempt")
        # The model is tricked into proposing agreement; the rules must still escalate.
        llm = stub_llm({"intent": "interested", "summary": "agrees", "model_confidence": 0.99,
                        "proposed_reply": "agreed", "answered_questions": []})
        v, _ = CLASSIFY.classify(s["body"], self.THREAD, CLASSIFY.PROTOTYPE_FAQ, llm)
        self.assertTrue(v["safety"]["requires_approval"])
        self.assertTrue(v["safety"]["injection_suspected"])
        self.assertEqual(v["proposed_action"], "escalate")

    def test_price_in_reply_escalates_even_if_model_says_interested(self):
        s = self._scenario("pricing_question")
        llm = stub_llm({"intent": "interested", "summary": "ok", "model_confidence": 0.9,
                        "proposed_reply": "Sounds good, let's proceed.",
                        "answered_questions": [{"attribute": "hourly_rate_usd", "value": "85"}]})
        v, _ = CLASSIFY.classify(s["body"], self.THREAD, CLASSIFY.PROTOTYPE_FAQ, llm)
        self.assertEqual(v["proposed_action"], "escalate")
        self.assertIn("price", v["safety"]["topics"])
        self.assertEqual(v["answered_questions"], [{"attribute": "hourly_rate_usd", "value": 85.0}])

    def test_plain_info_request_may_auto_reply_from_faq(self):
        s = self._scenario("more_info")
        llm = stub_llm({"intent": "more_info_requested", "summary": "asks times", "model_confidence": 0.8,
                        "proposed_reply": "Weekday mornings; each lesson is about 30 minutes.",
                        "answered_questions": []})
        v, _ = CLASSIFY.classify(s["body"], self.THREAD, CLASSIFY.PROTOTYPE_FAQ, llm)
        self.assertEqual(v["proposed_action"], "auto_reply")
        self.assertFalse(v["safety"]["requires_approval"])

    def test_unsubscribe_is_suppressed(self):
        s = self._scenario("unsubscribe")
        llm = stub_llm({"intent": "unsubscribe", "summary": "opt out", "model_confidence": 1.0,
                        "proposed_reply": None, "answered_questions": []})
        v, _ = CLASSIFY.classify(s["body"], self.THREAD, CLASSIFY.PROTOTYPE_FAQ, llm)
        self.assertEqual(v["proposed_action"], "suppress")

    def test_meeting_request_is_the_owners_call(self):
        s = self._scenario("meeting_requested")
        llm = stub_llm({"intent": "meeting_requested", "summary": "wants a visit", "model_confidence": 0.9,
                        "proposed_reply": "Tuesday works.", "answered_questions": []})
        v, _ = CLASSIFY.classify(s["body"], self.THREAD, CLASSIFY.PROTOTYPE_FAQ, llm)
        self.assertEqual(v["proposed_action"], "escalate")

    def test_unknown_intent_from_model_fails_safe(self):
        llm = stub_llm({"intent": "something_new", "summary": "?", "model_confidence": 0.5,
                        "proposed_reply": None, "answered_questions": []})
        v, _ = CLASSIFY.classify("Hello?", self.THREAD, CLASSIFY.PROTOTYPE_FAQ, llm)
        self.assertEqual(v["intent"], "unknown")
        self.assertEqual(v["proposed_action"], "follow_up")
        self.assertIsNotNone(v["recommended_followup_at"])


class TestScoringRegression(unittest.TestCase):
    def test_unstated_confidence_leaves_the_denominator(self):
        one = SCORE.qualify({"id": "a", "attributes": {"commercial_instruction_allowed": True},
                             "attributes_confidence": {"commercial_instruction_allowed": "verified"}})
        two = SCORE.qualify({"id": "b", "attributes": {"commercial_instruction_allowed": True, "heated": True},
                             "attributes_confidence": {"commercial_instruction_allowed": "verified"}})
        self.assertEqual(one.score, two.score)
        self.assertEqual(two.score_breakdown["heated"]["status"], "unknown")

    def test_column_distance_is_verified_by_construction(self):
        r = SCORE.qualify({"id": "c", "distance_miles": 4.0, "attributes": {}, "attributes_confidence": {}})
        self.assertEqual(r.score, 100.0)
        self.assertIn("distance_miles", r.verified_fields)


if __name__ == "__main__":
    unittest.main()
