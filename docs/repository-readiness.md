# Repository packaging and startup readiness

## Source layout

- `app/`: FastAPI routes, authentication, typed reads and domain actions.
- `core/`: SQLite stores, settings, identity, read projections.
- `services/`, `agents/`, `tools/`, `workers/`: existing business execution.
- `engines/g1`, `g2`, `g3`: existing marketing/content/media engines.
- `autoevolve-ui/`: React/Vite source, lockfile, generated contract, browser tests and baselines.
- `autoevolve-ui-agent-pack/`: original approved images and implementation rules.
- `templates/`, `static/`: public booking templates and logo; no old operator UI.
- `docs/`: current guides, clearly labelled historical audits, and current system diagram.
- `docs/plans/`: preserved original planning documents and target-state drawings.

The frontend is ordinary source in the main repository, not a nested Git
repository or a submodule. Its former Git metadata was backed up outside the
project before consolidation. Local `.env`, G3 secrets, virtual environments,
node_modules, builds, browser artifacts, databases, logs, and runtime projects
are excluded from Git. Docker context also excludes local secrets and registries.

## Startup contract

Use [README](../README.md) for the complete installation sequence and
[Frontend Guide](../autoevolve-ui/README.md) for development and browser setup.
Python 3.12+, Node.js 22, Make, OpenSSL, and FFmpeg are required. Setup creates
local credentials; npm builds React; `make dev` runs FastAPI on `0.0.0.0:8787`.
Open `http://localhost:8787`; `/` redirects to Home. Provider configuration is
required only for corresponding actions. A container is optional.

## Regression and documentation checks

The GitHub workflow retains backend/engine tests and adds frontend contract
drift, typecheck, lint, build, unit tests, and all four Playwright suites. Browser
suites execute sequentially with isolated fixture storage. Failed browser runs
upload traces/screenshots. Baselines are never automatically updated in CI.

Current guide links and Excalidraw JSON were checked locally. The startup
instructions and CI commands are documented precisely, but a new checkout's
installation has **not** been validated: fresh-clone testing was explicitly
excluded. Adding the workflow is not evidence that a hosted GitHub run passed.
Live paid providers and outbound writes remain outside fixture validation.

See [UI Reference Coverage](ui-reference-coverage.md) for original-image versus
implementation-baseline distinctions, and [Testing and Errors](v2-testing-and-errors.md)
for test commands and authoritative failure handling.


## Local validation record (2026-09-27)

Backend pytest: 186 passed. Frontend unit tests: 10 passed. Playwright: 31 passed
(17 default, 9 workflows, 4 sales workflow, 1 onboarding), including existing
visual comparisons. Backend lint and frontend typecheck/lint/build passed.
G1: 25 passed; G3: 30 passed. G2 initially failed because the local host lacked
FFmpeg/ffprobe; those documented prerequisites were installed and the rerun passed all 68 tests.
The existing GitHub backend job already installs FFmpeg before engine checks.
