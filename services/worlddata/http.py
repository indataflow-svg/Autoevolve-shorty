"""Shared HTTP for world-data connectors: stdlib only, short timeouts.

World sources are free but rate-sensitive. SEC fair-access (10 req/s) also
requires a contact token inside the User-Agent and 403s without one:
WORLDDATA_CONTACT sets your real contact address (contact@example.com is
the reserved placeholder default — replace it in production). The full UA
is overridable via WORLDDATA_USER_AGENT. Every connector makes as few
requests as possible (bulk files over per-record calls).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

USER_AGENT = os.getenv(
    "WORLDDATA_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) CompanyCore/1.2"
    f" (world-data ingest; {os.getenv('WORLDDATA_CONTACT', 'contact@example.com')})",
)
TIMEOUT_SECONDS = 30


class WorldDataError(RuntimeError):
    pass


def get_json(url: str, *, timeout: int = TIMEOUT_SECONDS) -> Any:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, method="GET")
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            if exc.code in {500, 502, 503, 504} and attempt == 0:
                time.sleep(1)
                continue
            raise WorldDataError(f"GET {url} status={exc.code}") from exc
        except (TimeoutError, urllib.error.URLError, ValueError) as exc:
            raise WorldDataError(f"GET {url} transport_error={exc}") from exc
    raise WorldDataError(f"GET {url} failed")


def get_text_lines(url: str, *, timeout: int = TIMEOUT_SECONDS) -> list[str]:
    """Newline-delimited JSON/text (Common Crawl index API shape).

    The index API answers 404 for unknown hosts and flaky 502/504 under
    load: 404 propagates (caller treats it as "try older crawl"), 502/504
    retry once here.
    """
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, method="GET")
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                break
        except urllib.error.HTTPError as exc:
            if exc.code in {502, 503, 504} and attempt == 0:
                time.sleep(2)
                continue
            raise WorldDataError(f"GET {url} status={exc.code}") from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            raise WorldDataError(f"GET {url} transport_error={exc}") from exc
    return [line for line in (raw or "").splitlines() if line.strip()]
