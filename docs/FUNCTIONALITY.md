# AutoEvolve functionality reference

Every capability the product actually has, department by department, verified
against the source at commit `96d6c8b`. Not a plan and not a roadmap: this is
what the code does.

**How to read this.** Each section states what the department does, then the
routes that expose it, then the tables it persists to, then the honest limits.
Counts: **125 unique HTTP operations across 17 routers**, **24 database
tables**, **3 engines**, **282 tests**.

A note on counting: [API Reference](API-REFERENCE.md) reports ~169 routes and
~26 tables because it extracts route decorators and `CREATE TABLE` statements
textually, so a path served by two routers is listed twice. The 125 / 24 figures
above come from the OpenAPI contract and a table enumeration that deduplicates.
Both are correct at what they measure; the OpenAPI number is the one to quote.

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
3. **Market** — campaigns, scripts, media generation, and publishing to social
   with per-post attribution.
4. **Produce video** — a brief becomes a storyboard becomes a rendered MP4.
5. **Improve itself** — the coding agent and orchestrator change the codebase,
   with checkpoints, validation, and reversible applies.

The through-line is **attribution**: every lead carries the campaign, post, and
UTM parameters that produced it, so marketing and sales share one record.

### The four operating states

| Department | Terminal states | Stored in |
|---|---|---|
| Sales lead | `won` `lost` `suppressed` (of 11 stages) | `sales_leads.stage` |
| Draft | approved → sent, or abandoned | `sales_drafts.status` |
| Campaign | `variants_ready` `drafted` `failed` `needs_campaign_review` | `marketing_campaigns.status` |
| Render job | `completed` / `failed` / `cancelled` | `video_render_jobs.status` |

---

## 2. Onboarding

First-run program that turns a company description into a calibrated sales
motion. Twelve write routes, one read projection, resumable — every step
persists to `settings` as a single `ProgramState` document, so a half-finished
onboarding survives a restart.

**Routes** — read: `GET /company/ui/onboarding`. Write (all founder-token):
`POST /company/setup/onboarding/{company,research-company,company/confirm,strategy/draft,strategy,search,calibration,refinement,buyer,draft,activate}`

**The twelve steps:**

| # | Route | What it does |
|---|---|---|
| 1 | `/company` | Name the company, pick industry/region |
| 2 | `/research-company` | Research it via `tools/domain_extract.py` (trafilatura, SSRF-guarded public-host validation) |
| 3 | `/company/confirm` | Founder confirms or edits the researched profile |
| 4 | `/strategy/draft` | AI drafts ICP + strategy; **founder may edit the suggestions** |
| 5 | `/strategy` | Confirm strategy, set approval policy and provider limits |
| 6 | `/search` | First real provider search — the cost-incurring step |
| 7 | `/calibration` | Founder rates sample leads: good/bad feedback per lead |
| 8 | `/refinement` | System proposes a refinement; founder approves or rejects |
| 9 | `/buyer` | Resolve which sample leads are actual buyers |
| 10 | `/draft` | Create the first outreach draft for review |
| 11 | `/activate` | Program goes live |

**What exists:** `AiIcp`/`AiStrategyDraft` require a *complete* model draft
before the founder can edit — the model cannot ship a half-answer. Calibrated
leads carry a `confidence_band` (`high`/`medium`/`borderline`) derived from
`lead_score`. Provider spend is capped by `ProviderLimits` and gated through
`claim_service_provider_request(provider, action, limit_24h)`.

**Honest limit:** `OnboardingView.confidence_basis` states in the payload
itself — *"Existing lead_score only; not a verified ICP fit score."* Calibration
scores lead quality for the founder; it does not train or verify a real ICP fit
model.

---

## 3. Sales

The largest department: 35 routes, 5 tables, 6 provider integrations, and the
most careful failure handling in the codebase.

### 3.1 Lead intake (unauthenticated, shared-secret + rate limited)

`POST /integrations/leads/website` · `/integrations/leads/tally` ·
`/integrations/email/sales` · `/integrations/resend/sales`

