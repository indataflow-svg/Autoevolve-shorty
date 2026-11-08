# Website authentication and free sessions

AutoEvolve has two authentication paths that share one FastAPI process:

| path | identity | organization |
|---|---|---|
| Website account | email + password, verified by email | the free organization created at signup |
| Operator dashboard (legacy) | HTTP Basic (`DASHBOARD_USER`/`DASHBOARD_PASSWORD`) | the global `active_org_id` setting |

The website path is what a free user gets. The Basic path remains for the
existing operator/dashboard deployment and is not exposed by the marketing
site.

## Account lifecycle

1. `POST /api/auth/signup` validates the email/password, creates a `users` row
   with a scrypt hash, creates a **free** `buffer_orgs` row, adds an owner
   `org_memberships` row, and issues a single-use verification token.
2. The verification email links to the website `/verify#token=…` page. The
   page calls `POST /api/auth/verify`; the token is consumed, the email is
   marked verified, and a session cookie is set.
3. `POST /api/auth/login` checks the password, requires a verified email, and
   creates a new session. `POST /api/auth/logout` deletes the session row and
   clears the cookie.
4. `GET /api/auth/me` returns the current user and organization. It is `401`
   without a session.

Signup is disabled with `AUTH_SIGNUP_ENABLED=false`. Login and resend responses
are deliberately generic for unknown addresses; signup does return a conflict
for an existing account.

## Session and organization isolation

The session cookie name is controlled by `AUTH_COOKIE_NAME` (default
`autoevolve_session`; production should use `__Secure-autoevolve_session`):

- `HttpOnly`, `SameSite=Lax`, `Path=/`
- `Secure` when the request is HTTPS or `AUTH_COOKIE_SECURE=true`
- `Domain=AUTH_COOKIE_DOMAIN` when configured, so `autoevolve.site` auth can hand
  the session to `app.autoevolve.site`
- 30-day server-side expiry; the cookie holds a random 256-bit token and the
  database stores only its SHA-256 digest

Middleware resolves the cookie before every non-asset request and binds three
request-scoped context values: user ID, organization ID, and session digest.
`core.state.get_active_org()` and `core.commercial_store.active_org_id()` read
that context first, so the existing org-scoped stores become tenant-scoped
without changing every call site.

**Free isolation uses `org_id` on the single `company.db` database, not a
separate database per session.** This is deliberate: one schema, one migration
path, and the same org filters as the paid operator. The session context is the
boundary that prevents a free account from falling back to the global active
org. If the scoped org disappears, reads fail closed instead of using another
org.

A session user can only:

- read/write their own org's context, plans, workflow records, content, limits,
  quotas, and publisher connection;
- see one organization in Settings and the marketing org selector;
- switch only to their own org (there is no cross-org switch);
- create a manual post only for that org.

Additional organizations, Buffer setup, provider-key setup, and global
marketing-org creation are operator-only. The creator is the owner of the one
free org; team invitations and multi-user membership management are not built
yet.

## Free plan boundary

A signup org is created with `plan='free'` and therefore gets:

- 1 validation plan / 1 run / 1 publish per UTC day (`core/quotas.py`);
- `GovernanceLimits` clamped to zero spend, one action, 20 outreach contacts,
  and 14 days;
- zero paid provider calls by default (P3 gate);
- no access to the shared Buffer account;
- its own signed webhook publisher (see [Publishers](publishers.md));
- real cold outreach is blocked at send time (drafting/approval remain
  available); the free plan publishes content, not outbound email;
- a four-card Get Started company-context wizard; completion hands off to the
  free daily loop and optionally the paid commercial workspace;
- a clearly labelled **sample free-account usage** card on Home (mock loop
  history, not real records) so the free rhythm is visible before data exists;
- paid pages (Outreach, Replies, Meetings, Research) render
  a blurred locked preview with a **Book a demo** CTA. The CTA opens the
  marketing site with `?demo=1`, which auto-opens the existing demo dialog;
- the normal org-scoped history read path. The 30-day history window is a
  product rule to enforce when retention is wired; the current storage does not
  delete older rows automatically.

The paid/operator path keeps the deployment-level Buffer and webhook settings.
Existing orgs default to `paid`; only an explicit signup sets `free`.

