# AutoEvolve backend system map

> Historical backend-focused snapshot. The current combined backend/frontend map is [system-architecture.md](system-architecture.md), with an [editable diagram](system-architecture.excalidraw).
> For the completed operator-route and onboarding changes, use [V2 closure](v2-closure.md) and [testing/error handling](v2-testing-and-errors.md).

**Snapshot:** 2026-09-24, from the current repository and generated FastAPI OpenAPI contract. The companion [editable Excalidraw diagram](backend-system-map.excalidraw) has a [PNG preview](backend-system-map-preview.png). This describes what is implemented, not what the approved UI screenshots imply.

## What the system actually is

AutoEvolve is one FastAPI application with several domains sharing a primary SQLite database. The React UI is a static build served by FastAPI. The older Jinja cockpit remains available beside it. Sales, marketing, setup, and operations routes call existing services; external providers and background workers are reached from those services. The database is authoritative for leads, drafts, organizations, campaigns, and posts. Provider profiles, research reports, media artifacts, and configuration also have file-backed parts.

The code is **not** organized around screenshot pages. A page is usually a projection over more than one backend domain. For example, the Research and Companies pages read sales leads plus a company-profile cache; a marketing organization is the operator's own brand and is not a prospect company. The current local `data/company.db` contains zero leads, drafts, interactions, profiles, campaigns, manual posts, organizations, and tasks. A correct live UI therefore shows empty states until real records arrive.

The current OpenAPI export contains **84 paths, 93 operations, and 44 schemas**. Seven successful `200` responses have typed response schemas: two Contacts reads, two Companies reads, two operational reads, and a dashboard session check. Most older write and list routes have validated input models but untyped response bodies. The generated React schema is refreshed after backend DTO work.

## Runtime and request path

| Layer | Responsibility | Source |
| --- | --- | --- |
| Browser | React routes `/contacts`, `/research`, `/companies`, `/integrations`, `/settings`; legacy pages under `/` and `/operations/*` | `autoevolve-ui/src/main.tsx`, `app/api.py`, `templates/` |
| Transport/auth | Same-origin `fetch`, HTTP Basic for operator APIs, separate founder token for gated actions | `autoevolve-ui/src/api/client.ts`, `app/security.py`, `app/sales_api.py` |
| FastAPI | Serves HTML/assets; mounts routers; exposes OpenAPI, health, public booking pages and intake webhooks | `app/api.py` |
| API adapters | Typed, read-only Contacts, Companies, Integrations, Settings, and session projections | `app/contacts_api.py`, `app/companies_api.py`, `app/workspace_api.py` |
| Business services | Research/enrichment, drafting/sending, marketing pipeline, monitoring, setup validation | `services/`, `agents/`, `engines/` |
| Persistence | Main SQLite data, ops SQLite data, project artifacts, `.env` configuration | `core/`, `data/`, `projects/`, `engines/g3/config/` |

FastAPI initializes the main database on startup and attempts safe reconciliation of stranded email sends. Sales and marketing tables are also initialized by their store modules. A manual foreground Uvicorn command is a development session, **not** a persistent deployment service. `compose.yaml` exposes port 8787, but this repository has no configured public tunnel hostname or checked-in process-manager unit.

## Route families and boundaries

| Family | Key reads | Key writes/events | Backing logic and data |
| --- | --- | --- | --- |
| Sales `/company/sales` | `/doctor`, `/leads`, `/leads/{id}`, `/drafts/reconcile`, `/hunter/account` | Manual lead, research, prospecting, enrichment, draft, approve, send, reconcile, meeting mark, suppress | `app/sales_api.py` → `services/sales_service.py` → `core/sales_store.py` |
| Contacts `/company/sales/contacts` | Paginated list and detail, typed | Uses existing sales actions rather than owning writes | `app/contacts_api.py` → `core/sales_store.py` |
| Companies `/company/sales/companies` | Paginated list and detail, typed | Uses existing research/profile/prospecting actions | `app/companies_api.py` → `core/company_read.py` → leads and profiles |
| Marketing `/company/marketing` | Doctor, orgs, campaigns, manual posts, asset packs, Buffer accounts, protected media files | Create/review/select/retry campaigns; media/post workflow; org and capability changes | `app/marketing_api.py` → `services/marketing_worker.py`, `services/asset_pack_worker.py` → `core/marketing_store.py`, `core/state.py`, `projects/` |
| Setup `/company/setup` | Masked provider groups, setup step | Test/save known keys, change step | `app/setup_api.py` → `core/setup_keys.py` → root `.env` or G3 env |
| Operations `/company` | Overview, coding tasks, incidents | Coding/apply, monitor runs | `app/company_ops_api.py` → `core/ops_store.py`, `services/monitor.py`, agent orchestration |
| Operational read view `/company/ui` | Typed session, provider-group, and settings summaries | None; existing setup/marketing routes own writes | `app/workspace_api.py` |
| Intake `/integrations` | None | Website/Tally leads, inbound email, Resend event webhook | `app/sales_api.py` → sales service/store; separate webhook secrets and rate limit |
| Legacy HTML | `/`, `/operations/*`, `/meet`, `/calendar` | Founder form and legacy operator controls | `app/api.py` → Jinja templates and same APIs/services |

