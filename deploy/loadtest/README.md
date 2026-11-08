# Load testing 1,000 simultaneous users

## What "1,000 users" actually means

1,000 people with a dashboard tab open is **not** 1,000 requests per second:

- ~1,000 idle keepalive connections (browsers hold these open).
- Each user opens a screen every 20–60 s, firing a burst of ~13 API calls, then
  idles. Aggregate: roughly **100–350 rps**, with bursts.
- Writes are rare — a founder saves something a few times a minute.

So there are two independent tests, and passing one proves nothing about the
other:

| Test | Question | Mode |
|---|---|---|
| Connection ceiling | Can the proxy hold 1,000 open sockets? | `--mode connections` |
| App capacity | Do reads stay fast under the burst pattern? | `--mode browse` |

Renders and model calls are a third, separate matter: they are queued and
bounded by governance, not by request concurrency.

## Run it

```bash
# 1. Disposable staging copy (own data/, port 8788). Never the live DB.
WORKERS=6 deploy/loadtest/staging.sh start

# 2. App capacity: 1,000 users, 5 minutes, thinking 15–45s between screens.
.venv/bin/python deploy/loadtest/loadtest.py \
    --target http://127.0.0.1:8788 --users 1000 --duration 300 --think 15-45

# 3. Connection ceiling (against nginx in production, not uvicorn):
.venv/bin/python deploy/loadtest/loadtest.py \
    --target http://127.0.0.1/ --mode connections --connections 1000 --duration 120

# 4. Done
deploy/loadtest/staging.sh stop
```

Credentials come from `.env` (`DASHBOARD_USER` / `DASHBOARD_PASSWORD`) or
`--user` / `--password`. `httpx` is already in the venv — nothing to install.

## The generator must not share the server's CPU

This is the single most important rule. Co-located, generator and app compete
for the same cores and every latency number becomes meaningless — you measure
the queue, not the app. Run the generator from **another machine** on the same
network:

```bash
# on the load box
python3 -m pip install --user httpx     # or copy the venv
.venv/bin/python deploy/loadtest/loadtest.py --target http://<server>/ --users 1000 --duration 300
```

On this 4-vCPU dev box, a 200-user run already reports p95 ≈ 5 s. That number
is **not** a capacity result: 4 API workers + the live dev server + the
generator were all competing for 4 cores. Reproduce on the target box with the
generator elsewhere before believing any figure.

## The per-IP rate limit will trip a single generator

`deploy/nginx.conf` allows 100 r/s of reads per IP. A real 1,000-user crowd has
1,000 IPs; one generator has one. So:

- Test **app capacity** directly against uvicorn (`:8788`), which is what the
  staging script exposes — no proxy limit in the way.
- Test **the proxy** with the limit raised temporarily, or from several
  generator IPs. Do not conclude "nginx can't take it" from the 429s a single
  IP earns.

## Pass criteria

Defaults: **p95 ≤ 800 ms** and **errors ≤ 1%** across the browse run. Both are
printed as a verdict; the script exits non-zero on failure so CI/cron can use
it.

Interpret per endpoint, not just the total:

- `session`, `offers`, `rules`, `imports`, `icps`, `pipelines` are cheap
  (single-digit to ~20 ms at low load). If these climb, the box is out of CPU.
- `benchmarks` and `network-stats` are expensive: each recomputes recorded
  engagement (`collect_evidence`). At 25 users they were already ~60 ms p50
  against ~10 ms for the rest — together roughly half the cost of a page load.
  If they dominate p95, the fix is memoising the engagement aggregate, not
  adding workers.
- `http_429` = proxy shedding load (by design). `5xx` = app failure.
  `timeout`/`ConnectError` = the box or the network ran out, not the app.

Record, alongside latency: `docker stats` RSS per worker (expect ~400 MB) and
`nproc` utilisation. A worker at 100% CPU with flat p95 means add workers; all
workers at 100% with rising p95 means vertical scale or move work off the
request path.

## Measured so far (co-located, directional only)

Same box, same run shape, one worker, 40 users hammering with no think time:

| Build | Throughput | p95 | Verdict |
|---|---|---|---|
| Before evidence cache | 101.8 rps | 1625 ms | FAIL |
| After evidence cache | 142.2 rps | 755 ms | PASS |

Sequential request cost on the two hot endpoints (30 requests each):

| Endpoint | Before | After |
|---|---|---|
| `/company/commercial/benchmarks` | 34.7 ms | 14.5 ms |
| `/company/commercial/network-stats` | 29.3 ms | 10.3 ms |

Both endpoints rebuild the evidence union; it is now cached per (org, database
fingerprint), so a committed write invalidates immediately. Numbers above are
directional because the generator shared the box with the server; the ratio is
still meaningful, the absolute capacity is not.

## What this harness does not test

- Writes and SQLite contention. Sends/saves are rare per user; test them
  separately, at a fixed low rate, against staging (never live): a burst of
  writes is the one thing that can make SQLite the bottleneck.
- Model-backed actions and renders. Queue depth, not request latency, governs
  those.
- TLS handshake cost at 1,000 connections/s (not the same as 1,000 idle
  sockets).
