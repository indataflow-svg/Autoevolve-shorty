# AutoEvolve operator UI

React/Vite is the sole operator UI for the existing FastAPI backend. `/` redirects
to `/home`; `/onboarding` guides first-run setup. See [Product Tour](../docs/product-tour.md)
for all twelve operator pages and [UI Reference Coverage](../docs/ui-reference-coverage.md)
for approved image mappings and current visual baselines.

## First startup

From the repository root, with Python 3.12+, Node.js 22, Make, OpenSSL, and FFmpeg:

```bash
make setup PYTHON=python3.12
npm --prefix autoevolve-ui ci
npm --prefix autoevolve-ui run build
make dev
```

Open `http://localhost:8787`. FastAPI serves both API routes and the built React
bundle. Provider keys are optional for opening the UI; actions report missing
configuration honestly. Docker is optional. Production uses a process manager
and HTTPS as described in [Deployment](../docs/deployment.md).

## Frontend development

Keep `make dev` running in one terminal. In another:

```bash
npm --prefix autoevolve-ui run dev
```

Open `http://localhost:5173/home`. Vite proxies `/company` to FastAPI on port 8787.
Rebuild before returning to the single-process FastAPI UI; Vite edits do not
update `dist` automatically. Browser paths and API paths are case-sensitive.

## Authentication

Sign in with `DASHBOARD_USER` and `DASHBOARD_PASSWORD` from the private `.env`.
Credentials live only in memory: refresh requires sign-in again, while URL
filters, record selections, and backend onboarding progress remain saved.
Guarded actions prompt for `SALES_ACTION_TOKEN`; it is never hardcoded or stored
persistently in the browser. A 401 clears sign-in; a 403 keeps it and reports the
forbidden action. See [Testing and Errors](../docs/v2-testing-and-errors.md).

## Validation

From the repository root:

```bash
npm --prefix autoevolve-ui run generate:api
npm --prefix autoevolve-ui run typecheck
npm --prefix autoevolve-ui run lint
npm --prefix autoevolve-ui run build
npm --prefix autoevolve-ui run test
cd autoevolve-ui
npx playwright install --with-deps chromium
cd ..
npm --prefix autoevolve-ui run test:e2e
npm --prefix autoevolve-ui run test:e2e:workflows
npm --prefix autoevolve-ui run test:e2e:sales-workflow
npm --prefix autoevolve-ui run test:e2e:onboarding
```

Run browser suites sequentially because they share artifact output directories.
Playwright runs the real FastAPI app with isolated SQLite fixture storage and
provider replacements only in `tests/*fixture_server.py`. It does not exercise
live outbound providers. CI checks generated OpenAPI/TypeScript drift, all
frontend checks, all four browser suites, and committed screenshot baselines.
Do not update baselines merely to make a failing comparison pass; review against
the approved images and backend limitations first.
