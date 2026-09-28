"""Search & scrape layer. The AI never browses: it only reads pages fetched here."""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
import trafilatura
from bs4 import BeautifulSoup

from .. import config
from ..knowledge.sources import classify, domain

log = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str


def search(query: str, max_results: int = 8) -> list[SearchHit]:
    """Web search (DuckDuckGo via ddgs). Returns [] on failure rather than raising."""
    from ddgs import DDGS
    for attempt in range(3):
        try:
            rows = DDGS().text(query, max_results=max_results) or []
            return [SearchHit(r.get("title", ""), r.get("href", ""), r.get("body", "")) for r in rows if r.get("href")]
        except Exception as e:  # ddgs raises on rate limit / no results
            if "no results" in str(e).lower():
                return []  # a genuine empty result: retrying won't change it
            log.warning("search failed (%s): %s", query, e)
            time.sleep(2 * (attempt + 1))
    return []


@dataclass
class Page:
    url: str
    title: str
    text: str
    links: list[tuple[str, str]]   # (anchor text, absolute url)


def _get(url: str) -> tuple[str, str] | None:
    """(final_url, html) or None. Uses a client that presents a real browser's TLS fingerprint
    (many directory/review sites 403 plain scripted requests), falling back to requests."""
    try:
        import primp
        # profiles in order of how often they pass bot checks (measured 2026-09-28)
        for profile in ("firefox", "safari", "chrome"):
            r = primp.Client(impersonate=profile, timeout=config.HTTP_TIMEOUT, follow_redirects=True).get(url)
            if r.status_code in (403, 429, 503):
                continue  # refused this browser profile; try the next
            if r.status_code < 400 and "html" in r.headers.get("content-type", "html"):
                return str(r.url), r.text
            break
    except Exception as e:  # primp missing or network error: try the plain client
        log.info("browser-like fetch failed %s: %s", url, e)
    try:
        r = requests.get(url, timeout=config.HTTP_TIMEOUT, headers={"User-Agent": UA, "Accept-Language": "en"})
        if r.status_code < 400 and "html" in r.headers.get("content-type", "html"):
            return r.url, r.text
    except requests.RequestException as e:
        log.info("fetch failed %s: %s", url, e)
    return None


def fetch(url: str, max_chars: int | None = None) -> Page | None:
    max_chars = max_chars or config.MAX_PAGE_CHARS
    got = _get(url)
    if not got:
        return None
    final_url, html = got
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    text = trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True) or ""
    if len(text) < 200:  # JS-heavy pages: fall back to visible text
        for t in soup(["script", "style", "noscript"]):
            t.decompose()
        text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(final_url, a["href"]).split("#")[0]
        if href.startswith("http"):
            links.append((a.get_text(" ", strip=True)[:80], href))
    return Page(url=final_url, title=title, text=text[:max_chars], links=links)


# pages worth reading on a competitor's own site (PDD step 6)
KEY_PAGE_PATTERNS = {
    "about": r"about|company|who-we-are|our-story",
    "pricing": r"pricing|plans|price",
    "product": r"product|features|platform|solutions?",
    "customers": r"customers|case-stud|success|testimonials",
    "partners": r"partners?|integrations?|marketplace",
    "news": r"news|press|blog|newsroom",
    "careers": r"careers|jobs",
}


def key_pages(home: Page, limit_per_kind: int = 1) -> dict[str, str]:
    """Pick the About/Pricing/Product/... pages linked from the homepage (same site only)."""
    site = domain(home.url)
    found: dict[str, str] = {}
    for kind, pat in KEY_PAGE_PATTERNS.items():
        for text, href in home.links:
            if domain(href) != site or href.rstrip("/") == home.url.rstrip("/"):
                continue
            path = urlparse(href).path.lower()
            if re.search(pat, path) or re.search(pat, text.lower()):
                found.setdefault(kind, href)
                break
    return found


# standard paths tried when a JS-rendered homepage exposes no links
GUESS_PATHS = {
    "about": ["/about", "/about-us", "/company"],
    "pricing": ["/pricing", "/plans"],
    "product": ["/features", "/product", "/platform"],
    "customers": ["/customers", "/case-studies"],
    "partners": ["/partners", "/integrations"],
    "news": ["/news", "/press", "/newsroom"],
    "careers": ["/careers", "/jobs"],
}


def guessed_pages(home_url: str, missing: list[str]) -> list[tuple[str, str]]:
    root = f"{urlparse(home_url).scheme}://{urlparse(home_url).netloc}"
    return [(kind, root + path) for kind in missing for path in GUESS_PATHS.get(kind, [])]


def rank_hits(hits: list[SearchHit]) -> list[SearchHit]:
    """Credible-source list first, low-value domains dropped, duplicates removed."""
    seen, out = set(), []
    for h in hits:
        if h.url in seen:
            continue
        seen.add(h.url)
        if classify(h.url)[1] < 9:
            out.append(h)
    return sorted(out, key=lambda h: classify(h.url)[1])


def mentions(text: str, name: str) -> bool:
    """Does the page mention the company? Ignores case, spaces and punctuation
    ("EventDiagram" matches "Event Diagram" and "eventdiagram.com")."""
    squash = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
    key = squash(name.split("(")[0])
    first = squash(name.split()[0]) if name.split() else ""
    body = squash(text)
    return bool(key) and (key in body or (len(first) >= 5 and first in body))
