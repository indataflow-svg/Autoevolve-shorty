# Commercial Setup — Function Reference (incl. new world-data functions)

Scope: item 1 of the functional inventory — everything under the Commercial
workspace (`/commercial`), its 6 tabs, and the Setup wizard. Each entry names
the function, the backend route, and the UI location. Entries marked NEW are
the world-data additions.

## Setup tab — identity-first wizard

- **View commercial identity** — `SetupWizard`, `autoevolve-ui/src/pages/commercial/wizard.tsx`. When any commercial fact exists (company name, completeness > 0, offers, ICPs, accounts, pipelines, rules, sessions), the tab shows the identity card (name, description, website, completeness %, readiness) with a 4-line checklist instead of the starter choices.
- **Start guided setup (path A: starting from zero)** — `POST /company/commercial/onboarding-sessions {path: A}`. 6-step stepper: Company & offer → ICP & market → Accounts & data → Pipeline & qualification → Integrations → Review/Activate.
- **Start guided setup (path B: already operating)** — same endpoint with `{path: B}`. Same stepper, but the ICP step starts from the template closest to best customers and the accounts step leads with CSV import.
- **Setup new company commercial identity** — secondary button on the identity card. Reveals the A/B starter cards without deleting existing accounts, offers, or history; "Back to company identity" returns.
- **Resume / leave setup** — session id persisted in `localStorage cx-setup-session`; open sessions listed with path + current step; leaving clears the pointer only.
- **Save company step (identity + offer)** — `CompanyStep`: company name/website ride the merge-only `PUT /company/context`; offer saved via `POST /company/commercial/offers` (name required, category/market/pricing optional).
- **Save provisional ICP** — blank hypothesis or from `GET /company/commercial/icp-templates`; industry-filled criteria; research-track handoff to `/onboarding` keeps the session.
- **Add account / import CSV** — `POST /company/commercial/accounts` (company_name minimum) or `CsvWizard`: `POST .../imports/preview` (suggested header mapping, exact duplicates, ambiguous rows, 10-row sample) then commit with upsert by domain.
- **Save qualification rule** — `POST /company/commercial/rules` (default shape: fit rule, threshold 40).
- **Activate setup** — `PATCH /company/commercial/onboarding-sessions/{id} {completed: true}`; gated on company + offer + ICP + account + pipeline + rule.
- **NEW: Predicted outcomes card** — `GET /company/commercial/benchmarks?sends=N` (`app/commercial_api.py:world_benchmarks`). Shows: industry used (or general-B2B fallback, stated), cold-reply band → expected replies per N sends, opt-in open/click band, cited-studies count + vintage + coverage, adjustable sends input (1–100000). Read-only; renders backend values only.
- **NEW: Your-vs-market position** — same endpoint's `recorded` + `market` fields. Below 10 sends: honest countdown ("N sends — 10+ sends position you against the market"). At 10+: "Your X% across N sends — above/within/below the world L–H% band."
- **NEW: Anonymized-pool preference** — `GET /company/commercial/network-stats` (counts only: industry, sends, replies, meetings; PII asserted absent by test) + founder-gated `POST /company/commercial/network-contribution {opt_in}`. Default **opted_out**; `pool: none_yet` is stated, nothing leaves the server.

## Company data (cross-tab dialog)

- **View/edit company data** — "Company data" button (`CommercialPage.tsx`) opens `CompanyDataDialog` (`CompanyDataCards.tsx`): 6 answer cards (Company, Product, Customer, Problem, Objective, Starting state), each with question, example, help, stored-vs-draft states. Auto-opens on arrival while fresh/blocked.
- **Save answers** — merge-only: refetch fresh context, merge touched sections, full-replacement `PUT /company/context` with founder token. Completeness %, missing groups, and workflow readiness recompute server-side.
- Gates: workflow actions need 40% (`SETUP_FLOOR_PERCENT`); plan generation needs 80% (`workflow_ready`).

## Accounts tab

- List/search/sort/paginate accounts (`GET /company/commercial/accounts`); account detail with intent score + activities; delete (`DELETE .../accounts/{id}`, founder-gated).
- **Suggest accounts** — `POST /company/commercial/accounts/suggest`: unclaimed lead domains + free enrichment + ICP fit (≥40) → ranked proposals with reason and ICP matches; creates nothing.
- **Qualify → preset ICP** — `POST .../accounts/{id}/qualify` jumps to ICPs & Qualification with the account preset.
- Log activities (`POST .../activities`).

## ICPs & Qualification tab

- List/propose/archive ICPs; ICP detail (criteria, exclusions, weights, provenance, evidence sources, assumptions, confidence); evaluate + patch (versioned).
- **Suggest criteria** — `GET /company/commercial/icps/suggest-criteria`: mines own accounts (customers > engaged > all) for top industry/size/region with support counts + fill rates + thin-evidence warnings.
- Qualification workspace: rules list, fit evaluation, `_refit_accounts` re-scores all linked accounts when ICP criteria change; default pipeline auto-created on first listing; missing pipeline falls back to `DEFAULT_PIPELINE_STAGES`.

## Pipeline tab

- Pipelines (default stages prospect → … → disqualified), opportunities board grouped by stage (`groupByStage`), create/move opportunity (founder-gated), first opportunity stage defaults from seed.

## Forms tab

- Form definitions + hosted paths, enable/disable (`PATCH .../forms/{slug}`), forms config (endpoint URL, secret header), website/Tally/Resend intake contracts.

## Integrations tab (commercial scope)

- Provider catalog with states (available/connected/coming soon), connect/sync/disconnect (founder-gated), Buffer OAuth flow, per-provider drawer (overview/usage/settings/logs).

## Data model (reference)

`offer_profiles`, `icp_profiles`, `commercial_accounts`, `commercial_opportunities`, `commercial_pipelines`, `qualification_rules`, `commercial_activities`, `csv_imports`, `onboarding_sessions`, `integration_connections` (+ `settings.worlddata_contribution` flag, `world_records` world store).
