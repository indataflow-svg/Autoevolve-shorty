# Configuration

Run `make setup`, then edit the generated `.env`. Empty provider values disable only the related
feature; the dashboard, `/health`, and `/docs` still start. Run `make doctor` after any change.
AI actions are the exception: they need `OMNIROUTE_API_KEY` and report `not configured` until it
is set. See [API keys](keys.md) for where to get every key.

## Required local settings

`DASHBOARD_USER`, `DASHBOARD_PASSWORD`, `SALES_ACTION_TOKEN`, `SALES_INTAKE_SECRET`, and
`SALES_EMAIL_WEBHOOK_SECRET` are generated automatically. Change `COMPANY_NAME`,
`COMPANY_PUBLIC_URL`, `COMPANY_FORMS_URL`, and `COMPANY_BRAND_LOGO_URL` for your brand.

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

The bundled engine paths in `.env.example` work from the repository root
(e.g. `MARKETING_G1_BIN=engines/g1/.venv/bin/company-core-g1`). The showcase and outro
placeholder files intentionally do not exist. Set both paths to your own licensed files before
publishing media. Set `COMPANY_BRAND_LOGO_URL` to a publicly reachable HTTPS PNG before sending
email; a localhost URL cannot be loaded by recipients.
