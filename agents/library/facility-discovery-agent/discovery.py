"""
Facility discovery - Google Places API (New) with bounded usage and mandatory provenance.

The rule that shapes this whole module: THE AGENT MAY NOT INVENT A FACILITY.
Every row it emits traces to a response from a named source, carries a stable
external id, and records when it was fetched. There is no code path that
fabricates a name, an address, a website or a contact - and `test_discovery.py`
asserts that an empty API response yields zero facilities rather than anything
plausible-looking.

Cost control is structural, not advisory: `max_requests` is enforced by the
client itself, so a loop bug cannot run up a bill. Each Places text search is a
billable request, so the ceiling is the budget.

Tenant-agnostic. Takes (company_id, search config) and returns facility dicts
shaped for public.swim_upsert_facility, so another business reuses this file.
"""

from __future__ import annotations

import os
import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

PLACES_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"

# Field mask is both a correctness and a cost control: Places (New) bills by SKU
# according to which fields you request, so asking for less is cheaper. These are
# the fields we actually persist.
FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.websiteUri",
    "places.nationalPhoneNumber",
    "places.primaryType",
    "places.types",
    "places.businessStatus",
])

# Query templates. Each is one billable request, so the list length is the cost.
# Ordered most-to-least likely to yield lesson-capable pools.
DEFAULT_QUERIES = (
    "indoor swimming pool",
    "aquatic center",
    "swim school",
    "hotel with indoor pool",
    "gym with swimming pool",
    "recreation center pool",
    "community pool",
    "YMCA pool",
)

# Places primaryType / types -> our facility_type. Anything unmapped stays
# 'unknown' rather than being guessed into a bucket.
_TYPE_MAP = {
    "swimming_pool": "aquatic_center",
    "sports_complex": "recreation_center",
    "fitness_center": "gym",
    "gym": "gym",
    "hotel": "hotel",
    "lodging": "hotel",
    "resort_hotel": "hotel",
    "school": "school",
    "country_club": "private_club",
    "recreation_center": "recreation_center",
    "community_center": "recreation_center",
}

KATY_TX = (29.7858, -95.8245)


class DiscoveryError(Exception):
    category = "discovery_error"


class PlacesConfigError(DiscoveryError):
    category = "validation_error"


@dataclass
class SearchConfig:
    center_lat: float = KATY_TX[0]
    center_lng: float = KATY_TX[1]
    radius_miles: float = 15.0
    queries: tuple = DEFAULT_QUERIES
    max_requests: int = 10          # hard ceiling on billable calls per run
    max_results_per_query: int = 20
    region_code: str = "US"