Four ingress paths — website form, Tally webhook, inbound email, Resend
webhook. Each verifies its own shared secret
(`X-Company-Core-Lead-Secret`, `X-Sales-Email-Webhook-Secret`, Svix signature
for Resend). These four routes sit **outside** dashboard auth and are
rate-limited per client IP by `rate_limit_intake` (`WINDOW_SECONDS`,
`WEBHOOK_PATHS`), with a separate bucket for failed dashboard sign-ins.

`upsert_lead(payload)` merges by email, passes `utm_*`/campaign/post
parameters through **verbatim**, and returns `(lead, created)` so
`maybe_auto_contact_lead` can react to genuinely new leads only.

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

**Honest limits:** every provider needs a paid key. No key → that route fails
with the provider's error preserved, never a silent empty result. Credit spend
is real money and is bounded only by `claim_service_provider_request`.

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
meetings all **stop the follow-up sequence**.

`POST /leads/{id}/schedule-meeting` records a manual marker.
`POST /leads/{id}/suppress` (`reason='founder_request'`) suppresses permanently.

### 3.6 Views

`GET /company/ui/outreach[/{id}]` · `/replies[/{id}]` · `/meetings[/{lead_id}]`
· `/company/sales/contacts[/{id}]` · `/companies[/{company_id}]`

Paginated projections over joins of `sales_drafts`, `sales_leads`,
`sales_interactions`, `sales_company_profiles`. Replies expose whether an
inbound is the lead's latest interaction and the exact thread id.

**Explicitly unsupported by the backend** (documented, and the UI omits them
rather than faking them): outreach owner, due date, follow-up queue,
personalization reason, reply intent/sentiment/objection classification,
meeting confirmation/attendees/duration/call link/outcome/no-show rate,
opportunity value.

---

## 4. Marketing

30 routes, 4 tables, three engines (`g1`, `g2`, `g3`).

### 4.1 Campaign lifecycle

```
brief → g1 package (validates claims) → FOUNDER script review
      → g2 media search/acquire/render → variant selection
      → g3 Buffer draft + R2 upload → FOUNDER approves → publish
      → tracked URL (?utm_campaign, campaign_id, post_id) → lead
```

Stages written by `services/marketing_worker.py::_stage`:
`g1_campaign` → `g1_review` → `media_search` → `media_acquisition` →
`voice_handoff` → `variant_rendering` → `founder_variant_review` →
`g3_draft_creation` → `buffer_review`.

**The approval gates are load-bearing.** A campaign waiting for review must be
approved or regenerated — `retry` is for failures, not for pending reviews
(`TERMINAL_CAMPAIGN_STATES`). `retry_campaign` exists as a route precisely
because confusing the two is the easy mistake.

Routes: `POST /company/marketing/campaigns` · `/campaigns/{id}/approve-script`
· `/regenerate-script` · `/retry` · `/drafts` · `/variants/{variant_id}/select`.

### 4.2 Voice, variants, captions

- `POST /campaigns/{id}/voice-recording` — founder voice upload, extension
  allow-list (`VOICE_UPLOAD_EXTENSIONS`), `MAX_ARTIFACT_BYTES` cap.
- `GET /campaigns/{id}/voice-handoff` — the brief for a voice actor.
- `POST /campaigns/{id}/variants/{variant_id}/select` — founder picks a variant.
- `services/caption_variants.py` builds per-platform short captions with
  platform-appropriate CTAs and a tracked CTA URL.
- `services/asset_scene_planner.py` splits a script into scene boundaries —
  deterministic fallback boundaries, or AI boundaries validated against
  paragraph count and target count (`_boundary_error`).

### 4.3 Manual posts and Buffer

Two paths: **manual** (operator uploads their own assets) and **generated**
(asset packs from a script).

- `POST /manual-posts/session` → `/manual-posts/{id}/assets` (upload) →
  `/finalize` — a three-step flow so uploads survive a failed finalize.
- `POST /manual-posts` — single-shot from the UI with `File[]` assets.
- `GET /buffer-accounts` — named accounts configured in `g3.env`; **keys never
  leave the server**.
