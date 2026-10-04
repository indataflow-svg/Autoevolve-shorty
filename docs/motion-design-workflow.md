# Motion designer workflow

This is the first media-creation workflow for launch videos and user showcases. It uses NotebookLM for source-grounded research, the reusable GPT skill for story and motion planning, Higgsfield for optional generated shots, and G2/FFmpeg for the controlled final edit.

## Tool roles

| Tool | Job | Boundary |
| --- | --- | --- |
| NotebookLM / Gemini Notebook | Gather evidence from approved product docs, interviews, release notes, and customer material. Produce a cited source brief. | The standard NotebookLM workflow is user-mediated. Gemini Notebook Enterprise has Preview APIs for notebook/source management; do not assume the consumer notebook exposes a programmatic query API. |
| GPT + Motion Designer skill | Turn the approved source brief into the message, storyboard, motion language, shot prompts, and asset checklist. | Claims and customer outcomes must cite supplied sources; creative proposals are labelled separately. |
| Higgsfield | Generate supplemental B-roll or abstract visual shots. | Higgsfield's platform and models are proprietary, not open source. Use the official API/catalog or website; generation can incur usage charges. |
| AutoEvolve G2 / FFmpeg | Match media to scenes, time to voiceover, render subtitles/transitions, fit the approved outro, and create review variants. | G2 is the deterministic compositor. It does not publish. Generated clips need provenance and approval before production use. |

## Prepare an approved source packet

For a customer showcase, collect:

- The approved campaign brief and product claims.
- Product screenshots or a real screen recording for any scene describing product behavior.
- The customer's approved quote, name/logo permission, and any measurable outcome with its source.
- The intended audience, one key takeaway, CTA, platform, and runtime.
- Brand logo, end card, typography, and any visual references you own or have permission to use.

Do not put confidential customer material into a personal NotebookLM or GPT account unless its owner has authorized that processing. For research, include only the sources necessary for the creative brief.

## Make the source-grounded story

1. Create a notebook for the launch or showcase. Add the approved source packet and ask for a concise evidence brief: supported claims, exact source references, customer-approved quotes, unresolved questions, and statements that must not appear.
2. Export/copy that brief and its citations into the GPT conversation. Upload `skills/motion-designer.skill.zip` in ChatGPT Skills where the workspace supports it, or use the skill folder with a compatible Agent Skills client.
3. Ask `$motion-designer` to create a 9:16 short-form motion packet. Default to 35–55 seconds and 5–6 scenes to match G2's current storyboard shape. Require a source reference for every factual beat.
4. Review the source ledger, narrative, scene timing, on-screen copy, and shot list. Replace any unsupported outcome or invented customer detail before generating visuals.

NotebookLM/Gemini Notebook Enterprise API capabilities are edition-specific and currently documented in Preview. The official API covers notebook and source operations; verify any needed generation/query operation in the current project documentation before designing unattended access. A UI export remains the fallback.

## Generate supplemental shots

1. Review Higgsfield's live model catalog and each selected endpoint's input schema. Prefer image-to-video when the visual needs a controlled starting frame; use text-to-video for supplemental atmosphere or motion metaphors.
2. Generate only the shots approved in the motion packet. Do not include customer-identifying material, confidential product screens, logos, or legible copy in prompts. Use real captured UI and approved customer footage for evidence.
3. Record the provider, model, request ID, exact prompt, date, duration, aspect ratio, cost/usage, downloaded filename, checksum, and rights/consent review in the campaign's asset manifest.
4. Download outputs into AutoEvolve-owned storage promptly. Higgsfield documents that API output files are available for at least seven days; do not treat the provider URL as long-term storage.

## Render and review

Keep generated source clips separate from the validated G1 campaign package. G2's owned-footage pool already ingests and matches video files, but its current pool policy requires consent-cleared clips; do not mark synthetic media as customer-consented footage. Before generated media enters the production pool, use an explicit generated-source approval path that records its provider provenance. For the first pilot, retain generated clips as review assets and use the existing campaign review/render handoff only for assets admitted by current G2 policy.

Review each output for:

- Factual and product accuracy; generated visuals never stand in for real UI or evidence.
- Customer permission, likeness, stock license, provider terms, and commercial-use conditions.
- Motion, crop, flashing, subtitles, phone-safe text, audio clarity, and end-card fit.
- Scene-to-narration timing and whether the visual supports rather than overstates the spoken claim.

Select and approve a final variant before using the existing G3 draft-only Buffer handoff. Buffer approval and publication remain separate operator actions.

## Integration sequence

1. Pilot the portable GPT skill and manual NotebookLM/Higgsfield handoff on one owned product showcase.
2. Add a typed generated-asset manifest and approval state to G2 so synthetic, stock, and consented owned video stay distinct.
3. Add a server-side Higgsfield adapter only after selecting model endpoints and validating their live schemas, cost handling, asynchronous status lifecycle, output download, and failure behavior.
4. Add NotebookLM Enterprise API support only if the required Google Cloud edition is available; otherwise preserve the manual source-export workflow.

This sequence keeps the existing G1 claim contract and G2 rendering/publishing boundaries intact while making a generated-video path reviewable.
