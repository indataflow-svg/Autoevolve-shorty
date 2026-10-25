from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class OpenCorporatesError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        self.status = status
        super().__init__(message)


#: Country name (lowercase) -> OpenCorporates jurisdiction code. Only entries
#: we are sure about: a wrong code verifies the wrong registry, which is
#: worse than skipping verification. US companies live under state
#: jurisdictions (us_ca, us_de, ...), so plain "united states" is
#: deliberately absent — verification stays silent instead of guessing.
COUNTRY_JURISDICTIONS = {
    "kenya": "ke",
    "uganda": "ug",
    "tanzania": "tz",
    "rwanda": "rw",
    "burundi": "bi",
    "ethiopia": "et",
    "united kingdom": "gb",
    "ireland": "ie",
    "germany": "de",
    "france": "fr",
    "netherlands": "nl",
    "united arab emirates": "ae",
    "saudi arabia": "sa",
    "south africa": "za",
    "nigeria": "ng",
    "ghana": "gh",
    "egypt": "eg",
    "india": "in",
    "singapore": "sg",
    "australia": "au",
    "canada": "ca",
}


def jurisdiction_for_country(country: str | None) -> str | None:
    """Map a free-text country to an OpenCorporates jurisdiction code.

    Returns None when unsure — callers must skip verification rather than
    search the wrong registry.
    """
    return COUNTRY_JURISDICTIONS.get(str(country or "").strip().lower())


def normalize_company_name(value: Any) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


class OpenCorporatesClient:
    """OpenCorporates company search (registry verification, not discovery).

    Needs any API token, including the free plan: since 2026 every v0.4
    endpoint 401s without ``api_token``. Set OPENCORPORATES_API_KEY once;
    there are no per-call credits to track, only the plan quota.
    """

    def __init__(self, api_key: str | None = None, base_url: str = "https://api.opencorporates.com/v0.4"):
        self.api_key = api_key or os.getenv("OPENCORPORATES_API_KEY", "").strip()
        if not self.api_key:
            raise OpenCorporatesError(
                "OPENCORPORATES_API_KEY is not configured (any plan works, "
                "including the free one — sign up at opencorporates.com)"
            )
        self.base_url = base_url.rstrip("/")

    def _request(self, endpoint: str, *, query: dict[str, Any] | None = None) -> dict:
        params = dict(query or {})
        params["api_token"] = self.api_key
        url = f"{self.base_url}/{endpoint.lstrip('/')}?{urllib.parse.urlencode(params, doseq=True)}"
        request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise OpenCorporatesError("OpenCorporates rejected the API token", 401) from exc
            if exc.code == 403:
                raise OpenCorporatesError("OpenCorporates quota exceeded", 403) from exc
            if exc.code == 404:
                return {}
            raise OpenCorporatesError(f"OpenCorporates request failed: HTTP {exc.code}", exc.code) from exc
        except urllib.error.URLError as exc:
            raise OpenCorporatesError(f"OpenCorporates request failed: {exc}") from exc

    def search_companies(self, name: str, *, jurisdiction: str | None = None, inactive: bool = False) -> list[dict]:
        """Raw registry hits for a company name, each with name/number/jurisdiction."""
        query: dict[str, Any] = {"q": name.strip(), "normalize": "true"}
        if jurisdiction:
            query["jurisdiction_code"] = jurisdiction
        if inactive:
            query["inactive"] = "true"
        payload = self._request("companies/search", query=query)
        results = payload.get("results") if isinstance(payload, dict) else None
        items = results.get("companies") if isinstance(results, dict) else None
        companies = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            company = item.get("company") if isinstance(item.get("company"), dict) else item
            companies.append({
                "name": str(company.get("name") or ""),
                "company_number": str(company.get("company_number") or ""),
                "jurisdiction_code": str(company.get("jurisdiction_code") or ""),
                "company_type": company.get("company_type"),
                "inactive": bool(company.get("inactive")),
            })
        return companies

    def verify_company(self, name: str, *, jurisdiction: str | None = None) -> dict | None:
        """Confirm a candidate exists in the registry under that jurisdiction.

        Matching is strict on purpose: the normalized registry name must equal
        the normalized candidate name (OC already matches loosely server-side,
        so anything looser here would corroborate near-misses). Returns the
        registry identity or None — never raises for "not found".
        """
        wanted = normalize_company_name(name)
        if not wanted:
            return None
        for hit in self.search_companies(name, jurisdiction=jurisdiction):
            if normalize_company_name(hit.get("name")) != wanted:
                continue
            if jurisdiction and hit.get("jurisdiction_code") and hit["jurisdiction_code"] != jurisdiction:
                continue
            return hit
        return None
