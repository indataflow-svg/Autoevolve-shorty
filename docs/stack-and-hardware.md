# Stack & Hardware Requirements — Company Core (AutoEvolve) v1.2.0

## Application stack (all verified in-repo)

| Layer | Technology | Notes |
|---|---|---|
| Language | Python 3.12 (isolated `.venv`) | 3.12 required by OpenHands SDK |
| API | FastAPI + Uvicorn, single process on `:8787` | No workers/queues; `--reload` dev only |
| Database | SQLite (WAL), 3 files: `company.db`, `workflows.db`, `company_ops.db` | ~7 MB live data; zero DB servers to run |
| Frontend | React 19 + Vite 7 SPA, served as static `dist/` (744 KB) | Built once; no Node at runtime |
| UI state | TanStack Query/Table, React Router, no store libs | |
| Media | Pillow (upload checks), OpenSSL | No renderer; media is uploaded by the operator |
| Key Python deps | `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`, `pydantic-ai`, `openhands-sdk==1.42.1`, `browser-use==0.11.13`, `trafilatura`, `email-validator` | See `pyproject.toml` |
| AI inference | **External gateway** (OmniRoute or Ollama or any OpenAI-compatible) | App holds no models, needs no GPU |
| Optional providers | Resend, Hunter/Apollo/Prospeo/Lusha/PDL, Buffer, R2, Tally, Calendar | All optional; dashboard runs without keys |
| Deploy shapes | `make dev` (native), `compose.yaml` (one service, 3 volume mounts), `Dockerfile` (node-build + python-slim stages) | |

## Measured footprint (production-like, Oct 2026)

- App RSS: **~400 MB** (imports OpenHands/pydantic-ai/browser toolchains)
- `.venv`: 631 MB · `node_modules` (build-time only): 217 MB · `dist`: <1 MB
- `data/`: ~5 MB (DBs + manual-post metadata)
- `engines/`: ~49 MB (G3) · `projects/`: small file artifacts

## Hardware requirements

**Minimum (app only, remote AI gateway):**
- 1 vCPU · **1 GB RAM** · 10 GB disk · outbound HTTPS · inbound `:8787`

**Recommended (single-tenant production):**
- 2 vCPU · **4 GB RAM** · 25 GB SSD (manual-post assets accumulate) · reverse
  proxy + TLS in front of `:8787` · `restart: unless-stopped` (compose)

**Local-AI option (Ollama `llama3.2`, no external gateway):**
- Add **8 GB RAM** (16 GB comfortable), 4+ vCPU, 10 GB for models.
  GPU optional — faster tokens, never required.

**Never needed by the app itself:** GPU, Redis, Postgres, Kafka, Kubernetes.
Scale-out is vertical (bigger box) until SQLite write contention says
otherwise; the next bottleneck is provider/API latency (G3/Buffer, AI gateway), which is
already job-queued.

## Serving 1,000 simultaneous users (single GPU host)

Deployment shape and the reasoning behind each choice live in
`deploy/README.md`. Summary of what the numbers mean:

- 1,000 simultaneous users ≈ 1,000 mostly-idle keepalive connections plus tens
  of active requests. nginx absorbs the connections; 4–8 uvicorn workers share
  the requests. This is not 1,000 concurrent SQLite writers, and nothing here
  assumes it is.
- **One host, not several small ones:** the three SQLite files live on local
  disk and cannot be shared across hosts. Multiple hosts would force a Postgres
  migration — a content change, not an infra change.
- **Statics never reach Python:** nginx serves `autoevolve-ui/dist/assets` from
  disk (`deploy/nginx-app.conf`) with a one-year immutable cache. A page load
  costs zero workers.
- **No API caching:** every `/company/*` GET is tenant data with live counters;
  the app sends `Cache-Control: no-store` (`cache_headers` in `app/api.py`).
  ETags were considered for `benchmarks`/`network-stats` and rejected — both
  embed recorded counts, so validators would almost never match.
- **SQLite tuning:** WAL + `synchronous=NORMAL` + 30s busy timeout
  (`core/db.py`). Reads scale with workers; writes serialise, by design.
- **Evidence union is cached per (org, database fingerprint)** in
  `core/evidence.py`: `benchmarks` and `network-stats` rebuilt the whole union
  on every request, which made them roughly half the cost of a Commercial page.
  Any committed write changes the database fingerprint and invalidates the
  entry, so counts are never stale — this is not an HTTP cache. Measured
  effect: those endpoints 2.4–2.8× faster, and `p95` halved at 40 concurrent
  users (`deploy/loadtest/README.md`).
- **No request-count worker recycling:** plan generation and provider calls run
  for minutes. Workers restart on crash (healthcheck) and are gracefully
  replaced once a day at 04:00 (`deploy/daily-jobs.sh reload`).
- **Daily jobs, no wipes:** backup + verify, world-data refresh, graceful
  reload, certificate renewal (`deploy/cron.d/autoevolve`). The databases are
  never deleted by automation.

**Production box:** 8 vCPU / 32 GB RAM / 100 GB SSD + 1× 24 GB GPU
(4–8 API workers at ~400 MB RSS each). Without a GPU — external model gateway —
2 vCPU / 4 GB is sufficient.
