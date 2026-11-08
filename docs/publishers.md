# Publishers: Buffer + webhook schedulers

Buffer is the default and only built-in publisher; the app does not hardcode
Buffer into the manual-post domain. A manual post stores a `publisher` and
provider-neutral `publisher_*` metadata. `services/publishers/` is the seam:

| adapter | transport | default |
|---|---|---|
| `buffer` | existing G3 CLI (handoff + R2 + Buffer API) | yes |
| `webhook` | signed JSON to `PUBLISHER_WEBHOOK_URL` | opt-in |

The legacy `/company/marketing/buffer-*` routes still work. New clients should
use the generic routes.

## App routes

| route | purpose |
|---|---|
| `GET /company/marketing/publishers` | adapters and capabilities for the current org |
| `GET /company/marketing/publisher-accounts?publisher=buffer` | accounts for one adapter |
| `POST /company/marketing/manual-posts/{id}/publish` | schedule (founder token or website session) |
| `POST /company/marketing/manual-posts/{id}/publish/draft` | optional draft (Buffer only) |
| `POST /company/marketing/manual-posts/{id}/publish/confirm` | provider status |
| `GET /company/marketing/manual-posts/{id}/publish/insights?post_id=...` | provider insights |
| `GET /company/ui/publishers` | current org's catalog and webhook status |
| `PUT /company/ui/publishers/webhook` | save the org's webhook URL/secret |
| `DELETE /company/ui/publishers/webhook` | remove the org's webhook |

The post's stored `publisher` selects the adapter; a request cannot choose an
adapter different from the one the post was created with.

## Webhook configuration

```dotenv
PUBLISHER_WEBHOOK_URL=https://scheduler.example/hook
PUBLISHER_WEBHOOK_SECRET=<long-random-shared-secret>
PUBLISHER_WEBHOOK_ACCOUNT=webhook
PUBLISHER_WEBHOOK_LABEL=Webhook scheduler
PUBLISHER_WEBHOOK_PLATFORMS=instagram,x,linkedin
PUBLISHER_WEBHOOK_TIMEOUT_SECONDS=30
PUBLISHER_WEBHOOK_ASSET_TTL_SECONDS=3600
PUBLIC_BASE_URL=https://your-public-host.example
```

The deployment-level adapter is not offered when URL or secret is missing.
`PUBLIC_BASE_URL` is the externally reachable origin used to build media links;
`localhost` only works for a scheduler on the same host. `APP_ENCRYPTION_KEY`
must stay stable for per-org secrets to remain decryptable.

## Per-organization connections

`publisher_connections` stores one webhook connection per organization. The URL,
account, label, and platform list are stored as configuration; the secret is
encrypted with Fernet using `APP_ENCRYPTION_KEY` and is never returned by the
API. A free org must configure its own connection; it never inherits the
deployment-level webhook or the shared Buffer account. Paid/operator orgs may
use their own connection, or fall back to the deployment env values when no
connection exists.

The free publisher catalog therefore contains only `webhook` after it is
configured. The paid/operator catalog contains Buffer and, when configured, the
deployment webhook. A manual post's stored `publisher` still selects the adapter.

Settings → **Publisher connection** is the UI for the URL, signing secret,
account name, label, and platforms. A verified website session is sufficient to
save its own org's connection; Basic/operator requests still need the founder
action token.

For media posts, `PUBLIC_BASE_URL` must be the externally reachable origin used
to build signed asset links. A text-only post has no media and does not require
it. The receiver verifies the signature and idempotency key as below.

## Request

Every request is JSON, signed with HMAC-SHA256 over the **raw body**:

```http
POST <PUBLISHER_WEBHOOK_URL>
Content-Type: application/json
X-Publisher-Signature: sha256=<hex digest>
X-Idempotency-Key: manual-post:<post id>:<action>:<account>:<mode>:<due_at>
```

```json
{
  "schema": "company-core.publisher.webhook.v1",
  "action": "schedule",
  "publisher": "webhook",
  "account": "webhook",
  "post": {
    "id": "<local record id>",
    "post_id": "<local post id>",
    "platform": "instagram",
    "post_type": "carousel",
    "caption": "...",
    "title": "...",
    "tracked_url": "https://.../form?utm_campaign=...",
    "destination_url": "https://.../form",
    "campaign_id": "mkt_...",
    "source_detail": "instagram_carousel"
  },
  "media": [
    {
      "index": 0,
      "filename": "slide.png",
      "content_type": "image/png",
      "size_bytes": 12345,
      "url": "https://your-public-host.example/public/manual-posts/<id>/assets/0?exp=...&token=...",
      "expires_at": 1790000000
    }
  ],
  "schedule": {"mode": "queue", "due_at": null}
}
```

`mode` is `queue`, `next`, or `timed`. `due_at` is ISO-8601 when `timed`.
Media links expire after `PUBLISHER_WEBHOOK_ASSET_TTL_SECONDS` and are signed
with the same secret. The receiver must fetch them before expiry.

`action` is also `status` or `insights` with `{post_id}` at the top level
instead of `post`/`media`/`schedule`:

```json
{"schema":"company-core.publisher.webhook.v1","action":"status",
 "publisher":"webhook","account":"webhook","post_id":"ext_123"}
```

## Response

```json
{"ok": true, "post_id": "ext_123", "status": "scheduled",
 "external_url": "https://social.example/post/123",
 "due_at": "2026-11-01T10:00:00Z", "metrics": []}
```

- `schedule` requires `post_id`.
- `status`/`insights` may omit `metrics`.
- `status` values are provider-defined; only an explicit `"sent"` marks the
  local confirmation as sent. `failed`/`error`/`cancel`/`reject` is failed;
  everything else stays pending/unknown.
- Non-2xx, non-JSON, or `{"ok": false}` is a publisher error (`502`).
- Idempotency keys are stable across retries; receivers should deduplicate on
  `X-Idempotency-Key`.

## Security

- Verify the HMAC over the raw body with the shared secret before parsing.
- Reject stale timestamps if you add one; the app does not currently send a
  timestamp header, so keep request replay windows short at the receiver.
- Media URLs are bearer credentials for one file, one post, and a short window.
  Do not log them; they are `Cache-Control: private`.
- The app only stores provider-neutral status; it never infers publication.

## UI handoff

The current Content UI and the remaining settings work are tracked in
[Publisher UI handoff](publisher-ui-handoff.md). For local end-to-end testing:

```bash
PUBLISHER_WEBHOOK_SECRET=dev-secret .venv/bin/python scripts/publisher_webhook_dev.py
```

## Adding another adapter

Implement the five methods in `services/publishers/base.py` (`accounts`,
`capabilities`, `draft`, `schedule`, `confirm`, `insights`), register it in
`services/publishers/__init__.py`, and add its configuration keys. The manual
post, UI selector, and generic routes need no further changes.
