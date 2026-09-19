# API keys: where to get them and how to verify

Start with `make setup`, then `make doctor`. Empty optional values are fine:
the dashboard, `/health`, and `/docs` start without provider keys. A feature
reports `not configured` only when you invoke it.

Recommended tiers:

- Tier 0 (UI only): no keys. Confirm `make doctor` shows `required secrets: ready`
  and `make dev` serves `/health`.
- Tier 1 (AI): `OMNIROUTE_*` (+ `CODING_*` for coding). Needed for drafts,
  research, campaign briefs, scene planning.
- Tier 2 (prospecting): `PROSPEO_API_KEY` + `PDL_API_KEY` or `CE_API_KEY`.
- Tier 3 (sending): `SALES_RESEND_*` with a verified domain.
- Tier 4 (media/publishing): `PEXELS/PIXABAY/COVERR`, `LORDICON_API_TOKEN`,
  plus `engines/g3/config/g3.env` for Buffer/R2.

After any edit: `make doctor`, then restart `make dev` (or the container).

## AI gateway (Tier 1, required for AI actions)

Pick one. Despite the variable name, the endpoint does not have to be OmniRoute.

### Option A: OmniRoute (recommended for routing + fallback)

1. `npm install -g omniroute` (needs Node 22.22.2+; check with `node --version`).
2. Run `omniroute`, open `http://localhost:20128`.
3. Connect at least one provider inside OmniRoute.
4. Copy the key under **Endpoints** (this is the endpoint key, not the
   upstream provider key).
5. Set in `.env`:
   ```dotenv
   OMNIROUTE_BASE_URL=http://127.0.0.1:20128/v1
   OMNIROUTE_API_KEY=<endpoint-key>
   MODEL_FAST=auto/best-fast
   MODEL_REASONING=auto/best-reasoning
   MODEL_FREE=auto/best-free
   MODEL_CODING=auto/best-coding
   MODEL_VISION=auto/best-vision
   CODING_BASE_URL=http://127.0.0.1:20128/v1
   CODING_API_KEY=<endpoint-key>
   CODING_DEFAULT_MODEL=auto/best-coding
   ```
6. Verify:
   ```bash
   curl http://127.0.0.1:20128/v1/models \
     -H "Authorization: Bearer <endpoint-key>"
   ```
   Expect a JSON list containing `auto/best-*`. If Docker is used, replace
   `127.0.0.1` with the Compose service name.

### Option B: Ollama (fully local)

1. Install Ollama, then:
   ```bash
   ollama pull llama3.2
   ollama serve
   curl http://127.0.0.1:11434/v1/models
   ```
2. Set every `MODEL_*` to a real name from `ollama list`. `auto/*` aliases
   do not exist in Ollama.
   ```dotenv
   OMNIROUTE_BASE_URL=http://127.0.0.1:11434/v1
   OMNIROUTE_API_KEY=ollama
   MODEL_FAST=llama3.2
   MODEL_REASONING=llama3.2
   MODEL_FREE=llama3.2
   MODEL_CODING=llama3.2
   MODEL_VISION=llama3.2
   CODING_BASE_URL=http://127.0.0.1:11434/v1
   CODING_API_KEY=ollama
   CODING_DEFAULT_MODEL=llama3.2
   ```
   The `ollama` key is a non-secret placeholder required by OpenAI clients.

### Option C: LiteLLM / hosted OpenAI-compatible API

Use its `/v1` base URL, private key, and exact model IDs:
```dotenv
OMNIROUTE_BASE_URL=https://your-gateway.example/v1
OMNIROUTE_API_KEY=<private-key>
MODEL_FAST=provider/model-name
```
Never commit keys. Verify with the provider's `/v1/models` endpoint first.

## Prospecting + enrichment (Tier 2)

Create each key in that provider's dashboard, paste only into `.env`,
then check `make doctor` and `/company/sales/doctor` in the UI.

