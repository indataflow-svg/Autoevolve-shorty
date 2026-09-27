# AutoEvolve system architecture

**Source snapshot:** 2026-09-27, inspected from this repository. The companion [editable system diagram](system-architecture.excalidraw) depicts the same runtime and trust boundaries. This is a map of implemented code, not a promise that optional providers or a public deployment are configured.

## 1. How the application is assembled

The deployable application is one FastAPI process (`app/api.py`) serving both JSON routes and a built React/Vite bundle. The React app lives in `autoevolve-ui/` and uses same-origin relative API paths. React is the sole operator UI; Jinja remains only for the public booking pages `/meet` and `/calendar`. A separate Cloudflare Email Routing worker source exists in `company-sales-email-ingress/`; it is **not** part of the Compose service.

```text
Browser / operator
  ├─ GET /contacts, /companies, ... → FastAPI serves React index + /assets
  ├─ GET/POST /company/* → Basic auth → router → service/store → SQLite/files/provider
  └─ GET /, /operations/history → redirect to React Home
      GET /meet, /calendar → public booking utilities

Website/Tally/Resend/Email Routing
  └─ POST /integrations/* → rate limit + route-specific secret/signature → sales service/store
```

`app/api.py` initializes the main database and seeds configured organizations on startup. It also attempts safe reconciliation of email drafts stranded in `sending`; a failure in that recovery path does not block boot. `/health` only returns `{ "status": "ok" }`; it is not a provider or database health report. The exported `autoevolve-ui/openapi.json` is the generated route/model inventory; CI checks it for drift. `scripts/export_openapi.py` exports the FastAPI contract, and `npm --prefix autoevolve-ui run generate:api` turns it into `src/api/schema.ts` with `openapi-typescript`.

## 2. Frontend structure

| Part | Implemented role | Source |
| --- | --- | --- |
| Entry and routing | React 19, React Router, twelve operator pages; unknown pages render a genuine 404 | `autoevolve-ui/src/main.tsx` |
| Sign-in | `AuthGate` checks `GET /company/ui/session`; credentials stay in React memory, so reload requires sign-in again | `autoevolve-ui/src/app/Auth.tsx` |
| Transport | Same-origin `fetch`; exact case-sensitive paths and JSON names; Basic header, `X-Requested-With`, optional `X-Founder-Action-Token`; typed `ApiError` for 401/403/404/422/429/5xx | `autoevolve-ui/src/api/client.ts` |
| API adapters | Domain functions and types from generated OpenAPI schemas | `autoevolve-ui/src/api/{contacts,companies,workflows,operational}.ts` |
| Server state | TanStack Query; keys include page/filter inputs, targeted invalidation after mutations, previous list data during refetch where used | `autoevolve-ui/src/pages/*.tsx` |
| Shared UI | Fixed navigation/topbar, metric/state/drawer primitives, TanStack Table workflow table | `autoevolve-ui/src/components/{Shell,Primitives,WorkflowTable}.tsx` |
| Styling | Project CSS tokens and page styles; Vite build emits `autoevolve-ui/dist` | `autoevolve-ui/src/styles.css`, `autoevolve-ui/vite.config.ts` |

The navigation's search field searches the **active page**, not one global cross-domain index. Pages use URL search parameters for applicable search, filters, sort, pagination, and selected record; temporary forms and entered action tokens use local component state. The frontend uses generated response types for the typed read views, and React-consumed actions use typed success models.

### Page-to-contract map

| Browser page | Primary read(s) | Existing write/action(s) surfaced |
| --- | --- | --- |
| `/onboarding` | `GET /company/ui/onboarding` | Existing-record orchestration through `/company/setup/onboarding/*`; see [V2 Closure](v2-closure.md) |
| `/home` | `GET /company/ui/home` | Links to the underlying domain pages; no invented dashboard mutation |
| `/contacts` | `GET /company/sales/contacts[/{id}]` | `POST /company/sales/leads`, `POST /company/sales/leads/{id}/draft` |
| `/research` | `GET /company/sales/companies[/{id}]` | `POST /company/sales/research/leads`, `/prospect/domain`, `/leads/{id}/resolve-company` |
| `/companies` | Same company list/detail projection with a different page mode | Same company research/prospect/profile actions where applicable |
| `/outreach` | `GET /company/ui/outreach[/{draft_id}]` | `POST /company/sales/drafts/{id}/update`, `/approve`, `/send` |
| `/replies` | `GET /company/ui/replies[/{reply_id}]` | `POST /company/sales/leads/{id}/draft` for an eligible reply |
| `/meetings` | `GET /company/ui/meetings[/{lead_id}]` | `POST /company/sales/leads/{id}/schedule-meeting` (manual marker) |
| `/campaigns` | `GET /company/ui/campaigns[/{id}]` | `POST /company/marketing/campaigns`, `/{id}/approve-script`, `/{id}/retry` |
| `/content` | `GET /company/ui/content`, Buffer accounts/insights and authenticated asset URLs | `POST /company/marketing/asset-packs`, `/manual-posts/{id}/buffer-schedule` |
| `/integrations` | `GET /company/ui/integrations` | `POST /company/setup/keys/test`, `/keys` |
| `/settings` | `GET /company/ui/settings` | `POST /company/marketing/orgs`, `/orgs/active`, `/orgs/{id}/capabilities` |

