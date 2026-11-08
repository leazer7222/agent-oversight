"""
Live website reading for the Facility Researcher.

Reads a facility's OWN website so that enrichment (enrich.py) can extract facts
with verbatim evidence. The fixture pages used by the prototype keep working;
this module is the production path for facilities that came from Google Places.

What it does, and the limits that make it polite and bounded:
  * robots.txt is honoured for our user agent; a disallowed site is skipped,
    never scraped around.
  * The homepage is fetched first, then up to MAX_EXTRA_PAGES same-host links
    whose URL or anchor text suggests pool / aquatics / rental / contact
    content. Nothing off-host, no mailto/tel, no binary files.
  * Each response is capped at MAX_BYTES and must be HTML. Timeouts are short.
  * Output is a "page" dict in the same shape enrich.extract expects, plus a
    `sections` list (url + text per fetched page) so a contact's source_url
    can point at the page that actually names them.

The HTTP call is injected (`http_get(url) -> (status, content_type, body)`)
so the selection logic is testable without a network.
"""

from __future__ import annotations

import os
import re
import html as htmllib
import urllib.parse
import urllib.robotparser
from typing import Callable, Optional, Tuple

DEFAULT_USER_AGENT = os.environ.get(
    "SWIM_FETCH_USER_AGENT",
    "AgentOversight-FacilityResearcher/1.0 (+https://agent-oversight.vercel.app)")
TIMEOUT_S = 12
ROBOTS_TIMEOUT_S = 6
MAX_BYTES = 1_500_000
MAX_EXTRA_PAGES = 3
PER_PAGE_CHARS = 9_000       # text kept per page before joining
TOTAL_CHARS = 24_000         # ceiling for the joined text handed to the model

# (keyword regex, weight). Higher weight = fetched first. Pool-specific pages
# beat generic ones because the facts we need live there.
LINK_HINTS = (
    (re.compile(r"pool|aquatic|swim|natator|lap", re.I), 3),
    (re.compile(r"rental|rent|reserv|book|facilit|venue|hire", re.I), 2),
    (re.compile(r"amenit|program|member|contact|about|staff|team", re.I), 1),
)
# Hunt mode: pages most likely to carry a person or an inbox. Used in addition to
# LINK_HINTS when the caller asks for an email hunt.
CONTACT_HINTS = (
    (re.compile(r"contact|staff|team|leadership|management|directory|our-people|meet-the|about", re.I), 3),
    (re.compile(r"rental|rent|event|part(y|ies)|book|reserv|facilit|venue|aquatic|pool|swim", re.I), 2),
    (re.compile(r"member|program|faq|hours|location", re.I), 1),
)
MAX_HUNT_PAGES = 8           # total pages per site when hunting for an inbox
SKIP_PATH = re.compile(r"career|job|press|investor|privacy|legal|terms|cookie|login|signin|cart|blog/20", re.I)
SKIP_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|svg|webp|mp4|mp3|zip|docx?|xlsx?|pptx?|ics)(\?|$)", re.I)
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "sms:")

NO_WEBSITE = "no_website"
ROBOTS_DISALLOWED = "robots_disallowed"
UNREACHABLE = "unreachable"
NOT_HTML = "not_html"
EMPTY = "empty"


def _requests_get(url: str, user_agent: str = DEFAULT_USER_AGENT,
                  timeout: float = TIMEOUT_S) -> Tuple[int, str, str]:
    """Default transport. Streams and stops at MAX_BYTES; never follows a
    redirect off http(s). Returns (status, content_type, body_text)."""
    import requests  # local import keeps the module importable without it (tests)
    with requests.get(url, headers={"User-Agent": user_agent, "Accept": "text/html,*/*;q=0.5"},
                      timeout=timeout, stream=True, allow_redirects=True) as resp:
        ctype = resp.headers.get("content-type", "")
        chunks, size = [], 0
        for chunk in resp.iter_content(chunk_size=65536):
            if not chunk:
                continue
            chunks.append(chunk)
            size += len(chunk)
            if size >= MAX_BYTES:
                break
        raw = b"".join(chunks)
        enc = resp.encoding or "utf-8"
        try:
            body = raw.decode(enc, errors="replace")
        except LookupError:
            body = raw.decode("utf-8", errors="replace")
        return resp.status_code, ctype, body


