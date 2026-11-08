# Production runbook: one box, 1000 users, nginx, same app

Decision record for this deployment. Everything here is free software, and the
application content is unchanged — this is transport, process model and
schedule only.

## Decisions (and why)

| Question | Chosen | Why not the alternative |
|---|---|---|
| Reverse proxy | **nginx** | Team familiarity and a config already validated here. Caddy's only real win is automatic TLS, which certbot covers. Caddy's cache and rate-limit are third-party modules; nginx has both built in. nginx also carries forward to load balancers and k8s ingress unchanged. |
| Worker model | **uvicorn `--workers`, via `--scale api=N`** | Gunicorn would add a dependency (`uvicorn[standard]` does not ship `uvicorn.workers`) for no gain: uvicorn has multi-worker and Unix-socket support natively. One host, N workers, one shared SQLite volume. |
| Worker recycling | **No `max_requests`** | A request counter kills workers mid-flight. Plan generation, FFmpeg renders and world-data ingest run for minutes. Replaced by crash restart (healthcheck) plus one graceful daily replacement at 04:00. |
| Edge cache | **Statics only** | Every `/company/*` GET is tenant data plus live counters. A 5-minute cache would serve stale send counts and would leak across tenants later. API responses are explicitly `no-store` from the app. |
| SQLite | **WAL + `synchronous=NORMAL` + 30s busy timeout** (already in `core/db.py`) | Concurrent readers scale with workers; writes serialise by design. `FULL` fsyncs every commit for no extra safety under WAL. |
| Daily reset with `rm *.db` | **Rejected** | The three databases *are* the product. Daily jobs are backup + verify, world-data refresh, graceful reload, cert renewal. |
| Box shape | **One host** | SQLite cannot span hosts. Many small hosts would force a Postgres migration (a content change). One box scales vertically and with workers. |

## 0. Size the box

| Role | Spec | Why |
|---|---|---|
| App + nginx | 8 vCPU / 32 GB RAM | 4–8 uvicorn workers (~400 MB each) + nginx + ingest + headroom |
| GPU | 1× 24 GB VRAM (RTX 4090 / L4) | Ollama `llama3.2` with `OLLAMA_NUM_PARALLEL=4`; bigger models need more VRAM |
| Disk | 100 GB SSD | `.venv` + `data/` (renders accumulate) + ~30 GB Ollama models |
| OS | Ubuntu 24.04, Docker Engine + NVIDIA Container Toolkit | |

**Small-VM variant:** if the box has no GPU, skip `--profile gpu` and point
`OMNIROUTE_BASE_URL` / `MODEL_*` at an external gateway. Then 2 vCPU / 4 GB is
enough for proxy + API; the GPU is the only reason to buy a big machine.

## 1. Build & start

```bash
cp .env.example .env        # fill DASHBOARD_*, provider keys as needed
# openssl rand -hex 32  -> SALES_ACTION_TOKEN, etc.
npm --prefix autoevolve-ui run build           # produces autoevolve-ui/dist (served by nginx from disk)
docker compose -f deploy/compose.prod.yaml --profile gpu up -d --build --scale api=6
docker compose -f deploy/compose.prod.yaml exec ollama ollama pull llama3.2
curl -o /dev/null -w "%{http_code}\n" http://localhost/health   # via nginx
```

## 2. What the edge does

- `/assets/*` is served from `autoevolve-ui/dist` on disk with a one-year
  immutable cache. Python is not involved, so a page load costs zero workers.
- Everything else is proxied. Reads get 100 r/s per IP (burst 200); writes get
  5 r/s (burst 20) and return `429` rather than queueing into SQLite. Tune
  `deploy/nginx.conf` if your users share one office NAT.
- Responses carry `Cache-Control: no-store` from the app (see the
  `cache_headers` middleware in `app/api.py`), so no proxy or CDN can cache
  tenant data even if one is added later.

## 3. Scheduled jobs

Install the cron file once (edit `APP_DIR` to the checkout path):

```bash
sudo cp deploy/cron.d/autoevolve /etc/cron.d/autoevolve
sudo chmod 644 /etc/cron.d/autoevolve
```

| Time | Job | What it does |
|---|---|---|
| 02:00 | `daily-jobs.sh backup` | SQLite-API snapshot, verify against manifest, prune >14 days |
| 03:00 | `daily-jobs.sh ingest` | Refresh EDGAR / CommonCrawl world data |
| 04:00 | `daily-jobs.sh reload` | Rolling graceful restart: one worker at a time, 300s drain |
| 04:17 | `daily-jobs.sh cert` | Certbot renew, then `nginx -s reload` |

