"""
Outreach drafting: a fixed template with slots, one LLM-written sentence, and
the anti-fabrication gate from outreach-agent/safety.py in front of the write.

Why mostly deterministic: a template is reviewable, consistent, cheap, and
cannot invent a claim. Every statement about the business comes from
business_profile.json (facts the owner supplied), rendered by code. The model
contributes exactly one sentence - a specific, evidence-grounded reason this
facility caught our eye - and that sentence is checked twice: by
assert_no_fabrication() against the supplied facts, and by a rule that it may
not make claims about the swim school at all.

Boundaries from the owner's brief are structural here, not prompted: no price,
schedule, exclusivity, staffing or contract commitment appears in the template;
insurance is never mentioned; the facility is never called "suitable".
"""

from __future__ import annotations

import sys
import re
import json
from pathlib import Path
from typing import Callable, Optional, Tuple

HERE = Path(__file__).resolve().parent
LIB = HERE.parent
sys.path.insert(0, str(LIB / "outreach-agent"))
from safety import assert_no_fabrication, body_sha256, FabricationError  # noqa: E402

PROFILE_PATH = HERE / "business_profile.json"


def load_business_profile(path: Optional[Path] = None) -> dict:
    p = path or PROFILE_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def profile_gaps(facts: dict) -> list:
    """What the owner still needs to supply before REAL sends. Shown in the UI."""
    gaps = []
    if not facts.get("postal_address"):
        gaps.append("postal_address (required in the footer of commercial email)")
    if not facts.get("reply_email"):
        gaps.append("reply_email")
    if not facts.get("business_name") or not facts.get("owner_name"):
        gaps.append("business_name / owner_name")
    return gaps


BUSINESS_FACTS = load_business_profile()
# Kept for the tests and the controller; same object.
PROTOTYPE_BUSINESS_FACTS = BUSINESS_FACTS

QUESTION_TEXT = {
    "commercial_instruction_allowed": "whether outside swim instructors may run paid lessons at your pool",
    "recurring_availability": "whether recurring weekly hours could be set aside, and which days or times tend to be quiet",
    "hourly_rate_usd": "how you would approach pricing - an hourly rate, a share of lesson revenue, or a mix",
    "depth_ft": "the shallow-end depth and how swimmers enter the water (beginners need a shallow area)",
    "indoor": "whether the pool is indoor or seasonal",
    "heated": "whether the pool is heated and what the water temperature usually is",
    "insurance_required": "what insurance, lifeguard or vendor requirements you would have for an outside instructor",
    "lesson_capacity": "roughly how many swimmers could be taught at once alongside your normal guest or member use",
    "pool_length_m": "the pool size and usable teaching space",
    "revenue_share_possible": "whether a share of lesson revenue would be of interest instead of a flat rate",
}

TOOL = {
    "name": "write_opening_sentence",
    "description": "Write ONE sentence for an outreach email explaining why this facility looks like a fit, using only the evidence given.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "sentence": {"type": "string",
                         "description": "One sentence, second person, about THEIR facility only. No claims about the swim school, no numbers that are not in the evidence, no judgement that the pool is suitable."},
        },
        "required": ["sentence"],
    },
}

SYSTEM = (
    "You write one sentence of a short, professional email from a children's and adult swim school "
    "to a facility that has a pool. The sentence says, specifically and warmly, what about THEIR "
    "facility caught our eye - using ONLY the evidence provided. Do not state anything about the swim "
    "school itself (no experience, insurance, credentials, awards, guarantees, prices, student numbers). "
    "Do not say the pool is suitable or a fit; say what looks promising and why. Do not invent facts. "
    "One sentence, under 35 words."
)

# Deterministic check on the model sentence: no self-claims, no suitability verdicts.
SELF_CLAIM = re.compile(
    r"\b(we are|we're|our (instructors|team|school|students) (is|are)|years|certified|insured|award|"
    r"guarantee|best|suitable|perfect fit|ideal fit)\b",
    re.I)


def pick_contact(fac: dict) -> Optional[dict]:
    contacts = fac.get("contacts") or []
    with_email = [c for c in contacts if c.get("email")]
    if with_email:
        return sorted(with_email, key=lambda c: (not c.get("is_primary"), c.get("full_name") or ""))[0]
    return None


def open_questions(fac: dict, limit: int = 4) -> list:
    q = ((fac.get("latest_qualification") or {}).get("open_questions") or [])
    out = []
    for item in q:
        attr = item.get("attribute")
        if attr in QUESTION_TEXT and attr not in out:
            out.append(attr)
        if len(out) >= limit:
            break
    # Always ask the two that decide everything if they are still unknown.
    for must in ("commercial_instruction_allowed", "recurring_availability"):
        attrs = fac.get("attributes") or {}
        if attrs.get(must) is None and must not in out:
            out.insert(0, must)
    return out[:limit]