- `POST /manual-posts/{id}/buffer-draft` → `/buffer-schedule` → `GET
  /buffer-insights`.

**Attribution is the point.** `_tracked_post_url` embeds
`?utm_campaign`, `campaign_id`, `post_id`, `source_detail`, `post_type`;
`_lead_attribution` reads them back onto the lead. `marketing_manual_posts`
stores `campaign_id`/`post_id`/`tracked_url`/`source_detail`, and
`sales_leads` stores the same fields verbatim. Post-level attribution is real,
not inferred.

**Honest limits:**
- A Buffer draft or scheduled post is **never labelled published** unless the
  provider reports it sent. G3's own README says scheduling "does not claim that
  a scheduled post was published."
- `buffer-insights` metrics require a *personal* Buffer API key and are
  documented by Buffer as experimental — values can be absent or delayed. The
  UI shows them only for a post ID saved by a confirmed schedule response.
- Content search/pagination run over an explicitly bounded loaded set
  (200 posts / 100 packs) and **the page warns when a source was truncated**.

### 4.4 Asset packs

`POST /company/marketing/asset-packs` → background `spawn_asset_pack` →
`GET /asset-packs` · `/asset-packs/{id}/files/{relative_path}`.
`services/asset_pack_builder.py` splits a script into slides, compresses to
`MAX_CONTENT_SLIDES`, derives headlines/keywords/image queries per slide;
`services/asset_pack_worker.py` runs it and persists a record.

File serving is path-traversal guarded (`{relative_path:path}` with a root
join check).

### 4.5 Orgs and capabilities

`GET/POST /company/marketing/orgs` · `POST /orgs/active` ·
`GET|POST /orgs/{org_id}/capabilities`. Multi-tenant by Buffer org, each with
its own accounts (`buffer_org_accounts`), capability flags (`org_capabilities`,
validated against `VALID_CAPABILITIES`), and slug/env prefix.

### 4.6 The three engines

| engine | does | invoked by |
|---|---|---|
| **g1** | brief → validated campaign package; enforces approved product claims, story order, CTA policy, image-search constraints | `marketing_worker.run_pipeline` |
| **g2** | media search/acquisition (Pexels, Pixabay, Coverr, Wikimedia, local approved pool), voice, subtitles, carousel and mixed-video rendering | `run_media_pipeline`, `run_real_voice_render` |
| **g3** | validates g2 handoff, uploads to S3-compatible storage (Cloudflare R2), creates Buffer drafts / scheduled posts | `run_g3` |

Coverr's short-lived download URL is resolved **only for the selected clip**.
`engines/g2/assets/owned/` is a consented, AI-tagged footage pool that wins
scenes its tags match, with stock as fallback. Editorial frames carry no
persistent logo or review badge — visible branding is limited to the configured
showcase and premade outro.

---

## 5. Video production

20 routes, 5 tables, a private MI300X worker.

### 5.1 Pipeline

```
brief / script → spec → storyboard → shot plan → render job(s) → queue → worker → QA → gates
```

`services/video/` split into `defs`, `script_parser`, `spec_builder`,
`shot_planner`, `job_builder`, `pipeline`.

| command | does |
|---|---|
| `plan` | prepared script → spec + shots + jobs |
| `direct` | raw brief → AI-directed spec (no script needed) |
| `queue` | enqueue a plan in a chosen render mode |
| `submit` | claim → POST → download → ffprobe QA → complete/fail |
| `worker-status` | `/health` + `/capacity`, starts no render |
| `launch` | the whole thing end to end |

### 5.2 AI creative director

`services/creative_director.py` routes 7 roles through OmniRoute. It is
**model-agnostic** — no Claude dependency — and every role has a deterministic
fallback. `DirectorUnavailable` is raised when a role needs a key, and never
silently degrades.

The AI is **never authoritative over source wording.** Deterministic timing
(`assign_durations`) exists because the model produced escalating 10/15/20…60s
beats totalling 385s against a 60s target. Storyboard output is
schema-validated before any GPU spend (`validate_storyboard_generatable`
requires at least one routable cinematic beat).

