# Redesign Prompt — Setup Pages (`/commercial`, `/onboarding`)

Use this prompt to redesign the three setup pages as one coherent flow. It
describes each page's current UI, the backend behind it, and the new
world-data functionality that exists but is not yet aligned with the page.
Respect the visual identity tokens and the honesty rules at the end.

---

## Page 1 — `/commercial` (Commercial workspace)

**Current UI** (`autoevolve-ui/src/pages/CommercialPage.tsx`, 93 lines):
- Header ("Customers, pipeline, and proof"), founder-token field, 6 tabs:
  Setup / Accounts / ICPs & Qualification / Pipeline / Forms / Integrations.
- A "Company data" button + completeness badge opens the 6-card dialog.
- Setup tab (`pages/commercial/wizard.tsx`): identity-first — an identity
  card (name, description, website, completeness, 4-line checklist, Resume /
  Setup-new buttons) when data exists, else A/B starter cards; then a 6-step
  stepper when a session is active. Below the identity card sits a
  **Predicted outcomes** card (`BenchmarkCard`): industry line, cold band →
  replies-per-sends, opt-in band, sources/vintage/coverage note, sends
  input, your-vs-market position line, pool opt-in/out button.

**Current backend:**
- `app/commercial_api.py` — offers, ICPs (+ templates, suggest-criteria),
  accounts (+ suggest, qualify), pipelines, opportunities, rules, imports
  (preview/commit), integrations, onboarding-sessions.
- `app/company_context_api.py` — `GET/PUT /company/context` (merge-only).
- `GET /company/commercial/benchmarks`, `GET|POST .../network-stats`,
  `.../network-contribution` (Part D).

**Not aligned (redesign must fix):**
1. The Predicted outcomes card is visually a sibling of the identity card
   but conceptually its *consequence* — the layout does not read as
   "data in → prediction out". Make the causal flow visible.
2. The your-vs-market line only activates at 10+ sends; below that the page
   gives no sense of progress toward it (no sends counter, no milestone).
3. The pool opt-in/out sits inside the predictions card where it looks like
   a prediction setting; it is a *privacy* decision and belongs with
   identity, stated next to what is shared (counts only) and what is not.
4. The 6 tabs mirror backend tables, not founder tasks ("who do I sell to",
   "what do I say", "am I winning"). Consider task-grouped navigation.
5. Benchmark coverage honesty ("no industry-specific study on file") is a
   small gray note; it should be a first-class state, not fine print.

## Page 2 — `/onboarding` (First-run setup)

**Current UI** (`autoevolve-ui/src/pages/OnboardingPage.tsx`, 301 lines):
- Progress banner (program name, status, next step) + context badge.
- 9 numbered sections shown one-at-a-time by `next_step`: 1. company form
  → 2. research + 30-field confirm form → 3. AI strategy draft → 4. company
  search → 5. good/maybe/bad calibration → 6. refinement proposal →
  7. one-buyer-per-company → 8. first drafts → 9. activate → home.

**Historical backend:** the old `app/onboarding_api.py` ProgramState funnel
was removed. The current page uses the four-card canonical context wizard and
`GET/PUT /company/context`.

**Not aligned (redesign must fix):**
1. Step 2's 30-field confirm form is the heaviest form in the app and
   duplicates the Commercial company-data cards — two sources of truth for
   the same facts. Unify: one company-facts editor used by both pages.
2. Steps 3–4 (strategy → search) never show world benchmarks: the founder
   picks ICP industry and markets with no market reality attached. The
   `/benchmarks` data (cold band per industry, opt-in bands) should appear
   beside the industry/market fields *before* the search runs.
3. Step 5 calibration bands ("research band, lead score") are explicitly
   "not a verified fit model" — yet the page offers no world-data
   alternative. Show GLEIF identity status per candidate (real company?
   where registered?) as a free verification column.
4. Steps 7–8 (buyers, drafts) duplicate Contacts/Outreach functionality
   instead of deep-linking with context. Prefer handoff over duplication.

## Global constraints for the redesign

- **Visual identity** (`autoevolve-ui/src/styles.css:1`): dark-navy
  (`--background:#091726`, surfaces `#0f2031/#13263a/#172d43`,
  `--primary:#0869e8`, success/warning/danger as defined, `--radius:6px`,
  `--control-height:36px`, Inter system font). Reuse `cx-cards/cx-card`,
  `onboarding-panel/head`, `validation-actions`, `operational-note`,
  `StateBadge`, `RightDrawer`. No new colors, radii, or spacing scales.
- **Honesty rules** (non-negotiable): ranges with sources, never single
  averages; fallbacks labeled as fallbacks; misses stated, never filled;
  recorded data always overrides world data; advisory-only suggesters;
  opt-in default off; every new number carries provenance + vintage.
- **Backend is authoritative**: redesign moves UI only. New endpoints
  needed must be proposed as additions, never as behavior changes to
  existing ones. OpenAPI contract (`openapi.json` + `schema.ts`) must be
  regenerated; CI enforces zero drift.
- **One causal spine**: Identity → Predict → Execute → Position vs market
  → Contribute. Every redesigned page must show where it sits on that
  spine and link its neighbors.
