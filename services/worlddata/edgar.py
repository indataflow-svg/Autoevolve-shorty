"""SEC EDGAR bulk company facts: every US-listed company, free, no key.

Source: https://www.sec.gov/files/company_tickers.json — one JSON object
mapping index -> {cik_str, ticker, title} for ~10k filers. Per-company
submissions (forms history) live at data.sec.gov/submissions/CIK{cik}.json
and are fetched on demand, never bulk (fair-access 10 req/s).

Transport note: SEC's edge filters Python TLS fingerprints (urllib and
httpx both 403 as of 2026-10; curl passes), so the bulk fetch shells out
to curl. Absent curl, or any fetch failure, raises WorldDataError and the
ingest script skips the source with a note.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from typing import Any

from services.worlddata.http import USER_AGENT, WorldDataError

SOURCE = "edgar"
KIND_LISTED = "listed_company"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def fetch_tickers() -> dict[str, dict[str, str]]:
    curl = shutil.which("curl")
    if not curl:
        raise WorldDataError("curl is required for SEC EDGAR fetch and was not found")
    try:
        completed = subprocess.run(
            [curl, "-sS", "--max-time", "120", "-A", USER_AGENT,
             "-H", "Accept: application/json", TICKERS_URL],
            capture_output=True, timeout=150, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorldDataError(f"curl SEC fetch failed: {exc}") from exc
    if completed.returncode != 0:
        raise WorldDataError(f"curl SEC fetch failed: {completed.stderr.decode()[:200]}")
    try:
        payload = json.loads(completed.stdout.decode("utf-8"))
    except ValueError as exc:
        raise WorldDataError(f"company_tickers.json did not parse: {exc}") from exc
    if not isinstance(payload, dict):
        raise WorldDataError("company_tickers.json did not parse as an object")
    return payload


def parse_tickers(payload: dict[str, Any], *, limit: int = 0) -> list[dict[str, Any]]:
    """Pure parse of the tickers object -> world records. Fixture-testable."""
    records = []
    items = list(payload.values()) if isinstance(payload, dict) else []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        cik = str(entry.get("cik_str") or "").strip().lstrip("0")
        name = str(entry.get("title") or "").strip()
        ticker = str(entry.get("ticker") or "").strip()
        if not cik or not name:
            continue
        records.append({
            "source": SOURCE, "kind": KIND_LISTED, "ref": cik, "name": name,
            "data": {"cik": cik, "ticker": ticker or None, "exchange": None},
            "vintage": str(date.today()),
        })
        if limit and len(records) >= limit:
            break
    return records


def ingest(*, limit: int = 0) -> list[dict[str, Any]]:
    """Fetch + parse. Vintage is the fetch date (bulk file has no version)."""
    return parse_tickers(fetch_tickers(), limit=limit)
