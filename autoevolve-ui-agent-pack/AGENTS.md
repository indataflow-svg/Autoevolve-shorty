# AGENTS.md — AutoEvolve

## Purpose
AutoEvolve is an existing sales and marketing operating system. The current frontend work must modernize the UI without rewriting the backend or inventing product behavior.

Read `docs/UI_IMPLEMENTATION.md` before frontend implementation. Read `docs/SCREENSHOT_REFERENCES.md` for any visual/layout task.

## Source-of-truth order
1. Existing backend behavior and persisted data
2. Existing API contracts / OpenAPI schema
3. Existing product/workflow docs
4. `docs/UI_IMPLEMENTATION.md`
5. Approved screenshots in `references/ui/`
6. Legacy frontend behavior
7. Agent assumptions

Never change backend semantics merely to make a screenshot easier to reproduce.

## Non-negotiable rules
- Backend is authoritative.
- Never fabricate production data, API fields, provider states, metrics, or successful actions.
- Never bypass approval/action gates.
- Do not rewrite working backend services for frontend convenience; add DTO/adapters where needed.
- Use generated OpenAPI TypeScript types whenever practical.
- Use TanStack Query for server state.
- Use TanStack Table for business tables.
- Use local React state for ephemeral UI.
- Use URL search params for shareable/restorable filters, tabs, sorting, pagination, and selection where appropriate.
- Reuse shared components before adding page-local variants.
- Use design tokens; do not invent arbitrary page-local colors, radii, shadows, or spacing.
- Every data page needs loading, empty, error, stale/refetching, and long-content states.
- Never report an external/destructive mutation as successful before backend confirmation.
- Do not add Next.js, Redux, Prisma, or a second application server unless explicitly approved.
- Mock data is allowed only in Storybook/tests, never production paths.
- Preserve program separation and existing workflow semantics.
- Preserve any manual-action boundary already enforced by the product.
- Use semantic HTML and keyboard-operable controls.

## Preferred frontend stack
- React
- Vite
- TypeScript strict
- Tailwind CSS
- shadcn/ui or Radix primitives
- TanStack Query
- TanStack Table
- React Router
- openapi-typescript or equivalent generated client
- Storybook
- Playwright

Do not replace working equivalents without a concrete reason.

## Preferred structure
```text
frontend/
  src/
    app/
    pages/
    components/
      shell/
      tables/
      records/
      metrics/
      ui/
    api/
    hooks/
    lib/
    styles/
  tests/
    e2e/
    visual/
  public/
```

Keep Python backend code where it already belongs.

## Required UI workflow
Before editing:
1. Inspect repo structure.
2. Locate relevant backend routes/models/services.
3. Inspect OpenAPI generation/client.
4. Read `docs/UI_IMPLEMENTATION.md`.
5. Read `docs/SCREENSHOT_REFERENCES.md`.
6. Inspect the matching screenshot at full/original detail.
7. Mark visible fields/actions as real, derivable, missing, or unsupported.
8. Write a short plan before broad edits.

During implementation:
1. Reuse/build shared primitives first.
2. Connect real queries before cosmetic polish.
3. Keep URL state synchronized.
4. Preserve action-gated transitions.
5. Use screenshots as visual targets, not reasons to hardcode pixels.
6. Test realistic long names, missing values, errors, and loading.
7. Keep stale data visible during background refetches when possible.

After implementation:
1. Typecheck.
2. Lint/format.
3. Run relevant unit/component tests.
4. Run Playwright e2e.
5. Run visual screenshot checks.
6. Run relevant backend tests if API/DTO changed.
7. Inspect in a real browser at the approved desktop viewport.
8. Report screenshot elements unsupported by current backend.

## Visual language
- dark navy application shell
- fixed left navigation
- top global search/header
- dense, readable enterprise tables
- restrained blue primary actions
- green/yellow/red/purple semantic accents
- subtle borders
- compact radii
- crisp white primary text and muted blue-gray secondary text
- contextual right-side drawers
- KPI strip near page top when appropriate
- saved views/status tabs above the main table
- row-level next actions
- compact iconography
- no neon glow
- no glassmorphism
- no generic admin-template styling
- no oversized marketing typography inside the app
- no random page-local gradients

Match hierarchy, density, alignment, spacing rhythm, shape, and interaction model before tiny pixel differences.

## Screenshot locations
```text
references/ui/
  01-integrations.jpeg
  02-research.jpeg
  03-content.jpeg
  04-settings.jpeg
  05-campaigns.jpeg
  06-meetings.jpeg
  07-replies.jpeg
  08-contacts.jpeg
  09-outreach.jpeg
```

## Recommended page order
1. App shell
2. Contacts
3. Outreach
4. Companies
5. Replies
6. Research
7. Meetings
8. Campaigns
9. Content
10. Integrations
11. Settings
12. Home/dashboard

Build Home last so it composes existing real queries/components.

## Mutation policy
Low-risk reversible metadata may be optimistic with rollback.

Do not optimistically confirm:
- send email
- suppress/unsubscribe
- publish content
- approve/execute external campaign actions
- provider configuration
- destructive settings
- billing/licensing
- any other external side effect

Use:
```text
user action
→ pending
→ backend confirmation
→ invalidate/refetch
→ authoritative rendered state
```

## Definition of done
A page is complete only when:
- real backend data renders
- visible actions map to real allowed transitions
- loading/empty/error states exist
- filters/sort/page persist in URL where appropriate
- selected-record drawer works
- keyboard/focus basics work
- TypeScript is clean
- relevant tests pass
- visual baseline is reviewed
- no fake production data remains
- browser output matches the approved visual language
- backend limitations are represented honestly