| Need | Variable | Get it | Note |
| --- | --- | --- | --- |
| Company/person search | `PROSPEO_API_KEY` | Prospeo dashboard > API | Practical minimum with PDL/CE |
| Extra search source | `LUSHA_API_KEY` | Lusha dashboard > API | Optional `LUSHA_USER_AGENT` |
| Domain/email lookup | `HUNTER_API_KEY` | Hunter dashboard > API | Lookup/verification is billable |
| Enrichment (plan-dependent) | `APOLLO_API_KEY` | Apollo > Settings > API | A configured key does not guarantee endpoint access; check your plan |
| Company profile | `CE_API_KEY` | CompanyEnrich dashboard > API | Preferred for Resolve company |
| Company fallback | `PDL_API_KEY` | People Data Labs dashboard > API key | Fallback for Resolve company |

Credit safety: company-first search is cached; contact/company resolution is
cached. Avoid `force=true` unless the saved record is stale. Start tutorials
with 5 results per provider.

## Outbound email (Tier 3)

1. In Resend: create an API key, verify your sending domain (DNS), and point
   the webhook to `<your-public-URL>/integrations/resend/sales`.
2. Set:
   ```dotenv
   SALES_RESEND_API_KEY=<key>
   SALES_RESEND_DOMAIN=your-verified-domain.example
   SALES_FROM_NAME=Your Company
   SALES_FROM_EMAIL=sales@your-verified-domain.example
   SALES_REPLY_TO_EMAIL=sales@your-verified-domain.example
   SALES_RESEND_WEBHOOK_SECRET=<webhook-secret>
   SALES_AUTO_CONTACT_ENABLED=false
   ```
3. `SALES_FROM_EMAIL` must use the verified domain. Keep auto-contact off
   until a test send to an address you control succeeds.

## Media + publishing (Tier 4)

Stock keys live in root `.env` (G2 inherits them). Buffer/R2 live in the
ignored file `engines/g3/config/g3.env` (created by `make setup` from
`g3.env.example`).

```dotenv
# root .env
PEXELS_API_KEY=<pexels.com/api>
PIXABAY_API_KEY=<pixabay.com/api/docs>
COVERR_API_KEY=<coverr.co/api, video-only>
LORDICON_API_TOKEN=<optional>
OMNIROUTE_IMAGE_MODEL=<optional image model for G2>
```

```dotenv
# engines/g3/config/g3.env
BUFFER_API_KEY=<buffer.com developer token>
BUFFER_ORGANIZATION_ID=<...>
BUFFER_INSTAGRAM_CHANNEL_ID=<...>
BUFFER_X_CHANNEL_ID=<...>
# Extra accounts (dashboard picker + `company-core-g3 --account <name>`):
BUFFER_ACME_API_KEY=<second buffer user token>
BUFFER_ACME_ORGANIZATION_ID=<...>
BUFFER_ACME_INSTAGRAM_CHANNEL_ID=<...>
BUFFER_ACME_X_CHANNEL_ID=<...>
R2_ACCOUNT_ID=<cloudflare R2 account id>
R2_ACCESS_KEY_ID=<...>
R2_SECRET_ACCESS_KEY=<...>
R2_BUCKET=company-core-social-media
R2_PUBLIC_BASE_URL=https://media.your-domain.example
```

Buffer tokens are per Buffer user: grab each one at
`publish.buffer.com/account/api` while logged in as that user, then list
channel IDs with `company-core-g3 channels` (or `--account <name> channels`).
One account is enough to start; add prefixed blocks only when you publish
from multiple brands. The dashboard shows an account picker on every manual
post, and drafts/schedules record which account they used. Validate:
```bash
engines/g3/.venv/bin/company-core-g3 accounts
engines/g3/.venv/bin/company-core-g3 account
engines/g3/.venv/bin/company-core-g3 channels
engines/g3/.venv/bin/company-core-g3 doctor --require instagram --require x
```

Showcase/outro placeholders (`replace-with-your-showcase.mp4`,
`replace-with-your-outro.png`) intentionally do not exist. Point
`MARKETING_G2_SHOWCASE` / `MARKETING_G2_OUTRO` to owned files before
publishing.

## Quick verify checklist

```bash
make doctor
curl http://localhost:8787/health
curl http://localhost:8787/company/sales/doctor -u "$DASHBOARD_USER:$DASHBOARD_PASSWORD"
curl http://localhost:8787/company/marketing/doctor -u "$DASHBOARD_USER:$DASHBOARD_PASSWORD"
```

If AI actions say `not configured`, re-check `OMNIROUTE_API_KEY` and the
`/v1/models` curl above. See `troubleshooting.md` for per-error fixes.
