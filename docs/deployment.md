# Deployment

Run Company Core behind HTTPS. SQLite is suitable for a single application process; use one
worker or migrate the stores before horizontal scaling.

Native deployment requires Python 3.12+, Node.js 22 for the UI build, Make,
OpenSSL, and FFmpeg. Docker is an optional packaging alternative, not a requirement.

## Native service

```bash
make setup
npm --prefix autoevolve-ui ci
npm --prefix autoevolve-ui run build
.venv/bin/uvicorn app.api:app --host 127.0.0.1 --port 8787
```

React is the sole operator UI, served by the same FastAPI process. `/` redirects to `/home`.
Available pages: `/home`, `/onboarding`, `/contacts`, `/companies`, `/research`, `/outreach`,
`/replies`, `/meetings`, `/campaigns`, `/content`, `/integrations`, and `/settings`.
Trailing slashes redirect to canonical paths and preserve query filters. Old `/operations/*`
and `/legacy/operations/*` bookmarks redirect to their replacements; the retired history
page redirects to Home. Historical records remain available through the existing APIs.
The former founder form at `POST /` has been removed. Domain actions remain available through
existing authenticated APIs and their React workflows.

Unknown browser addresses return HTTP 404 with a React not-found screen. Unknown API paths
return JSON 404; they never fall back to the app. `/meet` and `/calendar` remain public booking
utilities, independent of the operator UI.

Use systemd, Supervisor, or another process manager to keep the command running. Put Caddy,
Nginx, or Cloudflare Tunnel in front of `http://127.0.0.1:8787`.

## Docker Compose

Create local secrets before starting Compose:

```bash
make init
docker compose up --build -d
docker compose logs -f company-core
```

The Compose service persists `data/`, `projects/`, and `config/` on the host. If OmniRoute or Ollama
runs outside the container, do not assume `127.0.0.1` reaches the host. Use a private reachable host
address, `host.docker.internal` where supported, or put both services on the same Compose network
and use the model service name. Do not expose an unauthenticated model endpoint publicly.

## Cloudflare deployment

Recommended public topology:

```text
autoevolve.site / www.autoevolve.site
  -> Cloudflare Pages (marketing + auth pages)
  -> /api/auth/* Pages Function -> https://app.autoevolve.site/api/auth/*

app.autoevolve.site
  -> Cloudflare Tunnel -> nginx:80 -> uvicorn:8787
```

Use **Cloudflare Tunnel**, not a DNS-only origin record. The app host needs no
public inbound ports; all traffic flows through Cloudflare where DDoS/WAF rules
apply. The marketing/auth Pages project is separate from the app origin.

### DNS and Pages

- `autoevolve.site` / `www.autoevolve.site` -> Pages, proxied
- `www` -> 301 to the chosen canonical host (recommended: apex `autoevolve.site`)
- `app.autoevolve.site` -> Tunnel CNAME, proxied
- No DNS-only web records
- No public origin IP in DNS

The website repository (`indoha-commits/website-autoevolve`) owns `public/_redirects`; it handles `/signup`, `/signin`, `/login`, and
`/verify`. The website repository Pages Function `functions/api/auth/[[path]].js` proxies auth API
requests to `AUTH_API_ORIGIN` and forwards the original Cloudflare visitor IP.

### Tunnel

Create or reuse a remotely managed tunnel and route:

```text
app.autoevolve.site -> http://nginx:80
```

Keep nginx private. If using Docker Compose, the optional Tunnel overlay is
`deploy/compose.tunnel.yaml`; it removes published nginx ports and runs
`cloudflared` on the Compose network. One connector is sufficient for launch
with a single SQLite host; a second connector only protects against connector
failure, not host failure.

### Auth cookie and origins

```dotenv
AUTH_VERIFY_BASE_URL=https://autoevolve.site/verify
AUTH_COOKIE_NAME=__Secure-autoevolve_session
AUTH_COOKIE_DOMAIN=autoevolve.site
AUTH_COOKIE_SECURE=true
AUTH_ALLOWED_ORIGINS=https://autoevolve.site,https://app.autoevolve.site
VITE_APP_URL=https://app.autoevolve.site
VITE_MARKETING_URL=https://autoevolve.site
COMPANY_PUBLIC_URL=https://app.autoevolve.site
PUBLIC_BASE_URL=https://app.autoevolve.site
SALES_PUBLIC_BASE_URL=https://app.autoevolve.site
```

The auth link uses `/verify#token=…`; the token is not sent in a request URL.
The verify page requires an explicit click.

### Cloudflare Free plan

Free-plan features are sufficient for launch, with limits:

- one rate-limiting rule, IP-keyed, short fixed window
- Free Managed Ruleset only; five simple custom rules; no Log action
- 100,000 Pages Function/Worker requests per day
- no super bot management or enterprise log export
- approximately 125-second proxy read timeout

Use the single rate-limit rule on `/api/auth/*`. Keep Bot Fight Mode off until
you verify it does not challenge API/webhook traffic. Turnstile can be added to
signup/login without a paid Cloudflare plan.

### Origin client IP

Cloudflare supplies `CF-Connecting-IP`. nginx forwards it as
`X-AutoEvolve-Client-IP`; the app prefers that header when
`RATE_LIMIT_TRUST_PROXY=true`. Without this, every visitor collapses into the
tunnel/nginx address for app-level rate limits.

### Fresh database

A new installation must start data-free:

```bash
.venv/bin/python scripts/bootstrap_db.py
.venv/bin/python scripts/bootstrap_db.py --check
```

This creates the empty schema only. It does not seed an organization, user,
contact form, demo lead, or world record. The first verified website signup
creates the first free organization. Use `scripts/promote_org.py --org <id>
--plan paid` only for the operator account you intentionally created.

### Long-running requests

Cloudflare's proxy read timeout is about 125 seconds by default. Plan
generation is capped near 90 seconds; manual-post publishing can take longer.
The publish UI uses the async job endpoint:

```text
POST /company/marketing/manual-posts/{id}/publish/async
GET  /company/marketing/publish-jobs/{job_id}
```

Keep synchronous endpoints under the edge timeout. Do not rely on nginx's
longer `proxy_read_timeout` to bypass Cloudflare.
