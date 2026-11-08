# Cloudflare Free-plan launch notes

## DNS / pages

- `autoevolve.site` and `www.autoevolve.site` -> Cloudflare Pages (proxied)
- `www` -> 301 canonical apex
- `app.autoevolve.site` -> Cloudflare Tunnel (proxied)
- Never publish a DNS-only record for web traffic

## Tunnel

Tunnel public hostname:

```text
app.autoevolve.site -> http://nginx:80
```

No host ports 80/443. One connector is enough for a single app/SQLite host;
add a second connector only for connector redundancy or a second app host.

## Free-plan edge rules

- Use the one available rate-limit rule on `Path starts with /api/auth/`,
  IP-keyed, with a short window. Do not try to cover every API path with the
  Free plan's single rule.
- Keep Bot Fight Mode off initially; Free Bot Fight Mode cannot be bypassed
  with custom rules and may challenge legitimate API/webhook clients.
- Use Turnstile on signup/login if abuse appears.
- Free Managed Ruleset only; app authorization and tenant isolation remain in
  the application.
- Cache `/assets/*` and `/site-assets/*`; bypass `/api/*`, `/company/*`,
  `/public/manual-posts/*`, and `/health`.
- Pages Function environment: `AUTH_API_ORIGIN=https://app.autoevolve.site`.

## Timeouts

Cloudflare's proxy read timeout is about 125 seconds. Manual-post publishing is
async; poll the publish-job endpoint. Keep plan generation under the 90-second
target.
