# Architecture

Repository: `AutoEvolve`. Application: `Company Core`. Two flows below are the
runtime contracts; code references are the source of truth.

## Sales lifecycle: intake to reply

```text
website / Tally form / inbound email
  -> POST /integrations/{website,tally,email, resend}   (app/sales_api.py intake_router)
  -> upsert_lead +utm/campaign/post passthrough          (core/sales_store.py)
  -> resolve company (CE/PDL) + resolve contact          (action_router, cached)
  -> build draft (model gateway)                         (services/sales_service.py)
  -> human edit -> approve -> send (Resend)              (drafts lifecycle)
  -> delivery + reply webhooks                           (/integrations/resend/sales)
  -> reply detection -> meeting / follow-up / suppress
```

Approval and sending are separate actions. Suppression, bounces, replies, and
meetings stop the follow-up sequence. Contact and company resolution are cached;
`force=true` spends another credit.

## Publishing lifecycle: manual post to attribution

```text
operator uploads carousel images or one MP4        (Content page)
  -> POST /company/marketing/manual-posts/session
  -> /manual-posts/{id}/assets -> /manual-posts/{id}/finalize
  -> backend caption + tracked URL (?utm_campaign, campaign_id, post_id)
  -> G3 draft-only Buffer handoff + R2 upload       (engines/g3, g3.env)
  -> YOUR Buffer approval -> publish
  -> POST /manual-posts/{id}/buffer-confirm          (provider verdict)
  -> tracked URL -> form submit -> lead -> company -> opportunity
```

Generated campaigns and video production were removed. Manual posts are the only
marketing path; a Buffer draft or scheduled post is never labelled published
unless the provider reports it sent.

**Publisher seam.** The manual post stores a `publisher` (default `buffer`) and
provider-neutral `publisher_*` metadata. `services/publishers/` exposes one
small port: `accounts`, `draft`, `schedule`, `confirm`, `insights`.
`BufferPublisher` calls the existing G3 functions unchanged; `WebhookPublisher`
posts a signed JSON contract to `PUBLISHER_WEBHOOK_URL` and exposes media
through short-lived signed URLs. A Buffer draft or scheduled post is never
labelled published unless the provider says `sent`. `marketing_manual_posts` carries
`campaign_id/post_id/tracked_url/source_detail`; leads store the same fields
verbatim for post-level attribution.
