#!/usr/bin/env python3
"""Load generator for the "1,000 simultaneous users" model.

No extra tooling: uses the venv's httpx. Two modes:

  browse       N virtual users, each loading a page bundle then thinking.
               This is the realistic model — 1,000 users do not issue 1,000
               requests per second; they issue bursts of ~13 API calls when
               they open a screen, then idle.
  connections  N idle keepalive sockets held open against the proxy. Tests the
               connection ceiling (nginx worker_connections), not the app.

Examples:
  python deploy/loadtest/loadtest.py --target http://127.0.0.1:8788 \\
      --users 1000 --duration 300 --think 15-45
  python deploy/loadtest/loadtest.py --target http://127.0.0.1:8788 \\
      --mode connections --connections 1000 --duration 120

Read-only by design: it never calls a write route, a render, or an enrichment
endpoint that would hit a third-party API. Run it against a staging copy (see
deploy/loadtest/staging.sh), never against the live database.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

# What the Commercial screen actually requests on open. Kept in sync with the
# UI by convention; all of these are DB-only reads (no network enrichment).
PAGE = [
    ("session", "/company/ui/session"),
    ("context", "/company/context"),
    ("icps", "/company/commercial/icps"),
    ("icp_templates", "/company/commercial/icp-templates"),
    ("offers", "/company/commercial/offers"),
    ("onboarding_sessions", "/company/commercial/onboarding-sessions"),
    ("accounts", "/company/commercial/accounts?page_size=1"),
    ("pipelines", "/company/commercial/pipelines"),
    ("integrations", "/company/commercial/integrations"),
    ("rules", "/company/commercial/rules"),
    ("imports", "/company/commercial/imports"),
    ("network_stats", "/company/commercial/network-stats"),
    ("benchmarks", "/company/commercial/benchmarks?sends=100"),
]


def _credentials() -> tuple[str, str]:
    user = os.environ.get("DASHBOARD_USER") or os.environ.get("LOADTEST_USER") or ""
    password = os.environ.get("DASHBOARD_PASSWORD") or os.environ.get("LOADTEST_PASSWORD") or ""
    if user and password:
        return user, password
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.is_file():
        values: dict[str, str] = {}
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("'\"")
        user = values.get("DASHBOARD_USER", "")
        password = values.get("DASHBOARD_PASSWORD", "")
    if not user or not password:
        sys.exit("No credentials: set DASHBOARD_USER / DASHBOARD_PASSWORD or --user/--password.")
    return user, password


def _parse_think(text: str) -> tuple[float, float]:
    if "-" in text:
        low, high = text.split("-", 1)
        return float(low), float(high)
    return float(text), float(text)


def _pct(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


@dataclass
class Samples:
    latencies: list[float] = field(default_factory=list)
    statuses: dict[int, int] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    per_endpoint: dict[str, list[float]] = field(default_factory=dict)
    started: float = 0.0
    finished: float = 0.0

    def record(self, name: str, status: int | None, seconds: float, error: str = "") -> None:
        self.latencies.append(seconds * 1000)
        self.per_endpoint.setdefault(name, []).append(seconds * 1000)
        if status is None:
            self.failures[error or "error"] = self.failures.get(error or "error", 0) + 1
        else:
            self.statuses[status] = self.statuses.get(status, 0) + 1

    @property
    def total(self) -> int:
        return len(self.latencies)

    @property
    def failed(self) -> int:
        bad = sum(count for status, count in self.statuses.items() if status >= 400)
        return bad + sum(self.failures.values())


async def _browse_user(client: httpx.AsyncClient, deadline: float, think: tuple[float, float],
                       samples: Samples, page: list[tuple[str, str]]) -> None:
    while time.monotonic() < deadline:
        for name, path in page:
            if time.monotonic() >= deadline:
                return
            started = time.monotonic()
            try:
                response = await client.get(path, timeout=30.0)
                samples.record(name, response.status_code, time.monotonic() - started)
            except Exception as exc:  # noqa: BLE001 - a load test records, it does not raise
                samples.record(name, None, time.monotonic() - started, type(exc).__name__)
        pause = random.uniform(*think)
        await asyncio.sleep(max(0.0, min(pause, deadline - time.monotonic())))


async def run_browse(args: argparse.Namespace) -> int:
    user, password = _credentials()
    auth = httpx.BasicAuth(user, password)
    think = _parse_think(args.think)
    samples = Samples()
    limit = max(args.users * 4, 200)
    timeout = httpx.Timeout(30.0, connect=10.0)
    limits = httpx.Limits(max_connections=limit, max_keepalive_connections=limit)
    async with httpx.AsyncClient(base_url=args.target, auth=auth, timeout=timeout,
                                 limits=limits, headers={"Accept": "application/json"},
                                 follow_redirects=False) as client:
        # Warm the app so first-request imports do not pollute p95.
        for _, path in PAGE:
            try:
                await client.get(path)
            except Exception:  # noqa: BLE001
                pass
        deadline = time.monotonic() + args.duration
        samples.started = time.monotonic()
        await asyncio.gather(*[
            _browse_user(client, deadline, think, samples, PAGE) for _ in range(args.users)
        ])
        samples.finished = time.monotonic()
    return _report(samples, args, label=f"{args.users} users, think {args.think}s")


async def _held_connection(host: str, port: int, deadline: float, keepalive: float) -> tuple[bool, bool]:
    """Open one keepalive socket, then keep it serviceable until the deadline.

    Browsers do not sit on a socket forever without traffic; they revalidate.
    Poking every ``keepalive`` seconds is what keeps a real idle tab alive, and
    it distinguishes "the proxy accepts 1,000 sockets" from "the proxy holds
    1,000 sockets". Uvicorn's own keep-alive timeout is 5s, nginx's is 65s.
    """
    try:
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(b"GET /health HTTP/1.1\r\nHost: loadtest\r\nConnection: keep-alive\r\n\r\n")
        await writer.drain()
        await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=15)
    except Exception:  # noqa: BLE001
        return (False, False)
    opened = True
    while time.monotonic() < deadline:
        await asyncio.sleep(max(0.5, min(keepalive, deadline - time.monotonic())))
        try:
            writer.write(b"GET /health HTTP/1.1\r\nHost: loadtest\r\nConnection: keep-alive\r\n\r\n")
            await writer.drain()
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=15)
            if b" 200 " not in head.split(b"\r\n")[0]:
                writer.close()
                return (opened, False)
        except Exception:  # noqa: BLE001
            writer.close()
            return (opened, False)
    writer.close()
    return (opened, True)


async def run_connections(args: argparse.Namespace) -> int:
    parsed = httpx.URL(args.target)
    host, port = parsed.host, parsed.port or 80
    deadline = time.monotonic() + args.duration
    results = await asyncio.gather(*[
        _held_connection(host, port, deadline, args.keepalive) for _ in range(args.connections)
    ])
    opened = sum(1 for was_opened, _ in results if was_opened)
    held = sum(1 for _, still_held in results if still_held)
    print(f"sockets accepted: {opened}/{args.connections}")
    print(f"still serviceable after {args.duration}s (poke every {args.keepalive}s): {held}")
    ok = opened >= args.connections * 0.99 and held >= opened * 0.99
    print(f"verdict: {'PASS' if ok else 'FAIL'}  (connection ceiling)")
    return 0 if ok else 1


def _report(samples: Samples, args: argparse.Namespace, label: str) -> int:
    elapsed = max(samples.finished - samples.started, 0.001)
    total = samples.total
    failed = samples.failed
    rate = total / elapsed
    print()
    print(f"== {label} ==")
    print(f"duration      {elapsed:6.1f}s")
    print(f"requests      {total:6d}  ({rate:6.1f} rps aggregate)")
    print(f"errors        {failed:6d}  ({failed / max(total, 1) * 100:5.2f}%)")
    if samples.statuses:
        print("status codes  " + ", ".join(f"{code}={count}" for code, count in sorted(samples.statuses.items())))
    if samples.failures:
        print("transport     " + ", ".join(f"{name}={count}" for name, count in sorted(samples.failures.items())))
    print(f"latency ms    p50={_pct(samples.latencies, 0.50):6.1f}  p95={_pct(samples.latencies, 0.95):6.1f}  "
          f"p99={_pct(samples.latencies, 0.99):6.1f}  max={max(samples.latencies):7.1f}")
    print()
    print(f"{'endpoint':22s} {'n':>7s} {'p50':>8s} {'p95':>8s} {'p99':>8s}")
    for name, values in sorted(samples.per_endpoint.items()):
        print(f"{name:22s} {len(values):7d} {_pct(values, 0.5):8.1f} {_pct(values, 0.95):8.1f} {_pct(values, 0.99):8.1f}")

    # Pass criteria are about user experience, not raw rps.
    p95 = _pct(samples.latencies, 0.95)
    error_ratio = failed / max(total, 1)
    ok = p95 <= args.p95_budget and error_ratio <= args.max_error_rate
    print()
    print(f"verdict: {'PASS' if ok else 'FAIL'}"
          f"  (p95 {p95:.0f}ms vs budget {args.p95_budget:.0f}ms, "
          f"errors {error_ratio * 100:.2f}% vs {args.max_error_rate * 100:.2f}%)")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", default="http://127.0.0.1:8788")
    parser.add_argument("--mode", choices=("browse", "connections"), default="browse")
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--connections", type=int, default=1000)
    parser.add_argument("--keepalive", type=float, default=20.0,
                        help="seconds between keepalive pokes while holding sockets")
    parser.add_argument("--duration", type=int, default=60, help="seconds")
    parser.add_argument("--think", default="15-45", help="seconds between page loads, e.g. 15-45")
    parser.add_argument("--p95-budget", type=float, default=800.0, help="ms")
    parser.add_argument("--max-error-rate", type=float, default=0.01, help="0.01 = 1%%")
    args = parser.parse_args()
    if args.mode == "connections":
        return asyncio.run(run_connections(args))
    return asyncio.run(run_browse(args))


if __name__ == "__main__":
    raise SystemExit(main())
