# Contributing

Repository: `AutoEvolve`. Application: `Company Core` (dashboard, config keys, and
`company-core-g1/g2/g3` binaries).

Company Core is an early open-source project. Small changes with tests and a clear lifecycle impact
are preferred over broad feature additions.

## Development

```bash
make setup
npm --prefix autoevolve-ui ci
npm --prefix autoevolve-ui run build
make check
make dev
```

Python 3.12+, Node.js 22, Make, OpenSSL, and FFmpeg are required. Use `make setup
PYTHON=python3.12` if your default Python is older. Open `http://localhost:8787`
for the built UI, or run `npm --prefix autoevolve-ui run dev` separately for Vite.

Provider substitutes belong only in tests. Production must not contain mock data.
Tests must not require paid provider credentials. Browser fixtures use isolated
SQLite storage and real FastAPI routes.

Run frontend typecheck, lint, build, unit tests, and all four Playwright suites
before merging UI changes; see [the frontend guide](autoevolve-ui/README.md).
CI also rejects stale generated OpenAPI/TypeScript files. Review visual baselines
against the [approved images](docs/ui-reference-coverage.md) before updating them.

## Pull requests

- Open an issue before significant API, schema, provider, or lifecycle changes.
- Keep one concern per pull request.
- Add tests for behavior and failure cases.
- Update documentation and `CHANGELOG.md` when users are affected.
- Do not include customer data, provider payloads, secrets, proprietary prompts, or unlicensed assets.
- Preserve human approval and delivery-idempotency invariants.

By contributing, you agree that your contribution is licensed under the repository's MIT License
and that you have the right to submit it.

## Provider adapters

A provider adapter must:

- Implement an existing protocol without leaking provider-specific data into domain models.
- Declare required environment variables and link to provider terms.
- Use bounded timeouts and return actionable errors.
- Supply anonymized or synthetic contract fixtures.
- Avoid live API calls in the default test suite.
- Document which actions consume credits or send external messages.

## Commit style

Use imperative, scoped messages such as `sales: enforce approval hash before send`. Maintainers may squash pull requests when merging.

## Public demos

Never record `.env`, API keys, real contacts, email bodies containing personal data, tunnel tokens, or
provider account pages. Use synthetic leads and controlled test sends only.