The `/company/operations/overview` route combines limited sales, marketing, doctor, and history snapshots for the legacy cockpit. It is not a source of paginated domain lists. Existing `GET /company/sales/leads` is capped and the older campaign/manual-post lists are limit based. Contacts and Companies are the first page-oriented typed reads.

## Main persistence model

### `data/company.db`

| Table | Meaning | Linkage and caution |
| --- | --- | --- |
| `sales_leads` | Person leads and company research candidates; identity, source, attribution, stage, scores, metadata | Candidate marker is `metadata_json.company_candidate`; `company_domain` is optional. Sales list scope does not currently enforce active organization. |
| `sales_company_profiles` | Enrichment cache keyed by normalized domain | No foreign key to a company table. Raw provider JSON is stored but should not be exposed in page DTOs. |
| `sales_drafts` | Outreach drafts, approvals, send state, provider ID | Foreign key to lead. Draft status is distinct from lead stage. |
| `sales_interactions` | Inbound replies and outbound activity | Foreign key to lead; provider-message unique index supports deduplication. |
| `sales_events` | Audit/activity trail for sales transitions | Optional lead ID; event payload JSON. |
| `buffer_orgs`, `buffer_org_accounts`, `org_capabilities` | The operator's own brands, social accounts, enabled features | These are **not** prospect companies. Active org ID is in `settings`. |
| `tasks`, `settings` | Agent/marketing tasks and simple key-value state | Setup step and active org live here. |
| `marketing_campaigns` | Campaign request, org/task relation, stage/status and artifact paths | Campaign status is not social publication status. |
| `marketing_variants`, `marketing_events` | Video variants and campaign transition history | Foreign key to campaign. |
| `marketing_manual_posts` | Manually assembled posts with destination/tracked URL, assets and workflow metadata | Separate lifecycle from campaigns; Buffer scheduling is not confirmed publication. |
| `memories` + FTS5 | Brand-isolated recall | A background/agent feature, not a CRM record. |

`core/company_read.py` groups leads and cached profiles by normalized domain for the Companies UI. A company-name-only lead gets its own lead-based identity rather than being merged with every same-name record. The profile cache can also produce a profile-only company. Contacts stay person records. This is a projection, not a new canonical `companies` table.

### Other storage

- `data/company_ops.db`: coding tasks and incidents (`core/ops_store.py`), separate from the main CRM database.
- `projects/<org-slug>/research/research-*.json`: founder research reports shown by the legacy `/` cockpit (`core/dashboard.py`). These are distinct from sales company candidates.
- `projects/` and campaign/asset paths: generated scripts, media packages, asset-pack indexes, handoffs, rendered variants, and manual-post assets.
- Root `.env` and `engines/g3/config/g3.env`: provider and deployment configuration. Setup reads key **presence** and may save known keys after test/backup. Browser responses must never include secret values.

## Important end-to-end workflows

### Company discovery to a contact

`POST /company/sales/research/leads` invokes Prospeo, Apollo and Lusha searches independently. It stores company candidates as sales leads and returns per-provider warnings; a partial provider failure does not imply the entire research failed. `GET /company/sales/companies` projects candidate leads and cached profiles into company rows. `POST /company/sales/leads/{id}/resolve-company` caches domain enrichment. `POST /company/sales/prospect/domain` uses Hunter or Apollo to save person leads, linking them to a candidate where possible. The UI must refetch the authoritative list/detail after each action. Generic fit scores, saved watchlists, hiring/news signals, and research notes are not persisted.

### Contact to approved outbound email

Lead intake or prospecting creates/updates `sales_leads`. A draft action creates `sales_drafts` with status `draft`. Editing is allowed in `draft` or `approved`. Approval is a separate gated transition to `approved`; send atomically claims `sending`, calls Resend with an idempotency key, and records `sent` plus an outbound interaction only after provider confirmation. Ambiguous outcomes remain `sending` or become `send_unknown`; operator reconciliation is required rather than blindly resending. Lead stage may move independently (`draft_ready`, `approved`, `contacted`, `replied`, `suppressed`). The frontend must not flatten these into one status or present an unconfirmed send as successful.

