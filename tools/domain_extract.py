"""Domain intelligence: add a domain -> extract brand context.

Chain: trafilatura (clean article text) -> existing bs4 fetch fallback.
crawl4ai / browser-use promotion lands here behind flags when needed.

Writes NOTHING live: callers save the returned pack to
engines/g1/knowledge/_drafts/{brand}/ only after human approve.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx

from tools.research import HEADERS, fetch_page

try:
    import trafilatura

    _HAS_TRAFILATURA = True
except Exception:
    trafilatura = None  # type: ignore
    _HAS_TRAFILATURA = False


KEY_PAGE_HINTS = ("pricing", "about", "contact", "blog", "product", "how-it-works")

MAX_PAGES = 12


def normalize_domain_input(value: str) -> str:
    """Accept bare domains, URLs, www. prefixes -> canonical https URL + domain."""
    raw = (value or "").strip().lower()
    if not raw:
        raise ValueError("empty domain")
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lstrip("www.")
    if not host or "." not in host:
        raise ValueError(f"not a valid domain: {value}")
    return f"https://{host}", host


def _trafilatura_text(html: str, url: str) -> str:
    if not _HAS_TRAFILATURA:
        return ""
    try:
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            output_format="markdown",
        )
        return (extracted or "").strip()
    except Exception:
        return ""


async def fetch_domain_page(client: httpx.AsyncClient, url: str) -> dict:
    """Fetch one page with trafilatura-cleaned text, bs4 fallback."""
    result = await fetch_page(url)
    if not result.get("ok"):
        return result
    html = ""
    try:
        response = await client.get(url, headers=HEADERS, timeout=30)
        if response.status_code < 400 and "html" in response.headers.get("content-type", ""):
            html = response.text
    except Exception:
        html = ""
    clean = _trafilatura_text(html, url) if html else ""
    if clean:
        result["clean_text"] = clean[:12000]
        result["extractor"] = "trafilatura"
    else:
        result["clean_text"] = (result.get("text") or "")[:12000]
        result["extractor"] = "bs4-fallback"
    return result


def discover_key_urls(homepage_html: str, base_url: str) -> list[str]:
    """Find pricing/about/contact/blog/product links from homepage HTML."""
    from bs4 import BeautifulSoup

    found: list[str] = []
    try:
        soup = BeautifulSoup(homepage_html or "", "html.parser")
        for anchor in soup.find_all("a", href=True):
            href = str(anchor["href"])
            text = (anchor.get_text() or "").lower()
            absolute = urljoin(base_url + "/", href)
            parsed = urlparse(absolute)
            base_host = urlparse(base_url).netloc
            if parsed.netloc != base_host:
                continue
            path = parsed.path.lower()
            if any(hint in path or hint in text for hint in KEY_PAGE_HINTS):
                if absolute not in found:
                    found.append(absolute)
    except Exception:
        pass
    return found[: MAX_PAGES - 1]


async def extract_domain(domain_input: str, max_pages: int = MAX_PAGES) -> dict:
    """Crawl homepage + key subpages, return evidence pack (no writes)."""
    base_url, host = normalize_domain_input(domain_input)
    pages: list[dict] = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        home = await fetch_domain_page(client, base_url)
        pages.append({"url": base_url, **home})
        key_urls: list[str] = []
        try:
            resp = await client.get(base_url, headers=HEADERS, timeout=30)
            if resp.status_code < 400:
                key_urls = discover_key_urls(resp.text, base_url)
        except Exception:
            key_urls = []
        for url in key_urls[: max(0, max_pages - 1)]:
            pages.append({"url": url, **await fetch_domain_page(client, url)})
    ok_pages = [p for p in pages if p.get("ok")]
    return {
        "domain": host,
        "base_url": base_url,
        "pages_crawled": len(pages),
        "pages_ok": len(ok_pages),
        "extractor": "trafilatura" if _HAS_TRAFILATURA else "bs4-only",
        "pages": [
            {
                "url": p.get("url"),
                "title": p.get("title", ""),
                "ok": p.get("ok", False),
                "extractor": p.get("extractor", ""),
                "text": (p.get("clean_text") or p.get("text") or "")[:6000],
                "error": p.get("error"),
            }
            for p in pages
        ],
    }


BRAND_PACK_SYSTEM = """You structure crawled website evidence into a draft brand pack.
Rules: use ONLY the supplied page texts; never invent pricing, trial length, or
customer claims. Mark anything uncertain under unknowns. Output strict JSON with
keys: brand, positioning, voice[], offers{plans[], trial, contract, pricing_model},
icps{primary[{title, pains[]}]}, trigger_question, ctas{awareness, trial}, unknowns[]."""


async def structure_brand_pack(evidence: dict, model: str = "auto/best-reasoning") -> dict:
    """Use the OmniRoute gateway to structure evidence -> brand pack JSON."""
    import json

    from tools.omniroute_client import complete_json
    from core.models import ROUTES

    pages_text = "\n\n".join(
        f"URL: {p['url']}\nTITLE: {p.get('title', '')}\n{p.get('text', '')[:4000]}"
        for p in evidence.get("pages", [])
        if p.get("ok")
    )[:20000]
    user = f"Domain: {evidence.get('domain')}\n\n{pages_text}"
    chosen = ROUTES.get("reasoning", model)
    try:
        return complete_json(chosen, BRAND_PACK_SYSTEM, user, timeout=120)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "domain": evidence.get("domain")}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "brand"
