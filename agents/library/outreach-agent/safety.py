"""
Outreach safety rails.

This module exists because an autonomous email agent has two ways to cause real
harm that ordinary bugs do not: it can be talked into doing something by the
very content it is reading, and it can misrepresent a business to a stranger.

Three independent controls, each of which holds even if the others fail:

  1. INBOUND EMAIL IS DATA, NEVER INSTRUCTIONS. wrap_untrusted() fences reply
     text so it is unambiguous to the model which bytes came from a stranger.
     But fencing alone is not a security control - a sufficiently clever prompt
     may still shift the model's output. So:

  2. THE MODEL CANNOT ACT. Classification returns a PROPOSAL. The only code path
     that sends email requires a row in swim_sourcing.approvals written by an
     authenticated human, whose approved_sha256 must equal the hash of the exact
     bytes being sent. No prompt can create that row. This is the control that
     actually makes injection non-exploitable rather than merely harder.

  3. COMMITMENT TOPICS ARE ESCALATED BY RULE, NOT BY JUDGEMENT.
     requires_human_approval() is a deterministic keyword-and-intent check run
     over the model's proposal. Price, contract, exclusivity, insurance,
     schedule commitments and anything touching Cameron's credentials escalate
     regardless of what the model concluded or how confident it was.

Also here: assert_no_fabrication(), which refuses to let a draft claim anything
about Cameron that she did not supply - experience, insurance, budget, authority.
"""

from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass, field
from typing import Any, Optional

# The nine intents from the plan, plus 'unknown' for the honest default.
INTENTS = (
    "interested",
    "not_interested",
    "more_info_requested",
    "pricing_discussion",
    "availability_discussion",
    "meeting_requested",
    "requires_owner_decision",
    "out_of_office",
    "unsubscribe",
    "unknown",
)

# Intents that may never be auto-answered, whatever the model proposes.
ESCALATE_ALWAYS = {
    "pricing_discussion",
    "requires_owner_decision",
    "unsubscribe",          # must be honoured by a human-verified suppression write
}

# Topic patterns that force escalation. Deliberately broad: a false escalation
# costs Cameron a few seconds; a false auto-reply can commit her to a contract.
COMMITMENT_PATTERNS = (
    # The money pattern is a SEPARATE alternative with no leading \b. A leading
    # \b can never match before "$" - the space-to-"$" transition is not a word
    # boundary - so folding it into the keyword alternation silently disabled
    # dollar-amount detection altogether. Caught by
    # test_commitment_in_the_proposed_reply_also_escalates.
    (r"(?:\$\s*\d|\b\d+(?:\.\d+)?\s*(?:dollars|usd|per\s+hour|/\s*hr|/\s*hour)\b)", "price"),
    (r"\b(price|pricing|rate|rates|cost|fee|fees|charge|charges|quote|deposit|"
     r"pay|payment|hourly|invoice)\b", "price"),
    (r"\b(contract|agreement|terms|sign|signature|lease|waiver|liability)", "contract"),
    (r"\b(exclusiv\w*|sole provider|only instructor)", "exclusivity"),
    (r"\b(insur\w*|coverage|certificate of insurance|coi|indemnif\w*)", "insurance"),
    (r"\b(commit|guarantee|promise|lock in|binding)", "commitment"),
    (r"\b(every (week|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
     r"recurring schedule|permanent slot)", "schedule_commitment"),
    (r"\b(certif\w*|qualif\w*|licen[cs]\w*|background check|credential\w*)", "credentials"),
)

# Phrases that indicate an attempt to redirect the agent rather than reply to it.
# Used for DETECTION AND LOGGING, not as the primary defence - see control 2.
INJECTION_PATTERNS = (
    # Cover rules/guidelines/directions, not only the literal word
    # "instructions". "Ignore your rules" was slipping through, and that is at
    # least as likely a phrasing as the textbook one.
    r"ignore\s+(?:all\s+|your\s+|the\s+|previous\s+|prior\s+|my\s+)*"
    r"(?:instructions?|rules?|guidelines?|directions?|constraints?|polic\w+)",
    r"disregard\s+(?:all\s+|your\s+|the\s+|previous\s+|prior\s+)*"
    r"(?:instructions?|rules?|guidelines?|directions?|constraints?)",
    r"override\s+(?:your\s+|the\s+)?(?:instructions?|rules?|settings?|safety)",
    r"you\s+are\s+now\s+",
    r"new\s+(instructions|system\s+prompt|directive)",
    r"system\s*[:>]\s*",
    r"</?(system|assistant|instructions?)>",
    r"act\s+as\s+(if|though|a)\b",
    r"forget\s+(everything|your|all)\b",
    r"(do\s+not|don't)\s+(ask|require|seek)\s+(for\s+)?(approval|permission|confirmation)",
    r"(approve|authorize|confirm)\s+(this|it|the\s+\w+)\s+(automatically|without)",
    r"send\s+(the\s+)?(contract|agreement|payment)",
    r"on\s+behalf\s+of\s+(cameron|the\s+owner)",
    r"reply\s+with\s+(yes|agreed|confirmed)",
    r"\bprompt\s+injection\b",
)

