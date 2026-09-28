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
        src = Source(id=f"{self.prefix}{len(self.sources) + 1}", url=url, title=title or url,
                     kind=kind or classify(url)[0], text=text[: config.MAX_PAGE_CHARS])
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
            url = snippet_url(src.text, c.quote) if src.url.startswith("search://") else src.url
            out.append(Citation(source_id=src.id, url=url or src.url, quote=c.quote,
                                verified=quote_in_text(c.quote, src.text)))
        return out


def snippet_url(snippets: str, quote: str) -> str:
    """Search-snippet sources hold one result per line ending in '(url)'; return the URL of the
    line that contains the quote, so the citation points at the real page."""
    for line in snippets.splitlines():
        m = re.search(r"\((https?://[^)\s]+)\)\s*$", line)
        if m and quote_in_text(quote, line):
            return m.group(1)
    return ""


_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…|\[\.\.\.\])\s*")


def _norm(s: str) -> str:
    """Words only: punctuation and list bullets differ between a page and a faithful quote."""
    s = unicodedata.normalize("NFKC", s).lower().replace("’", "'").replace("'", "")
    s = re.sub(r"[^a-z0-9$%]+", " ", s)
    return s.strip()


def quote_in_text(quote: str, text: str, chunk_words: int = 6, threshold: float = 0.8) -> bool:
    """True if the quote appears in the text. Punctuation/case/bullets are ignored; an ellipsis
    splits the quote into parts that must each appear in order; otherwise ≥80% of 6-word chunks
    must appear (tolerates tiny edits, rejects invented quotes)."""
    t = _norm(text)
    parts = [_norm(x) for x in _ELLIPSIS.split(quote) if _norm(x)]
    if not parts or sum(len(x) for x in parts) < 12:
        return False
    pos, in_order = 0, True
    for part in parts:
        i = t.find(part, pos)
        if i < 0:
            in_order = False
            break
        pos = i + len(part)
    if in_order:
        return True
    words = " ".join(parts).split()
    if len(words) < chunk_words:
        return False
    chunks = [" ".join(words[i:i + chunk_words]) for i in range(0, len(words) - chunk_words + 1, chunk_words)]
    return sum(1 for c in chunks if c in t) / len(chunks) >= threshold
