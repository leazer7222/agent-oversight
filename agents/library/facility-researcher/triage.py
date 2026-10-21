"""
Pre-contact triage: four states, hard gates, a recommended channel.

Replaces "a number with a threshold" as the thing a human sees. The numeric
score from scoring.qualify() is kept as an internal diagnostic of assessable
weight; it carries almost no information before contact (discovery supplies
one attribute), so it must not rank facilities or gate sends.

States:
  contact_first          gates pass and an evidenced contact route exists
  research_further       gates pass, no evidenced contact route yet
  not_currently_suitable real, but a poor fit now (competitor, outdoor-only
                         unheated, members-only with no outside programs)
  disqualified           a hard gate failed

Everything here is deterministic. Tenant-agnostic: the only inputs are the
QualificationResult, the facility record (attributes + contacts) and config.

Four-state triage rides inside qualifications.score_breakdown until MVP 1
promotes it to a column; status_legacy maps onto the existing CHECK values so
the pipeline-stage advance in swim_record_qualification keeps working.
"""

from __future__ import annotations

from typing import Any

PROFESSIONALLY_MANAGED = {"hotel", "gym", "private_club", "aquatic_center"}
APPLICATION_PROCESS = {"recreation_center", "school"}


def _contacts(fac: dict) -> list:
    return list(fac.get("contacts") or [])


def recommend_channel(facility_type: str, attrs: dict, contacts: list, facility_phone: str | None) -> str:
    app_url = attrs.get("facility_use_application_url")
    has_email = any((c.get("email") or "").strip() for c in contacts)
    contact_phone = any((c.get("phone") or "").strip() for c in contacts)

    if facility_type in APPLICATION_PROCESS and app_url:
        return "facility_use_application"
    if has_email:
        return "email"
    if contact_phone:
        return "phone"
    if app_url:
        return "facility_use_application"
    # A bare facility switchboard number is a route only where a single
    # operator can say yes; for districts and municipalities it is not.
    if facility_phone and facility_type in PROFESSIONALLY_MANAGED:
        return "phone"
    return "none"


def triage(result: Any, fac: dict) -> dict:
    """result: scoring.QualificationResult; fac: swim_facility_attributes() payload."""
    attrs = dict(fac.get("attributes") or {})
    ftype = fac.get("facility_type") or "unknown"
    contacts = _contacts(fac)

    gates = {
        "commercial_instruction": ("fail" if attrs.get("commercial_instruction_allowed") is False
                                   else "pass" if attrs.get("commercial_instruction_allowed") is True
                                   else "unknown"),
        "distance": "fail" if any("distance" in d for d in result.disqualifiers) else "pass",
        "rate_ceiling": ("fail" if any("rate" in d for d in result.disqualifiers)
                         else "pass" if attrs.get("hourly_rate_usd") is not None else "unknown"),
        "pool_length": ("fail" if any("length" in d for d in result.disqualifiers)
                        else "pass" if attrs.get("pool_length_m") is not None else "unknown"),
        "safety_site_visit": "unknown",   # never inferable; a human signs this off on site
    }

    reasons: list = []
    if result.disqualifiers:
        state = "disqualified"
        reasons.extend(result.disqualifiers)
    elif ftype == "swim_school":
        state = "not_currently_suitable"
        reasons.append("swim school: a competitor, not a landlord")
    elif attrs.get("indoor") is False and attrs.get("heated") is False:
        state = "not_currently_suitable"
        reasons.append("outdoor and unheated: seasonal only")
    else:
        channel = recommend_channel(ftype, attrs, contacts, fac.get("phone"))
        state = "contact_first" if channel != "none" else "research_further"
        if state == "research_further":
            reasons.append("no evidenced contact route yet")

    channel = (recommend_channel(ftype, attrs, contacts, fac.get("phone"))
               if state in ("contact_first", "research_further") else "none")

    if state == "disqualified" or state == "not_currently_suitable":
        status_legacy = "disqualified"
    elif state == "contact_first" and result.status == "qualified":
        status_legacy = "qualified"
    else:
        status_legacy = "needs_info"

    return {
        "triage_state": state,
        "channel_recommended": channel,
        "status_legacy": status_legacy,
        "breakdown_extra": {
            "triage_state": state,
            "channel_recommended": channel,
            "gates": gates,
            "triage_reasons": reasons,
            "contact_count": len(contacts),
            "triage_model": "triage-v0.1-prototype",
        },
    }
