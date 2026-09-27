# V2 testing and error handling

## Verification commands

Run from the repository root after dependencies are installed:

```bash
make lint
make test
.venv/bin/python scripts/export_openapi.py
npm --prefix autoevolve-ui run generate:api
npm --prefix autoevolve-ui run typecheck
npm --prefix autoevolve-ui run lint
npm --prefix autoevolve-ui run build
npm --prefix autoevolve-ui run test
npm --prefix autoevolve-ui run test:e2e
npm --prefix autoevolve-ui run test:e2e:workflows
npm --prefix autoevolve-ui run test:e2e:sales-workflow
npm --prefix autoevolve-ui run test:e2e:onboarding
```

Run the Playwright suites **sequentially**. They use separate fixture ports but
share Playwright's `test-results` directory; concurrent runs can delete each
other's trace files. Build the React bundle before browser tests because FastAPI
serves `autoevolve-ui/dist`; source-only changes are not visible until a build.

The browser fixtures run the real FastAPI app against temporary SQLite files.
Only external provider/model responses are replaced in tests. The onboarding
fixture starts with an empty database, then verifies persisted company context,
strategy, real sales candidates, individual ratings, approved refinement,
contact, draft, activation, and refresh. Other suites cover Contacts, Research,
Companies, Outreach, Replies, Meetings, Campaigns, Content, Integrations,
Settings, URL state, authorization gates, failures, and desktop screenshots.
`runtime-pages.spec.ts` traverses every React route and fails on unexpected
browser errors or unsuccessful `/company/*` reads.

Latest closure run (2026-09-25): `make lint` passed; `make test` passed
182/182; OpenAPI export and generated TypeScript schema completed; frontend
typecheck, lint, build, and 10/10 unit tests passed. Playwright passed
15/15 default, 9/9 workflow, 4/4 sales workflow, and 1/1 onboarding tests
without snapshot updates. The actual FastAPI app bound to `0.0.0.0:8787`
and returned 200 for `/health`, `/openapi.json`, all 12 React entry routes,
and all 12 authenticated read endpoints checked; an unauthenticated Home API
read returned 401. The live-app probe was read-only and disabled startup send
reconciliation. Browser screenshot baselines were inspected and refreshed for
the new onboarding navigation and Home/Content changes.

## Action and HTTP gates

`autoevolve-ui/src/api/client.ts` is the single transport/error adapter. It
uses exact case-sensitive paths and Basic auth. The founder token is sent only
on actions that require it, in `X-Founder-Action-Token`; it is never embedded
in React source or persisted by onboarding. Each action follows input → auth →
token/authorization → validation → backend guard → provider (if needed) →
persistence → narrow query invalidation → authoritative refetch. The UI only
reports completion after a typed backend success response.

| HTTP result | Frontend behavior | Retry behavior |
| --- | --- | --- |
| 400 | Show backend request error. | No automatic retry. |
| 401 | Clear invalid credentials and return to sign-in. | Sign in again. |
| 403 | Keep sign-in; show that the action is not authorized. | Supply a valid founder token/permission. |
| 404 | Show missing route/entity as an error, never an empty list. | Check exact path or selected record. |
| 409 | Show the backend state conflict; do not advance the workflow. | Refresh and review the authoritative state. |
| 422 | Show Pydantic field errors or backend validation detail. | Correct the request; repeated 422 means a contract bug. |
| 429 | Show the rate limit and `Retry-After` delay. | No hammering retry loop. |
| 5xx / network | Preserve previous valid query data and show a non-destructive error. | Explicit retry; log request ID where supplied. |

An empty state is rendered only after a successful read with zero items.
Provider failures never become zero results or a healthy integration state.
Onboarding company research stores an error and permits user-confirmed facts;
first company search preserves progress on provider failure. Partial provider
warnings remain visible. A healthy zero-result search remains a valid empty
search that can be retried.

## Semantic regression boundaries

Tests and UI preserve these separate facts: own marketing organization versus
prospect company; company candidate versus resolved company profile; contact
versus company; draft versus approved versus sent versus provider delivery;
reply versus positive reply; meeting marker versus calendar booking; campaign
versus post; Buffer draft versus scheduled versus published; provider key
present versus provider healthy. No screen infers a later state from an earlier
one. In particular, a ready manual post is not scheduled, and a Buffer
scheduled post is not presented as published.

When debugging a page, check `/health`, the exact route in `/openapi.json`,
path casing, Basic auth, founder token requirement, exact HTTP status/body,
raw rows via curl, generated schema, adapter mapping, query result, and then
React rendering—in that order. A failure report should include the action,
expected and actual behavior, exact method/path, status/body, prior frontend
and backend state, first divergence, root cause, fix, changed files, and test.


## Operator routing cleanup (2026-09-27)

React is the sole operator UI. GET `/` and `/operations/history` redirect to
`/home`; the former POST `/` command form is removed (405). Existing sales and
marketing compatibility redirects retain query strings. Canonical React pages
redirect trailing slashes with 308. Unknown browser routes return the React
not-found document with HTTP 404, then show a recovery link after sign-in.
Unknown API and removed static asset paths return JSON 404, never a successful
SPA document. Public `/meet` and `/calendar` remain available.

Regression proof: `tests/test_operations_ui.py` and
`autoevolve-ui/tests/e2e/routing.spec.ts`. This pass ran 186 backend tests,
10 frontend unit tests, and 31 Playwright tests (17 default, 9 workflows,
4 sales workflow, 1 onboarding), including the unchanged visual baselines.
Typecheck, lint, build, and generated API schema checks passed.
