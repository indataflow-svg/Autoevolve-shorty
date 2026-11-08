# Production checklist

Complete this checklist before exposing Company Core or sending real outreach.

## Access and secrets

- Use long unique dashboard, action, intake, email webhook, and provider secrets.
- Keep `.env` readable only by the service account and confirm it is ignored by Git.
- Put the app behind Cloudflare Tunnel, not a DNS-only origin.
- Set `AUTH_COOKIE_DOMAIN`, `AUTH_COOKIE_SECURE`, `AUTH_COOKIE_NAME=__Secure-autoevolve_session`, `AUTH_ALLOWED_ORIGINS`, and `AUTH_VERIFY_BASE_URL` to public values.
- Configure the Pages Function `AUTH_API_ORIGIN` and test base-domain auth -> app-subdomain session.
- Use the Free-plan single rate-limit rule on `/api/auth/*`; keep Bot Fight Mode off until API testing.
- Keep Cloudflare proxied, cache tenant/API paths bypassed, and origin ports unexposed.
- Use async publish jobs for operations that can exceed Cloudflare's ~125s proxy timeout.
- Do not expose operator actions directly to an untrusted frontend.
- Rate-limit public intake and webhook endpoints.
- If the signed publisher webhook is enabled, set `PUBLIC_BASE_URL` to the externally reachable origin, verify `X-Publisher-Signature` on the receiver, and treat media links as short-lived credentials.

## Email and lead data

- Verify the Resend sender domain and test SPF, DKIM, DMARC, reply-to, and unsubscribe handling.
- Send first to an address you control and confirm HTML plus plain-text rendering.
- Keep `SALES_AUTO_CONTACT_ENABLED=false` until manual approval is proven reliable.
- Define lawful basis, consent, retention, deletion, and suppression procedures for your region.
- Never place real lead payloads in issues, fixtures, screenshots, or logs shared publicly.

## Models and claims

- Confirm every configured model ID exists and supports the required workload.
- Replace example company knowledge and review all approved product claims.
- Treat model output as a draft; retain human approval before email or publishing.
- Use only licensed stock, owned media, and authorized logos.

## Reliability

- Run `make check` and `make doctor` on the deployment host.
- Back up `.env`, `config/`, `data/`, `projects/`, and G3 configuration securely.
- Run one application process while using SQLite.
- Configure process restart, health monitoring, disk limits, and log rotation.
- Test restoration and webhook delivery before announcing the deployment.