def html_to_text(html: str) -> str:
    text = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    text = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</(p|div|li|h[1-6]|tr|section|article)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = htmllib.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def _page_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.S | re.I)
    return htmllib.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""


def candidate_links(base_url: str, html: str, limit: int = MAX_EXTRA_PAGES, hints=LINK_HINTS) -> list:
    """Same-host links ranked by how likely they are to describe the pool (or,
    with CONTACT_HINTS, to name a person or an inbox).
    Returns at most `limit` absolute URLs, best first, no duplicates."""
    base = urllib.parse.urlsplit(base_url)
    host = (base.netloc or "").lower().removeprefix("www.")
    scored: dict = {}
    for m in re.finditer(r"<a\b[^>]*?href\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</a>", html, flags=re.S | re.I):
        href, anchor = m.group(2).strip(), re.sub(r"<[^>]+>", " ", m.group(3))
        if not href or href.startswith("#") or href.lower().startswith(SKIP_SCHEMES):
            continue
        absu = urllib.parse.urljoin(base_url, href)
        parts = urllib.parse.urlsplit(absu)
        if parts.scheme not in ("http", "https"):
            continue
        if (parts.netloc or "").lower().removeprefix("www.") != host:
            continue
        if SKIP_EXT.search(parts.path or "") or SKIP_PATH.search(parts.path or ""):
            continue
        clean = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path or "/", "", ""))
        if clean.rstrip("/") == base_url.rstrip("/"):
            continue
        hay = f"{parts.path} {htmllib.unescape(anchor)}"
        score = 0
        for rx, w in hints:
            if rx.search(hay):
                score = max(score, w)
        if score == 0:
            continue
        # Prefer shallow paths at equal score (overview pages over deep posts).
        depth = parts.path.count("/")
        key = (-score, depth, clean)
        if clean not in scored or key < scored[clean]:
            scored[clean] = key
    ranked = sorted(scored.values())
    return [k[2] for k in ranked[:limit]]


def robots_allows(url: str, http_get: Callable, user_agent: str = DEFAULT_USER_AGENT) -> bool:
    """True unless robots.txt explicitly disallows this agent. Unreachable or
    malformed robots.txt counts as allowed (the conventional reading)."""
    parts = urllib.parse.urlsplit(url)
    robots_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    try:
        status, _ctype, body = http_get(robots_url)
    except Exception:
        return True
    if status != 200 or not body:
        return True
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.parse(body.splitlines())
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True