@dataclass
class DiscoveryStats:
    requests_made: int = 0
    raw_results: int = 0
    accepted: int = 0
    rejected_no_id: int = 0
    rejected_out_of_radius: int = 0
    rejected_closed: int = 0
    deduped: int = 0
    queries_run: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "requests_made": self.requests_made,
            "raw_results": self.raw_results,
            "accepted": self.accepted,
            "rejected_no_id": self.rejected_no_id,
            "rejected_out_of_radius": self.rejected_out_of_radius,
            "rejected_closed": self.rejected_closed,
            "deduped": self.deduped,
            "queries_run": self.queries_run,
        }


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def live_places_transport(api_key: str) -> Callable[[dict], dict]:
    """Real Places API (New) searchText transport."""
    def _call(body: dict) -> dict:
        req = urllib.request.Request(
            PLACES_ENDPOINT,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": FIELD_MASK,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read(400).decode("utf-8", "replace")
            raise DiscoveryError(f"Places API error {exc.code}: {detail}") from exc
    _call.source = "google_places"   # provenance label written to every row
    return _call


def fixture_transport(fixtures: dict, label: str = "katy_tx_places.json") -> Callable[[dict], dict]:
    """Replays recorded responses keyed by textQuery. Used by the test suite and
    by an explicitly fixture-driven run. Returns an EMPTY result for an unknown
    query rather than inventing one - that is the behaviour under test.

    Rows produced through this transport carry source='fixture' and a
    fixture:// source_url. A recorded result must never be persisted as if it
    came from Google Places."""
    def _call(body: dict) -> dict:
        return fixtures.get(body.get("textQuery", ""), {"places": []})
    _call.source = "fixture"
    _call.label = label
    return _call


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _facility_type(place: dict) -> str:
    primary = place.get("primaryType") or ""
    if primary in _TYPE_MAP:
        return _TYPE_MAP[primary]
    for t in place.get("types") or []:
        if t in _TYPE_MAP:
            return _TYPE_MAP[t]
    return "unknown"


def normalize_place(place: dict, cfg: SearchConfig,
                    source: str = "google_places",
                    source_label: str = "") -> Optional[dict]:
    """Turn one Places result into a facility dict, or None if unusable.

    Returns None rather than a partial guess when the result lacks a stable id
    or a name. A facility we cannot re-identify later is not a prospect.

    `source` is the provenance label ('google_places' or 'fixture'); it comes
    from the transport, never from the result, so a recorded response cannot
    present itself as live research.
    """
    place_id = place.get("id")
    name = ((place.get("displayName") or {}).get("text") or "").strip()
    if not place_id or not name:
        return None

    loc = place.get("location") or {}
    lat, lng = loc.get("latitude"), loc.get("longitude")
    distance = None
    if lat is not None and lng is not None:
        distance = round(haversine_miles(cfg.center_lat, cfg.center_lng, lat, lng), 2)

    address = place.get("formattedAddress")
    city = state = postal = None
    if address:
        # Places gives a single formatted string. Parse conservatively and leave
        # components NULL when the shape is unfamiliar - a wrong city is worse
        # than an absent one.
        parts = [p.strip() for p in address.split(",")]
        if len(parts) >= 3:
            city = parts[-3] or None
            tail = parts[-2].split()
            if tail:
                state = tail[0]
                if len(tail) > 1:
                    postal = tail[1]

    # Attributes the agent genuinely knows from Places. Pool specifics - depth,
    # length, heating, whether lessons are permitted - are NOT in Places, so they
    # are declared unknown and become the outreach agent's questions.
    attributes: dict[str, Any] = {}
    confidence: dict[str, str] = {}
    if distance is not None:
        attributes["distance_miles"] = distance
        confidence["distance_miles"] = "verified"

    unknown = [
        "commercial_instruction_allowed", "recurring_availability", "indoor",
        "heated", "pool_length_m", "depth_ft", "hourly_rate_usd",
        "lesson_capacity", "insurance_required", "revenue_share_possible",
    ]

    return {
        "name": name,
        "facility_type": _facility_type(place),
        "address": address,
        "city": city,
        "state": state,
        "postal_code": postal,
        "latitude": lat,
        "longitude": lng,
        "distance_miles": distance,
        "phone": place.get("nationalPhoneNumber"),
        "website": place.get("websiteUri"),
        "source": source,
        "source_ref": place_id,
        "source_url": (f"fixture://{source_label or 'recorded'}#{place_id}"
                       if source == "fixture"
                       else f"https://www.google.com/maps/place/?q=place_id:{place_id}"),
        "attributes": attributes,
        "attributes_confidence": confidence,
        "unknown_fields": unknown,
        "_business_status": place.get("businessStatus"),
    }


def discover(
    cfg: Optional[SearchConfig] = None,
    *,
    transport: Optional[Callable[[dict], dict]] = None,
) -> tuple:
    """Run discovery. Returns (facilities, stats).

    Deduplicates within the run by place_id and by (lower name, lower address),
    mirroring the two unique indexes in migration 049 so the same collision is
    caught before it reaches the database.
    """
    cfg = cfg or SearchConfig()
    stats = DiscoveryStats()

    if transport is None:
        api_key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
        if not api_key:
            raise PlacesConfigError(
                "GOOGLE_PLACES_API_KEY is not set. Either set it, or pass a "
                "fixture transport. Discovery will not invent results."
            )
        transport = live_places_transport(api_key)

    source = getattr(transport, "source", "google_places")
    source_label = getattr(transport, "label", "")
    radius_m = min(50000.0, cfg.radius_miles * 1609.344)  # Places caps at 50km
    seen_ids: set = set()
    seen_keys: set = set()
    out: list = []

    for query in cfg.queries:
        if stats.requests_made >= cfg.max_requests:
            break   # structural cost ceiling

        body = {
            "textQuery": query,
            "maxResultCount": cfg.max_results_per_query,
            "regionCode": cfg.region_code,
            "locationBias": {
                "circle": {
                    "center": {"latitude": cfg.center_lat, "longitude": cfg.center_lng},
                    "radius": radius_m,
                }
            },
        }
        payload = transport(body)
        stats.requests_made += 1
        stats.queries_run.append(query)

        places = payload.get("places") or []
        stats.raw_results += len(places)

        for place in places:
            norm = normalize_place(place, cfg, source=source, source_label=source_label)
            if norm is None:
                stats.rejected_no_id += 1
                continue
            if norm.pop("_business_status", None) == "CLOSED_PERMANENTLY":
                stats.rejected_closed += 1
                continue
            if norm["distance_miles"] is not None and norm["distance_miles"] > cfg.radius_miles:
                # locationBias is a bias, not a filter, so Places legitimately
                # returns results beyond the radius. Enforce it ourselves.
                stats.rejected_out_of_radius += 1
                continue

            key = (norm["name"].lower(), (norm.get("address") or "").lower())
            if norm["source_ref"] in seen_ids or key in seen_keys:
                stats.deduped += 1
                continue

            seen_ids.add(norm["source_ref"])
            seen_keys.add(key)
            out.append(norm)
            stats.accepted += 1

    out.sort(key=lambda f: (f["distance_miles"] is None, f["distance_miles"] or 0))
    return out, stats
