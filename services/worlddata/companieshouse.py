"""Companies House UK: registered-company facts, free with an API key.

Search endpoint (api.company-information.service.gov.uk) needs HTTP Basic
with a free key from developer.company-information.service.gov.uk. Without
COMPANIES_HOUSE_API_KEY every function raises CompaniesHouseError("not
configured") so the ingest script skips the source with a note instead of
failing. Parse functions stay pure and fixture-testable.
"""
from __future__ import annotations

import base64
import os
import urllib.parse
import urllib.request
from datetime import date
from typing import Any

from services.worlddata.http import TIMEOUT_SECONDS, USER_AGENT, WorldDataError

SOURCE = "companieshouse"
KIND_REGISTERED = "registered_company"
SEARCH_URL = "https://api.company-information.service.gov.uk/search/companies"


class CompaniesHouseError(WorldDataError):
    pass


def _api_key() -> str:
    key = (os.getenv("COMPANIES_HOUSE_API_KEY") or "").strip()
    if not key:
        raise CompaniesHouseError("COMPANIES_HOUSE_API_KEY is not configured")
    return key


def fetch_search(query: str, *, items_per_page: int = 20) -> dict[str, Any]:
    text = (query or "").strip()
    if not text:
        return {}
    credentials = base64.b64encode(f"{_api_key()}:".encode()).decode()
    url = f"{SEARCH_URL}?{urllib.parse.urlencode({'q': text, 'items_per_page': max(1, min(items_per_page, 100))})}"
    request = urllib.request.Request(
        url, headers={"Authorization": f"Basic {credentials}", "User-Agent": USER_AGENT,
                      "Accept": "application/json"}, method="GET")
    try:
        import json

        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
            return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        raise CompaniesHouseError(f"search failed: {exc}") from exc


def parse_search(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Pure parse of a search response -> world records."""
    records = []
    items = payload.get("items") if isinstance(payload, dict) else None
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        number = str(item.get("company_number") or "").strip()
        name = str(item.get("title") or "").strip()
        if not number or not name:
            continue
        records.append({
            "source": SOURCE, "kind": KIND_REGISTERED, "ref": number, "name": name,
            "data": {"company_number": number,
                     "company_status": item.get("company_status"),
                     "company_type": item.get("company_type"),
                     "date_of_creation": item.get("date_of_creation"),
                     "address": item.get("address") if isinstance(item.get("address"), dict) else None},
            "vintage": str(date.today()),
        })
    return records


def ingest(queries: list[str], *, items_per_page: int = 20) -> list[dict[str, Any]]:
    """Search each query. Raises CompaniesHouseError when unconfigured."""
    _api_key()
    records = []
    for query in queries:
        records.extend(parse_search(fetch_search(query, items_per_page=items_per_page)))
    return records
