# Product tour

React is the sole operator UI. `/` opens Home; existing operator bookmarks redirect to React.
Only the public booking utilities `/meet` and `/calendar` retain server-rendered pages.

| Page | Purpose |
| --- | --- |
| `/` | Redirects to React Home |
| `/onboarding` | First-run company research, strategy, calibration, buyers, and draft creation |
| `/home` | Saved work that needs review and links to each domain |
| `/research`, `/companies`, `/contacts` | Company discovery, candidate review, and contact resolution |
| `/outreach`, `/replies`, `/meetings` | Draft approval and sending, inbound replies, and manual meeting markers |
| `/campaigns` | Campaign briefs, script review, voice, variants, and retry actions |
| `/content` | Asset packs, manual uploads, and Buffer scheduling/insights |
| `/integrations`, `/settings` | Provider state, keys, and own marketing organizations |
| `/operations/history` | Retired UI; redirects to Home |
| `/docs` | Interactive FastAPI endpoint reference |

A good operator walkthrough covers provider diagnostics, a synthetic lead, an edited draft
without sending it, a campaign script review, a media preview, and persisted workflow activity. See
[Architecture](architecture.md) for both lifecycle diagrams.
