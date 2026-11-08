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


def candidate_links(base_url: str, html: str, limit: int = MAX_EXTRA_PAGES) -> list:
    """Same-host links ranked by how likely they are to describe the pool.
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
        if SKIP_EXT.search(parts.path or ""):
            continue
        clean = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path or "/", "", ""))
        if clean.rstrip("/") == base_url.rstrip("/"):
            continue
        hay = f"{parts.path} {htmllib.unescape(anchor)}"
        score = 0
        for rx, w in LINK_HINTS:
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


def fetch_site(website: Optional[str], *, http_get: Callable = _requests_get,
               user_agent: str = DEFAULT_USER_AGENT, max_extra_pages: int = MAX_EXTRA_PAGES
               ) -> Tuple[Optional[dict], Optional[str]]:
    """Read a facility website. Returns (page, None) or (None, reason).

    page = {url, html: "", text, fixture: False, sections: [{url, title, text}],
            pages_fetched}
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
    sections.append({"url": site, "title": _page_title(home_html), "text": home_text})

    for link in candidate_links(site, home_html, limit=max_extra_pages + 2):
        if len(sections) > max_extra_pages or _key(link) in seen:
            continue
        seen.add(_key(link))
        if not robots_allows(link, http_get, user_agent):
            continue
        body = _grab(link)
        if body is None or body == "__not_html__":
            continue
        sections.append({"url": link, "title": _page_title(body), "text": html_to_text(body)[:PER_PAGE_CHARS]})

    # Pool-specific pages first in the joined text: extraction truncates from the
    # end, so the most informative material must not be what gets cut.
    sections.sort(key=lambda s: 0 if LINK_HINTS[0][0].search(
        (urllib.parse.urlsplit(s["url"]).path or "") + " " + s["title"]) else 1)
    joined = "\n\n".join(f"[{s['url']}]\n{s['text']}" for s in sections)[:TOTAL_CHARS]
    if not joined.strip():
        return None, EMPTY
    return {"url": site, "html": "", "text": joined, "fixture": False,
            "sections": sections, "pages_fetched": len(sections)}, None
