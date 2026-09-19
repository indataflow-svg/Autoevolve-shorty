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

## Publishing lifecycle: G1 to attribution

```text
brief (objective/buyer/topic/platforms)
  -> G1 package (knowledge/*.json validates copy)       (engines/g1)
  -> YOUR script review (approve / regenerate)
  -> G2 media search + acquire + render                  (engines/g2, FFmpeg)
  -> variant selection
  -> G3 draft-only Buffer handoff + R2 upload            (engines/g3, g3.env)
  -> YOUR Buffer approval -> publish
  -> tracked URL (?utm_campaign, campaign_id, post_id)
  -> form submit -> lead -> company -> opportunity
```

Campaigns waiting for review must be approved or regenerated, not retried.
`marketing_manual_posts` carries `campaign_id/post_id/tracked_url/source_detail`;
leads store the same fields verbatim for post-level attribution.
See [Product Tour](product-tour.md), [First Sales Outreach](first-outreach.md),
and [First Marketing Campaign](first-campaign.md).
