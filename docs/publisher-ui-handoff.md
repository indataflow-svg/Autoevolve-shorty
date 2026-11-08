# Publisher UI handoff

Status as of 2026-10-28. Backend is live; Content already supports publisher
selection for Buffer and an optional signed webhook. This note is the checklist
for finishing the publisher experience in the UI.

See [Publishers: Buffer + webhook schedulers](publishers.md) for the wire
contract and [FUNCTIONALITY §4](FUNCTIONALITY.md) for the product view.

## Current state

| Area | State |
|---|---|
| Buffer adapter | Live, unchanged G3 path |
| Signed webhook adapter | Live, opt-in via `PUBLISHER_WEBHOOK_*` |
| Manual post `publisher` | Stored in metadata, default `buffer` |
| Content → New manual post | Publisher + publisher-account selectors |
| Content drawer | Schedule / draft / confirm / insights use generic routes |
| Content table | Publisher column |
| Settings/Integrations config UI | **Not built** — env only today |
| Per-organization webhook config | **Not built** — one global webhook |
| Retry/backoff UI | **Not built** — receiver should dedupe idempotency keys |

Buffer stays first and selected by default. The webhook option appears only
when `PUBLISHER_WEBHOOK_URL` and `PUBLISHER_WEBHOOK_SECRET` are set.

## API contract used by the UI

All routes are under `/company/marketing` and require dashboard Basic auth.
Scheduling and confirmation require the founder action token; draft creation
does not (Buffer-only parity with the legacy route).

### `GET /publishers`

```json
{"publishers":[
  {"name":"buffer","label":"Buffer",
   "capabilities":{"draft":true,"schedule":true,"confirm":true,"insights":true,
                   "platforms":["instagram","x","linkedin"]}},
  {"name":"webhook","label":"Webhook scheduler",
   "capabilities":{"draft":false,"schedule":true,"confirm":true,"insights":true,
                   "platforms":["instagram","x","linkedin"]}}
]}
```

### `GET /publisher-accounts?publisher=buffer|webhook`

```json
{"publisher":"buffer","label":"Buffer",
 "capabilities":{"draft":true,"schedule":true,"confirm":true,"insights":true,
                 "platforms":["instagram","x","linkedin"]},
 "error":null,
 "accounts":[
   {"name":"default","label":"Buffer · default","platforms":["instagram","x"],
    "details":{"publisher":"buffer","organization_id":"..."}}
 ]}
```

`error` is surfaced when G3 reports a Buffer configuration problem. The UI
currently disables scheduling and shows the error.

### `POST /manual-posts/{id}/publish`

```json
{"action":"schedule","mode":"queue|next|timed","due_at":null,"account":"default"}
```

`X-Founder-Action-Token` required. Dispatches to the post's stored publisher.
Response is the publisher result plus the refreshed post:

```json
{"ok":true,"post":{...ContentItem...},"result":{...},"message":"..."}
```

### `POST /manual-posts/{id}/publish/draft`

Buffer only; webhook returns `409`. No founder token (parity with the legacy
Buffer draft route).

### `POST /manual-posts/{id}/publish/confirm`

Founder token required. Returns:

```json
{"ok":true,"post":{...},"confirmation":{"checked_at":"...","overall":"sent|failed|pending|unknown","posts":{...}},"message":"..."}
```

### `GET /manual-posts/{id}/publish/insights?post_id=...`

Returns the existing insights shape (`post_id`, `buffer_account`, `status`,
`due_at`, `external_link`, `metrics`, `metrics_updated_at`, `experimental`).
For the webhook, `buffer_account` is the publisher account name.

### Content item fields added

`ContentItem` / `_public_manual_post` now include:

- `publisher` (`buffer` default)
- `publisher_status`
- `publisher_post_ids`
- `publisher_account`
- `publisher_scheduled_at`
- `publisher_send_confirmation`

Legacy `buffer_status`, `buffer_post_ids`, `buffer_account`,
`buffer_scheduled_at`, `buffer_send_confirmation` remain and are used as
fallbacks for records created before this change.

## UI work remaining

