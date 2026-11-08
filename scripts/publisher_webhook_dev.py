#!/usr/bin/env python3
"""Local receiver for the signed publisher webhook.

Usage:
    PUBLISHER_WEBHOOK_SECRET=dev-secret \
        .venv/bin/python scripts/publisher_webhook_dev.py

Set the app's PUBLISHER_WEBHOOK_URL to http://127.0.0.1:8799/hook and
PUBLIC_BASE_URL to the app origin (for example http://127.0.0.1:8787).
This is a development tool: it verifies the HMAC, prints the payload, fetches
one media link, and returns a deterministic provider response. It stores
nothing and is not for production.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET = os.environ.get("PUBLISHER_WEBHOOK_SECRET", "").strip()
PORT = int(os.environ.get("WEBHOOK_DEV_PORT", "8799"))
PATH = "/hook"


def _fetch_media(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            body = response.read(2048)
            return f"{response.status} {response.headers.get('content-type')} {len(body)}+ bytes"
    except Exception as exc:  # noqa: BLE001 - dev diagnostics
        return f"fetch failed: {type(exc).__name__}: {exc}"


class Handler(BaseHTTPRequestHandler):
    def _reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - stdlib API
        if self.path != PATH:
            self._reply(404, {"ok": False, "error": "not found"})
            return
        if not SECRET:
            self._reply(503, {"ok": False, "error": "PUBLISHER_WEBHOOK_SECRET is not set"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        expected = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, self.headers.get("X-Publisher-Signature", "")):
            self._reply(401, {"ok": False, "error": "bad signature"})
            return
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._reply(400, {"ok": False, "error": "invalid JSON"})
            return

        action = str(payload.get("action") or "")
        print(f"\n[{action}] idempotency={self.headers.get('X-Idempotency-Key')}")
        print(json.dumps(payload, indent=2)[:4000])
        if action == "schedule":
            media = payload.get("media") or []
            if media:
                print(f"  media[0]: {media[0].get('url')}")
                print(f"  fetch: {_fetch_media(str(media[0].get('url')))}")
            post_id = f"dev_{int(time.time())}"
            self._reply(200, {
                "ok": True,
                "post_id": post_id,
                "status": "scheduled",
                "due_at": (payload.get("schedule") or {}).get("due_at"),
            })
            return
        if action == "status":
            post_id = str(payload.get("post_id") or "dev")
            self._reply(200, {
                "ok": True,
                "status": "sent",
                "external_url": f"https://social.example/dev/{post_id}",
            })
            return
        if action == "insights":
            post_id = str(payload.get("post_id") or "dev")
            self._reply(200, {
                "ok": True,
                "status": "sent",
                "external_url": f"https://social.example/dev/{post_id}",
                "metrics": [{"type": "reactions", "name": "Reactions", "value": 12, "unit": "count"}],
                "metrics_updated_at": "2026-10-28T12:00:00Z",
            })
            return
        if action == "ping":
            self._reply(200, {"ok": True, "status": "ok", "message": "webhook receiver is alive"})
            return
        self._reply(400, {"ok": False, "error": f"unknown action {action!r}"})

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib API
        sys.stderr.write("webhook: " + (format % args) + "\n")


if __name__ == "__main__":
    print(f"publisher webhook dev receiver on http://127.0.0.1:{PORT}{PATH}")
    print("secret:", "set" if SECRET else "MISSING")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
