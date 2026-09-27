# UI_IMPLEMENTATION.md — AutoEvolve Frontend System

## Objective
Build a production frontend over the existing AutoEvolve backend.

The screenshots are the **visual specification**. The backend is the **behavioral and data specification**.

```text
BACKEND CONTRACT
      +
REFERENCE SCREENSHOT
      +
UI RULES
      ↓
inspect + plan
      ↓
implement one vertical slice
      ↓
run real app
      ↓
browser screenshot
      ↓
compare
      ↓
functional + visual tests
      ↓
accept
      ↓
reuse on next page
```

## Architecture boundary
Keep FastAPI, existing business services, storage/database, and provider integrations.

Preferred production shape:
```text
Cloudflare / reverse proxy
        ↓
FastAPI
  ├─ API routes
  ├─ business services
  ├─ storage/database
  ├─ provider integrations
  └─ built React application
```

The React app is a frontend client, not a second backend. Do not add Next.js only to proxy into FastAPI.

## API contract
Preferred flow:
```text
Pydantic / FastAPI
      ↓
OpenAPI
      ↓
generated TypeScript schema/client
      ↓
frontend domain adapters/hooks
      ↓
React components
```

Typical generation command:
```bash
npx openapi-typescript http://localhost:8787/openapi.json -o src/api/schema.ts
```
Adjust the port/path to the repo.

Do not scatter raw fetch calls through components. Prefer:
```text
src/api/
  client.ts
  companies.ts
  contacts.ts
  outreach.ts
  replies.ts
  meetings.ts
  campaigns.ts
  content.ts
  research.ts
  integrations.ts
  settings.ts
```

## State ownership
- TanStack Query → backend/server state
- local React state → drawer/modal/selection/transient UI
- URL params → page, filter, sort, active view, deep-linkable selection
- add a global client-state library only if a real cross-cutting need appears

Examples:
```text
/contacts?program=foundry&status=ready&page=2
/outreach?stage=followup_due
/replies?intent=meeting_request
/research?company=123
```

## Shared component system

### Shell
- AppShell
- Sidebar
- Topbar
- GlobalSearch
- PageHeader
- PageBody
- RightDrawer

### Data
- DataTable
- TableToolbar
- ViewTabs
- FilterButton
- FilterChip
- SortMenu
- Pagination
- BulkSelectionBar
- EmptyState
- ErrorState
- LoadingRows

### Records
- CompanyCell
- ContactCell
- FitScore
- ProgramBadge
- StatusBadge
- SourceBadge
- OwnerAvatar
- ActivityTimestamp
- SignalList

### Actions
- PrimaryButton
- SecondaryButton
- DangerButton
- ActionMenu
- ConfirmationDialog

### Metrics
- MetricCard
- TrendIndicator
- HealthStatus

Reuse semantic components rather than creating near-duplicates page by page.

## Initial visual tokens
Centralize values first and refine through browser comparison.

```css
:root {
  --background: #07111f;
  --surface-1: #0b1726;
  --surface-2: #0e1c2d;
  --surface-3: #102235;
  --border: #1c3044;
  --border-strong: #29445f;

  --text: #f6f8fb;
  --text-muted: #92a4b8;
  --text-subtle: #6f8298;

  --primary: #1476ff;
  --success: #31d89b;
  --warning: #f7c32e;
  --danger: #ff5d6c;
  --purple: #9b66ff;
}
```

Also define:
- radius scale
- spacing scale
- font scale
- control heights
- border widths
- drawer widths
- table row heights
- shadow levels

## Screenshot-derived desktop grammar
```text
┌──────────────┬───────────────────────────────────┬────────────────┐
│ Sidebar      │ Topbar / global search            │ optional       │
│ ~220px       ├───────────────────────────────────┤ right drawer   │
│              │ Page header + actions             │ ~340–400px     │
│              │ KPI strip                         │                │
│              │ View tabs / filters               │                │
│              │ Main table / content              │                │
│              │ Pagination / secondary section    │                │
└──────────────┴───────────────────────────────────┴────────────────┘
```

Use CSS Grid/Flexbox. Never trace this with absolute positioning.

## Density
The approved UI is deliberately information-dense:
- compact controls
- narrow card padding
- table-first hierarchy
- subtle separators
- modest radii
- minimal decorative emptiness

## Right drawer
- desktop: ~340–400px
- tablet: overlay drawer
- mobile: full-screen detail layer

The drawer exists to preserve table context.

## Page-specific guidance

### Contacts — `08-contacts.jpeg`
Recommended first vertical slice.

Core:
- title + import/enrich/add
- four KPIs
- program/status tabs
- filters/sort
- contact table
- selected contact drawer

Map real fields such as contact, company, role, email state, fit score, source, last activity, owner, next action.

Drawer:
- identity
- company
- contact methods
- fit/context
- research
- activity
- notes
- tags
- primary workflow action