## Email delivery

Resend is used when configured. Auth-specific values take precedence, then the
existing sales values are used as fallback:

```dotenv
AUTH_RESEND_API_KEY=
AUTH_FROM_NAME=AutoEvolve
AUTH_FROM_EMAIL=
AUTH_RESEND_DOMAIN=
# falls back to SALES_RESEND_API_KEY, SALES_FROM_EMAIL, SALES_RESEND_DOMAIN

AUTH_VERIFY_BASE_URL=https://autoevolve.site/verify
AUTH_COOKIE_NAME=__Secure-autoevolve_session
AUTH_COOKIE_DOMAIN=autoevolve.site
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=lax
AUTH_ALLOWED_ORIGINS=https://autoevolve.site,https://app.autoevolve.site
AUTH_EXPOSE_DEV_TOKEN=false
```

Without an API key or sender, the verification link is written to the server
log (never sent). `AUTH_EXPOSE_DEV_TOKEN=true` additionally returns the link in
the signup/resend JSON for local development; leave it false in production.

The link expires after 24 hours. Requesting a new link consumes the previous
one. Tokens are stored only as hashes.

## Website routing

The marketing site is the separate `indoha-commits/website-autoevolve` repository (React/Vite). It has three auth routes:

- `/signup`
- `/signin` (alias `/login`)
- `/verify#token=…`

The token is held in the fragment, not the query string, so it is never sent to
Cloudflare, Pages, nginx, or the app in a request URL. The verify page requires
an explicit **Verify email** click; it does not auto-consume the token.

Its Vite dev/preview server proxies `/api` and `/company` to
`http://127.0.0.1:8787`. In production, a Cloudflare Pages Function proxies
`/api/auth/*` from the base domain to `https://app.autoevolve.site/api/auth/*`, so
the browser remains same-origin.

- set `AUTH_VERIFY_BASE_URL=https://autoevolve.site/verify`;
- set `VITE_APP_URL=https://app.autoevolve.site`;
- set `AUTH_COOKIE_DOMAIN=autoevolve.site`;
- allow both base and app origins in `AUTH_ALLOWED_ORIGINS`.

The cookie is host-scoped unless `AUTH_COOKIE_DOMAIN` is set. For the
base-domain auth + app-subdomain topology it must be set to the registrable
domain. Never set it to a different registrable domain; the browser will not
share the session.

The dashboard `AuthGate` first probes `GET /company/ui/session` with the cookie.
If it succeeds, API calls omit the Basic header and use the session. If it
fails, the legacy Basic sign-in screen is shown. The client sends
`credentials: 'same-origin'` and never puts the session token in JavaScript.

## Security properties and limits

- Passwords use stdlib `scrypt`; session and verification tokens are random and
  hash-at-rest.
- Public auth routes are rate-limited per IP
  (`RATE_LIMIT_PUBLIC_AUTH_PER_MINUTE`, default 20/min); failed Basic attempts
  keep their separate bucket.
- Cookie mutations rely on `SameSite=Lax` and same-origin deployment. There is
  no separate CSRF token; add one before accepting cross-site form posts.
- No password reset, MFA, email-change flow, invitation flow, or session
  management UI yet.
- The free plan is one org per account, not one database per session. Isolation
  depends on every store using the org context; the auth/session and publisher
  regression tests cover the paths added here.
- `APP_ENCRYPTION_KEY` protects per-org publisher secrets. If it is absent, a
  stable fallback is derived from the dashboard/action secrets; set it
  explicitly in production and do not rotate it without re-entering secrets.

## Tests

- `tests/test_auth_api.py`: signup, verification, login, cookie session,
  free-org scope, quota visibility, per-org webhook save, Buffer denial,
  cross-org switch denial, operator-only denial, logout.
- `tests/test_auth_scope.py`: lead/draft/profile reads and summaries are
  scoped to the session org; free cold-outreach send raises `PermissionError`.
- `tests/test_org_publisher.py`: encrypted secret at rest, free/paid publisher
  catalogs, deployment-vs-org webhook selection.
- `website-autoevolve/src/test/auth.test.tsx`: signup and verification page behavior.
