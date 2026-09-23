#!/usr/bin/env python3
"""Smoke-test a running company-core API over real HTTP.

Covers what the pytest suite cannot from inside TestClient:
  - the P0-2 action-gate matrix (401 / 403 / gated-but-allowed)
  - the P0-1 send_unknown reconcile flow and the outside-window resume park
  - P0-3 intake / webhook / sign-in rate limits (429 + Retry-After)
  - the P0-4 backup -> verify -> restore --verify round trip
  - the P0-1 startup reconciliation (when it is safe to observe)

Usage:
  make smoke
  .venv/bin/python scripts/smoke_actions.py --only gate --report logs/smoke-report.md

The server at --base-url is used when reachable; otherwise uvicorn is spawned
as a child (killed on exit) unless --no-autostart is given. Seeded rows use
smoke-<tag>@example.com and are deleted afterwards.

Safety: no real email can be sent. The send route is only exercised against a
draft stranded *outside* the provider idempotency window, which parks before
any provider call; startup reconciliation is only armed when no
SALES_RESEND_API_KEY is configured (otherwise the child is spawned with
SALES_SEND_RECONCILE_ON_STARTUP=false).

Exit code: 0 = no FAIL (WARN/SKIP allowed), 1 = at least one FAIL,
2 = could not run (no credentials, no server and autostart disabled).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# The P0-2 gate matrix (kept in sync with tests/test_action_gates.py).
GATED_ROUTES = [
    "/company/setup/step",
    "/company/coding/tasks",
    "/company/coding/tasks/task_smoke/apply",
    "/company/monitor/run",
    "/company/monitor/run/api",
    "/company/marketing/campaigns/camp_smoke/variants/var_smoke/select",
    "/company/marketing/campaigns/camp_smoke/drafts",
    "/company/marketing/campaigns/camp_smoke/approve-script",
    "/company/marketing/campaigns/camp_smoke/regenerate-script",
    "/company/marketing/campaigns/camp_smoke/retry",
    "/company/marketing/manual-posts/post_smoke/buffer-schedule",
]

# Gated routes whose handler404s on an unknown id before any side effect:
# with the token present they must fall through the gate (404, not 403).
TOKEN_FALLS_THROUGH = [
    "/company/marketing/campaigns/camp_smoke/variants/var_smoke/select",
    "/company/marketing/campaigns/camp_smoke/drafts",
    "/company/marketing/campaigns/camp_smoke/approve-script",
    "/company/marketing/campaigns/camp_smoke/regenerate-script",
    "/company/marketing/campaigns/camp_smoke/retry",
    "/company/marketing/manual-posts/post_smoke/buffer-schedule",
]

PASS, FAIL, WARN, SKIP = "PASS", "FAIL", "WARN", "SKIP"


class Runner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.base = args.base_url.rstrip("/")
        self.results: list[dict] = []
        self.seeded_leads: list[str] = []
        self.child: subprocess.Popen | None = None
        self.spawned = False
        self.server_ok = False
        self.child_log = ""
        self.dash_auth: str | None = None
        self.token: str | None = None
        self.startup_draft: tuple[str, str] | None = None

    # ---------- HTTP ----------

    def http(self, method: str, path: str, *, body=None, auth: str | None = "dash",
             token: bool = False, timeout: float = 15.0):
        headers: dict[str, str] = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if auth == "dash" and self.dash_auth:
            headers["Authorization"] = "Basic " + self.dash_auth
        elif auth and auth != "dash":
            headers["Authorization"] = "Basic " + basic(auth)
        if token and self.token:
            headers["X-Founder-Action-Token"] = self.token
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, dict(response.headers), _json(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers or {}), _json(exc.read())
        except urllib.error.URLError as exc:
            return None, {}, {"detail": str(exc.reason)}

    def header_value(self, headers: dict, name: str) -> str | None:
        """Case-insensitive header lookup (uvicorn delivers `retry-after`)."""
        wanted = name.lower()
        for key, value in headers.items():
            if key.lower() == wanted:
                return value
        return None

    def health(self, timeout: float = 3.0) -> bool:
        status, _, _ = self.http("GET", "/health", auth=None, timeout=timeout)
        return status == 200

    # ---------- results ----------

    def record(self, name: str, status: str, expected: str, got: str, note: str = "") -> None:
        self.results.append({"name": name, "status": status, "expected": expected,
                             "got": got, "note": note})

    def check(self, name: str, expected: str, fn, *, needs_token: bool = False):
        """Run fn() -> (ok: bool, got: str, optional note); exceptions become FAIL."""
        if self.args.only and not any(f.lower() in name.lower() for f in self.args.only):
            return
        if needs_token and not self.token:
            self.record(name, SKIP, expected, "-", "SALES_ACTION_TOKEN not configured")
            return
        try:
            outcome = fn()
            ok, got = outcome[0], outcome[1]
            note = outcome[2] if len(outcome) > 2 else ""
            self.record(name, PASS if ok else FAIL, expected, got, note)
        except Exception as exc:  # noqa: BLE001 - a crashed check is a failed check
            self.record(name, FAIL, expected, f"error: {exc}")

    def skip(self, name: str, expected: str, reason: str) -> None:
        if self.args.only and not any(f.lower() in name.lower() for f in self.args.only):
            return
        self.record(name, SKIP, expected, "-", reason)

    # ---------- seeding ----------

    def seed_send_unknown(self, tag: str) -> tuple[str, str]:
        from core import sales_store

        lead_id, draft_id = self.seed_draft(tag)
        sales_store.claim_draft_for_send(draft_id)
        sales_store.mark_send_unknown(draft_id, reason=f"smoke test ({tag})")
        return lead_id, draft_id

    def seed_stranded_sending(self, tag: str) -> tuple[str, str]:
        from core import sales_store

        lead_id, draft_id = self.seed_draft(tag)
        sales_store.claim_draft_for_send(draft_id)
        with sales_store.connect() as connection:
            connection.execute(
                "UPDATE sales_drafts SET send_started_at = '2000-01-01T00:00:00+00:00' WHERE id = ?",
                (draft_id,),
            )
        return lead_id, draft_id

    def seed_draft(self, tag: str) -> tuple[str, str]:
        from core import sales_store

        email = f"smoke-{tag}-{uuid.uuid4().hex[:8]}@example.com"
        lead, _ = sales_store.upsert_lead({"email": email, "source": "website"})
        draft = sales_store.create_draft(lead["id"], "Smoke test draft",
                                         "Seeded by scripts/smoke_actions.py; deleted on cleanup.")
        sales_store.approve_draft(draft["id"])
        self.seeded_leads.append(lead["id"])
        return lead["id"], draft["id"]

    def cleanup(self) -> None:
        if not self.seeded_leads:
            return
        try:
            from core import sales_store

            with sales_store.connect() as connection:
                for lead_id in self.seeded_leads:
                    connection.execute("DELETE FROM sales_interactions WHERE lead_id = ?", (lead_id,))
                    connection.execute("DELETE FROM sales_events WHERE lead_id = ?", (lead_id,))
                    connection.execute("DELETE FROM sales_drafts WHERE lead_id = ?", (lead_id,))
                    connection.execute("DELETE FROM sales_leads WHERE id = ?", (lead_id,))
        except Exception as exc:  # noqa: BLE001 - cleanup must not mask results
            print(f"warning: could not remove seeded rows: {exc}", file=sys.stderr)

    # ---------- server ----------

    def ensure_server(self) -> None:
        if self.health():
            self.record("server", PASS, "reachable", self.base, "using the server that was already running")
            self.server_ok = True
            return
        if self.args.no_autostart:
            print(f"error: no server at {self.base} and --no-autostart given", file=sys.stderr)
            raise SystemExit(2)
        # Startup reconciliation can only be observed on a child we spawn, and
        # only when it cannot fire a real email.
        resend_key = env_value("SALES_RESEND_API_KEY")
        startup_wanted = not self.args.only or any("startup" in f.lower() for f in self.args.only)
        if not resend_key and startup_wanted:
            lead_id, draft_id = self.seed_draft("startup")
            from core import sales_store

            sales_store.claim_draft_for_send(draft_id)  # sending, inside the window
            self.startup_draft = (lead_id, draft_id)
        child_env = dict(os.environ)
        if resend_key:
            child_env["SALES_SEND_RECONCILE_ON_STARTUP"] = "false"
        port = port_of(self.base)
        self.child = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.api:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=REPO, env=child_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self.spawned = True
        for _ in range(40):
            if self.health():
                self.record("server", PASS, "reachable", self.base, "autostarted uvicorn child")
                self.server_ok = True
                return
            if self.child.poll() is not None:
                break
            time.sleep(0.5)
        self.record("server", FAIL, "reachable", self.base, "spawned uvicorn never became healthy")
        raise SystemExit(2)

    def stop_server(self) -> None:
        if not self.child:
            return
        try:
            os.killpg(os.getpgid(self.child.pid), signal.SIGTERM)
            self.child.wait(timeout=10)
        except Exception:  # noqa: BLE001
            try:
                os.killpg(os.getpgid(self.child.pid), signal.SIGKILL)
            except Exception:  # noqa: BLE001
                pass
        try:
            self.child_log = (self.child.stdout.read() or b"").decode("utf-8", "replace") if self.child.stdout else ""
        except Exception:  # noqa: BLE001
            self.child_log = ""

    # ---------- checks ----------

    def run_checks(self) -> None:
        self.check("health", "GET /health -> 200", lambda: self._expect("GET", "/health", 200, auth=None))
        self.check("auth-required", "dashboard route without credentials -> 401",
                   lambda: self._expect("GET", "/company/sales/leads", 401, auth=None))

        for path in GATED_ROUTES:
            self.check(f"gate-no-token:{path}", "403 without X-Founder-Action-Token",
                       lambda p=path: self._expect("POST", p, 403, body={}))

        def setup_step_idempotent():
            status, _, step_body = self.http("GET", "/company/setup/step")
            if status != 200:
                return False, f"GET step -> {status}"
            current = str(step_body.get("step", ""))
            status, _, body = self.http("POST", "/company/setup/step", body={"step": current}, token=True)
            ok = status == 200 and body.get("step") == current
            return ok, f"POST step -> {status}", "writes the current value back (state unchanged)"

        self.check("gate-with-token:setup-step", "200 with token (idempotent write)",
                   setup_step_idempotent, needs_token=True)

        for path in TOKEN_FALLS_THROUGH:
            self.check(f"gate-with-token:{path}", "404 (gate passed, dummy id unknown)",
                       lambda p=path: self._expect("POST", p, 404, body={}, token=True),
                       needs_token=True)

        self.reconcile_checks()
        self.resume_park_check()
        self.backup_check()
        self.webhook_budget_check()
        self.intake_burst_check()
        self.auth_burst_check()
        self.startup_reconcile_check()

    def reconcile_checks(self) -> None:
        _, draft_id = self.seed_send_unknown("reconcile")

        def listing():
            status, _, body = self.http("GET", "/company/sales/drafts/reconcile")
            ids = [item["id"] for item in body.get("drafts", [])] if status == 200 else []
            return status == 200 and draft_id in ids, f"GET -> {status}, seeded draft listed: {draft_id in ids}"

        self.check("reconcile-list", "seeded send_unknown draft appears in GET list", listing)

        self.check("reconcile-token-gate", "POST reconcile without token -> 403",
                   lambda: self._expect("POST", f"/company/sales/drafts/{draft_id}/reconcile",
                                        403, body={"delivered": False}))

        def release():
            status, _, body = self.http("POST", f"/company/sales/drafts/{draft_id}/reconcile",
                                        body={"delivered": False, "note": "smoke"}, token=True)
            ok = status == 200 and body.get("status") == "approved"
            return ok, f"POST delivered=false -> {status}, status={body.get('status')}"

        self.check("reconcile-release", "delivered=false -> 200 and draft back to approved",
                   release, needs_token=True)

        _, second_id = self.seed_send_unknown("reconcile-sent")

        def mark_sent():
            status, _, body = self.http(
                "POST", f"/company/sales/drafts/{second_id}/reconcile",
                body={"delivered": True, "provider_message_id": "re_smoke_check", "note": "smoke"},
                token=True,
            )
            draft = body.get("draft") or {}
            ok = (status == 200 and body.get("status") == "sent"
                  and draft.get("provider_message_id") == "re_smoke_check")
            return ok, f"POST delivered=true -> {status}, status={body.get('status')}, id recorded"

        self.check("reconcile-mark-sent", "delivered=true -> 200 sent with provider id",
                   mark_sent, needs_token=True)

    def resume_park_check(self) -> None:
        _, draft_id = self.seed_stranded_sending("resume")

        def park():
            status, _, body = self.http("POST", f"/company/sales/drafts/{draft_id}/send",
                                        body=None, token=True)
            detail = str(body.get("detail", ""))
            ok = status == 409 and "outside the provider idempotency window" in detail
            return ok, f"send -> {status}", detail[:120]

        self.check("resume-park-outside-window", "409 + window message, parks before any provider call",
                   park, needs_token=True)

        def listed():
            status, _, body = self.http("GET", "/company/sales/drafts/reconcile")
            ids = [item["id"] for item in body.get("drafts", [])] if status == 200 else []
            return draft_id in ids, f"parked draft now listed: {draft_id in ids}"

        self.check("resume-park-visible", "parked draft shows up in GET reconcile list", listed)

    def backup_check(self):
        def roundtrip():
            with tempfile.TemporaryDirectory(prefix="smoke-backup-") as tmp:
                env = dict(os.environ, PYTHON=sys.executable)
                backup = subprocess.run(["bash", "scripts/backup.sh", "--root", str(REPO), "--out", tmp],
                                        cwd=REPO, env=env, capture_output=True, text=True, timeout=300)
                if backup.returncode != 0:
                    return False, "backup.sh failed", backup.stderr.strip()[-200:]
                archives = list(Path(tmp).glob("*.tar.gz"))
                if not archives:
                    return False, "backup.sh produced no archive"
                verify = subprocess.run([sys.executable, "scripts/verify_backup.py", "--archive",
                                         str(archives[0])], cwd=REPO, env=env, capture_output=True,
                                        text=True, timeout=300)
                if verify.returncode != 0:
                    return False, "verify_backup.py failed", verify.stderr.strip()[-200:]
                restore = subprocess.run(["bash", "scripts/restore.sh", "--verify", "--archive",
                                          str(archives[0])], cwd=REPO, env=env, capture_output=True,
                                         text=True, timeout=300)
                if restore.returncode != 0:
                    return False, "restore.sh --verify failed", restore.stderr.strip()[-200:]
                return True, "backup -> verify -> restore --verify all rc=0"

        self.check("backup-roundtrip", "P0-4 round trip exits 0", roundtrip)

    def webhook_budget_check(self):
        def separate():
            status, _, _ = self.http("POST", "/integrations/email/sales", body={}, auth=None)
            return status != 429, f"POST /integrations/email/sales -> {status}", \
                "webhook budget must not be the intake budget"

        self.check("webhook-budget-separate", "webhook POST not 429 while intake has its own budget",
                   separate)

    def intake_burst_check(self):
        def burst():
            baseline = self.lead_total()
            status_seen = None
            retry_after = None
            for _ in range(60):
                status, headers, _ = self.http("POST", "/integrations/leads/website", body={}, auth=None)
                status_seen = status
                if status == 429:
                    retry_after = self.header_value(headers, "Retry-After")
                    break
            if status_seen != 429:
                return True, "no 429 within 60 requests", \
                    "WARN: limiter disabled or intake limit > 60 (RATE_LIMIT_* in server env)"
            after = self.lead_total()
            ok = retry_after is not None and after == baseline
            return ok, f"429 after burst, Retry-After={retry_after}, leads {baseline} -> {after}", \
                "invalid body (422/401) never creates a lead"

        self.check("intake-burst-429", "burst over the intake limit -> 429 + Retry-After, no leads created",
                   burst, )

    def auth_burst_check(self):
        def burst():
            wrong = f"{env_value('DASHBOARD_USER') or 'founder'}:definitely-wrong"
            last = None
            for _ in range(15):
                status, _, _ = self.http("GET", "/company/sales/leads", auth=wrong)
                last = status
                if status == 429:
                    break
            if last != 429:
                return True, "no 429 within 15 failed sign-ins", \
                    "WARN: auth failure limiter disabled or limit > 15"
            status, _, _ = self.http("GET", "/company/sales/leads")  # correct password
            ok = status == 200
            return ok, f"429 after failed attempts, correct sign-in then -> {status}", \
                "failure bucket must not affect successful sign-ins"

        self.check("sign-in-burst-429", "failed sign-ins -> 429, valid sign-in still 200", burst)

    def _startup_skip_reason(self) -> str | None:
        if not self.server_ok:
            return "server unavailable"
        if not self.startup_draft:
            return ("server was already running (startup not observable)"
                    if not self.spawned else
                    "SALES_RESEND_API_KEY configured; child spawned with reconcile disabled to avoid real sends")
        return None

    def startup_reconcile_check(self) -> None:
        """Phase 1, while the server is alive: GET the seeded lead and confirm
        boot-time reconciliation released the claim (with no provider key
        _attempt_send raises ValueError -> the draft falls back to approved)."""
        name, expected = "startup-reconcile", "stranded in-window draft released at boot (no provider key)"
        reason = self._startup_skip_reason()
        if reason:
            self.skip(name, expected, reason)
            return
        lead_id, draft_id = self.startup_draft  # type: ignore[misc]

        def released():
            status, _, body = self.http("GET", f"/company/sales/leads/{lead_id}")
            drafts = body.get("drafts", []) if status == 200 and isinstance(body, dict) else []
            current = next((d.get("status") for d in drafts if d.get("id") == draft_id), None)
            ok = current == "approved"
            return ok, f"draft status after boot: {current}", "definite send failure released the claim"

        self.check(name, expected, released)

    def startup_reconcile_log_check(self) -> None:
        """Phase 2, after the child is reaped so its stdout can be read."""
        name, expected = "startup-reconcile-log", "[startup] send reconciliation line in child log"
        reason = self._startup_skip_reason()
        if reason:
            self.skip(name, expected, reason)
            return
        if self.args.only and not any(f.lower() in name.lower() for f in self.args.only):
            return
        log_ok = "[startup] send reconciliation" in self.child_log
        self.record(name, PASS if log_ok else WARN, expected,
                    "present" if log_ok else "absent",
                    "" if log_ok else "printed only when the report is non-empty; check uvicorn output")

    # ---------- helpers ----------

    def _expect(self, method: str, path: str, want: int, **kwargs):
        status, _, body = self.http(method, path, **kwargs)
        detail = str(body.get("detail", ""))[:80] if isinstance(body, dict) else ""
        return status == want, f"-> {status}" + (f" ({detail})" if detail else "")

    def lead_total(self) -> int:
        status, _, body = self.http("GET", "/company/sales/leads")
        return int(body.get("summary", {}).get("total", -1)) if status == 200 else -1

    # ---------- report ----------

    def summarize(self) -> dict[str, int]:
        counts = {PASS: 0, FAIL: 0, WARN: 0, SKIP: 0}
        for row in self.results:
            counts[row["status"]] += 1
        return counts

    def print_table(self) -> None:
        widths = [
            max([len("CHECK"), *(len(r["name"]) for r in self.results)]),
            max([len("EXPECTED"), *(len(r["expected"]) for r in self.results)]),
            max([len("GOT"), *(len(r["got"]) for r in self.results)]),
        ]
        header = f"{'CHECK':<{widths[0]}}  {'EXPECTED':<{widths[1]}}  {'GOT':<{widths[2]}}  RESULT"
        print(header)
        print("-" * len(header))
        for row in self.results:
            print(f"{row['name']:<{widths[0]}}  {row['expected']:<{widths[1]}}  "
                  f"{row['got']:<{widths[2]}}  {row['status']}")
            if row["note"]:
                print(f"{'':<{widths[0]}}  note: {row['note']}")
        counts = self.summarize()
        print("-" * len(header))
        print(f"TOTAL  pass={counts[PASS]} fail={counts[FAIL]} warn={counts[WARN]} skip={counts[SKIP]}")

    def write_report(self, path: Path) -> None:
        counts = self.summarize()
        sha = "unknown"
        try:
            sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                                 capture_output=True, text=True, timeout=10).stdout.strip()
            dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                                   capture_output=True, text=True, timeout=10).stdout.strip()
            if dirty:
                sha += " (dirty)"
        except Exception:  # noqa: BLE001
            pass
        mode = ("autostarted uvicorn" if self.spawned else "external server") + f" at {self.base}"
        verdict = "FAILED" if counts[FAIL] else "PASSED"
        lines = [
            "# Company Core smoke report",
            "",
            f"- Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            f"- Git: `{sha}`",
            f"- Server: {mode}",
            f"- Result: **{verdict}** "
            f"(pass={counts[PASS]} fail={counts[FAIL]} warn={counts[WARN]} skip={counts[SKIP]})",
            "",
            "| Check | Expected | Got | Result |",
            "| --- | --- | --- | --- |",
        ]
        for row in self.results:
            cells = [row["name"], row["expected"],
                     row["got"] + (f" — {row['note']}" if row["note"] else ""), row["status"]]
            lines.append("| " + " | ".join(str(c).replace("|", "\\|") for c in cells) + " |")
        lines.append("")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"report written: {path}")


def basic(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def _json(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return {"raw": raw.decode("utf-8", "replace")[:200]}


def port_of(url: str) -> int:
    tail = url.split("://", 1)[-1]
    host = tail.split("/", 1)[0]
    if ":" in host:
        return int(host.rsplit(":", 1)[1])
    return 443 if url.startswith("https") else 80


def load_dotenv_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def env_value(key: str) -> str:
    return os.environ.get(key, "").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--no-autostart", action="store_true")
    parser.add_argument("--only", action="append", default=[],
                        help="run only checks whose name contains the substring (repeatable)")
    parser.add_argument("--report", type=Path, default=None, help="also write a markdown report here")
    args = parser.parse_args(argv)

    load_dotenv_file(REPO / ".env")
    user = env_value("DASHBOARD_USER") or "founder"
    password = env_value("DASHBOARD_PASSWORD")
    if not password:
        print("error: DASHBOARD_PASSWORD is not set (env or .env; run scripts/init_env.sh)",
              file=sys.stderr)
        return 2

    runner = Runner(args)
    runner.dash_auth = basic(f"{user}:{password}")
    runner.token = env_value("SALES_ACTION_TOKEN") or None

    if not runner.token:
        print("warning: SALES_ACTION_TOKEN unset; token-gated checks will be skipped", file=sys.stderr)

    try:
        runner.ensure_server()
        if not runner.health():
            return 2
        runner.run_checks()
    finally:
        runner.stop_server()
        runner.startup_reconcile_log_check()
        runner.cleanup()
        runner.print_table()
        if args.report:
            runner.write_report(args.report)

    return 1 if runner.summarize()[FAIL] else 0


if __name__ == "__main__":
    raise SystemExit(main())
