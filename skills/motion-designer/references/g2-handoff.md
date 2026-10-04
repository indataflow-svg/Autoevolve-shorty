# AutoEvolve motion-design handoff

Use this when converting a creative storyboard into media for the existing AutoEvolve campaign pipeline.

## Existing G2 contract

- G1 remains authoritative for campaign claims, narrative, headline, body, CTA, and claim IDs.
- G2 compiles a mixed-media storyboard with 5–6 scenes and scene timing. Current visual modes include `kinetic_stock`, `document_stack`, `role_route`, `status_handoff`, `control_layer`, and `branded_end_card`.
- G2 measures audio timing, renders subtitles, applies deterministic scene composition and restrained still-image movement, and fits the approved outro. It does not publish.
- The owned-media pool supports consented footage, metadata, tags, and scene matching. Product UI and testimonial footage must be owned and authorized.
- Generated video is not currently a first-party G2 generation provider. Do not label generated work as stock or product evidence. Record it as `generated` with provider/model, request ID when available, original prompt, generation date, rights/consent review, and checksum.

## Creative packet fields

Keep a motion packet separate from the validated G1 campaign JSON. A useful scene record includes:

```json
{
  "number": 1,
  "purpose": "cover",
  "claim_ids": [],
  "source_refs": [],
  "narration": "Approved narration for this scene.",
  "on_screen_copy": "Short readable phrase",
  "g2_visual_mode": "kinetic_stock",
  "motion_direction": "Slow lateral drift, then settle on the final beat.",
  "transition_in": "cut",
  "asset_type": "generated_illustration",
  "asset_prompt": "Model-specific prompt for a short background shot; no text, logo, UI, or identifiable customer."
}
```

This is a planning/handoff shape, not a schema accepted directly by G1 or G2. Preserve the validated campaign unchanged. Map approved asset files into the G2 asset workflow and keep generation metadata in a companion manifest until a typed provider adapter is implemented.

## Assembly rules

- Use real screen recordings for actual product behavior; never ask a video model to invent an AutoEvolve screen.
- Generated footage can establish mood or metaphor. It cannot substantiate claims, depict a real customer, or stand in for measured results.
- Render captions, headlines, logos, and CTA text in G2 or another deterministic editor so spelling and brand treatment remain controlled.
- Match motion intensity to narration. Prefer one clear camera move and one transition idea per shot over stacked effects.
- Keep key text inside platform-safe areas and hold it long enough to read.
- The final frame uses the approved owned end card; do not generate a replacement logo or CTA.

## Current provider notes

- NotebookLM is useful as a source-grounded research surface. NotebookLM/Gemini Notebook APIs vary by edition; confirm an official API and required Google Cloud access before designing unattended ingestion. Do not automate the consumer UI or use unofficial session scraping.
- Higgsfield's API is asynchronous: submit a model-specific request, poll or use a documented webhook, then download outputs into AutoEvolve-controlled storage before its retention window expires. Verify the active model endpoint, parameter schema, terms, and price in the official catalog before generation.
- Keep provider credentials server-side in the configured secret store. Do not put API keys in a skill prompt, campaign brief, browser bundle, or generated manifest.