def sitemap_urls(site: str, http_get: Callable, limit: int = 400) -> list:
    """URLs listed in /sitemap.xml (or the Sitemap: lines of robots.txt), same
    host only, one level of sitemap index followed. Empty on any failure."""
    parts = urllib.parse.urlsplit(site)
    host = (parts.netloc or "").lower().removeprefix("www.")
    roots = [urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/sitemap.xml", "", ""))]
    try:
        st, _c, body = http_get(urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", "")))
        if st == 200 and body:
            roots += [m.group(1).strip() for m in re.finditer(r"(?im)^\s*sitemap:\s*(\S+)", body)]
    except Exception:
        pass
    out: list = []
    seen_maps: set = set()
    queue = list(dict.fromkeys(roots))[:5]
    while queue and len(out) < limit:
        sm = queue.pop(0)
        if sm in seen_maps:
            continue
        seen_maps.add(sm)
        try:
            st, _c, body = http_get(sm)
        except Exception:
            continue
        if st != 200 or not body:
            continue
        locs = [htmllib.unescape(m.group(1).strip()) for m in re.finditer(r"<loc>\s*(.*?)\s*</loc>", body, flags=re.S | re.I)]
        for u in locs:
            lp = urllib.parse.urlsplit(u)
            if (lp.netloc or "").lower().removeprefix("www.") != host:
                continue
            if lp.path.lower().endswith(".xml") and len(seen_maps) < 6:
                queue.append(u)          # nested sitemap index
            elif not SKIP_EXT.search(lp.path or "") and not SKIP_PATH.search(lp.path or ""):
                out.append(urllib.parse.urlunsplit((lp.scheme, lp.netloc, lp.path or "/", "", "")))
            if len(out) >= limit:
                break
    return out


def rank_contact_pages(urls: list, limit: int) -> list:
    """Order sitemap URLs by CONTACT_HINTS weight, shallow first."""
    scored = []
    for u in urls:
        path = urllib.parse.urlsplit(u).path or "/"
        w = 0
        for rx, weight in CONTACT_HINTS:
            if rx.search(path):
                w = max(w, weight)
        if w:
            scored.append((-w, path.count("/"), u))
    return [u for _w, _d, u in sorted(scored)[:limit]]


def fetch_site(website: Optional[str], *, http_get: Callable = _requests_get,
               user_agent: str = DEFAULT_USER_AGENT, max_extra_pages: int = MAX_EXTRA_PAGES,
               hunt_emails: bool = False
               ) -> Tuple[Optional[dict], Optional[str]]:
    """Read a facility website. Returns (page, None) or (None, reason).

    page = {url, html: "", text, fixture: False, sections: [{url, title, text, html}],
            pages_fetched}

    hunt_emails=True widens the crawl to MAX_HUNT_PAGES, adds contact/staff/
    rental pages found via the homepage nav and the sitemap, and keeps each
    page's HTML so find_emails() can read mailto: links and protected addresses.
    """
    site = (website or "").strip()
    if not site:
        return None, NO_WEBSITE
    if not re.match(r"^https?://", site, flags=re.I):
        site = "https://" + site

    if not robots_allows(site, http_get, user_agent):
        return None, ROBOTS_DISALLOWED

    sections: list = []
    seen: set = set()

    def _key(url: str) -> str:
        # www.example.org/x and example.org/x are the same page.
        p = urllib.parse.urlsplit(url)
        return (p.netloc or "").lower().removeprefix("www.") + (p.path or "/").rstrip("/")

    def _grab(url: str) -> Optional[str]:
        try:
            status, ctype, body = http_get(url)
        except Exception:
            return None
        if status != 200 or not body:
            return None
        if ctype and "html" not in ctype.lower() and "xml" not in ctype.lower():
            return "__not_html__"
        return body

    home_html = _grab(site)
    if home_html is None:
        return None, UNREACHABLE
    if home_html == "__not_html__":
        return None, NOT_HTML
    seen.add(_key(site))
    home_text = html_to_text(home_html)[:PER_PAGE_CHARS]
    sections.append({"url": site, "title": _page_title(home_html), "text": home_text, "html": home_html})

    budget = (MAX_HUNT_PAGES - 1) if hunt_emails else max_extra_pages
    links = candidate_links(site, home_html, limit=budget + 2)
    if hunt_emails:
        # Contact-flavoured nav links first, then the pool pages, then whatever the
        # sitemap offers that the nav did not.
        links = candidate_links(site, home_html, limit=budget + 4, hints=CONTACT_HINTS) + links
        links += rank_contact_pages(sitemap_urls(site, http_get), limit=budget)
    for link in links:
        if len(sections) > budget or _key(link) in seen:
            continue
        seen.add(_key(link))
        if not robots_allows(link, http_get, user_agent):
            continue
        body = _grab(link)
        if body is None or body == "__not_html__":
            continue
        sections.append({"url": link, "title": _page_title(body), "text": html_to_text(body)[:PER_PAGE_CHARS],
                         "html": body})

    # Pool-specific pages first in the joined text: extraction truncates from the
    # end, so the most informative material must not be what gets cut.
    sections.sort(key=lambda s: 0 if LINK_HINTS[0][0].search(
        (urllib.parse.urlsplit(s["url"]).path or "") + " " + s["title"]) else 1)
    joined = "\n\n".join(f"[{s['url']}]\n{s['text']}" for s in sections)[:TOTAL_CHARS]
    if not joined.strip():
        return None, EMPTY
    return {"url": site, "html": "", "text": joined, "fixture": False,
            "sections": sections, "pages_fetched": len(sections)}, None


# ---------------------------------------------------------------------------
# Email hunt: deterministic, evidence-bound. An address is recorded only when it
# is literally on a fetched page: in a mailto: link, in the visible text, in a
# Cloudflare-protected span (decoded from the bytes the page serves), or in an
# obfuscated "name [at] domain [dot] com" form. Nothing is guessed from a name
# pattern or a domain. Each hit carries the page URL and the surrounding text.
# ---------------------------------------------------------------------------

EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}")
OBFUSCATED_RX = re.compile(
    r"([A-Za-z0-9._%+-]+)\s*(?:\[\s*at\s*\]|\(\s*at\s*\)|\{\s*at\s*\}|<at>)\s*"
    r"([A-Za-z0-9-]+(?:(?:\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\{\s*dot\s*\})\s*|\.(?=[A-Za-z0-9]))[A-Za-z0-9-]+)+)", re.I)
JUNK_DOMAINS = ("example.com", "example.org", "sentry.io", "wixpress.com", "w3.org", "schema.org",
                "googleapis.com", "squarespace.com", "godaddy.com", "wordpress.com", "cloudflare.com",
                "domain.com", "email.com", "yourdomain.com", "mysite.com")
JUNK_LOCAL = re.compile(
    r"^(noreply|no-reply|donotreply|do-not-reply|mailer-daemon|postmaster|abuse|unsubscribe|privacy|dmca|press|"
    r"careers?|jobs|hr|recruiting|customercare|customer\.care|customerservice|customer\.service|support|helpdesk|"
    r"billing|accounting|accounts?payable|accountservices|accessibility|ada|media|mediainquiries|mediarelations|"
    r"webmaster|security|compliance|legal|investor(relations)?|engagementhelp|member\.solutions|marketing|"
    r"newsletter|feedback|survey|donotemail|spam|test|commissions?|central\.commissions|travelagents?|"
    r"groupsales|reservations?|franchis(e|ing)|partnerships?|corporatepartnerships?\w*|vendor(s|relations)?)$", re.I)
STOP_TOKENS = {"swim", "school", "fitness", "center", "centre", "club", "pool", "pools", "aquatic", "aquatics",
               "recreation", "community", "hotel", "inn", "suites", "the", "and", "with", "academy", "park",
               "athletic", "health", "family", "locations", "location", "texas", "https", "http", "www", "com",
               "org", "net", "html", "index", "home", "page"}


def hint_tokens(*parts: str) -> set:
    """Place-name tokens from a facility name / URL path (katy, cinco, ranch,
    westhouston...). Used to prefer the inbox that belongs to THIS location on
    a franchise or district site that lists many."""
    out: set = set()
    for part in parts:
        for tok in re.split(r"[^a-z0-9]+", (part or "").lower()):
            if len(tok) >= 4 and tok not in STOP_TOKENS and not tok.isdigit():
                out.add(tok)
    return out
# Off-site vendors whose addresses end up in page templates (fonts, software, services).
VENDOR_DOMAINS = ("abcfitness.com", "trainerize.com", "peerfit.com", "ashn.com", "silversneakers.com",
                  "myrewardstore.com", "texaspridedisposal.com", "crunch.com", "sebrands.com", "rfuenzalida.com",
                  "fontsquirrel.com", "fonts.com", "typekit.com", "adobe.com", "shopify.com", "wix.com",
                  "weebly.com", "hubspot.com", "mailchimp.com", "constantcontact.com", "zendesk.com")
# Context words that mark an address as the one that owns pool time.
RELEVANT_CTX = re.compile(r"aquatic|pool|swim|natator|recreation|facilit|rental|event|membership|lifestyle|program|book", re.I)
IMAGE_TAIL = re.compile(r"\.(png|jpe?g|gif|svg|webp|css|js)$", re.I)
TITLE_RX = re.compile(
    r"\b((?:Aquatics?|Pool|Swim|Facilit(?:y|ies)|Events?|Rentals?|Membership|General|Operations|Recreation|"
    r"Programs?|Front\s+Desk|Executive|Lifestyle|Community|Athletic|Club|Sales|Catering|Guest\s+Services?|"
    r"Property|Site|Office|Business)\s+(?:Director|Manager|Coordinator|Supervisor|Chair|Lead|Office|Desk|Team))\b"
    r"|\b(Director|Manager|Coordinator|Owner|President|Principal|Superintendent)\b", re.I)
NAME_RX = re.compile(r"^[A-Z][a-zA-Z'.-]+(?:\s+[A-Z][a-zA-Z'.-]+){1,2}$")

# Which inbox to write to first. Pool-specific beats rentals beats a named
# manager beats a generic front door. Anything unrecognised scores 1.
EMAIL_RANK = (
    (re.compile(r"aquatic|pool|swim|natator", re.I), 5),
    (re.compile(r"rental|rentals|event|events|booking|bookings|facilit|venue|part(y|ies)|lifestyle|program", re.I), 4),
    (re.compile(r"manager|director|gm\b|operations|ops|membership|recreation|coordinator|request|inquir|enquir", re.I), 3),
    (re.compile(r"^(info|contact|hello|office|frontdesk|front\.desk|admin|mail|reception|general|team|hi|ask)$", re.I), 2),
)


def rank_email(email: str) -> int:
    local = (email or "").split("@")[0]
    for rx, w in EMAIL_RANK:
        if rx.search(local):
            return w
    return 1


def _decode_cfemail(hexstr: str) -> Optional[str]:
    try:
        raw = bytes.fromhex(hexstr)
    except ValueError:
        return None
    if len(raw) < 2:
        return None
    key = raw[0]
    try:
        return bytes(b ^ key for b in raw[1:]).decode("utf-8")
    except UnicodeDecodeError:
        return None


def _strip_noise_html(html: str) -> str:
    """HTML without comments, styles and scripts (JSON-LD kept): those blocks
    carry font licences, analytics config and escaped JSON, not contacts."""
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<script(?![^>]*application/ld\+json)[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    return html


def _clean_email(e: str) -> Optional[str]:
    e = (e or "").strip().split("?")[0]
    e = re.sub(r"^(?:%[0-9A-Fa-f]{2}|\\?u00[0-9A-Fa-f]{2}|mailto:)+", "", e, flags=re.I)   # %20, \u003e, mailto:
    e = e.strip().strip(".,;:()<>[]\"'")
    if "@" not in e or e.count("@") != 1:
        return None
    local, domain = e.rsplit("@", 1)
    domain = domain.lower().rstrip(".")
    if not re.match(r"^[A-Za-z0-9]", local):
        return None
    if any(domain == v or domain.endswith("." + v) for v in VENDOR_DOMAINS):
        return None
    if IMAGE_TAIL.search(domain) or IMAGE_TAIL.search(local) or re.fullmatch(r"\dx(\.\w+)?", domain):
        return None
    if any(domain == j or domain.endswith("." + j) for j in JUNK_DOMAINS):
        return None
    if JUNK_LOCAL.match(local) or len(local) > 64 or "." not in domain:
        return None
    if re.fullmatch(r"[0-9a-f]{16,}", local):     # tracking hashes
        return None
    return f"{local}@{domain}"


def _context(text: str, needle: str, width: int = 140) -> str:
    if not needle:
        return ""
    i = text.lower().find(needle.lower())
    if i < 0:
        return ""
    a, b = max(0, i - width), min(len(text), i + len(needle) + width)
    return re.sub(r"\s+", " ", text[a:b]).strip()


GENERIC_LOCAL = re.compile(r"^(info|contact|hello|office|frontdesk|front\.desk|admin|mail|reception|general|team|hi|ask|sales|support|help)$", re.I)


def _title_before(text: str, needle: str, email: str, width: int = 70) -> Optional[str]:
    """Role title appearing just before the address on the page, if any."""
    if not needle or GENERIC_LOCAL.match((email or "").split("@")[0]):
        return None
    i = text.lower().find(needle.lower())
    if i < 0:
        return None
    before = text[max(0, i - width):i]
    hits = [m.group(0) for m in TITLE_RX.finditer(before)]
    return hits[-1].strip() if hits else None


def _site_domain(url: str) -> str:
    host = (urllib.parse.urlsplit(url or "").netloc or "").lower().removeprefix("www.")
    labels = host.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def find_emails(sections: list, site_url: Optional[str] = None, cap: int = 6, hints: Optional[set] = None) -> list:
    """Scan fetched sections for addresses. Returns contact dicts ready for
    swim_record_contact (full_name, role_title, email, phone, confidence,
    source_url, evidence_snippet, is_primary) ordered best first; at most one
    entry per address and at most `cap` per site (a staff directory of forty
    addresses is not forty leads).

    Order: inbox purpose (rank_email), then the facility's own domain over a
    third party, then pool/rental words near the address, then name known."""
    found: dict = {}
    own = _site_domain(site_url or (sections[0]["url"] if sections else ""))

    def add(email, url, snippet, name=None, title=None, how="text"):
        email = _clean_email(email)
        if not email:
            return
        key = email.lower()
        cand = {"full_name": name, "role_title": title, "email": email, "phone": None,
                "confidence": "verified", "source_url": url,
                "evidence_snippet": (snippet or f"{how}: {email}")[:400],
                "_ondomain": int(email.lower().endswith("@" + own) or email.lower().endswith("." + own)) if own else 0,
                "_relevant": int(bool(RELEVANT_CTX.search((snippet or "") + " " + (title or "")))),
                "_local": int(any(h in email.lower().split("@")[0].replace(".", "").replace("_", "").replace("-", "")
                                  for h in (hints or ())))}
        cur = found.get(key)
        if cur is None or ((name or title) and not (cur.get("full_name") or cur.get("role_title"))):
            found[key] = cand
        elif cand["_relevant"] and not cur["_relevant"]:
            cur["_relevant"] = 1

    for sec in sections:
        url, text = sec.get("url") or "", sec.get("text") or ""
        html = _strip_noise_html(sec.get("html") or "")
        # 1. mailto: links (anchor text may be a name)
        for m in re.finditer(r"<a\b[^>]*?href\s*=\s*([\"'])mailto:(.*?)\1[^>]*>(.*?)</a>", html, flags=re.S | re.I):
            email = htmllib.unescape(m.group(2)).split("?")[0]
            anchor = re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", m.group(3)))).strip()
            name = anchor if NAME_RX.match(anchor) and "@" not in anchor else None
            ctx = _context(text, email) or _context(text, anchor)
            title = _title_before(text, email, email) or _title_before(text, anchor, email)
            add(email, url, ctx or f'mailto link "{anchor}" -> {email}', name, title, "mailto")
        # 2. Cloudflare email protection
        for m in re.finditer(r"data-cfemail=\"([0-9a-fA-F]+)\"", html):
            dec = _decode_cfemail(m.group(1))
            if dec:
                add(dec, url, f"protected address on page, decoded: {dec}", None, None, "cfemail")
        # 3. plain addresses in the visible text
        for m in EMAIL_RX.finditer(text):
            ctx = _context(text, m.group(0))
            add(m.group(0), url, ctx, None, _title_before(text, m.group(0), m.group(0)), "text")
        # 4. plain addresses only in the HTML (e.g. JSON-LD "email": ...)
        for m in EMAIL_RX.finditer(html):
            if m.group(0).lower() in found:
                continue
            add(m.group(0), url, f"address in page markup: {m.group(0)}", None, None, "markup")
        # 4b. on-domain addresses in script config (location inboxes often live in JSON)
        if own:
            for sm in re.finditer(r"<script(?![^>]*application/ld\+json)[^>]*>(.*?)</script>", sec.get("html") or "", flags=re.S | re.I):
                for m in EMAIL_RX.finditer(sm.group(1)):
                    e = m.group(0)
                    if e.lower() in found or not (e.lower().endswith("@" + own) or e.lower().endswith("." + own)):
                        continue
                    add(e, url, f"address in page script config: {e}", None, None, "script")
        # 5. obfuscated forms
        for m in OBFUSCATED_RX.finditer(text):
            domain = re.sub(r"\s*(?:\[\s*dot\s*\]|\(\s*dot\s*\)|\{\s*dot\s*\})\s*", ".", m.group(2), flags=re.I)
            domain = re.sub(r"\s+", "", domain)
            add(f"{m.group(1)}@{domain}", url, _context(text, m.group(0)) or m.group(0), None, None, "obfuscated")

    # Purpose first (an aquatics inbox beats everything), then this location's own
    # inbox among equals (katyinfo@ on a franchise site), then own domain, then pool
    # words nearby, then a named person. Purpose stays ahead of the location hint
    # because name tokens can be brand words ("villa" matched a spa inbox once).
    out = sorted(found.values(), key=lambda c: (-rank_email(c["email"]), -c["_local"], -c["_ondomain"],
                                                 -c["_relevant"], not c.get("full_name"), c["email"].lower()))[:cap]
    for i, c in enumerate(out):
        c["is_primary"] = (i == 0)
        for k in ("_ondomain", "_relevant", "_local"):
            c.pop(k, None)
    return out
