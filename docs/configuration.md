# Configuration

Run `make setup`, then edit the generated `.env`. Empty provider values disable only the related
feature; the dashboard, `/health`, and `/docs` still start. Run `make doctor` after any change.
AI actions are the exception: they need `OMNIROUTE_API_KEY` and report `not configured` until it
is set. See [API keys](keys.md) for where to get every key.

## Required local settings

`DASHBOARD_USER`, `DASHBOARD_PASSWORD`, `SALES_ACTION_TOKEN`, `SALES_INTAKE_SECRET`,
`SALES_EMAIL_WEBHOOK_SECRET`, and `APP_ENCRYPTION_KEY` are generated automatically.
`APP_ENCRYPTION_KEY` encrypts per-organization publisher secrets; keep it stable.
Change `COMPANY_NAME`, `COMPANY_PUBLIC_URL`, `COMPANY_FORMS_URL`, and
`COMPANY_BRAND_LOGO_URL` for your brand.

## AI gateway

Set `OMNIROUTE_BASE_URL` and `OMNIROUTE_API_KEY` to an OpenAI-compatible endpoint. Model route
names are controlled by `MODEL_FAST`, `MODEL_REASONING`, `MODEL_FREE`, `MODEL_CODING`, and
`MODEL_VISION`. Coding operations additionally use the `CODING_*` values. Despite the environment
variable name, the endpoint does not have to be OmniRoute; Ollama, LiteLLM, and hosted
OpenAI-compatible APIs can be used. See [Model Routing](model-routing.md) for the option summary
and [API Keys](keys.md) for canonical values.

## Optional providers

| Capability | Environment variables |
| --- | --- |
| Prospecting | `HUNTER_API_KEY`, `APOLLO_API_KEY`, `PROSPEO_API_KEY`, `LUSHA_API_KEY` |
| Company enrichment | `PDL_API_KEY`, `CE_API_KEY` |
| Outbound email | `SALES_RESEND_API_KEY`, `SALES_RESEND_DOMAIN`, `SALES_FROM_EMAIL` |
| Reply webhooks | `SALES_RESEND_WEBHOOK_SECRET` |
| Stock media | `PEXELS_API_KEY`, `PIXABAY_API_KEY`, `COVERR_API_KEY` in the G2 environment |
| Social publishing | Buffer and R2 values in `engines/g3/config/g3.env` |
| Calendar | `SALES_CALENDAR_BASE_URL`, `SALES_CALENDAR_EVENT_PATH` |
| Website accounts | `AUTH_RESEND_API_KEY`, `AUTH_FROM_EMAIL`, `AUTH_RESEND_DOMAIN` (fall back to the sales Resend values) |
| Per-org publishers | `APP_ENCRYPTION_KEY`, `PUBLIC_BASE_URL` for media links |

## Website authentication

Signup is public by default. `AUTH_SIGNUP_ENABLED=false` closes it. Verification
links use `AUTH_VERIFY_BASE_URL` (default `http://localhost:4181/verify`; set
`https://example.com/verify` in production). The email link puts the token in
the URL fragment. `AUTH_COOKIE_DOMAIN=example.com` shares the session with
`app.example.com`; `AUTH_COOKIE_SECURE=true` is required in production.
`AUTH_ALLOWED_ORIGINS` must list both the base and app origins. For local
development only, `AUTH_EXPOSE_DEV_TOKEN=true` returns the verification link in
the signup/resend response; leave it false in production. See
[Website authentication](authentication.md) for the session and free-org model.

The bundled engine paths in `.env.example` work from the repository root
(e.g. `MARKETING_G1_BIN=engines/g1/.venv/bin/company-core-g1`). The showcase and outro
placeholder files intentionally do not exist. Set both paths to your own licensed files before
publishing media. Set `COMPANY_BRAND_LOGO_URL` to a publicly reachable HTTPS PNG before sending
email; a localhost URL cannot be loaded by recipients.
