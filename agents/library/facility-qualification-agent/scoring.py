"""
Facility qualification scoring - deterministic, transparent, reusable.

Three design rules, each of which exists because the alternative causes real harm:

  1. DETERMINISTIC. The same inputs under the same model_version always produce
     the same score. No LLM call participates in the number. An LLM may later
     *extract* an attribute from a web page, but the scoring of that attribute is
     arithmetic. A score that drifts between runs cannot be argued with.

  2. UNKNOWN IS NOT ZERO, AND IT IS NOT A GUESS. A missing attribute contributes
     nothing and is recorded in unknown_fields. It never silently scores as bad
     (which would hide good prospects) or as good (which would send Cameron to a
     pool that cannot host lessons). The score is always reported alongside a
     completeness ratio so a 70 built on two known facts is distinguishable from
     a 70 built on ten.

  3. DISQUALIFIERS ARE ABSOLUTE. A hard blocker - commercial instruction
     forbidden, outside the travel radius - produces status='disqualified'
     regardless of how attractive everything else looks.

This module is tenant-agnostic. Weights and thresholds arrive as a config dict
(stored in agents.config_overrides), so a second business reuses this file with
different weights rather than forking it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

MODEL_VERSION = "qual-v1.0.0"

# Confidence of a source claim. Only 'verified' counts at full weight; an
# inferred value is discounted, because acting on an inference as though it were
# a fact is how an agent ends up misrepresenting a facility to its owner.
CONFIDENCE_MULTIPLIER = {"verified": 1.0, "inferred": 0.6, "unknown": 0.0}

DEFAULT_CONFIG: dict[str, Any] = {
    "max_distance_miles": 15.0,
    "ideal_distance_miles": 7.0,
    "min_pool_length_m": 15.0,
    "min_depth_ft": 3.0,
    "max_hourly_rate_usd": 120.0,
    "qualified_threshold": 60.0,
    "min_completeness": 0.45,
    "weights": {
        "distance": 15.0,
        "commercial_instruction_allowed": 20.0,
        "recurring_availability": 15.0,
        "indoor": 10.0,
        "heated": 10.0,
        "pool_size": 10.0,
        "depth_suitable": 5.0,
        "hourly_rate": 10.0,
        "lesson_capacity": 5.0,
    },
}

# Every attribute the model looks at. Anything in here that the facility does not
# supply lands in unknown_fields - the list is the definition of "what we would
# need to know", which is also what the outreach agent needs to ask about.
SCORED_ATTRIBUTES = (
    "distance_miles", "commercial_instruction_allowed", "recurring_availability",
    "indoor", "heated", "pool_length_m", "depth_ft", "hourly_rate_usd",
    "lesson_capacity", "insurance_required", "revenue_share_possible",
)

# Questions to ask when an attribute is unknown. Phrased as Cameron would ask
# them, because these become the body of the outreach email.
OPEN_QUESTIONS = {
    "commercial_instruction_allowed":
        "Do you permit outside instructors to run paid swim lessons at your pool?",
    "recurring_availability":
        "Would you have recurring weekly time slots available, and which days and times work best?",
    "indoor": "Is the pool indoor, outdoor, or covered seasonally?",
    "heated": "Is the pool heated, and is it available year-round?",
    "pool_length_m": "How long is the pool, and how many lanes does it have?",
    "depth_ft": "What is the shallow-end depth? Lessons need a shallow area for beginners.",
    "hourly_rate_usd": "What would you charge per hour for recurring lesson use?",
    "lesson_capacity": "How many students could use the pool at once?",
    "insurance_required":
        "What insurance coverage would you require from an instructor?",
    "revenue_share_possible":
        "Would you prefer a flat rental rate or a share of lesson revenue?",
}


@dataclass
class QualificationResult:
    facility_id: str
    model_version: str
    score: float
    status: str                       # qualified | disqualified | needs_info
    completeness: float
    score_breakdown: dict = field(default_factory=dict)
    verified_fields: list = field(default_factory=list)
    inferred_fields: list = field(default_factory=list)
    unknown_fields: list = field(default_factory=list)
    open_questions: list = field(default_factory=list)
    disqualifiers: list = field(default_factory=list)

    def to_payload(self, run_id: Optional[str] = None) -> dict:
        return {
            "facility_id": self.facility_id,
            "run_id": run_id,
            "model_version": self.model_version,
            "score": round(self.score, 2),
            "status": self.status,
            "completeness": round(self.completeness, 4),
            "score_breakdown": self.score_breakdown,
            "verified_fields": self.verified_fields,
            "inferred_fields": self.inferred_fields,
            "unknown_fields": self.unknown_fields,
            "open_questions": self.open_questions,
            "disqualifiers": self.disqualifiers,
        }


def _confidence_of(attr: str, confidence_map: dict) -> str:
    c = (confidence_map or {}).get(attr, "unknown")
    return c if c in CONFIDENCE_MULTIPLIER else "unknown"


def _linear_score(value: float, best: float, worst: float) -> float:
    """1.0 at `best`, 0.0 at `worst`, linear between, clamped."""
    if best == worst:
        return 1.0
    raw = (worst - value) / (worst - best)
    return max(0.0, min(1.0, raw))


def qualify(
    facility: dict,
    config: Optional[dict] = None,
) -> QualificationResult:
    """Score one facility.

    `facility` is a dict with `id`, `attributes` and `attributes_confidence`
    (as persisted by swim_upsert_facility), plus optionally `distance_miles`.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    weights = {**DEFAULT_CONFIG["weights"], **(cfg.get("weights") or {})}

    attrs = dict(facility.get("attributes") or {})
    if facility.get("distance_miles") is not None:
        attrs.setdefault("distance_miles", facility["distance_miles"])
    conf = facility.get("attributes_confidence") or {}

    verified, inferred, unknown = [], [], []
    for attr in SCORED_ATTRIBUTES:
        if attrs.get(attr) is None:
            unknown.append(attr)
            continue
        c = _confidence_of(attr, conf)
        if c == "verified":
            verified.append(attr)
        elif c == "inferred":
            inferred.append(attr)
        else:
            # Present but with no stated confidence: treat as unknown rather than
            # assuming it is good data. Provenance discipline, not pedantry.
            unknown.append(attr)

    breakdown: dict[str, Any] = {}
    disqualifiers: list[str] = []
    earned = 0.0
    available = 0.0

    def contribute(key: str, normalized: float, note: str) -> None:
        nonlocal earned, available
        weight = weights.get(key, 0.0)
        mult = CONFIDENCE_MULTIPLIER[_confidence_of(_attr_for(key), conf)]
        if attrs.get(_attr_for(key)) is None:
            breakdown[key] = {"status": "unknown", "weight": weight, "earned": 0.0,
                              "note": "not known - excluded from the denominator"}
            return
        available += weight
        got = weight * normalized * mult
        earned += got
        breakdown[key] = {
            "status": "scored", "weight": weight, "normalized": round(normalized, 3),
            "confidence": _confidence_of(_attr_for(key), conf),
            "earned": round(got, 2), "note": note,
        }

    # --- hard disqualifiers -------------------------------------------------
    dist = attrs.get("distance_miles")
    if dist is not None and dist > cfg["max_distance_miles"]:
        disqualifiers.append(
            f"distance {dist} mi exceeds max {cfg['max_distance_miles']} mi")
    if attrs.get("commercial_instruction_allowed") is False:
        disqualifiers.append("facility does not permit outside commercial instruction")

    # --- scored criteria ----------------------------------------------------
    if dist is not None:
        contribute("distance",
                   _linear_score(float(dist), cfg["ideal_distance_miles"], cfg["max_distance_miles"]),
                   f"{dist} mi (ideal <= {cfg['ideal_distance_miles']})")

    if attrs.get("commercial_instruction_allowed") is not None:
        contribute("commercial_instruction_allowed",
                   1.0 if attrs["commercial_instruction_allowed"] else 0.0,
                   "explicitly permitted" if attrs["commercial_instruction_allowed"]
                   else "not permitted")

    if attrs.get("recurring_availability") is not None:
        contribute("recurring_availability",
                   1.0 if attrs["recurring_availability"] else 0.0,
                   "recurring slots available" if attrs["recurring_availability"]
                   else "no recurring availability")

    if attrs.get("indoor") is not None:
        contribute("indoor", 1.0 if attrs["indoor"] else 0.4,
                   "indoor - year-round" if attrs["indoor"] else "outdoor - seasonal")

    if attrs.get("heated") is not None:
        contribute("heated", 1.0 if attrs["heated"] else 0.3,
                   "heated" if attrs["heated"] else "unheated")

    if attrs.get("pool_length_m") is not None:
        length = float(attrs["pool_length_m"])
        contribute("pool_size", min(1.0, length / 25.0),
                   f"{length} m (25 m scores full)")
        if length < cfg["min_pool_length_m"]:
            disqualifiers.append(
                f"pool length {length} m below minimum {cfg['min_pool_length_m']} m")

    if attrs.get("depth_ft") is not None:
        depth = float(attrs["depth_ft"])
        contribute("depth_suitable", 1.0 if depth >= cfg["min_depth_ft"] else 0.2,
                   f"shallow end {depth} ft")

    if attrs.get("hourly_rate_usd") is not None:
        rate = float(attrs["hourly_rate_usd"])
        contribute("hourly_rate", _linear_score(rate, 0.0, cfg["max_hourly_rate_usd"]),
                   f"${rate}/hr (max acceptable ${cfg['max_hourly_rate_usd']})")
        if rate > cfg["max_hourly_rate_usd"]:
            disqualifiers.append(
                f"hourly rate ${rate} exceeds ceiling ${cfg['max_hourly_rate_usd']}")

    if attrs.get("lesson_capacity") is not None:
        contribute("lesson_capacity", min(1.0, float(attrs["lesson_capacity"]) / 12.0),
                   f"{attrs['lesson_capacity']} students (12 scores full)")

    # --- aggregate ----------------------------------------------------------
    # Score is a percentage of the weight that was ACTUALLY ASSESSABLE. Unknown
    # attributes leave the denominator rather than dragging the score down, so an
    # under-researched facility reads as "needs_info", never as "bad".
    score = (earned / available * 100.0) if available > 0 else 0.0
    completeness = available / sum(weights.values()) if sum(weights.values()) else 0.0

    questions = [
        {"attribute": a, "question": OPEN_QUESTIONS[a]}
        for a in unknown if a in OPEN_QUESTIONS
    ]

    if disqualifiers:
        status = "disqualified"
    elif completeness < cfg["min_completeness"]:
        status = "needs_info"
    elif score >= cfg["qualified_threshold"]:
        status = "qualified"
    else:
        status = "needs_info" if questions else "disqualified"

    return QualificationResult(
        facility_id=str(facility.get("id") or facility.get("facility_id") or ""),
        model_version=MODEL_VERSION,
        score=score,
        status=status,
        completeness=completeness,
        score_breakdown=breakdown,
        verified_fields=sorted(verified),
        inferred_fields=sorted(inferred),
        unknown_fields=sorted(unknown),
        open_questions=questions,
        disqualifiers=disqualifiers,
    )


_KEY_TO_ATTR = {
    "distance": "distance_miles",
    "pool_size": "pool_length_m",
    "depth_suitable": "depth_ft",
    "hourly_rate": "hourly_rate_usd",
}


def _attr_for(weight_key: str) -> str:
    return _KEY_TO_ATTR.get(weight_key, weight_key)
