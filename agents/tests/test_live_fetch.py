"""
Live website reading (facility-researcher/fetch.py). No network: the HTTP call
is a fake that serves a tiny in-memory site.

    python -m pytest agents/tests/test_live_fetch.py -q
"""
from __future__ import annotations

import sys
import unittest
import importlib.util as ilu
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "agents" / "library" / "facility-researcher"


def _load(path: Path, name: str):
    spec = ilu.spec_from_file_location(name, path)
    mod = ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


F = _load(LIB / "fetch.py", "sitefetch")
E = _load(LIB / "enrich.py", "enrich")

SITE = {
    "https://example-pool.test/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /private/\n"),
    "https://example-pool.test": (200, "text/html; charset=utf-8", """
        <html><head><title>Example Club</title></head><body>
        <a href="/about">About us</a>
        <a href="/aquatics/pool">Our Aquatics Center &amp; Pool</a>
        <a href="/facility-rentals">Facility rentals</a>
        <a href="/private/members">Members</a>
        <a href="https://other.test/pool">Partner pool</a>
        <a href="/brochure.pdf">Pool brochure</a>
        <a href="mailto:info@example-pool.test">Email</a>
        <a href="/blog/2024/05/pool-party">Pool party recap</a>
        <p>Welcome to Example Club in Katy.</p></body></html>"""),
    "https://example-pool.test/aquatics/pool": (200, "text/html", """
        <html><head><title>Aquatics</title></head><body>
        <h1>Indoor heated pool</h1><p>Our 25-yard indoor pool is heated year round.</p>
        <p>Aquatics Director: Jordan Lee, jordan.lee@example-pool.test</p></body></html>"""),
    "https://example-pool.test/facility-rentals": (200, "text/html",
        "<html><body><p>Rent the pool for $95 per hour. Outside instructors welcome with insurance.</p></body></html>"),
    "https://example-pool.test/about": (200, "text/html", "<html><body><p>Founded 1990.</p></body></html>"),
    "https://example-pool.test/blog/2024/05/pool-party": (200, "text/html", "<html><body><p>Fun.</p></body></html>"),
    "https://example-pool.test/private/members": (200, "text/html", "<html><body><p>secret</p></body></html>"),
}


def fake_get(url):
    if url in SITE:
        return SITE[url]
    return 404, "text/html", ""


class TestLinkSelection(unittest.TestCase):
    def test_pool_pages_rank_first_and_offhost_binaries_are_skipped(self):
        links = F.candidate_links("https://example-pool.test", SITE["https://example-pool.test"][2], limit=3)
        self.assertEqual(links[0], "https://example-pool.test/aquatics/pool")
        self.assertIn("https://example-pool.test/facility-rentals", links)
        for bad in ("other.test", ".pdf", "mailto:"):
            self.assertFalse(any(bad in l for l in links))
        self.assertEqual(len(links), 3)

    def test_shallow_pool_page_beats_deep_blog_post(self):
        links = F.candidate_links("https://example-pool.test", SITE["https://example-pool.test"][2], limit=5)
        self.assertLess(links.index("https://example-pool.test/aquatics/pool"),
                        links.index("https://example-pool.test/blog/2024/05/pool-party"))


class TestFetchSite(unittest.TestCase):
    def test_reads_home_and_pool_pages_and_honours_robots(self):
        page, reason = F.fetch_site("example-pool.test", http_get=fake_get)
        self.assertIsNone(reason)
        urls = [s["url"] for s in page["sections"]]
        self.assertIn("https://example-pool.test/aquatics/pool", urls)
        self.assertNotIn("https://example-pool.test/private/members", urls)
        self.assertFalse(page["fixture"])
        self.assertIn("25-yard indoor pool", page["text"])
        # pool page is placed before the homepage in the joined text
        self.assertLess(page["text"].index("25-yard"), page["text"].index("Welcome to Example Club"))

    def test_missing_website_and_unreachable_and_not_html(self):
        self.assertEqual(F.fetch_site(None, http_get=fake_get), (None, F.NO_WEBSITE))
        self.assertEqual(F.fetch_site("https://nowhere.test", http_get=fake_get), (None, F.UNREACHABLE))
        self.assertEqual(F.fetch_site("https://pdf.test", http_get=lambda u: (200, "application/pdf", "%PDF"))[1], F.NOT_HTML)

    def test_robots_disallow_on_homepage_skips_the_site(self):
        def get(url):
            if url.endswith("/robots.txt"):
                return 200, "text/plain", "User-agent: *\nDisallow: /\n"
            return 200, "text/html", "<html><body>pool</body></html>"
        self.assertEqual(F.fetch_site("https://closed.test", http_get=get), (None, F.ROBOTS_DISALLOWED))


class TestExtractUsesSectionUrls(unittest.TestCase):
    def test_contact_source_url_points_at_the_page_that_names_them(self):
        page, _ = F.fetch_site("https://example-pool.test", http_get=fake_get)

        def llm(system, user, tool):
            return {"attributes": [
                        {"attribute": "heated", "value": "true", "confidence": "verified",
                         "evidence_snippet": "Our 25-yard indoor pool is heated year round."},
                        {"attribute": "hourly_rate_usd", "value": "95", "confidence": "verified",
                         "evidence_snippet": "Rent the pool for $95 per hour."},
                        {"attribute": "depth_ft", "value": "4", "confidence": "verified",
                         "evidence_snippet": "shallow end is four feet"}],   # not on any page -> rejected
                    "contacts": [{"full_name": "Jordan Lee", "role_title": "Aquatics Director",
                                  "email": "jordan.lee@example-pool.test", "phone": None,
                                  "evidence_snippet": "Aquatics Director: Jordan Lee, jordan.lee@example-pool.test"}],
                    "notes": "No depth stated."}, {"input_tokens": 1, "output_tokens": 1}

        result, _usage = E.extract({"name": "Example Club", "facility_type": "gym"}, page, llm, max_chars=F.TOTAL_CHARS)
        self.assertEqual(result["attributes"], {"heated": True, "hourly_rate_usd": 95.0})
        self.assertEqual(result["evidence_rejected"], 1)
        self.assertEqual(result["contacts"][0]["source_url"], "https://example-pool.test/aquatics/pool")


if __name__ == "__main__":
    unittest.main()
