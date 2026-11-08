# AutoEvolve functionality reference

Every capability the product actually has, department by department, verified
against the source at commit `1023af7`. Not a plan and not a roadmap: this is
what the code does.

**How to read this.** Each section states what the department does, then the
routes that expose it, then the tables it persists to, then the honest limits.
Counts: **178 HTTP operations across 151 OpenAPI paths**, **39 tables in
`company.db`** (plus 2 ops and 1 workflow database), **1 engine (G3)**, **512
tests** (510 pass, 1 skipped, 1 known pre-existing flake, listed in §11), plus
**10 website tests**.

A note on counting: [API Reference](API-REFERENCE.md) reports a higher route
and table count because it extracts route decorators and `CREATE TABLE`
statements textually, so a path served by two routers is listed twice. The
figures above come from the OpenAPI contract and a table enumeration that
deduplicates. Both are correct at what they measure; the OpenAPI number is the
one to quote.

**Authority.** Where this document and the code disagree, the code wins. Two
generated sources are the tie-breakers: the OpenAPI contract (`/openapi.json`)
and the code itself. See [API Reference](API-REFERENCE.md) for every public
function signature, and [System Architecture](system-architecture.md) for the
runtime diagram.

---

## 1. What the product is

One system that runs a company:

1. **Research** who to sell to, from real provider data.
2. **Sell** to them — email and LinkedIn outreach, drafted by AI, approved and
   sent by a human, with replies and meetings tracked back to the source.
3. **Market** — upload owned carousel/video assets, hand them to Buffer through
   G3, and keep post-level attribution.
4. **Automate** — workflow preparation unlocks at 80% company data, then
   founder-approved workflows and governance runs.
5. **Improve itself** — the coding agent and orchestrator change the codebase,
   with checkpoints, validation, and reversible applies.

The through-line is **attribution**: every lead carries the post and UTM
parameters that produced it (and a campaign id when the source supplies one),
so marketing and sales share one record.

Generated campaigns and video production were removed on 2026-10-28. §5 records
what was removed; the rest of this document describes the current surface.

### The operating states

| Department | Terminal states | Stored in |
|---|---|---|
| Sales lead | `won` `lost` `suppressed` (of 11 stages) | `sales_leads.stage` |
| Draft | approved → sent, or abandoned | `sales_drafts.status` |
| Manual post | `saved` → `buffer_draft` → `scheduled`, then provider `sent` / `failed` / `pending` | `marketing_manual_posts` |
| Company context | `workflow_ready` at ≥80% completeness | `company_context` |

---

## 2. Get Started (company context)

The React `/onboarding` page is now a **four-card company-context wizard**, not
the old sales-calibration funnel. It writes the same org-scoped
`company_context` used by Workflows and Commercial.

**Cards**

| Card | Required answers | Canonical groups |
|---|---|---|
| Company identity | company name, company description; website optional | `company` |
| What you sell | product/offer name, product/offer description | `product` |
| Who buys and why | ideal customer, problem | `customer`, `problem` |
| First objective | primary objective, starting state | `objective`, `marketing_stage` |

Each card has a **Next** and **Back** button, validates its required fields,
and saves through the existing full-replacement context endpoint. A failed save
leaves the card open and shows the backend reason.

**Read/write routes:** `GET /company/context` for the wizard read; `PUT
/company/context` for each saved card. The PUT is founder-gated; a verified
website session satisfies the gate for its own organization.

**Completion and handoff.** `GET /company/context` returns the derived
`completeness_percent`, `missing`, and `workflow_ready` flags. The wizard shows
the handoff state when `workflow_ready` is true (the same 80% gate used by
Workflows). The handoff contains exactly two choices:

- **Your daily loop** — included in free: open Workflows.
- **Commercial outreach** — free accounts see a blurred locked card with an
  Upgrade CTA; paid/operator accounts see an accessible Open Commercial card.

The Upgrade CTA opens the marketing site at `/?demo=1`, which auto-opens the
existing Book a demo dialog. `Home` also exposes `onboarding_ready` so a
completed context stops showing the stale “Finish first-run setup” prompt.

**Same source of truth.** Get Started and Commercial both read/write the
canonical `company_context`; there is no second company form. Commercial keeps
its richer offer/ICP/account/pipeline setup for paid work. The legacy
`ProgramState` onboarding API and its global settings record were removed; the
new page is the only onboarding contract.

