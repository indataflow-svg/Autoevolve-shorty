"""Common Crawl web presence: how long a company domain has been visible.

Source: index.commoncrawl.org — free, no key. The collinfo endpoint names
the latest crawl; the index API returns newline-delimited captures per
domain. Signal, not content: first/last seen timestamps + capture count
answer "is this company real and alive on the web" without fetching pages.
"""
from __future__ import annotations

import json
from typing import Any

from services.worlddata.http import WorldDataError, get_json, get_text_lines

SOURCE = "commoncrawl"
KIND_PRESENCE = "web_presence"
COLLINFO_URL = "https://index.commoncrawl.org/collinfo.json"


def latest_crawl_id() -> str:
    return recent_crawl_ids(limit=1)[0]


def recent_crawl_ids(limit: int = 3) -> list[str]:
    """Newest crawl ids by end date. The newest index is sometimes not
    queryable yet, so ingest walks this list until one answers."""
    colls = get_json(COLLINFO_URL)
    if not isinstance(colls, list):
        raise WorldDataError("collinfo.json did not parse as a list")
    mains = [c for c in colls
             if isinstance(c, dict) and str(c.get("id") or "").startswith("CC-MAIN")]
    if not mains:
        raise WorldDataError("no CC-MAIN crawl listed")
    ordered = sorted(mains, key=lambda c: str(c.get("to") or ""))
    return [str(c["id"]) for c in ordered[-max(1, limit):]][::-1]


def fetch_captures(domain: str, crawl_id: str) -> list[dict[str, Any]]:
    import urllib.parse

    domain = (domain or "").strip().lower().split("/")[0]
    if not domain:
        return []
    # The index needs a path wildcard: a bare domain 404s even when seen.
    url = (f"https://index.commoncrawl.org/{crawl_id}-index?"
           f"{urllib.parse.urlencode({'url': domain + '/*', 'output': 'json'})}")
    captures = []
    for line in get_text_lines(url):
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            captures.append(item)
    return captures


def parse_presence(domain: str, crawl_id: str, captures: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pure fold of captures -> one world record. None when never seen."""
    stamps = sorted(c.get("timestamp") or "" for c in captures if isinstance(c, dict) and c.get("timestamp"))
    if not stamps:
        return None
    mimes: dict[str, int] = {}
    for item in captures:
        mime = str(item.get("mime") or "unknown").split(";")[0]
        mimes[mime] = mimes.get(mime, 0) + 1
    return {
        "source": SOURCE, "kind": KIND_PRESENCE, "ref": domain.lower(), "name": domain.lower(),
        "data": {"captures": len(captures), "first_seen": stamps[0], "last_seen": stamps[-1],
                 "mime_mix": sorted(mimes.items(), key=lambda kv: -kv[1])[:5]},
        "vintage": crawl_id,
    }


def ingest(domains: list[str], *, crawl_id: str = "") -> list[dict[str, Any]]:
    """Presence records for domains seen in a recent crawl. Unseen -> skipped.

    An explicit crawl_id pins one index; otherwise the newest queryable
    crawl wins (the newest listed index is sometimes not deployed yet).
    """
    from services.worlddata.http import WorldDataError

    crawls = [crawl_id.strip()] if crawl_id.strip() else recent_crawl_ids(limit=3)
    records = []
    for domain in domains:
        for crawl in crawls:
            try:
                record = parse_presence(domain, crawl, fetch_captures(domain, crawl))
            except WorldDataError:
                continue
            if record is not None:
                records.append(record)
            break
    return records