### Outreach — `09-outreach.jpeg`
Preserve explicit workflow states:
- draft ready
- needs edit
- approved
- sending
- sent
- follow-up due
- replied
- suppressed

Do not bypass action gates. "Approve & send" is valid only if the backend safely executes the required authorized transitions.

### Replies — `07-replies.jpeg`
Keep original inbound message distinct from generated signals/response.
Expose intent, confidence, last received, suggested action.
Suppression must be backend-confirmed.

### Meetings — `06-meetings.jpeg`
Use actionable list as primary surface. Calendar summary is secondary.
Meeting links, status, notes, agenda, source, and opportunity must come from real data.

### Campaigns — `05-campaigns.jpeg`
Show program/channel/status/owner/launch/leads/next step.
Only render real analytics. Keep marketing state machine aligned with backend gates.

### Content — `03-content.jpeg`
Separate format from lifecycle stage.
Drawer may contain script/caption, assets, platform targets, review/regenerate/handoff actions only when supported.

### Research — `02-research.jpeg`
Company-centric workspace.
Keep filters separate from table toolbar.
Do not invent technologies, signals, or recommendations.

### Integrations — `01-integrations.jpeg`
Show real provider/category/status/activity/capabilities.
Never fake health, usage, webhook activity, or connection state.
Never expose credentials.

### Settings — `04-settings.jpeg`
Use sectional forms with secondary settings navigation.
Do not expose secrets or create fake security/billing controls.

## Responsive behavior
### Desktop
fixed sidebar + main workspace + contextual drawer

### Tablet
collapsed navigation + main workspace + overlay drawer

### Mobile
compact navigation + list/card adaptation + full-screen record detail

Do not squeeze desktop tables into a phone viewport.

## Table policy
Use TanStack Table for:
- sorting
- filtering
- visibility
- row selection
- pagination
- bulk action state

Prefer server-side pagination/filtering for large datasets.

Example:
```text
?page=1
&page_size=50
&sort=-last_activity
&program=foundry
&status=qualified
```

## Loading/refetch
Avoid a giant blocking spinner.
Use:
- metric skeletons
- row skeletons
- drawer skeletons
- pending action states

During background refresh:
- keep existing data visible
- show a restrained refresh indicator
- never flash the whole table empty

## Mutations
Optimistic UI is acceptable for reversible metadata with rollback.

Wait for backend confirmation for:
- send
- publish
- suppress
- provider changes
- destructive settings
- campaign execution

## Storybook minimum matrix
```text
FitScore / high
FitScore / medium
FitScore / low

StatusBadge / draft
StatusBadge / approved
StatusBadge / sent
StatusBadge / suppressed
StatusBadge / warning

DataTable / loading
DataTable / empty
DataTable / populated
DataTable / long-content

RightDrawer / loading
RightDrawer / complete
RightDrawer / missing-data
RightDrawer / error
```

## Visual regression
Use Playwright screenshot tests for approved pages.

Example:
```ts
await expect(page).toHaveScreenshot("contacts.png");
```

Keep the comparison environment consistent because fonts/OS rendering can affect pixels.

Visual diffs should catch:
- shell width drift
- padding drift
- typography drift
- missing separators
- drawer sizing
- toolbar misalignment
- badge inconsistency

Do not use pixel parity as the only quality gate.

## Contacts first-slice acceptance
```text
GET real contacts
→ render table
→ filter/sort/page
→ select row
→ open drawer
→ show real contact/company
→ trigger real draft-outreach path
→ receive backend confirmation
→ update authoritative state
```

Acceptance:
- no production mock records
- real auth transport works
- refresh preserves URL state
- selection deep-link works where practical
- screenshot is visually close to reference
- keyboard focus is usable
- typecheck/lint/tests pass

## Implementation phases
### Phase A — foundation
Shell, router, API client, generated types, auth transport, tokens, shared components, Storybook, Playwright.

### Phase B — Contacts
Complete end-to-end vertical slice.

### Phase C — Outreach
Real state machine and action gates.

### Phase D — sales loop
Companies, Replies, Research, Meetings.

### Phase E — marketing
Campaigns, Content.

### Phase F — operations
Integrations, Settings, then Home/dashboard.

## Reject these anti-patterns
- "copy screenshot" without backend mapping
- implementing every page in one giant pass
- absolute-position screenshot tracing
- production mock data
- random raw fetches in components
- duplicated page-local table/badge systems
- backend schema rewrites for frontend convenience
- fake analytics/provider health
- optimistic success for external side effects
- unnecessary framework expansion
- hiding unsupported features behind fake success

## Visual success priority
1. information architecture
2. shell proportions
3. page hierarchy
4. table/drawer geometry
5. spacing rhythm
6. typography
7. semantic color roles
8. component consistency
9. interaction fidelity
10. small pixel refinements

A 95% visual match backed by real behavior is better than a 100% screenshot trace backed by fake data.
