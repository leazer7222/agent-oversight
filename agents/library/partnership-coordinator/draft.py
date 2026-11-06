"""
Outreach drafting: a fixed template with slots, one LLM-written sentence, and
the anti-fabrication gate from outreach-agent/safety.py in front of the write.

Why mostly deterministic: a template is reviewable, consistent, cheap, and
cannot invent a claim. The model contributes exactly one sentence - a specific,
evidence-grounded reason this facility caught our eye - and that sentence is
checked twice: by assert_no_fabrication() against the business facts the owner
actually supplied, and by a simple rule that the sentence must not introduce
numbers or claims about the swim school itself.

Nothing here sends. The output is a draft row (status='draft', provider='mock').
"""

from __future__ import annotations

import sys
import re
from pathlib import Path
from typing import Callable, Optional, Tuple

LIB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LIB / "outreach-agent"))
from safety import assert_no_fabrication, body_sha256, FabricationError  # noqa: E402

# Facts the prototype may state. Everything else about the business is a
# placeholder the owner must confirm - the gate refuses drafts that claim more.
PROTOTYPE_BUSINESS_FACTS = {
    "business_name": "Cameron's Swim School (PROTOTYPE - name to be confirmed)",
    "owner_first_name": "Cameron",
    "service": "private swimming lessons for children aged eight and under",
    "city": "Katy, Texas",
    "postal_address": "[postal address to be confirmed by the owner before any send]",
    "reply_email": "[reply address to be confirmed]",
    # Deliberately absent: years_experience, insurance_status, certifications,
    # budget_usd, signing_authority. Their absence is what makes the gate bite.
}

QUESTION_TEXT = {
    "commercial_instruction_allowed": "whether you permit outside instructors to run paid lessons",
    "recurring_availability": "whether recurring weekly time slots might be available",
    "hourly_rate_usd": "what you would charge per hour for recurring lesson use",
    "depth_ft": "the shallow-end depth (beginners need a shallow area)",
    "indoor": "whether the pool is indoor or seasonal",
    "heated": "whether the pool is heated year-round",
    "insurance_required": "what insurance you would require from an instructor",
    "lesson_capacity": "roughly how many students could use the pool at once",
    "pool_length_m": "the pool length and number of lanes",
    "revenue_share_possible": "whether you would prefer a flat rate or a share of lesson revenue",
}

TOOL = {
    "name": "write_opening_sentence",
    "description": "Write ONE sentence for an outreach email explaining why this facility looks like a fit, using only the evidence given.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "sentence": {"type": "string",
                         "description": "One sentence, second person, no claims about the swim school, no numbers that are not in the evidence."},
        },
        "required": ["sentence"],
    },
}

SYSTEM = (
    "You write one sentence of a short, polite email from a small children's swim school to a "
    "facility that has a pool. The sentence explains, specifically and warmly, why this facility "
    "caught our eye - using ONLY the evidence provided. Do not state anything about the swim "
    "school itself (no experience, insurance, credentials, awards, guarantees, prices). Do not "
    "invent facts about the facility. One sentence, under 35 words."
)

# A second, deterministic check on the model sentence: no self-claims.
SELF_CLAIM = re.compile(
    r"\b(we are|we're|our (instructors|team|school) (is|are)|years|certified|insured|award|guarantee|best)\b",
    re.I)


def pick_contact(fac: dict) -> Optional[dict]:
    contacts = fac.get("contacts") or []
    with_email = [c for c in contacts if c.get("email")]
    if with_email:
        return sorted(with_email, key=lambda c: (not c.get("is_primary"), c.get("full_name") or ""))[0]
    return None


def open_questions(fac: dict, limit: int = 3) -> list:
    q = ((fac.get("latest_qualification") or {}).get("open_questions") or [])
    out = []
    for item in q:
        attr = item.get("attribute")
        if attr in QUESTION_TEXT and attr not in out:
            out.append(attr)
        if len(out) >= limit:
            break
    return out


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


def compose(fac: dict, business: dict, llm: Callable) -> Tuple[Optional[dict], dict]:
    """Returns (draft or None if no email contact, usage)."""
    contact = pick_contact(fac)
    if contact is None:
        return None, {}

    evidence = evidence_lines(fac)
    questions = open_questions(fac)
    user = (
        f"Facility: {fac.get('name')} ({fac.get('facility_type')}), {fac.get('distance_miles')} miles "
        f"from {business.get('city')}.\nEvidence from their website: "
        + ("; ".join(evidence) if evidence else "nothing specific beyond that they have a pool")
    )
    proposal, usage = llm(SYSTEM, user, TOOL, 1200)
    sentence = (proposal.get("sentence") or "").strip()
    if not sentence or SELF_CLAIM.search(sentence):
        raise FabricationError("model sentence made a claim about the business or was empty")

    first = contact.get("full_name") or "there"
    greeting = f"Hello {first.split()[0] if first != 'there' else 'there'},"
    qlines = "".join(f"\n  - {QUESTION_TEXT[a]}" for a in questions)
    body = (
        f"{greeting}\n\n"
        f"My name is {business['owner_first_name']} and I run {business['business_name']}, offering "
        f"{business['service']} in {business['city']}. {sentence}\n\n"
        f"I am looking for a pool that could host recurring private lessons, and I wondered whether "
        f"{fac.get('name')} might be open to that. Shared or exclusive arrangements are both fine. "
        f"If it is worth a conversation, a few things I would want to understand:{qlines}\n\n"
        f"If a short call is easier, I am happy to work around your schedule.\n\n"
        f"Kind regards,\n{business['owner_first_name']}\n{business['business_name']}\n"
        f"{business['postal_address']}\n"
        f"Reply with 'unsubscribe' and we will not contact you again.\n"
        f"\n[PROTOTYPE DRAFT - not sent]"
    )
    assert_no_fabrication(body, business)   # raises FabricationError on any unsupported claim

    subject = f"Recurring swim lesson space at {fac.get('name')}"
    return {
        "contact_id": contact.get("contact_id"),
        "to_email": contact.get("email"),
        "subject": subject,
        "body": body,
        "body_sha256": body_sha256(body),
        "open_questions_used": questions,
        "sentence": sentence,
    }, usage