1. **Publishers settings panel.** Put it under Integrations → Setup or
   Settings → Publishing:
   - Buffer row: read-only accounts/health, link to existing Buffer setup.
   - Webhook row: URL, secret, account name, label, platforms,
     `PUBLIC_BASE_URL`, timeout, asset TTL.
   - Masked secret on read; never return it.
   - “Send test event” button.
   - Save/restart behavior must be explicit (env writes need a restart today).
2. **Backend endpoints for that panel** (not yet built):
   - `GET /company/marketing/publishers/webhook` → masked configured state.
   - `PUT /company/marketing/publishers/webhook` (founder token) → write
     values via `core.setup_keys` or a new `publisher_connections` table.
   - `POST /company/marketing/publishers/webhook/test` → signed `ping` action,
     returns the receiver's response or the transport error.
   - Never return `PUBLISHER_WEBHOOK_SECRET` or signed media URLs from reads.
3. **Per-account platform gating.** Today the platform list comes from adapter
   capabilities; warn if the selected account has no channel for that platform.
4. **Capability gating.** Hide draft/confirm/insights when the adapter says
   false; keep the current schedule gating and the `error` state.
5. **Empty/error states.** Unconfigured webhook, missing `PUBLIC_BASE_URL`,
   unreachable receiver, invalid signature, unsupported platform, and
   no-saved-post confirm each need a specific message.
6. **Retry/backoff.** Add a visible retry for `502` schedule failures; the
   idempotency key is stable, so receivers can safely dedupe.
7. **Per-organization webhooks (later).** The current adapter is global env,
   matching the single-tenant dashboard. A per-org table and credential
   resolution are separate work.

## Local end-to-end test

Start the dev receiver (stdlib, verifies HMAC, fetches media links):

```bash
PUBLISHER_WEBHOOK_SECRET=dev-secret \
  .venv/bin/python scripts/publisher_webhook_dev.py
```

Configure the app (`.env` then restart uvicorn):

```dotenv
PUBLISHER_WEBHOOK_URL=http://127.0.0.1:8799/hook
PUBLISHER_WEBHOOK_SECRET=dev-secret
PUBLISHER_WEBHOOK_ACCOUNT=dev
PUBLISHER_WEBHOOK_LABEL=Dev scheduler
PUBLISHER_WEBHOOK_PLATFORMS=instagram,x,linkedin
PUBLIC_BASE_URL=http://127.0.0.1:8787
```

Then in Content: **New manual post → Publisher: Dev scheduler**, upload media,
save, open the drawer, schedule, confirm. The receiver prints the payload and
media fetch result, then answers `scheduled`, `sent`, and metrics.

If the app runs in Docker, use a host reachable from the container
(`host.docker.internal` on Docker Desktop or the host bridge IP on Linux) for
`PUBLISHER_WEBHOOK_URL`, and the app's externally reachable origin for
`PUBLIC_BASE_URL`.

## Tests to keep green

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q tests/test_publishers.py tests/test_publisher_api.py
cd autoevolve-ui && npm run lint && npm run typecheck && npm test
cd autoevolve-ui && npx playwright test --config playwright.workflows.config.ts
```

The workflows fixture seeds Buffer manual posts; it currently does not set
`PUBLISHER_WEBHOOK_*`. To test webhook UI, add those env vars to
`tests/workflow_fixture_server.py` and a receiver (or mock `httpx.post`).

## Files

- `services/publishers/base.py` — port types
- `services/publishers/buffer.py` — Buffer/G3 wrapper
- `services/publishers/webhook.py` — signed adapter, media links, status
- `services/publishers/__init__.py` — registry/catalog
- `app/marketing_api.py` — publisher routes, manual-post metadata
- `app/workflow_views_api.py` — ContentItem publisher fields
- `app/api.py` — `/public/manual-posts/...` signed media route
- `autoevolve-ui/src/pages/ContentPage.tsx` — publisher selector/drawer
- `autoevolve-ui/src/api/workflows.ts` — publisher client calls
- `docs/publishers.md` — wire contract
- `deploy/nginx-app.conf` — public media location and rate bucket
- `scripts/publisher_webhook_dev.py` — local receiver for UI work
