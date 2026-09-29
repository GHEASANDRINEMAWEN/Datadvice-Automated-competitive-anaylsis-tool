"""Source registry: numbers fetched pages [S1], [S2]... so the AI can cite them,
and verifies every quote the AI returns against the fetched text."""
from __future__ import annotations

import re
import unicodedata

from .. import config
from ..knowledge.sources import classify
from ..models import Citation, Source


class Corpus:
    def __init__(self, prefix: str = "S", sources: list[Source] | None = None):
        self.prefix = prefix
        self.sources: list[Source] = list(sources or [])

    def add(self, url: str, title: str, text: str, kind: str = "") -> Source | None:
        text = (text or "").strip()
        if not text or any(s.url == url for s in self.sources):
            return None
        kind = kind or classify(url)[0]
        # a search-results source bundles many hits; the per-page cap would cut it to a handful
        limit = config.MAX_SNIPPET_CHARS if kind == "search" else config.MAX_PAGE_CHARS
        src = Source(id=f"{self.prefix}{len(self.sources) + 1}", url=url, title=title or url, kind=kind, text=text[:limit])
        self.sources.append(src)
        return src

    def get(self, sid: str) -> Source | None:
        return next((s for s in self.sources if s.id == sid), None)

    def render(self, max_chars: int | None = None) -> str:
        """Prompt block. Sources are added in priority order, so truncation drops the weakest."""
        budget = max_chars or config.MAX_CORPUS_CHARS
        parts, used = [], 0
        for s in self.sources:
            block = f"[{s.id}] ({s.kind}) {s.title}\nURL: {s.url}\n{s.text}\n"
            if used + len(block) > budget:
                block = block[: max(0, budget - used)]
            if not block:
                break
            parts.append(block)
            used += len(block)
        return "\n---\n".join(parts)

    def resolve(self, cites: list[Citation]) -> list[Citation]:
        """Fill URLs, drop citations to unknown sources, and verify quotes."""
        out = []
        for c in cites:
            src = self.get(c.source_id.strip("[] "))
            if not src:
                continue
            if src.url.startswith("search://"):
                # a search bundle holds many unrelated results: the quote must sit inside ONE of
                # them (no stitching across results), and the citation points at that result's page
                url = snippet_url(src.text, c.quote)
                ok = bool(url)
            else:
                url, ok = src.url, quote_in_text(c.quote, src.text)
            out.append(Citation(source_id=src.id, url=url or src.url, quote=c.quote, verified=ok))
        return out


def verify(src: Source | None, quote: str) -> bool:
    """The single rule for 'is this quote really in this source?' (used live and on re-check)."""
    if not src:
        return False
    if src.url.startswith("search://"):
        return bool(snippet_url(src.text, quote))
    return quote_in_text(quote, src.text)


def snippet_url(snippets: str, quote: str) -> str:
    """Search-snippet sources hold one result per line ending in '(url)'; return the URL of the
    line that contains the quote, so the citation points at the real page."""
    for line in snippets.splitlines():
        i = line.rfind(" (http")
        if i < 0 or not line.rstrip().endswith(")"):
            continue
        url = line[i + 2: line.rstrip().rfind(")")]
        if quote_in_text(quote, line[:i]):
            return url
    return ""


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[float]:
    """Significant figures in a text: years, counts, prices ('$9.00' == '9', '3,601' == 3601).
    Single digits are ignored (too common to be evidence)."""
    out = set()
    for m in _NUM.findall(text or ""):
        try:
            v = float(m.replace(",", ""))
        except ValueError:
            continue
        if v >= 10:
            out.add(v)
    return out


def numbers_supported(value: str, quotes: list[str]) -> bool | None:
    """Does at least one figure in the value appear in the quoted evidence? None when the value
    has no figures. Catches a real quote that doesn't back the number (e.g. a founding year taken
    from the model's memory next to a quote that never mentions it)."""
    vals = _numbers(value)
    if not vals:
        return None
    quoted = set().union(*(_numbers(q) for q in quotes)) if quotes else set()
    return bool(vals & quoted)


_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…|\[\.\.\.\])\s*")


def _norm(s: str) -> str:
    """Words only: punctuation and list bullets differ between a page and a faithful quote."""
    s = unicodedata.normalize("NFKC", s).lower().replace("’", "'").replace("'", "")
    s = re.sub(r"[^a-z0-9$%]+", " ", s)
    return s.strip()


MIN_PART_WORDS = 3      # a quote, and each "…"-separated part of it, must be a real phrase
MAX_GAP = 250           # "…" may skip at most this much text: parts must come from the same passage


def quote_in_text(quote: str, text: str) -> bool:
    """True if the quote appears in the text word for word (case, punctuation and list bullets
    ignored; whole words only). No word may differ: tolerating even one edit let "does not include"
    pass for "does include" and "$50 million" for "$5 million". An ellipsis splits the quote into
    parts that must appear in order, each within MAX_GAP characters of the previous one. A part
    needs ≥3 words, or ≥2 when it carries a figure ("founded 2011")."""
    t = f" {_norm(text)} "
    parts = [_norm(x) for x in _ELLIPSIS.split(quote) if _norm(x)]
    has_fig = lambda x: bool(re.search(r"\d{2,}", x))
    if not parts or any(len(p.split()) < (2 if has_fig(p) else MIN_PART_WORDS) for p in parts):
        return False

    def place(k: int, lo: int, hi: int) -> bool:
        needle = f" {parts[k]} "
        i = t.find(needle, lo)
        while i >= 0 and i <= hi:
            end = i + len(needle) - 1
            if k == len(parts) - 1 or place(k + 1, end, end + MAX_GAP):
                return True
            i = t.find(needle, i + 1)
        return False

    return place(0, 0, len(t))
