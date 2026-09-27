# AutoEvolve V2 closure report

## IMPLEMENTED

- First-run React onboarding over the existing settings, sales leads, company
  projections, contact resolution, and sales drafts. It saves own-company
  context, one conservative strategy, bounded real prospect calibration,
  explicit refinement decisions, one buyer per good company, and first drafts.
  It resumes after refresh/sign-in and activates only after backend-confirmed
  drafts exist. A wrong initial website can be corrected before research.
- Home now prioritizes saved drafts, campaign reviews, latest inbound replies,
  service incidents, and unfinished onboarding. Cards link to the relevant
  domain view; no positive intent, delivery, booking, or publication is inferred.
- Content now supports manual media upload/finalization through the existing
  marketing action and still treats Buffer draft, scheduled, and published as
  separate states.
- React-consumed JSON actions use typed Pydantic success responses and generated
  OpenAPI TypeScript types. The shared client handles JSON and multipart bodies
  correctly, and duplicate draft adapters were removed.

## CONTRACT CHANGES

- Typed onboarding read: `GET /company/ui/onboarding`.
- Typed, founder-token-gated onboarding writes:
  `/company/setup/onboarding/company`, `/research-company`,
  `/company/confirm`, `/strategy`, `/search`, `/calibration`, `/refinement`,
  `/buyer`, `/draft`, and `/activate`.
- Typed responses added to React-used sales, marketing, setup, Buffer schedule,
  manual-post creation, and incident reads. The existing `GET /company/incidents`
  path retains its semantics and now has a response model.
- OpenAPI and `autoevolve-ui/src/api/schema.ts` were regenerated from FastAPI.

## LEGACY CLEANUP

The replaced `/operations` sales and marketing routes, including the legacy
aliases and publishing URL, retain 307 redirects into React. The old general,
sales, and marketing Jinja templates were removed after caller and test checks.
The subsequent routing cleanup removed the root founder cockpit, the history UI,
and their CSS/JS. `/` and `/operations/history` now redirect to React Home.
`POST /` is retired; existing domain services and APIs remain available.
`/meet` and `/calendar` remain public booking utilities.
See [the route-by-route disposition](v2-closure.md#legacy-routes).

## TEST RESULTS

| Gate | Result |
| --- | --- |
| `make lint` | Passed |
| `make test` | 186 passed |
| OpenAPI export and TypeScript generation | Passed |
| Frontend typecheck, lint, build | Passed |
| Frontend unit tests | 10 passed |
| Default Playwright and visual regressions | 17 passed |
| Workflow Playwright and visual regressions | 9 passed |
| Sales workflow Playwright and visual regressions | 4 passed |
| Onboarding Playwright and visual regression | 1 passed |
| `git diff --check` | Passed |

The [testing and error-handling guide](v2-testing-and-errors.md) lists exact
commands, isolation rules, HTTP handling, and debugging order.

## RUNTIME VALIDATION

The actual FastAPI app started on `0.0.0.0:8787`. `/health` and `/openapi.json`
returned 200; all 12 React entry routes returned 200; all 12 authenticated
domain reads returned 200; an unauthenticated Home read returned 401. A browser
route sweep of all 12 operator pages reported no unexpected console errors or
unsuccessful API reads. Browser tests verified URL state, action-token denial,
backend-confirmed refresh, manual upload, Buffer scheduling/insights boundaries,
read-failure states, and onboarding resume/activation. The live-app probe was
read-only and disabled startup send reconciliation.

## KNOWN LIMITATIONS

- Live external research/enrichment, model drafting, outbound delivery, and
  Buffer publication were not invoked during regression tests. Browser fixtures
  replace providers while exercising the real FastAPI routes and temporary
  SQLite stores. Production-config authenticated **reads** were verified.
- The current backend has no trusted due-follow-up, positive-reply classifier,
  confirmed calendar booking, or program cost projection. Home omits those
  metrics rather than inventing them.
- Vite reports a non-failing warning for a roughly 513 kB JS chunk. This is a
  performance improvement opportunity, not a contract or workflow failure.

## DEFERRED ON PURPOSE

LinkedIn automation, fabricated provider health, scheduled-as-published status,
delivery confirmation inferred from send acceptance, and changes to the public booking utilities were excluded by the product
boundaries. The later operator cleanup removed the founder cockpit and history UI.

## FINAL VERDICT

**V2 closure pass complete for the requested scope.** All required test gates
passed. External provider outcomes remain subject to live credentials and the
existing backend gates; they were not simulated in production code.
