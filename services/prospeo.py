from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any


class ProspeoError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, error_code: str | None = None):
        super().__init__(message)
        self.status = status
        self.error_code = error_code


logger = logging.getLogger(__name__)


class ProspeoClient:
    def __init__(self, api_key: str | None = None, base_url: str = "https://api.prospeo.io"):
        self.api_key = api_key or os.getenv("PROSPEO_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        if not self.api_key:
            raise ProspeoError("PROSPEO_API_KEY is not configured")

    def _request(self, endpoint: str, body: dict[str, Any], attempts: int = 3) -> dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        body_preview = json.dumps(body, ensure_ascii=True)[:500]
        payload = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "X-KEY": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                raw = ""
                detail = str(exc)
                error_code = None
                try:
                    raw = exc.read().decode("utf-8")
                    error_payload = json.loads(raw)
                    error_code = error_payload.get("error_code")
                    detail = error_payload.get("message") or error_code or error_payload.get("detail") or raw[:500]
                except Exception:
                    if not raw:
                        raw = detail
                log = logger.info if error_code == "NO_RESULTS" else logger.warning
                log(
                    "Prospeo %s method=%s url=%s status=%s attempt=%s body=%s response=%s",
                    "search returned no results" if error_code == "NO_RESULTS" else "upstream error",
                    request.get_method(),
                    url,
                    exc.code,
                    attempt + 1,
                    body_preview,
                    raw[:500],
                )
                if exc.code in {403, 409, 422, 429, 500, 502, 503, 504} and attempt + 1 < attempts:
                    time.sleep(2 ** attempt)
                    continue
                raise ProspeoError(
                    f"method={request.get_method()} url={url} status={exc.code} detail={detail} body={body_preview}",
                    exc.code,
                    error_code,
                ) from exc
            except (TimeoutError, urllib.error.URLError) as exc:
                logger.warning(
                    "Prospeo upstream transport error method=%s url=%s attempt=%s body=%s error=%s",
                    request.get_method(),
                    url,
                    attempt + 1,
                    body_preview,
                    exc,
                )
                if attempt + 1 < attempts:
                    time.sleep(2 ** attempt)
                    continue
                raise ProspeoError(
                    f"method={request.get_method()} url={url} transport_error={exc} body={body_preview}"
                ) from exc
        raise ProspeoError(f"Prospeo request failed method={request.get_method()} url={url} body={body_preview}")

    def search_person(self, filters: dict[str, Any], page: int = 1) -> dict:
        return self._request("search-person", {"page": page, "filters": filters})

    def search_suggestions(self, *, job_title: str | None = None, location: str | None = None, industry: str | None = None) -> dict:
        body = {}
        if job_title:
            body["job_title_search"] = job_title
        elif location:
            body["location_search"] = location
        elif industry:
            body["industry_search"] = industry
        else:
            raise ProspeoError("a suggestion query is required")
        return self._request("search-suggestions", body)

    def extract_contact_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        person = payload.get("person") if isinstance(payload.get("person"), dict) else payload
        email_info = person.get("email") if isinstance(person.get("email"), dict) else {}
        phone_info = person.get("mobile") if isinstance(person.get("mobile"), dict) else {}
        raw_email = person.get("email") if isinstance(person.get("email"), str) else None
        raw_mobile = person.get("mobile") if isinstance(person.get("mobile"), str) else None
        email = email_info.get("email") or raw_email
        phone = phone_info.get("number") or person.get("phone") or raw_mobile
        return {
            "email": email,
            "phone": phone,
            "verification_status": email_info.get("status"),
            "linkedin_url": person.get("linkedin_url"),
            "person_id": person.get("person_id"),
        }

    def enrich_person(self, person_id: str) -> dict:
        payload = self._request(
            "enrich-person",
            {
                "only_verified_email": True,
                "data": {"person_id": person_id},
            },
        )
        person = payload.get("person")
        if isinstance(person, dict):
            return person
        return payload if isinstance(payload, dict) else {}