## 3. Sales

The largest department: **~45 routes** (sales, workflow views, and the custom
form routers), 6 tables, 6 provider integrations, and
the most careful failure handling in the codebase.

### 3.1 Lead intake (unauthenticated, shared-secret + rate limited)

`POST /integrations/leads/website` · `/integrations/leads/tally` ·
`/integrations/leads/form` · `/integrations/email/sales` ·
`/integrations/resend/sales`

Five ingress paths — website form, Tally webhook, custom form, inbound email,
Resend webhook. Each verifies its own shared secret
(`X-Company-Core-Lead-Secret`, `X-Sales-Email-Webhook-Secret`, Svix signature
for Resend). These routes sit **outside** dashboard auth and are
rate-limited per client IP by `rate_limit_intake` (`WINDOW_SECONDS`,
`WEBHOOK_PATHS`), with a separate bucket for failed dashboard sign-ins.

`upsert_lead(payload)` merges by email, passes `utm_*`/campaign/post
parameters through **verbatim**, and returns `(lead, created)` so
`maybe_auto_contact_lead` can react to genuinely new leads only.

#### Custom lead forms (`core/form_store.py`, `app/forms_api.py`)

A form is a slug plus an ordered field list (`form_definitions` table, one
seeded `contact` form). The same definition drives two submission paths that
land in exactly the same place:

- **Hosted page** `GET/POST /f/{slug}` — branded, mobile-clean, honeypot
  field, no secret (it is a public form). POST redirects to `?sent=1`.
- **Shared endpoint** `POST /integrations/leads/form` — for external tools
  (an indataflow form, any POSTing service). Accepts JSON
  (`{"form": "contact", "answers": {...}}` or a flat object of answers) or
  form-encoded bodies; enforces `X-Company-Core-Lead-Secret` when
  `SALES_INTAKE_SECRET` is set.

Known keys (`email`, `full_name`, `company`, `phone`, `message`, …) map onto
the lead record; every non-empty answer is also kept under its form label as
an inbound `form`/`submission` interaction, so Replies shows the submission
as clean question/answer rows. `GET/POST/PATCH /company/commercial/forms`
(authenticated + founder-gated writes) manage definitions. `GET
/company/commercial/forms/config` returns the one-screen connection kit —
the absolute endpoint URL plus `X-Company-Core-Lead-Secret` when set — shown
in the Commercial → Forms "Connect an external form tool" panel. When
`COMPANY_FORMS_URL` is empty, the workspace "Lead forms" link defaults to the
hosted contact form at `{COMPANY_PUBLIC_URL}/f/contact`.

### 3.2 Research and enrichment

| capability | routes | providers |
|---|---|---|
| Domain prospecting | `POST /company/sales/prospect/domain` | Hunter, Apollo |
| Market/ICP search | `POST /company/sales/research/leads` | Prospeo, Lusha, Apollo |
| Filter suggestions | `POST /company/sales/research/suggestions` | Prospeo, Lusha |
| Company resolution | `POST /company/sales/leads/{id}/resolve-company` | CE, PDL (cached) |
| Contact resolution | `POST /company/sales/leads/{id}/resolve-contact` | Prospeo (cached) |
| Email enrichment | `POST /company/sales/leads/{id}/enrich` | Hunter |
| LinkedIn discovery | `POST /company/sales/leads/{id}/discover-linkedin` | Apollo, Prospeo |

Five provider clients, each with a typed error: `HunterClient`/`HunterError`,
`ApolloClient`/`ApolloError`, `LushaClient`/`LushaError`,
`ProspeoClient`/`ProspeoError`, `PeopleDataLabsClient`/`PeopleDataLabsError`.

**Caching is explicit.** Resolution results are cached per domain/lead; `force=true`
spends another provider credit. `_ordered_company_profile_providers("auto")`
falls back through available providers in order.

**One registry, two search modes.** `services/provider_registry.py` declares
every supplier once (data points, keys, error types, validators); fan-out
research and the `waterfall_company_search` (stop when `target` unique
candidates are held, skipped providers logged, never called) both run off
it. Governed research uses the waterfall with `target=max_contacts`, so a
small ceiling means small provider spend. Adding a tool is one `register()`
call — no branching code anywhere else.