### Inbound message and meeting marker

`/integrations/email/sales` and `/integrations/resend/sales` validate their own webhook credentials/signatures, deduplicate provider IDs, and write `sales_interactions`. Replies can update a lead's stage and support drafting a response through the existing sales path. `POST /company/sales/leads/{id}/schedule-meeting` only writes a manual `metadata.meeting` marker and stage `scheduled`. It is **not** a calendar booking record. `/meet` and `/calendar` are public pages that link/embed an externally configured booking destination.

### Campaign to Buffer handoff

Campaign creation requires an active operator org, creates a task and campaign, then starts a background marketing pipeline. The pipeline writes script/media artifacts, may stop for founder script review, may require real-voice upload, renders variants, then waits for variant selection. The gated G3 handoff creates **Buffer drafts only** (`publish_allowed=False`). Manual posts have their own upload/finalize/Buffer-draft/schedule lifecycle; a scheduled post is not proof of publication. Campaign status, manual-post workflow status, and Buffer status must remain separate in UI projections.

## Authentication and exposure

| Surface | Protection | Consequence |
| --- | --- | --- |
| Operator `/company/*` API | Dashboard HTTP Basic (`DASHBOARD_USER`, `DASHBOARD_PASSWORD`) | Frontend supplies `Authorization` and `X-Requested-With`. Invalid fetch credentials return inline 401 rather than opening a native Basic prompt. |
| Gated sales/setup/campaign/monitor actions | Basic plus `X-Founder-Action-Token` matching `SALES_ACTION_TOKEN` | The action token is separate from the dashboard password and is not hardcoded in React. Some marketing create/org actions are Basic-only; preserve each route's actual gate. |
| Intake/webhooks `/integrations/*` | Route-specific shared secret or signature, plus intake rate limit | They intentionally do not use dashboard Basic. |
| Legacy `/`, `/operations/*` HTML | Server-side Basic dependency | Browser may show a native Basic challenge. |
| React `/contacts`, `/research`, `/companies` HTML and `/assets/*` | Static files are served without Basic; data APIs remain protected | A public hostname can load the sign-in shell, but cannot read operator data without credentials. |
| `/meet`, `/calendar`, `/health`, default `/docs` and `/openapi.json` | Public by current route configuration | Protect operator routes at a reverse proxy/Access layer if exposing the host broadly. |

The current React `AuthGate` tests credentials by fetching **`/company/sales/contacts?page=1&page_size=1`**, even when the user navigates to Research or Companies. Therefore a failure of that probe blocks every React page. The credentials live only in React memory, so a reload asks for sign-in again. After successful sign-in, Research calls `/company/sales/companies`; Companies uses the same endpoint with different page layout and URL state. All of these requests are same-origin relative paths.

## Public links: what is configured and what is not

The repository's current `.env` contains `COMPANY_PUBLIC_URL=http://localhost:8787`, `SALES_PUBLIC_BASE_URL=http://localhost:8787`, and `SALES_CALENDAR_BASE_URL=http://localhost:3000`; `COMPANY_FORMS_URL` and `MARKETING_FORMS_BASE_URL` point to `https://forms.example.com`. No booking override or public tunnel hostname is configured in this checkout. These are local/placeholder values, **not verified public links**.

| Link/path | How it is built | Current implication |
| --- | --- | --- |
| React navigation | Relative `/contacts`, `/research`, `/companies`; FastAPI serves the same `index.html` | Works on any correctly forwarded host if proxy routes all paths and `/assets/*`. No public origin is embedded in React. |
| Sent-email meeting CTA | `SALES_SCHEDULE_URL` or `SALES_PUBLIC_BASE_URL`/`COMPANY_PUBLIC_URL` + `/meet` | With current localhost base, recipients would receive a broken link on their own machine. Set the actual HTTPS hostname before live sending. |
| `/meet` and `/calendar` | External booking URL override or calendar base + event path | Current destination is localhost:3000, so public booking is not ready. An internal manual meeting marker does not confirm a booking. |
| Lead forms / tracked campaign URLs | `MARKETING_FORMS_BASE_URL` or `COMPANY_FORMS_URL`; destination may be overridden per post | Current example.com value is a placeholder, not a real lead form. The fallback `/contact` URL is not an implemented `app/api.py` page. |
| Logo/media links | `COMPANY_PUBLIC_URL` and R2 public base where configured | Public media needs a reachable HTTPS origin and correct read permissions. |

