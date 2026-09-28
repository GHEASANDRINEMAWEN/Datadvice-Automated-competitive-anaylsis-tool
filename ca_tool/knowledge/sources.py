"""Credible sources, from the Datadvise Competitive Intelligence Process (§4 Tools & Data Sources).

TODO: replace/extend with the official "Datadvise Credible Data Sources for Competitive
Analysis" list referenced in the PDD (§2.5) once it is provided.
"""
from urllib.parse import urlparse

# domain -> (category, priority 1=highest)
CREDIBLE_DOMAINS: dict[str, tuple[str, int]] = {
    # market perception / reviews
    "g2.com": ("review", 1),
    "capterra.com": ("review", 1),
    "trustpilot.com": ("review", 1),
    "getapp.com": ("review", 2),
    "softwareadvice.com": ("review", 2),
    "reddit.com": ("review", 2),
    "glassdoor.com": ("review", 2),
    # startup / funding
    "crunchbase.com": ("funding", 1),
    "pitchbook.com": ("funding", 1),
    "tracxn.com": ("funding", 1),
    "cbinsights.com": ("funding", 1),
    # company / people
    "linkedin.com": ("company", 1),
    # news / press
    "prnewswire.com": ("news", 1),
    "businesswire.com": ("news", 1),
    "globenewswire.com": ("news", 1),
    "techcrunch.com": ("news", 1),
    "reuters.com": ("news", 1),
    "bloomberg.com": ("news", 1),
    # analysts / market data
    "gartner.com": ("analyst", 1),
    "forrester.com": ("analyst", 1),
    "grandviewresearch.com": ("analyst", 2),
    "statista.com": ("analyst", 2),
    # tech stack / traffic
    "builtwith.com": ("tech", 1),
    "wappalyzer.com": ("tech", 1),
    "similarweb.com": ("tech", 1),
    "web.archive.org": ("tech", 2),
}

# domains that are rarely useful as evidence
LOW_VALUE_DOMAINS = {"pinterest.com", "facebook.com", "instagram.com", "tiktok.com", "quora.com"}

# credible sites that block automated page reads (verified 2026-09-28). Their search snippets are
# still used as evidence; fetching them only wastes the page budget.
NO_FETCH_SITES = {"g2", "capterra", "getapp", "trustpilot", "reddit", "crunchbase", "pitchbook"}


def site_name(url: str) -> str:
    """'www.capterra.co.uk' and 'capterra.ae' -> 'capterra' (one site, many country domains)."""
    parts = domain(url).split(".")
    while len(parts) > 1 and parts[-1] in {"com", "co", "org", "net", "io", "uk", "ae", "ca", "in", "au", "de", "fr", "es", "it", "nl", "ai"}:
        parts.pop()
    return parts[-1] if parts else ""


def fetchable(url: str) -> bool:
    return site_name(url) not in NO_FETCH_SITES


def domain(url: str) -> str:
    d = urlparse(url).netloc.lower()
    return d[4:] if d.startswith("www.") else d


def classify(url: str) -> tuple[str, int]:
    """Return (category, priority). Unknown domains get priority 3."""
    d = domain(url)
    for known, meta in CREDIBLE_DOMAINS.items():
        if d == known or d.endswith("." + known):
            return meta
    if any(d == x or d.endswith("." + x) for x in LOW_VALUE_DOMAINS):
        return ("low", 9)
    return ("web", 3)
