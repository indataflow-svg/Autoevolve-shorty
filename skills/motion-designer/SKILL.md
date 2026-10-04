---
name: motion-designer
description: "Turn approved product or customer stories into source-grounded short-video storyboards, motion directions, and generation-ready shot prompts for AutoEvolve marketing."
---

# Motion Designer

Create a production-ready motion design packet for an AutoEvolve launch, product walkthrough, or customer showcase. Keep every factual statement tied to supplied approved sources; treat generated imagery as illustration, never as evidence.

## Workflow

1. **Gather approved inputs.** Use the user's brief, product screenshots or recordings, approved claims, customer quotes, release notes, and any NotebookLM notes or citations they provide. Ask for missing customer permission or product evidence when the requested story depends on it. Do not infer permission from a public page.
2. **Build a source ledger.** Separate verified product facts, customer statements, outcomes, and creative assumptions. Attach a source reference to every factual scene. Mark unsupported or disputed claims for removal or review.
3. **Set the story and motion system.** State audience, one message, CTA, platform/aspect ratio, runtime, visual motif, type treatment, motion principles, transitions, and sound direction. Keep motion purposeful and legible on a phone. Preserve the AutoEvolve brand assets supplied for the campaign.
4. **Storyboard to the existing G2 shape.** Default to a 9:16, 35–55 second short with 5–6 scenes. Keep scene purpose, narration, on-screen copy, visual mode, and claim IDs aligned with the current G2 campaign. Read [references/g2-handoff.md](references/g2-handoff.md) when mapping the packet into AutoEvolve media.
5. **Write shot prompts for Higgsfield.** Generate one concise, model-appropriate prompt per supplemental shot, with subject, action, environment, lens/camera movement, lighting, duration, aspect ratio, and negative constraints. Keep text, logos, UI labels, charts, and customer identities out of generated frames; add readable type and approved product UI in the deterministic edit. Use the selected model's live official schema and preserve the original prompt and generation metadata.
6. **Review the package.** Include an asset list distinguishing owned product capture, customer-authorized footage, generated illustration, stock, and branded end card. Include risks, approvals still needed, and a shot-by-shot QC checklist. Never state that generation, rendering, or publication happened unless the user or tool confirms it.

## Tool boundaries

- **NotebookLM / Gemini Notebook:** use source-grounded notebooks to explore provided research and extract cited facts. In standard consumer workflows, treat source gathering and export as user-mediated. Do not assume the notebook can be queried from AutoEvolve through an API. For Gemini Notebook Enterprise, only use API capabilities documented and enabled for the user's project.
- **GPT:** use this skill to turn the approved source packet into a structured narrative, storyboard, motion system, and shot prompts. Keep supplied facts and creative proposals visibly distinct.
- **Higgsfield:** treat it as an optional proprietary generation provider, not open-source software. Generation may incur cost. Prepare prompts and a manifest first; do not submit paid jobs unless the user explicitly asks for generation and the account/credential is configured.
- **G2 / FFmpeg:** remain the deterministic compositor for narration timing, subtitles, cuts, restrained motion, branding, and final encoding. Generated clips are source assets that require provenance and review before entering the production asset pool.

## Output

Return a source ledger, one-paragraph creative direction, a scene-by-scene storyboard, Higgsfield shot prompts, asset/provenance checklist, and review gates. Produce JSON only when requested or when the caller needs a machine-readable handoff; otherwise use a compact table plus a prompt block per shot.
