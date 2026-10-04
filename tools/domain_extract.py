"""Domain intelligence: add a domain -> extract brand context.

Chain: trafilatura (clean article text) -> existing bs4 fetch fallback.
crawl4ai / browser-use promotion lands here behind flags when needed.

Writes NOTHING live: callers save the returned pack to
engines/g1/knowledge/_drafts/{brand}/ only after human approve.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from tools.research import HEADERS

try:
    import trafilatura

    _HAS_TRAFILATURA = True
except Exception:
    trafilatura = None  # type: ignore
    _HAS_TRAFILATURA = False


KEY_PAGE_HINTS = ("pricing", "about", "contact", "blog", "product", "how-it-works")

MAX_PAGES = 12
MAX_PAGE_BYTES = 512_000
MAX_REDIRECTS = 3
PAGE_TIMEOUT_SECONDS = 12


class WebsiteUnavailableError(RuntimeError):
    """The website could not be reached, but the URL itself is safe to query."""


def normalize_domain_input(value: str) -> tuple[str, str]:
    """Accept bare domains or HTTP(S) URLs and return their site root and domain."""
    raw = (value or "").strip()
    if not raw:
        raise ValueError("empty domain")
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ValueError("website must be a public HTTP(S) URL without credentials")
    if parsed.port not in {None, 80, 443} or not host or len(host) > 253:
        raise ValueError("website must use a public domain on a standard port")
    if host.startswith("www."):
        host = host[4:]
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("website must use a public domain, not an IP address")
    if "." not in host or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split(".")):
        raise ValueError("website must use a valid public domain")
    if host.endswith((".local", ".localhost", ".internal", ".test", ".invalid", ".example")):
        raise ValueError("website must use a public domain")
    return f"{parsed.scheme}://{host}", host


def _validate_public_host(host: str) -> None:
    """Reject local/private DNS answers before each website request."""
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise WebsiteUnavailableError(f"website domain could not be resolved: {host}") from exc
    if not addresses:
        raise WebsiteUnavailableError(f"website domain could not be resolved: {host}")
    if any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("website resolves to a non-public address")


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


async def fetch_domain_page(client: httpx.AsyncClient, url: str, base_host: str) -> dict:
    """Fetch bounded public HTML, checking every redirect before following it."""
    current = url
    html = ""
    try:
        for _ in range(MAX_REDIRECTS + 1):
            parsed = urlparse(current)
            if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
                raise ValueError("website redirect is not a public HTTP(S) URL")
            host = (parsed.hostname or "").lower().rstrip(".")
            if host not in {base_host, f"www.{base_host}"}:
                raise ValueError("website redirected outside its domain")
            _validate_public_host(host)
            async with client.stream("GET", current, headers=HEADERS) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("website redirect has no location")
                    current = urljoin(current, location)
                    continue
                if response.status_code >= 400:
                    return {"ok": False, "url": current, "error": f"HTTP {response.status_code}"}
                content_type = response.headers.get("content-type", "").lower()
                if content_type and not any(kind in content_type for kind in ("text/html", "application/xhtml+xml")):
                    raise ValueError("website page is not HTML")
                if int(response.headers.get("content-length", "0") or "0") > MAX_PAGE_BYTES:
                    raise ValueError("website page exceeds fetch limit")
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > MAX_PAGE_BYTES:
                        raise ValueError("website page exceeds fetch limit")
                html = chunks.decode(response.encoding or "utf-8", errors="replace")
                break
        else:
            raise ValueError("website exceeded redirect limit")
    except (httpx.HTTPError, ValueError, WebsiteUnavailableError) as exc:
        return {"ok": False, "url": current, "error": str(exc)}
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    description_tag = soup.select_one('meta[name="description"], meta[property="og:description"]')
    site_name_tag = soup.select_one('meta[property="og:site_name"]')
    description = (description_tag.get("content") or "").strip() if description_tag else ""
    site_name = (site_name_tag.get("content") or "").strip() if site_name_tag else ""
    clean = _trafilatura_text(html, current)
    if not clean:
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg"]):
            element.decompose()
        clean = soup.get_text(" ", strip=True)
    return {
        "ok": bool(clean or description), "url": current, "title": title,
        "description": description[:1000], "site_name": site_name[:120],
        "text": clean[:6000], "extractor": "trafilatura" if _HAS_TRAFILATURA else "bs4-fallback",
        "_html": html,
    }


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
            if parsed.netloc not in {base_host, base_host.removeprefix("www."), f"www.{base_host.removeprefix('www.')}"}:
                continue
            path = parsed.path.lower()
            if any(hint in path or hint in text for hint in KEY_PAGE_HINTS):
                if absolute not in found:
                    found.append(absolute)
    except Exception:
        pass
    return found[: MAX_PAGES - 1]


async def extract_domain(domain_input: str, max_pages: int = MAX_PAGES, *, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """Crawl homepage + key subpages, return evidence pack (no writes)."""
    base_url, host = normalize_domain_input(domain_input)
    _validate_public_host(host)
    pages: list[dict] = []
    page_limit = min(max(max_pages, 1), MAX_PAGES)
    async with httpx.AsyncClient(follow_redirects=False, timeout=PAGE_TIMEOUT_SECONDS, trust_env=False, transport=transport) as client:
        home = await fetch_domain_page(client, base_url, host)
        pages.append({"url": base_url, **home})
        key_urls = discover_key_urls(home.get("_html", ""), home.get("url", base_url)) if home.get("ok") else []
        for url in key_urls[: page_limit - 1]:
            pages.append({"url": url, **await fetch_domain_page(client, url, host)})
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
                "description": p.get("description", ""),
                "site_name": p.get("site_name", ""),
                "ok": p.get("ok", False),
                "extractor": p.get("extractor", ""),
                "text": (p.get("clean_text") or p.get("text") or "")[:6000],
                "error": p.get("error"),
            }
            for p in pages
        ],
    }


def company_profile_from_evidence(evidence: dict, supplied_name: str) -> dict | None:
    """Build a conservative onboarding draft from observable website text."""
    pages = [page for page in evidence.get("pages", []) if page.get("ok")]
    if not pages:
        return None
    description = ""
    source_url = ""
    for page in pages:
        candidate = " ".join(str(page.get("description") or "").split())
        if len(candidate) < 30:
            for line in str(page.get("text") or "").splitlines():
                candidate = " ".join(line.lstrip("# ").split())
                if 40 <= len(candidate) <= 600:
                    break
        if len(candidate) >= 30:
            description = candidate[:600]
            source_url = str(page.get("url") or "")
            break
    if not description:
        return None
    site_name = str(pages[0].get("site_name") or "").strip()
    name = site_name or supplied_name
    sources = [{"field": "description", "url": source_url}]
    if site_name:
        sources.insert(0, {"field": "name", "url": str(pages[0].get("url") or "")})
    return {
        "name": name,
        "domain": evidence["domain"],
        "website": evidence["base_url"],
        "description": description,
        "industry": None,
        "specialties": [],
        "signals": {"summary_line": description},
        "sources": sources,
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
