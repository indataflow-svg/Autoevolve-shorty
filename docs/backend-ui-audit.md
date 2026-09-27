# Backend alignment audit for the remaining UI pages

> Historical gap audit. Current operator routes and onboarding behavior are recorded in [V2 closure](v2-closure.md).

**Implementation update (2026-09-24):** Research/Companies, Integrations, and Settings now have typed React pages. Integrations reads `GET /company/ui/integrations` and uses the existing founder-token-gated `/company/setup/keys/test` and `/company/setup/keys` actions. Settings reads `GET /company/ui/settings` and uses the existing Basic-authenticated marketing organization create, active selection, and capability actions. Sign-in probes `GET /company/ui/session`; it no longer depends on Contacts. The generated OpenAPI export now has 84 paths, 93 operations, and 44 schemas. The audit below records the pre-implementation gaps and remains relevant for the unsupported screenshot concepts.

**Implementation update (2026-09-25):** Replies and Meetings now have typed read projections at `/company/ui/replies` and `/company/ui/meetings`, with React pages and existing founder-token-gated sales actions. Replies displays original inbound messages and can create a reply draft only while that message remains the lead's latest eligible interaction. Meetings displays and creates manual meeting markers; it does not claim calendar booking confirmation. The earlier “adapter needed” notes below describe the original gap, while unsupported concepts remain unsupported.

For the complete route, storage, auth, workflow, and public-link relationships, see [the backend system map](backend-system-map.md) and its [editable Excalidraw diagram](backend-system-map.excalidraw).

This is a read-only audit of the existing FastAPI contract, business logic, SQLite schema, legacy pages, tests, and the eight approved screenshots other than Contacts. Each reference image was inspected at its original 1536 × 864 resolution. The screenshots specify layout and interaction patterns; persisted data and existing workflows determine what can be shown as real.

## Overall finding

The backend is functional but organized by **sales leads and drafts**, **marketing campaigns and manual posts**, **organizations and setup**, and **operations**. It is not organized around the screenshot pages. The alignment is therefore **partial and scattered**, not a missing backend and not a complete match. Most pages can reuse existing records and actions, but a few screenshot concepts require new domain decisions and persistence rather than a visual adapter.

The current local `data/company.db` has zero leads, drafts, interactions, company profiles, campaigns, manual posts, and organizations. Populated UI validation needs isolated test fixtures or actual operator data; production pages must render truthful empty states. The generated OpenAPI document matches the live app's 79 paths. It describes request bodies for many writes, but only 2 of 25 sales endpoints and 0 of 31 marketing endpoints have typed `200` response schemas. The two typed sales responses are the new Contacts reads. New page DTOs should be typed in Pydantic and generated into TypeScript.

All `/company/*` API routes use dashboard Basic authentication. Sales writes, setup key writes, campaign review/selection/draft/retry, and Buffer scheduling have an additional founder action token gate. Other existing marketing creation and handoff routes rely on dashboard authentication without that extra gate. Preserve the actual gate on each route; do not infer a gate from the screenshot. The outbound send flow separately requires saved draft approval, then a send call, then provider confirmation. A `send_unknown` draft must be reconciled by an operator.

Current list scope also differs by domain: `GET /company/marketing/campaigns` reads campaigns across organizations, while manual posts and asset packs use the active organization; the sales leads and Contacts lists do not filter by `org_id`. A screenshot “program” or active-org tab must not claim scoped counts until the read contract enforces that scope. Existing list endpoints are capped (`list_leads` at 200, campaigns at 100, manual posts at their own limit) and do not provide page/total semantics.

The meaningful Pydantic input contracts are `LeadIntake`, `LeadResearchRequest`, `DraftUpdatePayload`, `MeetingScheduledPayload`, `InboundEmailPayload`, `CampaignLaunchRequest`, `ManualPostSessionRequest`, `AssetPackRequest`, `BufferScheduleRequest`, `MarketingOrgCreateRequest`, `OrgCapabilitiesRequest`, and `SetupKeysPayload`. Their many untyped response bodies are the principal OpenAPI gap for a generated frontend client.