**Honest limits:** every provider needs a paid key. No key → that route fails
with the provider's error preserved, never a silent empty result. Credit spend
is real money and is bounded only by `claim_service_provider_request`.

**Provider contracts (verified against vendor OpenAPI, 2026-10).** Lusha V3
takes `{ids, reveal[]}` for enrich and `{pagination, filters, options}` for
prospecting — `requestId/contactIds/revealEmails`, `searchText`, and string
`sizes` are not real fields and used to 400 or silently miss. CompanyEnrich
`location`/`socials` are nested `{name}` objects, `socials.linkedin_url` is
the LinkedIn source, and there are no specialities/target-market fields.
Research input stays verbatim: Prospeo runs one exact rung and rejects an
unrecognised location instead of searching worldwide (`widen=True` restores
the old ladder explicitly), and `score_lead` carries no industry or geography
bonuses — ranking reflects deliverability signals (verified email, title,
phone), never ICP fit or origin. Merged market results are ordered best-first
by query relevance (literal name/domain match on the request wording — a loose
provider hit like a law firm for "freight forwarder" can never top an exact
match), then cross-provider corroboration, then neutral completeness, with each
item's `match` naming the providers and signals behind its position. OpenCorporates (any plan token, free included) verifies each merged candidate against its home registry and counts as corroboration; unknown registries and misses simply add nothing.

### 3.3 Drafting

`POST /company/sales/leads/{id}/draft-preview` (discard) and `/draft` (persist).
`agents/sales.py` provides `draft_outreach(lead) -> OutreachDraft`;
`services/sales_service.py` provides `preview_draft` / `build_draft`, each with
a **deterministic fallback** (`_FallbackDraft`,
`_simple_auto_contact_draft`) so a gateway outage degrades to a usable draft
instead of an error.

`company_enrich.py` derives `personalization_points` and `pain_points` from the
resolved company profile — this is what makes a draft specific rather than
generic.

LinkedIn: `POST /leads/{id}/linkedin-preview` and `/linkedin-draft` with
`piece ∈ {invite, dm1, dm2}` (`LINKEDIN_PIECES`, `LINKEDIN_KINDS`), backed by
`agents/linkedin.py::draft_linkedin_outreach`.

### 3.4 The send path — the most carefully built part

Five separate actions, deliberately not collapsed:

```
update → approve → send          # human edits first
claim_draft_for_send → attempt   # atomic claim, then send
release_send_claim               # on failure
mark_sent / mark_send_unknown    # outcome recording
```

Routes: `POST /drafts/{id}/update`, `/approve`, `/send`, `/reconcile`;
read-only `GET /drafts/reconcile`.

**Why so much machinery.** Email send has an unavoidable failure mode: you
click send, the network dies, and you don't know if it went. Rather than
pretend otherwise:

- `claim_draft_for_send` takes an atomic claim so two operators can't
  double-send.
- `mark_send_unknown` records *unknown*, distinct from sent and distinct from
  failed — `GET /company/sales/drafts/reconcile` lists exactly those drafts for
  a human decision, and `reconcile_sending_drafts()` runs at startup
  (`_reconcile_stranded_sends`).
- Resend idempotency keys (`_draft_idempotency_key`), plus
  `ResendAmbiguousError` and `ResendIdempotencyConflictError` as distinct
  outcomes.
- **A draft is never labelled sent** without the provider response *and* a
  refreshed record.

### 3.5 Inbound, replies, meetings

`ingest_resend_event` (delivery, bounce, open, reply) → `_resolve_inbound_lead`
matching on `in_reply_to`/`references` → `mark_replied`. Bounces, replies, and
meetings all **stop the follow-up sequence**. The `email.received` branch
shares `_ingest_received_email` with the `POST /company/sales/inbox/sync`
mirror: when the Resend webhook was down or unconfigured, the Replies page's
"Sync inbox now" pulls recent received mail (Resend stores it regardless)
through the identical ingest path, so re-syncs are no-op duplicates and
senders that match no lead are reported as unmatched instead of dropped.

`POST /leads/{id}/schedule-meeting` records a manual marker.
`POST /leads/{id}/suppress` (`reason='founder_request'`) suppresses permanently.