# Claims a draft may never make unless the value came from Cameron's own config.
FABRICATION_PATTERNS = (
    (r"\b(\d+)\+?\s*years?\s+(of\s+)?experience", "experience_claim"),
    (r"\bfully\s+insured\b", "insurance_claim"),
    (r"\b(certified|licensed)\s+(by|instructor|coach)", "credential_claim"),
    (r"\bwe\s+(guarantee|promise)\b", "guarantee"),
    (r"\b(award[- ]winning|best[- ]rated|number\s+one)\b", "superlative"),
    (r"\bbudget\s+of\s+\$?\d", "budget_claim"),
    (r"\bauthoriz(ed|ation)\s+to\s+(sign|commit|bind)", "authority_claim"),
)

UNTRUSTED_OPEN = "<<<UNTRUSTED_EMAIL_CONTENT>>>"
UNTRUSTED_CLOSE = "<<<END_UNTRUSTED_EMAIL_CONTENT>>>"


@dataclass
class SafetyVerdict:
    requires_approval: bool
    reasons: list = field(default_factory=list)
    topics: list = field(default_factory=list)
    injection_suspected: bool = False
    injection_matches: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "requires_approval": self.requires_approval,
            "reasons": self.reasons,
            "topics": self.topics,
            "injection_suspected": self.injection_suspected,
            "injection_matches": self.injection_matches,
        }


def body_sha256(text: str) -> str:
    """Canonical hash used to bind an approval to exact bytes. Newlines are
    normalised so a CRLF round-trip through a mail provider does not invalidate
    an otherwise-identical approval, but nothing else is touched."""
    return hashlib.sha256(text.replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()


def strip_untrusted_fences(text: str) -> str:
    """Remove any fence markers the sender included themselves, so they cannot
    forge the end of the untrusted region and appear to speak as the system."""
    out = text.replace(UNTRUSTED_OPEN, "[removed]").replace(UNTRUSTED_CLOSE, "[removed]")
    return re.sub(r"<<<\s*/?\s*(END_)?UNTRUSTED[^>]*>>>", "[removed]", out, flags=re.I)


def wrap_untrusted(text: str) -> str:
    """Fence inbound content for inclusion in a prompt."""
    return f"{UNTRUSTED_OPEN}\n{strip_untrusted_fences(text)}\n{UNTRUSTED_CLOSE}"


def detect_injection(text: str) -> list:
    """Returns the injection patterns found. Detection is for logging and for
    forcing escalation - it is explicitly NOT the primary defence, because
    pattern matching cannot be complete."""
    found = []
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, flags=re.I):
            found.append(pattern)
    return found


def detect_commitment_topics(text: str) -> list:
    topics = []
    for pattern, topic in COMMITMENT_PATTERNS:
        if re.search(pattern, text, flags=re.I) and topic not in topics:
            topics.append(topic)
    return topics


def requires_human_approval(
    inbound_text: str,
    proposed_intent: str,
    proposed_reply: Optional[str] = None,
) -> SafetyVerdict:
    """Deterministic gate over a model proposal.

    Escalates when the intent is inherently commercial, when either the inbound
    text or the proposed reply touches a commitment topic, or when injection is
    suspected. The model's own confidence is not an input: a confident wrong
    answer is exactly the case this must catch.
    """
    reasons: list = []
    verdict_topics: list = []

    injection = detect_injection(inbound_text)
    if injection:
        reasons.append(
            "inbound content attempts to redirect the agent - escalating and "
            "taking no action on its instructions")

    if proposed_intent in ESCALATE_ALWAYS:
        reasons.append(f"intent '{proposed_intent}' always requires Cameron's decision")

    if proposed_intent not in INTENTS:
        reasons.append(f"unrecognised intent '{proposed_intent}' - failing safe")

    for source_name, source in (("inbound", inbound_text), ("proposed_reply", proposed_reply or "")):
        for topic in detect_commitment_topics(source):
            if topic not in verdict_topics:
                verdict_topics.append(topic)
                reasons.append(f"{source_name} touches '{topic}'")

    return SafetyVerdict(
        requires_approval=bool(reasons),
        reasons=reasons,
        topics=verdict_topics,
        injection_suspected=bool(injection),
        injection_matches=injection,
    )


class FabricationError(Exception):
    category = "validation_error"


def assert_no_fabrication(draft: str, business_facts: dict) -> None:
    """Refuse a draft that asserts something about Cameron she did not supply.

    business_facts is her confirmed configuration. A claim is permitted only if
    the corresponding fact is present AND its value appears in the draft. The
    default is refusal, so forgetting to configure something cannot result in
    the agent inventing it.
    """
    allowed = {
        "experience_claim": business_facts.get("years_experience"),
        "insurance_claim": business_facts.get("insurance_status"),
        "credential_claim": business_facts.get("certifications"),
        "budget_claim": business_facts.get("budget_usd"),
        "authority_claim": business_facts.get("signing_authority"),
    }
    for pattern, claim in FABRICATION_PATTERNS:
        if re.search(pattern, draft, flags=re.I):
            if claim in ("guarantee", "superlative"):
                raise FabricationError(
                    f"draft contains a '{claim}' which outreach may never make")
            if not allowed.get(claim):
                raise FabricationError(
                    f"draft makes a '{claim}' but no corresponding confirmed fact "
                    f"was supplied by the business owner")


def can_auto_reply(intent: str, verdict: SafetyVerdict, faq: dict) -> bool:
    """Auto-reply is permitted only for an informational intent, with no
    escalation reason, and only when a pre-approved FAQ answer exists."""
    if verdict.requires_approval:
        return False
    if intent != "more_info_requested":
        return False
    return bool(faq)
