# G3 Lite closure plan

G3 is a narrow Buffer delivery boundary. It does not render media, write copy, directly publish posts, or host a web application. The handoff remains draft-only; scheduling requires a separate explicit command and founder-gated FastAPI action. A read-only command can retrieve provider post state and optional metrics.

## Architecture

1. G2 emits a checksummed `company-core.g3-handoff.v1` manifest.
2. G3 verifies the manifest, local path confinement, MIME type, and every media SHA-256.
3. G3 uploads immutable media objects to Cloudflare R2.
4. G3 proves the exact public URL is anonymously readable and returns the expected media bytes and content type.
5. `draft` creates an Instagram carousel draft and/or X thread draft through Buffer GraphQL.
6. `schedule` separately requests queue, next-slot, or timed scheduling and records Buffer's confirmed post ID.
7. `insights` reads the saved Buffer post ID's provider state and optional personal-key metrics.
8. The founder retains control; a scheduled post is not labelled published until Buffer reports it sent.

## Closure gates

| Gate | Evidence |
| --- | --- |
| Local footprint | Python virtual environment plus SQLite; no Docker services |
| Buffer connection | `company-core-g3 doctor --require instagram --require x` |
| Media hosting | R2 credentials validate and each permanent HTTPS URL passes an anonymous range request |
| Safety | Manifest rejects publication fields; API boundary hard-codes and checks `saveToDraft: true` |
| Instagram | One multi-image Buffer draft appears in the Instagram channel |
| X | One Buffer X thread draft appears with ordered parts |
| Idempotency | Re-running the same handoff returns `duplicate_skipped` |
| Human control | Scheduling is a separate founder-gated action; direct publication is unavailable |
| Insights | Read only, personal API key, experimental metrics may be unavailable or delayed |