`POST /leads/{id}/meeting-request` (founder-gated) is the booking-link flow:
the founder offers 1–5 slots and a note, which are saved as
`metadata.meeting.status='awaiting_booking'` (the lead stage does **not**
move), and an email listing the slots is sent to the contact's address via
the same Resend path as drafts. Each slot links to the public
`GET/POST /book/{lead_id}` page; the contact choosing a slot there is the
only thing that records the meeting — `mark_meeting_scheduled(...,
source='booking_link')` sets the marker, moves the stage to `scheduled`, and
emits `meeting.scheduled`. If Resend is unconfigured the request is still
saved and the API returns an honest warning (same pattern as enrichment).

### 3.6 Views

`GET /company/ui/outreach[/{id}]` · `/replies[/{id}]` · `/meetings[/{lead_id}]`
· `/company/sales/contacts[/{id}]` · `/companies[/{company_id}]`

Paginated projections over joins of `sales_drafts`, `sales_leads`,
`sales_interactions`, `sales_company_profiles`. Replies cover both inbound
channels — email replies and form submissions — expose whether an inbound is
the lead's latest interaction and the exact thread id, and offer the
meeting-request action. Meetings cover both marker states, `scheduled` and
`awaiting_booking` (the offered slots are listed until the contact chooses).

**Explicitly unsupported by the backend** (documented, and the UI omits them
rather than faking them): outreach owner, due date, follow-up queue,
personalization reason, reply intent/sentiment/objection classification,
meeting confirmation/attendees/duration/call link/outcome/no-show rate,
opportunity value.

---

## 4. Marketing: manual posts and Buffer

**One path only.** Generated campaigns, asset packs, scripts, media search, and
video production were removed on 2026-10-28. The remaining marketing surface is
an operator uploading media they own and handing it to a publisher.

**Publishers.** Buffer is the default and keeps its exact G3 path. A manual post
stores `publisher` (default `buffer`) plus provider-neutral `publisher_status`,
`publisher_post_ids`, `publisher_account`, and `publisher_send_confirmation`.
`GET /company/marketing/publishers` lists capabilities, and
`GET /company/marketing/publisher-accounts` lists accounts. A signed webhook
scheduler can be configured with `PUBLISHER_WEBHOOK_*`; its contract is in
[publishers.md](publishers.md). The generic routes are
`POST /manual-posts/{id}/publish`, `/publish/draft`, `/publish/confirm`, and
`GET /publish/insights`; the legacy `/buffer-*` routes remain aliases.

```
Content page -> POST /manual-posts/session -> /manual-posts/{id}/assets
  -> /manual-posts/{id}/finalize -> caption + tracked URL
  -> G3 draft/schedule -> Buffer -> provider confirmation -> attribution
```

- `POST /manual-posts/session` → `/assets` (upload) → `/finalize` — three steps
  so uploads survive a failed finalize.
- `POST /manual-posts` — single-shot with `File[]` assets.
- `POST /manual-posts/preview` — read-only caption, CTA, and tracked-link
  preview built by the same helpers as finalize. Nothing is persisted.
- `GET /buffer-accounts` — named accounts configured in `g3.env`; keys never
  leave the server.
- `POST /manual-posts/{id}/buffer-draft` → `/buffer-schedule` →
  `GET /manual-posts/{id}/buffer-insights`.
- `POST /manual-posts/{id}/buffer-confirm` (founder-gated) records Buffer's
  verdict per saved post ID. Only an explicit `sent` counts as sent; the local
  `buffer_status` is left untouched.

**Attribution.** `_tracked_post_url` embeds `utm_campaign`, `campaign_id`,
`post_id`, `source_detail`, and `post_type`; `_lead_attribution` reads them back
onto the lead. `marketing_manual_posts` and `sales_leads` store the same fields
verbatim.

**Honest limits.** A Buffer draft or scheduled post is never labelled published
unless the provider reports it sent. Buffer insights require a personal API key
and are experimental; values can be absent or delayed. Content search/pagination
run over a bounded loaded set and the page says when it is truncated.

**Orgs and capabilities.** `GET/POST /company/marketing/orgs`, `POST
/orgs/active`, `GET|POST /orgs/{org_id}/capabilities`. Each Buffer org has its
own accounts and capability flags.

**G3 remains** (`engines/g3`, `g3.env`): validate the handoff, upload media to
R2, create Buffer drafts or scheduled posts. It never claims publication.

