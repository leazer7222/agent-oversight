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

    def test_pool_page_first_and_dated_blog_posts_skipped(self):
        links = F.candidate_links("https://example-pool.test", SITE["https://example-pool.test"][2], limit=5)
        self.assertEqual(links[0], "https://example-pool.test/aquatics/pool")
        self.assertNotIn("https://example-pool.test/blog/2024/05/pool-party", links)


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


# --- email hunt -------------------------------------------------------------

def _cfemail(addr: str, key: int = 0x2d) -> str:
    return "%02x" % key + "".join("%02x" % (ord(ch) ^ key) for ch in addr)


HUNT_SITE = {
    "https://club.test/robots.txt": (200, "text/plain", "User-agent: *\nSitemap: https://club.test/sitemap.xml\n"),
    "https://club.test/sitemap.xml": (200, "application/xml",
        "<urlset><url><loc>https://club.test/our-team</loc></url><url><loc>https://club.test/careers</loc></url>"
        "<url><loc>https://club.test/blog/2024/x</loc></url><url><loc>https://other.test/contact</loc></url></urlset>"),
    "https://club.test": (200, "text/html", "<html><head><title>Club</title></head><body><a href='/pool'>Pool</a><p>Hi</p></body></html>"),
    "https://club.test/pool": (200, "text/html", "<html><body><p>25 yard pool</p></body></html>"),
    "https://club.test/our-team": (200, "text/html", f"""<html><body>
        <p>Aquatics Director <a href="mailto:jordan.lee@club.test?subject=Pool">Jordan Lee</a></p>
        <p>Front desk: <span class="__cf_email__" data-cfemail="{_cfemail('info@club.test')}">[email protected]</span></p>
        <p>Rentals: rentals [at] club [dot] test. Press: press@club.test. Logo: hero@2x.png</p>
        <script type="application/ld+json">{{"email": "events@club.test"}}</script></body></html>"""),
    "https://club.test/careers": (200, "text/html", "<html><body>jobs@club.test</body></html>"),
}


def hunt_get(url):
    return HUNT_SITE.get(url, (404, "text/html", ""))


class TestEmailHunt(unittest.TestCase):
    def test_sitemap_lists_same_host_pages_and_skips_careers_and_blog(self):
        urls = F.sitemap_urls("https://club.test", hunt_get)
        self.assertEqual(urls, ["https://club.test/our-team"])

    def test_hunt_mode_reaches_the_team_page_via_the_sitemap(self):
        page, reason = F.fetch_site("https://club.test", http_get=hunt_get, hunt_emails=True)
        self.assertIsNone(reason)
        self.assertIn("https://club.test/our-team", [s["url"] for s in page["sections"]])
        self.assertNotIn("https://club.test/careers", [s["url"] for s in page["sections"]])

    def test_find_emails_reads_mailto_protected_obfuscated_and_markup_and_drops_junk(self):
        page, _ = F.fetch_site("https://club.test", http_get=hunt_get, hunt_emails=True)
        found = F.find_emails(page["sections"])
        by = {c["email"].lower(): c for c in found}
        self.assertIn("jordan.lee@club.test", by)
        self.assertEqual(by["jordan.lee@club.test"]["full_name"], "Jordan Lee")
        self.assertEqual(by["jordan.lee@club.test"]["role_title"], "Aquatics Director")
        self.assertIn("info@club.test", by)            # Cloudflare-protected, decoded
        self.assertIn("rentals@club.test", by)         # [at] [dot]
        self.assertIn("events@club.test", by)          # JSON-LD in markup
        self.assertNotIn("press@club.test", by)        # junk local part
        self.assertNotIn("jobs@club.test", by)         # careers page never fetched
        self.assertFalse(any("2x.png" in e for e in by))
        for c in found:
            self.assertEqual(c["source_url"], "https://club.test/our-team")
            self.assertTrue(c["evidence_snippet"])
        # ranking: rentals/events (4) beat a named manager (1) and info (2)
        self.assertIn(found[0]["email"], ("rentals@club.test", "events@club.test"))
        self.assertTrue(found[0]["is_primary"])
        self.assertEqual(sum(1 for c in found if c["is_primary"]), 1)

    def test_no_guessing_from_names_or_domains(self):
        secs = [{"url": "https://x.test", "text": "Contact our manager Pat Jones at the front desk.", "html": "<p>Pat Jones</p>"}]
        self.assertEqual(F.find_emails(secs), [])

    def test_rank_parity_with_the_drafter(self):
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("draft_mod", REPO / "agents" / "library" / "partnership-coordinator" / "draft.py")
        D = _ilu.module_from_spec(spec); sys.modules["draft_mod"] = D; spec.loader.exec_module(D)
        for e in ("aquatics@a.test", "rentals@a.test", "manager@a.test", "info@a.test", "pat@a.test", "events@a.test"):
            self.assertEqual(F.rank_email(e), D._email_rank(e), e)


