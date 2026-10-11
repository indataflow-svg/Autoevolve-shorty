# Phase 1 commercial foundation — architecture specification

Verified against the actual repository on 2026-10-11. Facts first; recommendations marked [R].

## 1. Repository architecture and file map

- Frontend: React 19 + react-router 7 + Vite 7 + TS 5.9, hand-rolled CSS (`autoevolve-ui/src/styles.css`), tanstack query/table, lucide icons. Routes in `autoevolve-ui/src/main.tsx`; 16 pages in `src/pages/`; 9 hand-typed API clients in `src/api/` plus generated `schema.ts` (from `scripts/export_openapi.py`). Auth: memory-only Basic creds (`src/app/Auth.tsx`), founder token per-write header.
- Backend: single FastAPI `app.api:app`; routers in `app/*_api.py` under `/company/*` (Basic) with founder-gated writes (`X-Founder-Action-Token`), public `/integrations/*` (shared-secret + ratelimit). Business logic in `services/*`, persistence in `core/*_store.py`.
- DB: SQLite via `core.db.open_db` (WAL, FK on). `data/company.db` (state, sales, marketing, context, video, commercial), `data/workflows.db`, `data/company_ops.db`. No migrations framework — `CREATE TABLE IF NOT EXISTS` in `init_*` functions; schema changes need manual `ALTER`/rebuild shims.
- Auth: `DASHBOARD_USER/DASHBOARD_PASSWORD` (Basic), `SALES_ACTION_TOKEN` (founder writes). Tenant isolation is conventional: `org_id` columns + `settings.active_org_id`; `sales_leads.org_id` not enforced on list. No RLS, no per-tenant DB.
- Flows: UI (`api/client.ts`) → `app/api.py` (mount+auth) → `app/*_api.py` (Pydantic) → `services/*` → `core/*_store.py` → `data/*.db`.

## 2. Reused components and services

`core.sales_store` (leads/drafts/interactions/events/profiles, `PIPELINE_STAGES`, `score_lead`), `services.sales_service` (Resend send incl. idempotency + reconcile, Hunter/Apollo/Prospeo/Lusha, inbound webhooks), `core.company_context` (single-row canonical context), `core.state` (orgs/settings), `core.setup_keys` (masked provider groups), UI `Shell/Primitives/client.ts` patterns. New `core.commercial_store` extends these; it does not duplicate leads.

## 3. Canonical commercial data model (physical)

All in `data/company.db`, all rows carry `org_id` (server-derived from `active_org_id`, never client-supplied):

| table | key contents |
|---|---|
| `offer_profiles` | name, description, category, target_market, pricing, value_prop, differentiators[], limitations, status |
| `icp_profiles` | name, segment, offer_id, criteria[] (`field/operator/value/weight`), exclusions[], weights{}, thresholds{}, provenance{} (per-field user-provided/imported/inferred/verified), evidence_sources[], assumptions[], confidence, status provisional/validated/archived, version++ on edit |
| `commercial_accounts` | company_name, domain (NULL-able; UNIQUE(org,domain) dedupes real domains, allows many undomed), industry/size/region, source+source_ref (CSV filename:row preserved), icp_id, fit_score/grade/explanation, verification_status, lifecycle_status, owner, next_action |
| `commercial_pipelines` | name, stages[] (`key/label/allowed_next/required_fields`), active, version; seeded Default sales pipeline |
| `commercial_opportunities` | account_id FK, contact_ids[], offer_id, pipeline_id, stage, stage_history[] (`stage/at/by`), value/currency, expected_close, outcome, lost_reason |
| `qualification_rules` | name, icp_id?, pipeline_id?, criterion, rule_type fit/intent/qualification, weight, threshold?, hard_disqualify, evidence_required[], active, version |
| `commercial_activities` | type, timestamp, outcome, owner, account/contact/lead/opportunity/campaign links, source, audit{} |
| `integration_connections` | provider UNIQUE per org, external_account_ref, scopes[], status healthy/action_required/disconnected, sync_status idle/in_progress/succeeded/failed/pending, last_sync_at, last_error_sanitized (≤400 chars, no secrets), credential_ref (env var **name** only) |
| `csv_imports` | entity_type, filename, status preview/committed, mapping{}, totals{}, row_errors[], rows[] (bounded 2000 rows / 2 MB); committed imports replay idempotently |
| `onboarding_sessions` | path A/B, current_step, progress{} (merged), completed |

`sales_leads` remains the contact/lead truth (extended only by `csv:` source rows); accounts reference leads by domain/company rather than duplicating them.

## 4. API contracts (`/company/commercial/*`, Basic; writes + founder token)