## Page-by-page mapping

### Outreach — `09-outreach.jpeg`

- **Real records:** `sales_drafts` holds lead ID, channel, kind, subject, body, status, approval/send timestamps, and provider message ID. `sales_leads` holds contact and company identity. `sales_interactions` and `sales_events` hold delivery and reply activity. `GET /company/sales/leads/{id}` nests drafts and activity; `GET /company/sales/drafts/reconcile` exposes ambiguous sends.
- **Real actions:** lead draft/preview, saved-draft update, approve, send, and reconcile endpoints exist in `app/sales_api.py`. The store enforces `draft → approved → sending → sent`, with `send_unknown` for ambiguous delivery. LinkedIn preview/draft exists, but the email send endpoint does not imply automated LinkedIn sending.
- **Scattered/adapter needed:** there is no paginated all-drafts endpoint. A read-only outreach list/detail DTO should join drafts to leads and expose actual status, channel, timestamps, and latest activity. Counts can be computed from records. Keep `send_unknown` visible; do not collapse it into “sent.”
- **Unsupported screenshot fields/actions:** owner, due date, follow-up queue, persisted personalization reason, and program are not normalized. “Needs edit,” “follow-up due,” and “Approve & send” are not single backend transitions. The latter must remain two confirmed actions. Trend arrows in KPI cards have no historical analytics source.

### Replies — `07-replies.jpeg`

- **Real records:** inbound email is stored in `sales_interactions` with `direction=inbound`, `kind=reply`, original subject/body, sender/thread metadata, and timestamp. Related lead and company data are available through `GET /company/sales/leads/{id}`. Resend/Cloudflare intake and deduplication are in `services/sales_service.py`.
- **Real actions:** drafting a reply uses the existing lead draft path when the latest interaction is inbound; saved drafts can be edited, approved, and sent. Suppression is a gated lead action. A meeting can be manually marked scheduled, and `/calendar` links to an external booking page.
- **Scattered/adapter needed:** there is no replies inbox endpoint. A read-only paginated inbox DTO can join inbound interactions to leads and derive message snippets, last received, and thread activity without replacing original message text.
- **Unsupported screenshot fields/actions:** persisted intent labels, confidence, “positive,” “not now,” “objection,” priority/needs-review state, high-value account flag, extracted signals, suggested response, notes, and meeting-request counts are absent as authoritative fields. Sending an automatically suggested reply, creating a meeting booking, or adding a note cannot be claimed as supported merely because a button appears in the screenshot. Subject-equals-`unsubscribe` does trigger suppression on intake; arbitrary opt-out intent classification does not exist.

### Meetings — `06-meetings.jpeg`

- **Real records:** a gated `POST /company/sales/leads/{id}/schedule-meeting` writes `metadata.meeting` on a lead (`status`, free-text `scheduled_for`, note, update time, `source=manual`) and changes the lead stage to `scheduled`. `/meet` and `/calendar` show or link to an externally configured booking URL.
- **Scattered/adapter needed:** scheduled leads could form a limited meeting list, with only fields actually stored. The external calendar is not a local meeting store and cannot confirm that a booking occurred.
- **Unsupported screenshot fields/actions:** dedicated meeting ID, type, duration, attendees, join URL, agenda, outcome, no-show state, follow-up state, opportunity/value, source campaign relation, weekly schedule, reschedule, and booking confirmation have no authoritative local model/API. This page needs an explicit meeting-domain design and calendar integration before the reference can be reproduced functionally.

### Research — `02-research.jpeg`