**Routing guard:** information displays — labeled diagrams, holographic data,
logos, taglines, "sign reading X" — route to `motion_graphics`, never Hunyuan,
because generating them *fabricates information*. `INFO_DISPLAY_CUES` enforces
this; real product captures (`product_capture`/`source_capture`) keep their
acquisition families.

`visual_bible.adapt_bible` switches the default bible's freight environment to a
tech variant for software briefs (word-boundary matched, so "important" ≠
"port"), and `motion_recipes` selects among 10 recipes.

### 5.3 Render modes

`full` (product default) = one whole-video job. `shots` = one job per clip,
available only as an explicit opt-in via `?render_mode=`.

### 5.4 Worker protocol

`GET /health` (unauthenticated), `GET /capacity` (Bearer), synchronous
`POST /render`. Auth is `RENDER_WORKER_API_TOKEN` from `.env` — never in
source, never in logs. The endpoint comes only from `RENDER_WORKER_URL`; no
worker IP is hard-coded. Tailscale-only, UFW-restricted.

Output retrieval is a documented chain: inline bytes → `output_url` → async
poll + download → `GET /video/{output_name}` → terminal `output_unavailable`.

### 5.5 Measured worker envelope — and its limit

The binding constraint is **wall-clock time, not frame count**: the worker's
synchronous `/render` gives up after exactly 60 minutes (measured 3600.0s on the
480-frame run).

| frames | wall time | result |
|---|---|---|
| 81 | — | HTTP 500 *after* full 20-step sampling (post-sampling failure) |
| 144 | — | completed (141 frames delivered) |
| 240 | ~20 min | **completed** (237 frames delivered) |
| 480 | 60 min | HTTP 504 "Render timed out" — hit the wall exactly |
| 720 | 31 min | HTTP 500 mid-render |
| 1440 | — | HTTP 504 "Render timed out" |

**A full-length video has never rendered.** 240 frames (10s) is the only proven
full-video success. Gates, validators, and the queue all behave correctly on
failure — nothing is ever silently marked complete — but the product's headline
capability is bounded by hardware, not by code.

**Frame-count drift is tolerated, truncation is not.** The worker consistently
delivers a few frames short of the request (237/240, 141/144). `qa_render_output`
accepts up to `FRAME_COUNT_TOLERANCE` (2%) and records the true count plus the
shortfall; anything larger still fails as a truncated render.

---

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

### Auth model — three tiers

| tier | mechanism | scope |
|---|---|---|
| Dashboard | HTTP Basic (`app/security.py::authenticate`) | all `/company/*` reads and writes |
| Founder action | `X-Founder-Action-Token` (`verify_founder_action`) | every mutation: send, approve, schedule, queue, retry, cancel, coding apply, monitor |
| Integration | shared secrets / Svix signature + rate limit | `/integrations/*`, outside dashboard auth |

Reads need credentials; **writes need credentials *and* the founder token.** The
UI sends the action token only for guarded mutations. A 401 ends the frontend
session; a 403 leaves it intact.

### Setup and keys

`GET /company/setup/providers` · `POST /keys/test` · `POST /keys` ·
`GET|POST /step`. `core/setup_keys.py` groups keys, detects secrets
(`SECRET_HINTS`), backs up `.env` before writing, and **prunes to 5 backups**.
`g3.env` is stored separately and kept private.

### Model routing

`core/models.py` exposes five routes — `fast`, `reasoning`, `free`, `coding`,
`vision` — each env-overridable. `is_model_configured()` gates AI features;
`require_model_configured()` raises rather than degrading silently.

### Memory, workspace, session

`GET /company/ui/session` validates credentials without touching a product
domain. `GET /company/ui/integrations` reports provider groups and
capabilities. `GET /company/ui/settings` returns orgs and public links.
`GET /company/ui/home` is the review queue: what needs your attention.

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

React is the sole operator UI. 14 pages, 9,894 LOC, 65 exported API functions.
FastAPI serves the built `dist/` and redirects trailing slashes (308).

