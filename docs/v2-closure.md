# V2 closure: operator UI and first-run workflow

React under `autoevolve-ui/` is the operator UI. FastAPI remains the authority for
authentication, action tokens, records, provider calls, state transitions, and
persistence. The first-run program is one JSON setting (`v2_onboarding_program`) in
the existing state database. Its candidate companies and contacts are existing
`sales_leads`; its drafts are existing `sales_drafts`. The program's own company
context is distinct from prospect companies and own marketing organizations.

## First-run path

`GET /company/ui/onboarding` returns the typed saved program, next incomplete
step, and bounded real candidate sample. Mutations under
`/company/setup/onboarding/*` require Basic authentication and the existing
`SALES_ACTION_TOKEN`. Own-company research uses the configured CompanyEnrich or
PDL provider; unavailable research is reported and confirmed facts may be entered
manually. Search uses the existing sales research service and samples from actual
company candidates. Every candidate rating persists independently. Suggested
exclusions are applied only after an explicit approval. Buyer resolution uses
one existing contact at the same domain or a bounded provider lookup. Drafts use
the existing sales drafting service. Activation requires a good company, buyer,
and saved draft. It does not approve, send, schedule, or publish anything.

The strategy is saved with company context, offer, ICP, markets, buyer titles,
signals, exclusions, tone, approved/prohibited claims, channels, conservative
approval policy, and small provider limits. Onboarding buyers carry a program ID
in existing lead metadata; the existing draft context includes that program's
offer/tone/claim boundaries. Human review and existing send guards still apply.

## Legacy routes

| Old route | Current destination | Caller migration and disposition |
| --- | --- | --- |
| `/operations`, `/legacy/operations` | `/home` | Old Jinja operator overview removed; redirect retained. |
| `/operations/sales`, `/operations/sales/discovery` | `/research` | Old sales template removed; redirect retained. |
| `/operations/sales/email`, `/legacy/operations/sales/email` | `/outreach` | Old email template and legacy script removed; redirect retained. |
| `/operations/marketing`, `/operations/marketing/campaigns`, `/legacy/operations/marketing[/campaigns]` | `/campaigns` | Old marketing template removed; redirect retained. |
| `/operations/marketing/assets`, `/legacy/operations/marketing/assets` | `/content` | Old marketing template removed; redirect retained. |
| `/operations/marketing/publishing` | `/content` | React Content now uploads/finalizes manual posts; redirect retained. |
| `/operations/history` | `/home` | Old archive UI removed; historical records retained in existing APIs. |
| `/` | `/home` | Founder cockpit UI removed; old POST command entry retired (405). |
| `/meet`, `/calendar` | kept | Public utility pages. |

`templates/operations.html`, `operations_sales.html`, and
`operations_marketing.html` were removed after checking code/tests/docs callers
and proving compatibility redirects. The subsequent routing cleanup also removed
`templates/index.html`, `templates/operations_history.html`, `static/cockpit.css`,
`static/cockpit.js`, and `static/operations.js`. No operator Jinja templates remain.
Public `/meet` and `/calendar` retain their independent booking templates.

Canonical React paths omit trailing slashes (308 redirects preserve queries).
Legacy bookmarks keep 307 redirects and query state. Unknown browser addresses
receive a React not-found document with HTTP 404; unknown API routes remain JSON
404. Backend authentication and action-token gates are unchanged.

## Contract and error boundaries

React reads use Pydantic response projections. React-consumed sales, setup,
marketing, Buffer schedule, and onboarding mutations have typed success models;
TypeScript adapters use the generated OpenAPI schema. The shared client retains
distinct 401, 403, 404, 422, 429, and 5xx handling. FormData uploads omit a
manually supplied JSON content type. Draft, approved, sent, delivered, scheduled,
published, candidate, contact, and own-organization states remain separate.

Home counts saved work requiring review: unapproved drafts, campaigns awaiting
review, latest inbound replies, and unresolved service incidents. Cards link to
the relevant React domain page. It does not infer positive intent from replies,
confirmed calendar bookings from meeting markers, or publication from Buffer
scheduling.