The `GET /company/ui/*` workflow routes in `app/workflow_views_api.py` and workspace routes in `app/workspace_api.py` are **read projections**. They join or summarize existing state; they do not own the write semantics. Contacts are read from `sales_leads` through `app/contacts_api.py`; Companies are assembled by `core/company_read.py` through `app/companies_api.py`.

## 3. Backend modules and request boundaries

| Router / surface | Models and logic | State or external dependency |
| --- | --- | --- |
| `app/contacts_api.py`, `/company/sales/contacts` | Pydantic `Contact`, `ContactDetail`, `ContactsPage`, metrics; paginated reads | `core/sales_store.py` |
| `app/companies_api.py`, `/company/sales/companies` | `CompanySummary`, `CompanyDetail`, `CompaniesPage`; domain/lead identity | `core/company_read.py` over leads and profile cache |
| `app/workflow_views_api.py`, `/company/ui` | `RepliesPage`, `MeetingsPage`, `OutreachPage`, `CampaignsPage`, `ContentView`, `HomeView` | `core/sales_store.py`, `core/marketing_store.py`, `core/state.py`, asset-pack files |
| `app/workspace_api.py`, `/company/ui` | `SessionStatus`, `IntegrationsView`, `SettingsView` | Organization/capability state, masked provider-key presence, configured public URLs |
| `app/sales_api.py`, `/company/sales` | `LeadIntake`, research, prospecting, enrichment, draft/send, suppression, meeting payloads; founder-gated action router | `services/sales_service.py`, Hunter/Apollo/Prospeo/Lusha/Resend and sales store |
| `app/marketing_api.py`, `/company/marketing` | Organizations, campaigns, manual posts, asset packs, Buffer draft/schedule/accounts/insights | `core/marketing_store.py`, `core/state.py`, worker subprocesses, G1/G2/G3, Buffer |
| `app/onboarding_api.py`, `/company/ui/onboarding`, `/company/setup/onboarding` | Typed resume projection and guided setup actions | One existing settings record; existing sales candidates, contacts, and drafts |
| `app/setup_api.py`, `/company/setup` | Provider groups, key test/save, setup step | `core/setup_keys.py`, root `.env` and G3 env |
| `app/company_ops_api.py`, `/company` | Operations overview, coding tasks/apply, incidents, monitor runs | `core/ops_store.py`, services and agents |
| `app/sales_api.py`, `/integrations` | Website/Tally lead intake, inbound email, Resend events | Sales service/store; route-specific webhook validation |
| `app/api.py`, HTML/public | `/`, `/operations/history`, legacy redirects, `/meet`, `/calendar`, `/health`, React entry routes, `/static`, `/assets` | React operator frontend, compatibility redirects, public booking templates |

The same `app/sales_api.py` defines a Basic-auth sales router, a Basic-plus-founder-token action router, and an independently protected public intake router. `app/api.py` mounts `/company/*` routers with `Depends(authenticate)`. `/integrations/*` receives `rate_limit_intake` and validates its own secret/signature inside each handler. A missing `DASHBOARD_PASSWORD` is an explicit configuration error. `SALES_ACTION_TOKEN` is checked through `X-Founder-Action-Token` only on routes that declare `verify_founder_action`; some marketing creation and org actions require Basic only. Do not infer a gate from the page or button label.

The React client distinguishes 401 (clear invalid sign-in), 403 (keep sign-in, report forbidden), 404, 422 field issues, 429 `Retry-After`, and 5xx (preserve existing data while reporting failure). Basic credentials and action tokens are different. The action token is entered for gated actions and is not hardcoded into production frontend code.

## 4. Persistence and identity

| Storage | Concrete records | Key distinction |
| --- | --- | --- |
| `data/company.db` via `core/state.py` | `buffer_orgs`, `buffer_org_accounts`, `org_capabilities`, `tasks`, `settings` | Organizations are **our own marketing brands**, not prospect companies. |
| Same database via `core/sales_store.py` | `sales_leads`, `sales_drafts`, `sales_interactions`, `sales_events`, `sales_company_profiles` | A lead/contact is a person or candidate record. A domain-keyed profile is cached enrichment, not a canonical company entity. |
| Same database via `core/marketing_store.py` | `marketing_campaigns`, `marketing_variants`, `marketing_events`, `marketing_manual_posts` | A campaign, content asset, manual post, Buffer draft, and scheduled post have different states. |
| Same database via `core/memory.py` | `memories` plus FTS5 index and triggers | Brand-isolated agent recall; not CRM records. |
| `data/company_ops.db` via `core/ops_store.py` | `coding_tasks`, `incidents` | Separate operations database. |
| `projects/` | Research reports, campaign scripts, media, voice handoffs, rendered variants, asset packs, post assets | File artifacts referenced from store rows or read directly by service/projection. |
| `.env`, `engines/g3/config/g3.env` | Secrets and provider configuration | Presence is not provider health; UI receives masked status, never raw keys. |

