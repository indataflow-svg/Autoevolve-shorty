# Provider setup

All external providers are optional. Add credentials only for the workflow you use, restart Company
Core, and inspect `/company/sales/doctor` or `/company/marketing/doctor`. For exact acquisition
steps and verify commands, start with [API Keys](keys.md).

| Provider | Purpose | Configuration | Credit-sensitive action |
| --- | --- | --- | --- |
| Prospeo | Company/person search and contact resolution | `PROSPEO_API_KEY` | Search and resolve contact |
| Lusha | Additional prospect search/contact source | `LUSHA_API_KEY`, optional `LUSHA_USER_AGENT` | Search and contact lookup |
| Hunter | Domain discovery, email lookup/verification | `HUNTER_API_KEY` | Lookup and verification |
| Apollo | Optional enrichment where the account permits its endpoints | `APOLLO_API_KEY` | Provider-dependent lookup |
| CompanyEnrich | Company profile by domain | `CE_API_KEY` | Company resolution |
| People Data Labs | Company profile fallback | `PDL_API_KEY` | Company resolution |
| Resend | Approved outbound email and event tracking | `SALES_RESEND_*` | Sending email |
| Pexels | Stock image/video search | `PEXELS_API_KEY` | Provider request |
| Pixabay | Stock media fallback | `PIXABAY_API_KEY` | Provider request |
| Coverr | Additional stock-video search | `COVERR_API_KEY` | Provider request; selected download only |
| Buffer | Social draft creation, explicit scheduling, and experimental post insights | `BUFFER_API_KEY` and channel IDs | Draft/schedule mutations; read-only post status and available metrics for saved Buffer IDs |
| Cloudflare R2 | Public media hosting for Buffer | `R2_*` | Upload/storage |

## Sales providers

Provider keys are created in each provider's account dashboard; see [API keys](keys.md) for
per-provider locations, plan notes, and verify commands. Put them only in `.env`. Company
Core's company-first workflow saves search results before contact resolution, caches resolved
contacts, and caches company profiles. Avoid `force=true` unless you intentionally want another
billable lookup.

You do not need every sales provider. A practical minimum is Prospeo plus one company enrichment
provider. Hunter and Lusha can be added as alternatives. Apollo features depend on which endpoints
your account plan permits; a configured key does not guarantee access to restricted endpoints.

The service-first path at `/services` accepts a service description and a target of 1–25 contacts.
AI drafts buyer keywords and titles, then one bounded people-search request runs against Apollo
first and Prospeo only if more contacts are needed. It saves names, titles, and companies as
contact previews; it does not automatically reveal email or phone. Lusha preview search is
disabled by default because its credit cost depends on the account. Optional rolling 24-hour
local request caps can be set in `.env`:

```dotenv
SERVICE_APOLLO_PREVIEW_CAP_24H=20
SERVICE_PROSPEO_PREVIEW_CAP_24H=1
SERVICE_LUSHA_PREVIEW_CAP_24H=0
```

Prospeo validates an inherited or edited market against its free location suggestions before
using it as a location filter. Broad regions such as "Africa" may not be supported; in that case
the search continues without a location filter and the service page warns that results may be
outside the requested market. A Prospeo `NO_RESULTS` response is shown as no matches, not a
provider outage. Use a supported country or city when geography is essential.

These caps count preview search attempts made by this application; free Prospeo location
suggestions are separate. They cannot read credits spent
outside AutoEvolve or guarantee a provider account remains within its free allowance.
The current [Apollo people-search documentation](https://docs.apollo.io/reference/people-api-search)
lists that preview endpoint at zero credits. The current [Prospeo search documentation](https://prospeo.io/api-docs/search-person)
lists one credit for a results page. Check your own plan before raising the caps.

## Resend

Canonical values and webhook setup live in [API keys](keys.md#outbound-email-tier-3).
Summary: verify your sending domain with Resend, set `SALES_RESEND_*` so that
`SALES_FROM_EMAIL` uses the verified domain, point the webhook at
`/integrations/resend/sales`, and keep automatic contact disabled until a
controlled test email succeeds.

## Media providers

Set `PEXELS_API_KEY`, `PIXABAY_API_KEY`, and/or `COVERR_API_KEY` in the root `.env`; G2 inherits the
application environment. Coverr is video-only and its short-lived download URL is requested only
after a candidate wins selection. Stock results still require operator review for relevance and licensing. Lordicon is
optional and uses `LORDICON_API_TOKEN`.

## Buffer and R2

Canonical values live in [API keys](keys.md#media--publishing-tier-4). Summary: run `make setup`
(or `make init` for env files only on an existing install), then edit the ignored file
`engines/g3/config/g3.env` with per-account `BUFFER_*` and `R2_*` values. The R2 public URL must
use HTTPS and allow anonymous reads of published media. Validate before a campaign:

```bash
engines/g3/.venv/bin/company-core-g3 account
engines/g3/.venv/bin/company-core-g3 channels
engines/g3/.venv/bin/company-core-g3 doctor --require instagram --require x
```