---

## 5. Video production — removed

The Video page, `app/video_api.py`, `core/video_store.py`, `services/video/`,
`services/renderers.py`, the Hunyuan/MI300X queue, the five `video_*` tables,
and their data were removed on 2026-10-28. There are no video routes or tables.
Manual posts may contain one MP4 that the operator uploads; the app does not
render or transform it.

## 6. Engineering / self-improvement

The system modifies its own codebase.

- `agents/coder.py` (~50 functions): chat index, workspaces, task files,
  **repo snapshots**, checkpoints, `undo_task`, validation runs, compact
  memory. `CATEGORY_MODEL_MAP` routes task categories to models;
  `classify_task` infers the category.
- **Bounded repair loops:** `MAX_REPAIR_CYCLES`, with
  `PROTECTED_REPAIR_PREFIXES`/`PROTECTED_REPAIR_NAMES` and `EXCLUDED_*` lists so
  repairs cannot rewrite protected files. `restore_file_from_task_checkpoint`
  rolls back individual files.
- `agents/coding_orchestrator.py`: architect plans → editor applies in a
  worktree → `apply_task` publishes. Separate plan and edit models.
- `tools/repo_intelligence.py`: repo map, validation error counting, file
  excerpts — the orchestrator's read-only view of the code.

Routes: `POST /company/coding/tasks` · `GET /coding/tasks[/{id}]` ·
`POST /coding/tasks/{id}/apply` · `GET /company/incidents[/{id}]` ·
`POST /company/monitor/run[/{service}]` · `GET /company/operations/overview`.

`services/monitor.py` reads `config/services.json` (health URL, severity,
recovery command, diagnostic and canary commands, code-error patterns) and
`handle_failure` escalates: known failure → recovery command; code-like error →
incident record; unknown → optional AI repair, gated by
`allow_auto_promote`/`ai_repair_on_unknown` (both `false` in the shipped
config).

---

## 7. Research and memory

- `agents/researcher.py` — a three-stage pipeline: `plan_queries` (cheap fast
  model fans out queries) → `gather_evidence` (no-LLM fetch + verify, where the
  latency tail lives) → `synthesize_report` (reasoning model, no tools).
  Structured outputs `SearchPlan`, `Source`, `ResearchReport`. The separation
  exists so the expensive model never does retrieval.
- `tools/research.py` — `unwrap_search_url` and web fetch/verify helpers.
- `core/memory.py` — `write_memory`, `recall` (FTS5), `list_recent`,
  `count_by_brand`, `record_outcome`, `brand_for_lead`. Brand-scoped, so
  multi-tenant memory never bleeds.

---

## 8. Platform, security, operations

### Auth model — four tiers

| tier | mechanism | scope |
|---|---|---|
| Website account | email/password + verified email, HttpOnly session cookie | one free org; org-bound APIs |
| Dashboard | HTTP Basic (`app/security.py::authenticate`) | operator/paid deployment; global active org |
| Founder action | `X-Founder-Action-Token` (`verify_founder_action`) | every mutation; a verified website session satisfies it for its own org |
| Integration | shared secrets / Svix signature + rate limit | `/integrations/*`, outside dashboard auth |

Website middleware resolves the cookie into request-scoped user/org/session
context. `get_active_org()` and commercial queries read that context first, so
the existing org-scoped stores become tenant-scoped. A free session cannot
switch to another org, list other orgs, use the shared Buffer account, or edit
deployment provider keys. See [Website authentication](authentication.md).

Reads need credentials; **operator writes need credentials *and* the founder
token; website writes use the verified session.** A 401 ends the frontend
session; a 403 leaves it intact.

### Setup and keys

`GET /company/setup/providers` · `POST /keys/test` · `POST /keys` ·
`GET|POST /step`. `core/setup_keys.py` groups keys, detects secrets
(`SECRET_HINTS`), backs up `.env` before writing, and **prunes to 5 backups**.
`g3.env` is stored separately and kept private.