`core/company_read.py` groups leads and profile-cache entries by normalized domain. A lead with only a company name retains lead-based identity; a profile-only domain can appear without a contact. There is no canonical `companies` table. The projection does not turn a company candidate into a verified enriched company profile. Current list views are not a general multi-tenant organization isolation layer; sales reads and the Home totals operate over the shared sales store. The Content view is bounded to the latest 200 manual posts and up to 100 asset packs for the active org and exposes truncation flags. These are material limits when interpreting aggregate UI counts.

## 5. Actual workflow paths

1. **Research → company projection → contact.** `POST /company/sales/research/leads` runs provider-specific discovery and can return partial warnings. It stores candidates in `sales_leads`. The company read projection groups candidates and cached domain profiles. `resolve-company` caches enrichment; `prospect/domain` creates person leads. Research output, company identity, and contact identity remain separate.
2. **Contact → outreach → provider-confirmed send.** A lead can produce a `sales_drafts` row. Draft update/approval are guarded transitions. Send claims `sending`, calls Resend with idempotency handling, and records `sent` only after provider confirmation. A timeout or crash can leave `sending` or `send_unknown`; reconciliation is a separate action. `approved` does not mean sent, and `sent` does not establish delivery.
3. **Inbound email → reply → manual meeting marker.** Website/Tally and email/Resend hooks authenticate independently and write sales leads/interactions. The Replies projection reads inbound email reply interactions and marks whether a new reply draft is currently allowed. The Meetings projection reads `sales_leads.metadata_json.meeting` where status is `scheduled`; the matching write records a manual marker and lead stage, **not** a confirmed calendar booking. `/meet` and `/calendar` link/embed an external configured destination.
4. **Campaign → artifacts → Buffer.** Campaign creation stores a task/campaign and starts a subprocess pipeline. G1 generates campaign/script material, G2 renders media variants, a founder selects a variant, and G3 hands selected content to Buffer as **drafts**. Manual posts have a separate asset/finalization path and an explicit gated Buffer scheduling endpoint. Buffer schedule success means an accepted scheduled post, not publication. Insights call G3's Buffer post query for a saved Buffer post ID; unavailable provider responses are errors, not zero engagement.
5. **Configuration and operations.** Setup exposes configured-key presence and tests/saves approved keys; Settings manages operator organizations/capabilities. Coding-task/monitor APIs live in the same FastAPI process but use `data/company_ops.db`. Those operations are separate from sales lead and marketing campaign state.

## 6. Runtime, exposure, and validation

`Dockerfile` builds the React bundle in a Node stage and runs Python 3.12 with Uvicorn bound to `0.0.0.0:8787` (`0.0.0.0` is a bind address; local browsers use `127.0.0.1:8787`). `compose.yaml` defines one `company-core` service, port `8787:8787`, and persistent mounts for `data/`, `projects/`, and `config/`. A native development server is `make dev`; a production process manager or Compose is needed for always-on hosting. The repository documents a Cloudflare Tunnel example in `docs/deployment.md`, but `compose.yaml` does not provision a public hostname or tunnel. The external email worker has its own `wrangler.jsonc` and must be deployed/configured separately. There is no always-running daily scheduler in the FastAPI/Compose topology; campaign and asset-pack workers are launched in response to actions. The current `/docs` and `/openapi.json` paths are public FastAPI defaults.

Useful verification commands:

```bash
make dev
curl -i http://127.0.0.1:8787/health
curl -s http://127.0.0.1:8787/openapi.json
make lint
make test
npm --prefix autoevolve-ui run typecheck
npm --prefix autoevolve-ui run lint
npm --prefix autoevolve-ui run build
npm --prefix autoevolve-ui run test
npm --prefix autoevolve-ui run test:e2e
npm --prefix autoevolve-ui run test:e2e:workflows
npm --prefix autoevolve-ui run test:e2e:sales-workflow
npm --prefix autoevolve-ui run test:e2e:onboarding
```

Playwright's four configurations run the **real FastAPI app** against isolated SQLite fixtures in `tests/contacts_fixture_server.py`, `tests/workflow_fixture_server.py`, `tests/sales_workflow_fixture_server.py`, and `tests/onboarding_fixture_server.py`; provider replacements are test-only. Backend route tests live under `tests/test_*`, and G1/G2/G3 have engine-local tests. The checked-in OpenAPI export is a generated snapshot; regenerate it after contract changes and compare the exact route casing before debugging React rendering.

## 7. Where to start when tracing a failure

Trace `browser URL → React page/query key → src/api adapter → exact HTTP path/header/status/body → FastAPI router/model → service/state guard → SQLite/file/provider → refetch`. In particular, never translate a failed read into an empty list, a missing provider key into a healthy integration, a meeting marker into a booking, or a Buffer draft into publication. `/health` confirms process responsiveness only; inspect the specific route and provider result to locate the first divergence.
