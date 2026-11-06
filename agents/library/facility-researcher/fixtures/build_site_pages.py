#!/usr/bin/env python3
"""
Generates site_pages.json: RECORDED, CLEARLY-LABELLED fixture web pages for the
FIXTURE facilities in facility-discovery-agent/fixtures/katy_tx_places.json.

These are not real websites. Every page says so in its title, in a visible
banner and in an HTML comment. They exist so the enrichment stage can be
exercised end to end - real LLM extraction, real evidence validation - without
a live crawl. Variation is deterministic by facility index so the same inputs
produce the same pages: some facilities publish a named aquatics contact, some
only a phone number, some say outside instructors are not permitted, some
publish a facility-use application, some are sparse.

    python agents/library/facility-researcher/fixtures/build_site_pages.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLACES = HERE.parent.parent / "facility-discovery-agent" / "fixtures" / "katy_tx_places.json"
OUT = HERE / "site_pages.json"

BANNER = ("<!-- FIXTURE PAGE: recorded for the pool-acquisition prototype. Not a real website. -->\n"
          "<div class=\"fixture-banner\">FIXTURE PAGE - this is a recorded page used for a prototype "
          "demonstration. It does not describe a real business.</div>\n")


def page(name: str, ptype: str, idx: int, url: str, phone: str | None) -> str:
    n = idx % 4
    num = f"{idx:03d}"
    parts = [f"<html><head><title>FIXTURE: {name}</title></head><body>", BANNER, f"<h1>{name}</h1>"]

    if ptype in ("hotel", "lodging"):
        if ptype == "lodging" and n != 1:
            parts.append("<p>Our outdoor pool is open seasonally from May through September and is "
                         "unheated. The pool is reserved for registered guests.</p>")
        else:
            parts.append("<p>Our indoor heated pool is open year-round. The pool is 20 metres long with "
                         "a shallow end of 3.5 feet, ideal for families.</p>")
            if n in (0, 2):
                parts.append(f"<p>Group and private swim instruction by outside providers is available by "
                             f"arrangement. Contact Dana Whitfield, Director of Operations, at "
                             f"dana.whitfield@fixture-facility-{num}.example.com.</p>")
            elif n == 1:
                parts.append("<p>The pool is for registered guests only. Outside programs and "
                             "instructors are not permitted.</p>")
            else:
                parts.append(f"<p>For event and pool enquiries call the front desk at {phone or '(281) 555-0100'}.</p>")

    elif ptype in ("gym", "fitness_center"):
        parts.append("<p>Members enjoy a 25-metre indoor lap pool, heated year-round, with a shallow "
                     "teaching lane of 3 feet.</p>")
        if n in (0, 3):
            parts.append(f"<p>Aquatics Coordinator: Marcus Lee - marcus.lee@fixture-facility-{num}.example.com "
                         f"- {phone or '(281) 555-0101'}. We welcome enquiries from outside instructors; "
                         f"a certificate of insurance is required and lane time is available on a "
                         f"recurring weekly schedule.</p>")
        elif n == 1:
            parts.append("<p>The pool is available to members only. Outside instructors are not permitted "
                         "to run paid lessons on the premises.</p>")
        else:
            parts.append("<p>Pool schedules are posted at the front desk. Please call for details.</p>")

    elif ptype == "swimming_pool":
        parts.append("<p>Public aquatic center with a 25-yard, 8-lane indoor competition pool and a "
                     "separate warm-water teaching pool, depth 3 feet to 4 feet.</p>")
        if n in (0, 2):
            parts.append(f"<p>Lane rentals are available to certified instructors at $55 per hour; proof "
                         f"of insurance is required. Aquatics Director: Priya Nair, "
                         f"priya.nair@fixture-facility-{num}.example.com.</p>")
        elif n == 1:
            parts.append("<p>We operate our own learn-to-swim program. We do not rent lanes to outside "
                         "swim instructors.</p>")
        else:
            parts.append(f"<p>Rental enquiries: call {phone or '(281) 555-0102'}.</p>")

    elif ptype in ("community_center", "sports_complex"):
        if ptype == "sports_complex":
            parts.append("<p>Outdoor 50-metre pool, heated and open year-round, with a 3.5-foot shallow "
                         "end.</p>")
        else:
            parts.append("<p>Municipal community pool, indoor, 25 yards, open to the public.</p>")
        if n in (0, 1):
            parts.append(f"<p>Organisations wishing to run programs must submit a <a "
                         f"href=\"{url}/facility-use-application\">Facility Use Application</a>. The "
                         f"rental rate for the pool is $45 per hour and a certificate of insurance "
                         f"naming the City is required.</p>")
        elif n == 2:
            parts.append(f"<p>Recreation Supervisor: Tomas Ortega - tomas.ortega@fixture-facility-{num}"
                         f".example.com. Recurring weekly bookings are considered each season.</p>")
        else:
            parts.append("<p>Pool hours vary by season. See the city calendar.</p>")

    elif ptype == "school":
        parts.append("<p>District natatorium: 25-yard, 10-lane indoor pool used for athletics and "
                     "physical education.</p>")
        if n in (0, 2):
            parts.append(f"<p>Community use of district facilities is governed by board policy; apply via "
                         f"the <a href=\"{url}/facility-use-agreement\">Facility Use Agreement</a>. "
                         f"Hourly fee $60; insurance certificate required.</p>")
        else:
            parts.append("<p>Facilities office: see the district directory.</p>")

    elif ptype == "country_club":
        parts.append("<p>Members-only club with an outdoor heated pool (25 metres) and a children's "
                     "pool, open March through November.</p>")
        if n in (0, 3):
            parts.append(f"<p>Outside instructors holding a certificate of insurance may apply to offer "
                         f"lessons to members. General Manager: Elena Rossi, "
                         f"elena.rossi@fixture-facility-{num}.example.com.</p>")
        else:
            parts.append("<p>Pool access is a benefit of membership.</p>")

    else:
        parts.append("<p>Welcome. Please contact us for information.</p>")

    parts.append("</body></html>")
    return "\n".join(parts)


def main() -> int:
    data = json.loads(PLACES.read_text(encoding="utf-8"))
    seen: dict = {}
    for q in data.values():
        for p in q.get("places", []):
            pid = p.get("id")
            if not pid or pid in seen:
                continue
            seen[pid] = p
    pages = {}
    for pid, p in seen.items():
        name = p["displayName"]["text"]
        try:
            idx = int(pid.rsplit("_", 1)[1])
        except ValueError:
            idx = len(pages)
        url = p.get("websiteUri") or f"https://fixture-{pid.lower()}.example.com"
        pages[pid] = {
            "source_ref": pid,
            "url": url,
            "fetched_at": "2026-10-20T00:00:00Z",
            "fixture": True,
            "html": page(name, p.get("primaryType") or "", idx, url, p.get("nationalPhoneNumber")),
        }
    OUT.write_text(json.dumps({"_note": "FIXTURE pages for the prototype. Not real websites.",
                               "pages": pages}, indent=2), encoding="utf-8")
    print(f"wrote {len(pages)} fixture pages to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