Provider setup is operator-only: free website sessions get a 403 from the setup
router. `GET /company/setup/buffer/accounts` · `POST /buffer/discover` ·
`POST /buffer/connect` back the guided publishing setup. One Buffer token
discovers the organizations and channels it can reach; the operator then binds
the Instagram/X/LinkedIn channel IDs. Channel IDs are identifiers, not extra secrets,
and the token is never returned. Named accounts use G3's `BUFFER_<NAME>_*`
prefix and are visible immediately after saving. The Integrations page keeps
read-only **Overview** separate from **Setup**, and generates key inputs from
the provider registry instead of a fixed list. The registry also has a
**Media hosting (R2)** group: G3 uploads every post media file to Cloudflare
R2 and hands Buffer the public URLs, so drafting or scheduling a post with
media fails fast with a 409 naming the missing `R2_*` keys instead of dying
inside the G3 subprocess. Posts without local media (text-only X) skip R2
entirely.

**Upgrade path: full two-bucket media flow.** The current setup is the
minimal version — local disk is the private store and G3's uploader is the
only writer to the public bucket. The full version makes the private bucket
the canonical store: (1) dashboard asset uploads `PUT` to the private bucket
instead of local disk; (2) asset serving reads it back from there;
(3) at draft/schedule time the app copies the object server-side
(`copy_object`, same credentials, no bytes through us) into
`buffer-publishable-content` before the existing probe-and-send, so the
private bucket is never publicly touched; (4) the private bucket keeps the
custom domain for human/team access (optionally behind Access) while the
public bucket stays on its `r2.dev` URL, immune to zone bot rules.
Media goes public at draft time in either version, because Buffer drafts
already carry the URLs — and the API token should be scoped to the public
bucket only, with periodic deletion of `g3/` objects older than the
scheduling horizon.

### Model routing

`core/models.py` exposes five routes — `fast`, `reasoning`, `free`, `coding`,
`vision` — each env-overridable. `is_model_configured()` gates AI features;
`require_model_configured()` raises rather than degrading silently.

### Memory, workspace, session

`GET /company/ui/session` validates Basic credentials or the website cookie
without touching a product domain. `GET /company/ui/quotas` reports daily plan,
run, and publish remaining/limit/reset; `GET/PUT /company/ui/limits` reads and
updates per-org governance caps. `GET/PUT/DELETE /company/ui/publishers` and
`/publishers/webhook` manage the org's encrypted webhook connection.
`GET /company/ui/integrations` reports provider groups, named Buffer accounts,
and capabilities (operator/paid only). `GET /company/ui/settings` returns the
visible orgs and public links; a website session sees only its own org.
`GET /company/ui/home` is the review queue: what needs your attention.

Signup creates a free org with **1 plan / 1 run / 1 publish per UTC day** and a
zero-spend, 20-contact, 14-day governance clamp. Free publishing uses the org's
signed webhook; paid keeps Buffer as the default publisher.

### Operations

`scripts/backup.py` + `backup_lib.py` (manifest, SHA-256 per file, SQLite
online snapshot via `.backup()`, verified extract, row-count reports) ·
`restore.py` with explicit `verify` then `apply` ·
`verify_backup.py` · `doctor.py` · `smoke_actions.py`.

Backup safety is deliberate: `verify_extracted` opens the archive and asserts
schema and row counts before anything is restored, and restore is two
commands so verification can't be skipped by accident.

---

## 9. Frontend

React is the sole operator UI. 13 page components and 15 routes, ~12,000 LOC
under `src/`. FastAPI serves the built `dist/` and redirects trailing slashes
(308).

| page | reads | writes |
|---|---|---|
| `/onboarding` | `/company/context` | four company-context cards, then the free/paid handoff |
| `/home` | `/company/ui/home` | navigation only |
| `/workflows` | `/company/automation/workflows` | plan, workflow approve/run, governance (`/validation` redirects here) |
| `/research`, `/companies`, `/contacts` | company/contact projections | research, prospect, resolve, draft |
| `/outreach` | `/company/ui/outreach` | draft update/approve/send |
| `/replies`, `/meetings` | reply and meeting projections | draft, schedule-meeting |
| `/content` | `/company/ui/content` | manual posts, publisher draft/schedule/confirm |
| `/integrations`, `/settings` | provider and org state | keys, orgs, capabilities |

`/meet` and `/calendar` remain public server-rendered booking pages. Unknown
non-API paths return a genuine JSON 404 — never a fake SPA success.