`compose.yaml` maps port 8787, and `docs/deployment.md` describes a reverse proxy/Cloudflare Tunnel, but neither DNS nor a tunnel is provisioned by this repository. A real public-link validation needs the chosen hostname, HTTPS proxy/tunnel routing to port 8787, deployment credentials, and checks of `/assets/*`, `/meet`, calendar destination, forms destination, and webhook endpoints. Do not switch the current placeholders to invented URLs.

## Why Research and Companies appeared to fail

During this audit, requests to `127.0.0.1:8787` initially returned **connection refused** for `/health`, `/research`, and `/companies`: the foreground development server from the previous turn was no longer running. When FastAPI was started and reached `Application startup complete`, both page HTML routes returned HTTP 200, their JS/CSS assets returned HTTP 200, and the configured dashboard credentials returned HTTP 200 for the exact Contacts sign-in probe and Companies list API. That establishes a **server-lifecycle failure** for the observed local outage. A public-host failure could still be different; no real public hostname is configured here to test. Browser-console validation and the user's failing URL/error remain useful to distinguish remote proxy or cached-asset problems.

The durable fix is to run FastAPI under Docker Compose or a process manager and point a stable HTTPS hostname at it. Keeping a tool-command Uvicorn session open is only a temporary local preview.

## Page alignment and next safe work

| Page | Backend readiness | UI consequence |
| --- | --- | --- |
| Contacts | Complete typed list/detail and real draft action | Built and browser-tested. |
| Research / Companies | Company projection plus existing gated research/profile/prospecting actions | Built; no fake watchlists, intent, or signals. |
| Integrations | Typed masked setup-group view and token-gated key test/save | Built and browser-tested; shows key presence and supported key actions, not “connected”, spend or sync history. |
| Settings | Typed org/capability/public-link view and existing org actions | Built and browser-tested; shows actual organizations, feature flags and link configuration, without unsupported team, backup, billing or generic workspace forms. |
| Outreach | Real draft state machine exists but no paginated all-drafts read | Add a typed read projection, preserve separate approve/send/reconcile transitions. |
| Replies | Inbound interactions exist but no inbox read model or intent classification | Add typed inbox projection; show original message, avoid fake intent. |
| Campaigns / Content | Real campaigns, manual posts, asset packs and workers exist with divergent states | Separate source/lifecycle types in typed page views; never claim published from Buffer draft/schedule. |
| Meetings | Only manual lead marker and external booking link | Needs a meeting domain/calendar contract before screenshot-level page behavior. |
| Home | Overview endpoint is a limited composition | Build last from trusted domain reads. |

The companion diagram groups these paths by security boundary, router, service, and store. It is intentionally a **system diagram**, not a screenshot imitation.

## Source and verification index

- Entry and auth: [`app/api.py`](../app/api.py), [`app/security.py`](../app/security.py), [`app/ratelimit.py`](../app/ratelimit.py), [`autoevolve-ui/src/app/Auth.tsx`](../autoevolve-ui/src/app/Auth.tsx), [`autoevolve-ui/src/api/client.ts`](../autoevolve-ui/src/api/client.ts).
- Sales: [`app/sales_api.py`](../app/sales_api.py), [`services/sales_service.py`](../services/sales_service.py), [`core/sales_store.py`](../core/sales_store.py), [`app/contacts_api.py`](../app/contacts_api.py), [`app/companies_api.py`](../app/companies_api.py), [`core/company_read.py`](../core/company_read.py).
- Marketing/setup/ops: [`app/marketing_api.py`](../app/marketing_api.py), [`services/marketing_worker.py`](../services/marketing_worker.py), [`core/marketing_store.py`](../core/marketing_store.py), [`app/setup_api.py`](../app/setup_api.py), [`core/setup_keys.py`](../core/setup_keys.py), [`app/company_ops_api.py`](../app/company_ops_api.py), [`core/state.py`](../core/state.py), [`core/ops_store.py`](../core/ops_store.py).
- Public linking/deployment: [`core/branding.py`](../core/branding.py), [`docs/deployment.md`](deployment.md), [`compose.yaml`](../compose.yaml), [`docs/providers.md`](providers.md).
- Tests: [`tests/test_sales_contracts.py`](../tests/test_sales_contracts.py), [`tests/test_sales_api.py`](../tests/test_sales_api.py), [`tests/test_contacts_api.py`](../tests/test_contacts_api.py), [`tests/test_companies_api.py`](../tests/test_companies_api.py), [`tests/test_setup_api.py`](../tests/test_setup_api.py), [`tests/test_workspace_api.py`](../tests/test_workspace_api.py), [`autoevolve-ui/tests/e2e/`](../autoevolve-ui/tests/e2e/).

The route counts above were checked with a fresh `app.openapi()` export. The empty database counts were read directly from `data/company.db`. No provider calls or production writes were performed for this map.