Offers CRUD; ICPs CRUD + `POST /icps/{id}/evaluate` (fit+intent); accounts CRUD + `GET /accounts/{id}` (detail+intent+activities) + `POST /accounts/{id}/qualify`; pipelines list/create (auto-seed) ; opportunities list/create + `POST /opportunities/{id}/move` (transition + required-field + reason enforcement); rules list/create; activities log; `POST /imports/preview?entity_type=` (multipart CSV) + `POST /imports/{id}/commit`; `GET /integrations` (catalog with truthful states) + `/{provider}/{connect,disconnect,sync}`; onboarding-sessions CRUD. Errors: 404 unknown id, 409 duplicate domain, 422 rule/transition/mapping violations with reasons.

## 5. Migration plan

No migration runner: `init_commercial_db()` creates all tables `IF NOT EXISTS`. One live data migration shipped: `commercial_accounts.domain` `NOT NULL ''` → nullable (rebuild with `''→NULL` mapping) so undomed accounts coexist with domain dedupe. Future alters must follow the same probe-and-rebuild pattern.

## 6. Frontend→backend flow

`CommercialPage (/commercial)` + `api/commercial.ts` (hand-typed, like `video.ts` — no schema regen needed): react-query per entity (`c-offers`, `c-icps`, …), in-memory founder token, `run()` helper (token gate → write → invalidate). Tabs: setup (sessions A/B, offers, ICPs, rules), accounts (CRUD + CSV preview/commit + qualify), pipeline (pipelines, opportunities, moves), integrations (catalog states + connect/sync/disconnect). Nav entry added to `Shell.tsx`.

## 7. Auth, isolation, security

Reuse Basic + founder token; no second auth system. `org_id` is always server-derived; no endpoint accepts it. CSV bounded (2 MB/2000 rows/UTF-8); mapping values whitelisted to `CANONICAL_FIELDS`; secrets never leave the server (`credential_ref` is a name, errors sanitized + truncated, catalog exposes booleans not keys). Disconnect revokes locally; OAuth providers stay `coming_soon` until app approval exists.

## 8. CSV import and dedupe

Preview → suggested mapping (header similarity) → counts (rows/exact/ambiguous/to-create) + 10-row sample + ambiguous list → user-edited mapping → commit (transactional per-row with row-level errors; exact domain/email matches skipped; missing required field = error row). Commit is idempotent (re-POST returns stored totals).

## 9. Pipeline and qualification execution

Moves validated against the pipeline's own `allowed_next`; `required_fields` must be present on the opportunity; terminal stages (`lost/deferred/disqualified`) require a reason. Fit = weighted criteria (missing = `unknown`, never positive) + exclusions (hard disqualify). Intent = recorded `sales_events`/`sales_interactions` only (reply +30, meeting +50, inbound +20, capped 100; none = `level:none`). Qualification = fit + intent + active rules (thresholds; `hard_disqualify` fails closed); `qualified` requires fit ≥ 40 and no unmet rules; anything unmet sets `needs_human`.

## 10. Integration adapter and states

`CATALOG` (11 providers) × stored row × env presence → `healthy/action_required/disconnected` + `available/unavailable/coming_soon`. Live validation only where a check exists today (Hunter `account()`, Resend key presence); all others validate on first sync. Sync is read-only and never writes to providers. OAuth/CRM providers (WhatsApp, Meta/Google ads, GA, HubSpot, Salesforce) are catalog-only with an explicit blocker string.

## 11. Ordered tasks (as built)

1. `core/commercial_store.py` + tables/fit/intent → 2. `app/commercial_api.py` + mount + `/commercial` SPA route → 3. `api/commercial.ts` + `CommercialPage` + nav → 4. `tests/test_commercial_phase1.py` + `commercial.test.ts` → 5. docs (`PHASE1-COMMERCIAL`, FUNCTIONALITY §2c, PROGRESS).

## 12. Acceptance and test plan

Backend `tests/test_commercial_phase1.py` (8): offer CRUD, ICP version+fit+exclusion, CSV preview/commit/replay, pipeline allow/refuse, fit/intent separation, catalog truthfulness (no token leak), sessions A/B persist, org isolation. Frontend `commercial.test.ts` (2): auth header, catalog path. Full `make test` + `tsc` + `eslint` + `vite build` must pass with only the 3 pre-existing unrelated failures.

## 13. Blockers requiring human approval

Provider OAuth app approvals + credentials (WhatsApp, Meta/Google ads, GA, HubSpot, Salesforce); production DASHBOARD/SALES secrets rotation; no migration runner (manual shims); single-tenant `org_id` convention is not RLS — multi-tenant needs a real isolation design; `sales_leads.org_id` unenforced on list (pre-existing).