Nothing deletes data. Restores are manual and verified: `scripts/restore.sh --verify --archive <file>`.

## 4. TLS

```bash
./deploy/enable-tls.sh example.com you@example.com
```

Issues the certificate via the shared webroot (nginx keeps serving), writes a
TLS server block to `deploy/tls-sites/`, and adds `deploy/compose.tls.yaml`
with port 443. Once that file exists every compose command picks it up
automatically (`daily-jobs.sh` does this too).

## 5. Operate

- Logs: `docker compose -f deploy/compose.prod.yaml logs -f nginx api`
- Scale workers (same host, same SQLite volume): `--scale api=N`; 4–8 is the
  sweet spot. Each worker is ~400 MB RSS.
- Backup: `make backup` / restore check: `make verify-backup ARCHIVE=<file>`
- Updates: rebuild api, `up -d` one replica at a time. Route changes require
  regenerating `openapi.json` + `schema.ts` — CI fails on drift.

## 6. Know your ceilings

- **Writes** serialise on SQLite. Watch p95 on `POST`; when it climbs while
  reads stay flat, the next step is Postgres (the `core/*_store.py` boundary
  isolates that change).
- **Model calls** queue at Ollama once `OLLAMA_NUM_PARALLEL` (4) is busy.
  Raise it if VRAM allows, or move `MODEL_REASONING` to an external gateway and
  keep `MODEL_FAST` local.
- **Renders** are CPU-bound. Governance limits already cap concurrency in-app;
  a second CPU-only render box is the escape hatch.
- **Edge cache of API JSON** is deliberately absent. `benchmarks` and
  `network-stats` embed live recorded counts, so ETags would rarely validate
  and would add a staleness class of bug. gzip already covers bandwidth.

## 7. Security posture

What this deployment enforces today:

| Control | Where | Note |
|---|---|---|
| Dashboard/operator auth | `app/security.py` | Basic operator path; website users use org-bound sessions; failed attempts are rate-limited per client. |
| TLS | `deploy/enable-tls.sh` | Run it before exposing the host. Basic credentials are plaintext without it. |
| Per-client request limits | `deploy/nginx.conf` + `app/ratelimit.py` | nginx overwrites `X-Forwarded-For` with the peer address and the app trusts it (`RATE_LIMIT_TRUST_PROXY=true`). Without both halves, every user behind the proxy shares one bucket. |
| Browser hardening | `app/api.py` (`security_headers`) | CSP (same-origin scripts), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, COOP. |
| No API caching | `app/api.py` (`cache_headers`) | Tenant responses are `no-store`; only hashed assets are cacheable. |
| No CORS | (absent by design) | Same-origin only. Basic auth headers are not attached to cross-site navigations, which also limits CSRF. |
| Founder action token | `app/sales_api.py` gates | Every write, send, approve and run needs the token; the UI never stores it. |
| Signed publisher webhook | `services/publishers/webhook.py` + nginx | HMAC over the raw body; `/public/manual-posts/` is unauthenticated but token-scoped and short-lived; `PUBLIC_BASE_URL` must be the HTTPS origin. |
| Secrets | `.env` (git-ignored) + `.dockerignore` | `.env`, `data/`, `node_modules` and `dist` never enter the image. |
| Containers | compose | API has no published port; only nginx is reachable. Runs as the image user, `restart: unless-stopped`. |

Known limits, stated rather than hidden:

- **Tenant isolation is application-level.** Website sessions bind requests to
  one organization; Cloudflare/WAF is not an authorization boundary.
- **No 2FA.** Basic auth is the only factor.
- **`shell=True` remains in `services/worktrees.py` and `services/monitor.py`.**
  Not reachable with untrusted input today (task ids are server-generated,
  monitor commands come from `config/services.json`), but it should become an
  argv list before either surface accepts user input.
- **Rate limits are per process.** With `--scale api=N` each worker counts
  separately; nginx remains the authoritative limit.
- **Uploads are bounded by nginx** (`client_max_body_size 25m`), not by the app.
- **Webhook media links are bearer credentials.** They are signed, scoped to one
  post/asset, and expire; there is no per-recipient identity beyond that link.

## 8. Prove it

`deploy/loadtest/` holds a zero-install generator and a disposable staging
copy. Read `deploy/loadtest/README.md` before quoting any number — in
particular, the generator must run on a **different machine** from the server,
and `benchmarks`/`network-stats` dominate per-page cost because each
recomputes recorded engagement.