| page | reads | writes |
|---|---|---|
| `/onboarding` | `/company/ui/onboarding` | 12 onboarding routes |
| `/home` | `/company/ui/home` | navigation only |
| `/research`, `/companies`, `/contacts` | company/contact projections | research, prospect, resolve, draft |
| `/outreach` | `/company/ui/outreach` | draft update/approve/send |
| `/replies`, `/meetings` | reply and meeting projections | draft, schedule-meeting |
| `/campaigns` | `/company/ui/campaigns` | create, approve-script, retry |
| `/content` | `/company/ui/content` | asset packs, manual posts, Buffer |
| `/integrations`, `/settings` | provider and org state | keys, orgs, capabilities |
| `/operations/history` | retired → redirects to Home | — |

`/meet` and `/calendar` remain public server-rendered booking pages. Unknown
non-API paths return a genuine JSON 404 — never a fake SPA success.

**Conventions:** projections return backend field names verbatim, no camelCase
conversion. Draft status, campaign status, content stage, and Buffer status
render as separate fields. Unknown values render explicitly as unknown. React
Query keys include URL filters, sort, page, and selection; mutations invalidate
only affected queries, and failed refreshes retain prior data.

---

## 10. Data model — all 24 tables

| table | holds |
|---|---|
| `sales_leads` | lead + stage + `metadata` (utm/campaign/post/meeting) |
| `sales_drafts` | subject/body, status, provider message id, send state |
| `sales_interactions` | every inbound/outbound touch |
| `sales_events` | audit trail |
| `sales_company_profiles` | cached provider resolution by domain |
| `marketing_campaigns` | brief, stage, status, script, errors |
| `marketing_variants` | per-platform voice/speed renders |
| `marketing_events` | campaign audit trail |
| `marketing_manual_posts` | `campaign_id`/`post_id`/`tracked_url`/`source_detail` |
| `video_specs` | format, brand, assets, narrative |
| `video_shot_plans` | shots, timing, prompts |
| `video_render_jobs` | queue, lease, attempts, error, output |
| `video_visual_bibles` | environment/style continuity |
| `video_assets` | registered references |
| `coding_tasks` | agent task state |
| `incidents` | monitor-detected failures |
| `buffer_orgs` / `buffer_org_accounts` | marketing tenants |
| `org_capabilities` | per-org feature flags |
| `tasks` / `settings` | generic queue; key-value config incl. onboarding program |
| `service_discovery_runs` / `service_provider_requests` | prospecting runs, credit spend |
| `memories` | FTS5 brand-scoped memory |

Schema migrations are guarded and additive (`_migrate_*` functions in
`core/state.py`, `core/sales_store.py`, `core/marketing_store.py`).

---

## 11. What is verified vs. what is claimed

Being explicit, because a reference doc that implies everything works is worse
than no doc.

**Verified by tests** — 282 tests, 36 files. Video/director alone: 49 pipeline
+ creative-director tests, plus Hunyuan renderer tests covering a
**double-worker** (ensuring a job can't be double-claimed). Smoke suite: 33/33
pass, report at `logs/smoke-report.md`.

**Verified live:** worker `/health` + `/capacity` 200; a 144-frame render
completed worker-side; `GET /video/shot_001.mp4` returned 782,773 bytes in
0.34s, decoding as h264/480×848/24fps/5.875s. Note that file held **141 frames
against the job's 144** — the worker under-delivers on frame count, and QA
caught it.

**Known pre-existing failures** (3, unrelated to video): `test_operations_ui`,
`test_sales_contracts::test_resend_send_marks_draft_sent`,
`test_sales_workflow_views_api`.

**Not proven:**
- No 60s or 30s full-video render has completed. The envelope is the binding
  constraint.
- Real product footage for I2V shots is absent — no product UI capture has been
  registered, so identity-preserving shots have no reference image.
- Vision-based review (`review.ai_visual_review`) abstains without a vision key.
- The `skills/motion-designer` pack is verified byte-identical as a zip but has
  never been piloted end to end (needs a GPT workspace plus Higgsfield).
- OmniRoute availability is flaky; `auto/best-reasoning` intermittently returns
  403 `insufficient_quota`.
