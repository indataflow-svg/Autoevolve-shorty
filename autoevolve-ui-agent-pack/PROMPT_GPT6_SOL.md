# GPT-6 Sol Prompt — AutoEvolve UI Implementation

You are working inside the existing AutoEvolve repository.

Your task is to implement the production frontend from the approved screenshot references while preserving the existing FastAPI backend, data model, workflow semantics, security boundaries, action gates, and provider behavior.

Use high reasoning by default.

Use xhigh reasoning for:
- first-page architecture
- screenshot decomposition
- backend-contract mapping
- difficult visual parity work
- cross-file debugging
- API/frontend integration problems

Use max reasoning only if a problem remains unresolved after a serious xhigh attempt.

## Read before changing code

Inspect:

1. `AGENTS.md`
2. `docs/UI_IMPLEMENTATION.md`
3. `docs/SCREENSHOT_REFERENCES.md`
4. current repository architecture
5. current frontend implementation
6. relevant FastAPI routes
7. relevant Pydantic models
8. relevant services
9. generated or live OpenAPI schema
10. the screenshot(s) for the requested page under `references/ui/`

Do not begin by generating generic UI code.

Do not rewrite the frontend architecture until you understand the existing application.

---

## Visual-reference method

Treat each screenshot as a structured interface specification, not as a flat image.

Inspect the relevant screenshot directly as image input at the highest/original detail available.

Analyze:

- global shell regions
- sidebar width and hierarchy
- topbar geometry
- page header placement
- grid/flex relationships
- main content width
- right-drawer width
- repeated alignment lines
- spacing rhythm
- typography hierarchy
- font size relationships
- control heights
- card dimensions
- table row density
- border treatment
- radius treatment
- icon sizing
- semantic colors
- selected-row state
- hover/action affordances
- drawer anatomy
- KPI-card structure
- filter/tab hierarchy
- pagination placement
- reusable component families
- responsive implications

Do not copy screenshot sample text or values blindly.

The screenshot defines:

- visual hierarchy
- proportions
- density
- interaction patterns
- component relationships
- styling direction

The backend defines:

- actual fields
- actual values
- workflow states
- permissions
- provider health
- metrics
- actions
- side effects

If the screenshot contains information unavailable from the backend:

1. map it to a real derivable value if possible,
2. otherwise omit it cleanly,
3. or show a truthful unavailable/unconfigured state.

Never fabricate production data.

---

## Architecture target

Unless the repository already contains equivalent approved tooling, prefer:

- React
- Vite
- TypeScript strict
- Tailwind
- shadcn/Radix primitives
- TanStack Query
- TanStack Table
- React Router
- generated OpenAPI TypeScript types/client
- Storybook
- Playwright

Do not introduce:

- Next.js
- Redux
- Prisma
- a second backend
- an unnecessary BFF layer
- a generic admin-dashboard template

unless the repository has a real requirement for it.

The React frontend should remain a client of the existing FastAPI application.

---

## Core principle

This is not screenshot cloning.

Build:

```text
real backend contract
+
approved visual reference
+
shared design system
+
real workflow behavior