Free accounts see a clearly labelled **sample free-account usage** card on Home
and route-level locked previews for paid surfaces (Outreach, Replies, Meetings,
Research). The lock is UI-level; paid APIs remain separately
gated, free cold-outreach send returns 403, and the upgrade CTA opens the
marketing site at `/?demo=1`, which auto-opens the Book a demo dialog.

**Conventions:** projections return backend field names verbatim, no camelCase
conversion. Draft status, manual-post stage, and Buffer status render as
separate fields. Unknown values render explicitly as unknown. React
Query keys include URL filters, sort, page, and selection; mutations invalidate
only affected queries, and failed refreshes retain prior data.

---

## 10. Data model — 39 tables in `company.db`

| table | holds |
|---|---|
| `sales_leads` | lead + stage + `metadata` (utm/campaign/post/meeting) |
| `sales_drafts` | subject/body, status, provider message id, send state |
| `sales_interactions` | every inbound/outbound touch |
| `sales_events` | audit trail |
| `sales_company_profiles` | cached provider resolution by domain |
| `marketing_campaigns` | dormant; retained only for the manual-post FK and historical attribution |
| `marketing_variants` | dormant; no API or UI writes |
| `marketing_events` | dormant; no API or UI writes |
| `marketing_manual_posts` | `campaign_id`/`post_id`/`tracked_url`/`source_detail` |
| `coding_tasks` | agent task state |
| `incidents` | monitor-detected failures |
| `buffer_orgs` / `buffer_org_accounts` | marketing tenants |
| `org_capabilities` | per-org feature flags |
| `tasks` / `settings` | generic queue; key-value config incl. onboarding program |
| `service_provider_requests` | provider credit-spend gate |
| `memories` | FTS5 brand-scoped memory |
| `company_context` | canonical company answers, completeness, workflow readiness |
| `workflows` | automation workflow definitions |
| `validation_plans` / `validation_workflows` | plan + workflow records for the automation flow |
| `users` | website accounts; scrypt password hashes, verified email timestamp |
| `org_memberships` | user ↔ org ownership/membership |
| `auth_sessions` | hashed session tokens, org binding, 30-day expiry |
| `email_verifications` | hashed, single-use, 24-hour verification tokens |
| `publisher_connections` | per-org webhook config; encrypted signing secret |
| `usage_events` | per-org daily plan/run/publish ledger |
| `publish_jobs` | durable async publish status/results for edge-timeout-safe publishes |
| `plan_inputs` | durable PlanInput snapshots keyed by org and input hash |
| `world_records` | canonical evidence/world records used by research |

Schema migrations are guarded and additive (`_migrate_*` functions in
`core/state.py`, `core/sales_store.py`, `core/marketing_store.py`).

---

## 11. What is verified vs. what is claimed

Being explicit, because a reference doc that implies everything works is worse
than no doc.

**Verified by tests** — 512 collected; 510 pass, 1 skipped, 1 known flake.
The website suite adds 10 tests (8 marketing, 2 auth). The
manual-post path, Buffer handoff, sales lifecycle, evidence, governance,
onboarding, and provider registry are covered. The executable workflow engine
still has model/runner/API tests using the four remaining actions.

**Verified live after the cut (2026-10-28):**

- `GET /company/ui/content` returns the **4 persisted manual posts** and no
  asset packs; the Content page renders them.
- `GET /company/ui/home` no longer contains campaign fields; Home renders the
  manual-post count.
- `/company/marketing/campaigns`, `/company/video/specs`, and
  `/company/ui/campaigns` return **404**. `/campaigns` and `/video` render the
  React not-found page.
- `/validation` returns the SPA; `/services` is removed and falls through to the
  React not-found screen.
- The Workflows page exposes **Plan / Governance / What next** only.
- `GET /company/marketing/doctor` checks only `g3_bin`.

**Known pre-existing failure:** `tests/test_sales_contracts.py::test_resend_send_marks_draft_sent`
is a timing-sensitive flake; it passes in isolation.

**Not proven:**
- Buffer publication is never inferred. A scheduled post is only "sent" when
  the provider explicitly says so; insights require a personal API key and are
  experimental.
- Campaign generation, asset packs, video rendering, and the MI300X worker were
  removed, not disabled. Any historical screenshots of those pages are no
  longer reproducible from this tree.
- The coding/self-improvement surface remains a CLI/ops subsystem with an empty
  live queue (`company_ops.db`: 0 tasks, 0 incidents).