- **Real records:** provider research actions at `/company/sales/research/leads`, `/research/suggestions`, and `/prospect/domain` persist company candidates as `sales_leads` with `metadata.company_candidate` and research filters. Resolved company profiles are cached by domain in `sales_company_profiles` and attached to lead detail. Separate founder research reports are JSON files under `projects/<slug>/research`, surfaced in the legacy `/` page via `core/dashboard.py`.
- **Scattered/adapter needed:** a company-centric read model could group candidate leads and resolved profiles by normalized domain, while keeping actual contacts distinct. Research report files and sales prospecting records are separate sources and should not be silently merged. The existing `/operations/sales/discovery` page already performs provider search and resolution.
- **Unsupported screenshot fields/actions:** a canonical company ID/list, saved searches, watchlists, monitored/new-signal counts, normalized market/employee-size filters, technologies, hiring/news signals, account owner, recommendation, and notes are not established backend contracts. Provider summary JSON may contain some enrichment facts, but those are optional and untyped. Do not turn an organization (`buffer_orgs`, the operator's own brands) into a researched prospect company.

### Campaigns — `05-campaigns.jpeg`

- **Real records:** `marketing_campaigns`, `marketing_variants`, and `marketing_events` carry campaign brief/objective/buyer/topic, org, channels, pipeline status/stage, timestamps, artifacts, variant state, and history. `GET /company/marketing/campaigns` and `/{id}` expose projections. `marketing_manual_posts` and lead `campaign_id`/`post_id`/UTM fields provide tracked links and some attribution.
- **Real actions:** create a campaign, approve or regenerate its script, select a ready variant, create **draft-only** Buffer handoff, upload real voice, and retry eligible failures. The gated actions enforce stage checks. Existing `/operations/marketing/campaigns` is a legacy operator view.
- **Scattered/adapter needed:** page-oriented pagination, filters, status counts, org labels, post attribution, and next allowed action should be read-only projections over the existing state machine. Campaign and manual-post statuses are different lifecycles. `org_id` is not the screenshot's “program” unless product semantics explicitly define it that way.
- **Unsupported screenshot fields/actions:** owner, committed launch date, impressions, clicks, conversion rate, performance trend, and provider-confirmed “published” status are not available from the current campaign model. Lead attribution can be counted from saved lead IDs; it cannot stand in for impressions or conversion. A G3 Buffer draft is not publication, and the current backend intentionally keeps `publish_allowed=False`.

### Content — `03-content.jpeg`

- **Real records:** three sources exist: campaign script/media/variant artifacts; file-backed asset packs with scenes and assets; and `marketing_manual_posts` with title, platform, post type, caption, tracked URL, assets, workflow/Buffer status, and lead attribution. `/company/marketing/asset-packs`, `/manual-posts`, and `/campaigns` expose these. Existing `/operations/marketing/assets` and `/operations/marketing/publishing` are legacy views.
- **Real actions:** create asset packs, upload/finalize manual posts, generate captions, create Buffer drafts, schedule manual posts, approve/regenerate campaign scripts, and select variants. The exact action gate differs by route. Buffer scheduling confirms a queue/schedule operation, not publication.
- **Scattered/adapter needed:** a content index needs a discriminated union or separate tabs keyed by source type; do not flatten all three into one fictitious lifecycle. `post_type` and platform are separate from workflow status. Asset URLs and campaign previews already have protected file routes.
- **Unsupported screenshot fields/actions:** common content owner, generic “in review/approved/published” lifecycle across every source, published-this-month count, content-level performance analytics, and a universal edit/review/regenerate action do not exist. Campaign script review is real; generic manual-post review is not. Publication must not be inferred from `scheduled`.

### Integrations — `01-integrations.jpeg`

- **Real records/reads:** `GET /company/setup/providers` returns masked configuration groups and key presence; sales/marketing `/doctor` return configuration and diagnostic checks; `/company/marketing/buffer-accounts` and `/company/sales/hunter/account` expose limited provider information. `/company/operations/overview` bundles diagnostics. `/docs` exposes API documentation.
- **Real actions:** known provider keys can be tested and saved via gated `/company/setup/keys/test` and `/keys`; no arbitrary provider plugin installation route exists.
- **Scattered/adapter needed:** a provider catalog can map known providers to category, configured state, capabilities, and diagnostics while accurately distinguishing **configured**, **diagnostic OK**, and **live connected**. Never return secret values. Avoid calling credit-consuming provider checks simply to render the page.
- **Unsupported screenshot fields/actions:** a reliable per-provider connected/healthy state, recent sync/activity, 30-day API spend, usage quota, webhook log, provider notes, and “add any integration” are not persisted as a unified contract. Google Calendar is currently a configured booking URL, not a connected integration record.

### Settings — `04-settings.jpeg`

- **Real records/reads:** `buffer_orgs` stores own-org name/slug/domain; `org_capabilities` stores enabled features; `/company/marketing/orgs` and org capability routes read these. `/company/setup/providers` masks key presence, `/step` stores setup progress, and doctor/monitor routes expose scoped diagnostics. Sender details and many defaults are environment configuration. Backup/verify/restore are command-line scripts.
- **Real actions:** create/set active org and change org capabilities use dashboard authentication; known provider-key saves and monitor runs additionally require the founder action token. A monitor run may attempt repair. These are not generic profile settings.
- **Scattered/adapter needed:** a safe read-only settings summary can combine org/capability/setup/diagnostic facts. Any form field that is editable needs a validated, authorized endpoint with explicit persistence and tests; do not write directly to `.env` from browser code.
- **Unsupported screenshot fields/actions:** editing workspace name/slug, team administration, security policies, notifications, industry/market/size/research-depth defaults, value proposition/persona, sender signature, billing/license, backup schedule/retention/size, and “Run backup now” have no equivalent settings API. A backup CLI script is not a browser action. “All systems operational” cannot be inferred from key presence.

## Navigation entries without approved screenshots

- **Companies:** no approved `Companies` reference image or company list/detail API. `sales_company_profiles` is a domain-keyed enrichment cache; `buffer_orgs` represents the operator's own organizations; company candidates live in lead metadata. A company page requires a clear identity and deduplication rule before its DTO and UI.
- **Home:** no approved `Home` image. `GET /company/operations/overview` already aggregates real sales, marketing, history, and diagnostics, but list limits and untyped responses make it a summary source, not a replacement for individual pages. Build this after the domain pages so it composes their trusted queries.

## Backend alignment work, in order

1. **Shared read contracts:** add typed, paginated, filterable read-only DTOs for outreach drafts, inbound replies, campaigns, content sources, and company candidates. Preserve existing stores and write routes; generate the TypeScript contract from OpenAPI. This is the least disruptive way to align scattered data with page layouts.
2. **Workflow projections:** expose only backend-confirmed status, available actions, and counts. Keep sales draft status distinct from lead stage; marketing campaign status distinct from manual-post and Buffer status. Refetch after every external or gated action.
3. **Missing domains:** decide whether Meetings needs a persisted booking/calendar model, whether Replies needs an explicit reviewed classification, and whether Research needs canonical company/watchlist/saved-search records. These cannot be truthfully created by frontend adapters alone.
4. **Operational surfaces:** model provider health/usage and settings only where real diagnostics or persisted controls exist. Leave unsupported screenshot cards and controls absent or clearly unavailable until the backing contract exists.
5. **Build order:** Outreach first (real state machine), then Campaigns and Content (real workflows but divergent states), then Research/Companies and Replies, then Meetings once its domain is specified, then Integrations and Settings; compose Home last. Reuse the Contacts shell, table, metrics, drawer, API client, and URL-state patterns.

## Evidence locations

- API and authentication: `app/api.py`, `app/security.py`, `app/sales_api.py`, `app/marketing_api.py`, `app/setup_api.py`, `app/company_ops_api.py`, `autoevolve-ui/openapi.json`.
- Persistence and services: `core/sales_store.py`, `core/marketing_store.py`, `core/state.py`, `core/dashboard.py`, `core/setup_keys.py`, `services/sales_service.py`, `services/marketing_worker.py`, `services/monitor.py`.
- Existing UI and validation: `templates/operations_sales.html`, `templates/operations_marketing.html`, `templates/index.html`, `tests/test_sales_contracts.py`, `tests/test_sales_api.py`, `tests/test_marketing_live_ui.py`, `tests/test_marketing_store.py`, `tests/test_setup_api.py`, `tests/test_operations_ui.py`.
