# Troubleshooting

If React routes return `503 Frontend has not been built`, install Node.js 22 and run
`npm --prefix autoevolve-ui ci` followed by `npm --prefix autoevolve-ui run build`,
then restart FastAPI. `/` now redirects to `/home`; it does not serve the retired
founder cockpit. A valid sign-in is still required before protected API reads.

Start with:

```bash
make doctor
curl http://localhost:8787/health
curl http://localhost:8787/company/sales/doctor -u "$DASHBOARD_USER:$DASHBOARD_PASSWORD"
curl http://localhost:8787/company/marketing/doctor -u "$DASHBOARD_USER:$DASHBOARD_PASSWORD"
```

## Smoke-test a change

After touching routes, action gates, or send handling, run the HTTP smoke suite. It uses the server at `http://127.0.0.1:8787` if one is running and starts a temporary uvicorn child otherwise (killed on exit):

```bash
make smoke
.venv/bin/python scripts/smoke_actions.py --only gate            # one block only
.venv/bin/python scripts/smoke_actions.py --report logs/smoke-report.md
```

What one run proves, over real HTTP:

- `health` / `auth-required` — the server answers and dashboard routes demand Basic auth (`401`).
- `gate-no-token:*` — all `P0-2` gated routes return `403` without `X-Founder-Action-Token`.
- `gate-with-token:*` — with the token the gate falls through: `setup/step` re-writes the current value (state unchanged), the six marketing routes `404` on dummy ids before any side effect.
- `reconcile-*` — the `P0-1` `send_unknown` flow: seeded draft appears in `GET reconcile`, token gate `403`, `delivered=false` re-parks it as `approved`, `delivered=true` marks it `sent` with the provider message id.
- `resume-park-*` — a draft stranded *outside* the Resend idempotency window gets `409` with the window message and parks; it never reaches the provider.
- `backup-roundtrip` — the `P0-4` `backup.sh → verify_backup.py → restore.sh --verify` round trip exits `0`.
- `webhook-budget-separate` / `intake-burst-429` / `sign-in-burst-429` — the `P0-3` limiter buckets are separate; bursts end in `429` with `Retry-After`, invalid intake bodies create no leads, and a valid sign-in still works after the failure burst. These run last because they fill the `RATE_LIMIT_*` buckets for up to a minute.
- `startup-reconcile*` — a stranded in-window draft is released at boot. Skipped when the server was already running (no startup log) or when `SALES_RESEND_API_KEY` is set (the child is then spawned with `SALES_SEND_RECONCILE_ON_STARTUP=false` so a restart can never fire a real email).

Seeded rows use `smoke-<tag>@example.com` and are deleted at the end; a run never sends email. Exit code is `0` unless a check `FAIL`s (`WARN`/`SKIP` are allowed). Unit-level detail (SQLite connection reuse, idempotency-key bytes, limiter internals) stays in `make test`.

## Common failures

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `401` | Missing dashboard/action/webhook secret | Check the required header and matching `.env` value |
| `403` from provider | Plan restriction, blocked request, or unverified domain | Read the provider response; verify account access instead of retrying repeatedly |
| `409` | Action does not match the current lifecycle state | Complete the preceding review, approval, or selection step |
| `422` | Payload validation failed | Compare field names and types with `/docs` and `lead-intake.md` |
| `502` | Upstream provider or model gateway failed | Read the nested method, URL, status, and body; test that provider directly |
| Cloudflare `524` | A synchronous operation exceeded proxy timeout | Confirm background workers are used and inspect origin logs |
| Empty search results | Filters are too narrow or provider has no match | Broaden industry/location once; do not repeatedly force the same lookup |
| Model connection failure | Wrong base URL, key, alias, or router is stopped | Query `/v1/models`; use real model IDs with Ollama; see `keys.md` |
| `openai.OpenAIError: Missing credentials` at startup | Empty `OMNIROUTE_API_KEY` on an old install | Update to a build with the `not-configured` fallback in `core/models.py`, or set any non-empty `OMNIROUTE_API_KEY`; dashboard starts keyless, AI actions fail only when invoked |
| Media doctor unavailable | G1/G2/G3 environment was not installed | Run `make setup-engines` |
| Showcase/outro unavailable | Placeholder paths were not replaced | Point both variables to owned files that exist locally |
| FFmpeg error | FFmpeg is absent or source media is invalid | Run `ffmpeg -version` and validate the input file |
| Buffer draft failure | Missing channel ID or media URL is not public | Run the G3 doctor and open the R2 media URL without authentication |
| Resend domain error | Sender domain is not verified | Verify the domain and make `SALES_FROM_EMAIL` use that domain |
| `No matching distribution` for OpenHands | Setup is running on Python 3.11 or older | Install Python 3.12 and run `make setup PYTHON=python3.12` |

## Logs and retries

Run `make dev` in a terminal and preserve the complete exception, including upstream status and
response body. Retry only after changing the failing condition. Contact and company resolution are
cached; `force=true` deliberately bypasses that protection and may consume another credit.

For a failed campaign, correct missing configuration or media first, then use **Retry**. Campaigns
waiting for review must be approved or regenerated instead of retried.