class TestEmailHuntNoise(unittest.TestCase):
    def test_scripts_styles_comments_and_vendors_are_ignored_and_artifacts_cleaned(self):
        html = '''<html><head><style>/* Font by hello@fontguy.test */</style>
        <script>var cfg = {"support":"\u003ecustomercare@abcfitness.com","x":"%20agm@club.test"}</script>
        <!-- webmaster@club.test --></head><body>
        <p>Pool rentals: <a href="mailto:%20rentals@club.test">email us</a> or aquatics@club.test</p>
        <script type="application/ld+json">{"email":"events@club.test"}</script>
        <p>Trash: service@texaspridedisposal.com, accessibility@club.test</p></body></html>'''
        secs = [{"url": "https://club.test/contact", "text": F.html_to_text(html), "html": html}]
        emails = [c["email"].lower() for c in F.find_emails(secs, site_url="https://club.test")]
        # agm@club.test is on the site's own domain, so it is recovered from the script config
        self.assertEqual(set(emails), {"rentals@club.test", "aquatics@club.test", "events@club.test", "agm@club.test"})
        self.assertEqual(emails[0], "aquatics@club.test")

    def test_directory_dump_is_capped_and_own_domain_preferred(self):
        text = " ".join(f"staff{i}@district.test" for i in range(40)) + " pool.manager@club.test info@vendor.test"
        secs = [{"url": "https://club.test/staff", "text": text, "html": ""}]
        out = F.find_emails(secs, site_url="https://club.test")
        self.assertLessEqual(len(out), 6)
        self.assertEqual(out[0]["email"], "pool.manager@club.test")
        self.assertTrue(out[0]["is_primary"])


class TestLocationPreference(unittest.TestCase):
    def test_franchise_site_prefers_this_locations_inbox_and_script_config_on_own_domain(self):
        html = '''<html><body><p>Contact a location: abuhamourinfo@aqua-tots.com, ajaxinfo@aqua-tots.com,
        katyinfo@aqua-tots.com, alpharettainfo@aqua-tots.com</p>
        <script>window.cfg={"loc":{"email":"KatyTX@aqua-tots.com"},"vendor":"ops@vendor.test"}</script></body></html>'''
        secs = [{"url": "https://www.aqua-tots.com/katy/", "text": F.html_to_text(html), "html": html}]
        hints = F.hint_tokens("Aqua-Tots Swim School Katy", "/katy/")
        self.assertIn("katy", hints)
        out = F.find_emails(secs, site_url="https://www.aqua-tots.com/katy/", hints=hints)
        emails = [c["email"].lower() for c in out]
        self.assertEqual(emails[0][:4], "katy")                     # a Katy inbox is primary
        self.assertIn("katytx@aqua-tots.com", emails)                # on-domain script config recovered
        self.assertNotIn("ops@vendor.test", emails)                  # off-domain script junk ignored

    def test_purpose_beats_a_brand_word_in_the_name(self):
        text = "CRContactFormVillaSpaDepartment@x.test CRContactFormAquaticsDepartment@x.test"
        secs = [{"url": "https://villasport.test/cinco-ranch/", "text": text, "html": ""}]
        out = F.find_emails(secs, site_url="https://villasport.test", hints=F.hint_tokens("Villa Sport Athletic Club", "/cinco-ranch/"))
        self.assertEqual(out[0]["email"], "CRContactFormAquaticsDepartment@x.test")

    def test_commission_desks_are_junk(self):
        secs = [{"url": "https://w.test", "text": "central.commissions@w.test frontdesk@w.test", "html": ""}]
        self.assertEqual([c["email"] for c in F.find_emails(secs, site_url="https://w.test")], ["frontdesk@w.test"])