def evidence_lines(fac: dict) -> list:
    attrs = fac.get("attributes") or {}
    lines = []
    if attrs.get("indoor") is True:
        lines.append("the pool is indoor")
    if attrs.get("heated") is True:
        lines.append("the pool is heated")
    if attrs.get("pool_length_m"):
        lines.append(f"the pool is about {attrs['pool_length_m']} metres long")
    if attrs.get("depth_ft"):
        lines.append(f"the shallow end is about {attrs['depth_ft']} feet")
    if attrs.get("commercial_instruction_allowed") is True:
        lines.append("outside instructors are welcome by arrangement")
    if attrs.get("recurring_availability") is True:
        lines.append("recurring weekly bookings are considered")
    return lines


def render(fac: dict, business: dict, contact: dict, sentence: str, questions: list) -> Tuple[str, str]:
    """Deterministic template. Returns (subject, body)."""
    first = (contact.get("full_name") or "").split()[0] if contact.get("full_name") else "there"
    name = business.get("business_name", "")
    owner = business.get("owner_name", "")
    programs = business.get("programs") or []
    program_text = ", ".join(programs[:-1]) + (f", and {programs[-1]}" if len(programs) > 1 else (programs[0] if programs else ""))
    structures = business.get("partnership_structures") or []
    structure_text = ", ".join(structures[:-1]) + (f" or {structures[-1]}" if len(structures) > 1 else (structures[0] if structures else ""))
    creds = " | ".join(business.get("credentials") or [])
    facility = fac.get("name") or "your facility"
    qlines = "".join(f"\n  - {QUESTION_TEXT[a]}" for a in questions)
    address = business.get("postal_address") or "[Mailing address - Cameron to confirm before any real send]"
    sentence = sentence.strip()
    if sentence and not sentence.endswith((".", "!", "?")):
        sentence += "."

    subject = f"Pool partnership inquiry from {name}"
    body = (
        f"Hello {first},\n\n"
        f"I'm {owner}, owner of {name} in {business.get('service_area', '')}. We teach water safety and "
        f"swimming to {business.get('ages_served', 'children and adults')} - {program_text} - with "
        f"{business.get('approach', 'water safety first')}. We work with {business.get('students_per_year', 'a growing number of')} students a year.\n\n"
        f"{sentence}\n\n"
        f"I'm writing because we are looking for {business.get('ask', 'consistent pool access')}. We are open to "
        f"{structure_text}, and happy to discuss what would work for your facility. "
        f"To see whether {facility} might work for recurring lessons, I would want to understand:{qlines}\n\n"
        f"If someone else handles pool use or partnerships, I would be grateful for an introduction. "
        f"A short call, or a walkthrough of the pool with me, would be the natural next step.\n\n"
        f"Kind regards,\n{owner}\nOwner, {name}\n{creds}\n{business.get('reply_email', '')}\n{address}\n"
        f"If you would rather not hear from us, reply \"unsubscribe\" and we will not contact you again.\n"
    )
    return subject, body


def compose(fac: dict, business: dict, llm: Callable) -> Tuple[Optional[dict], dict]:
    """Returns (draft or None if no email contact, usage)."""
    contact = pick_contact(fac)
    if contact is None:
        return None, {}

    evidence = evidence_lines(fac)
    questions = open_questions(fac)
    user = (
        f"Facility: {fac.get('name')} ({fac.get('facility_type')}), {fac.get('distance_miles')} miles "
        f"from Katy, Texas.\nEvidence from their website: "
        + ("; ".join(evidence) if evidence else "nothing specific beyond that they have a pool")
    )
    proposal, usage = llm(SYSTEM, user, TOOL, 1200)
    sentence = (proposal.get("sentence") or "").strip()
    if not sentence or SELF_CLAIM.search(sentence):
        raise FabricationError("model sentence made a claim about the business, judged suitability, or was empty")

    subject, body = render(fac, business, contact, sentence, questions)
    assert_no_fabrication(body, business)   # raises FabricationError on any unsupported claim

    return {
        "contact_id": contact.get("contact_id"),
        "to_email": contact.get("email"),
        "subject": subject,
        "body": body,
        "body_sha256": body_sha256(body),
        "open_questions_used": questions,
        "sentence": sentence,
        "profile_version": business.get("profile_version"),
    }, usage
