# AI Creative Director (template-4 phases 3, 20, 21)

Model-agnostic direction over OmniRoute. The application never branches on
provider names; roles map to OmniRoute routes and structured outputs are
pydantic-validated before anything reaches planning, let alone the GPU.

## Roles (`services/creative_director.py`)

| Role | Route | Used for |
| --- | --- | --- |
| `creative_direction` | reasoning | brief → `CreativeBriefResponse` |
| `storyboarding` | reasoning | direction → `StoryboardOutline` (validated continuity) |
| `prompt_compilation` | fast | prompt wording refinement |
| `asset_selection` | fast | reference resolution assist |
| `visual_review` | vision | independent render review |
| `continuity_review` | vision | cross-shot film coherence |
| `revision` | reasoning | correction planning |

Without `OMNIROUTE_API_KEY` every role raises `DirectorUnavailable` and the
deterministic pipeline continues (or, for brief-driven directing, exits with
a clear error). AI output is assist-only:Schema validation precedes
generation, and generation precedes review.

## Flow (`video_pipeline.direct_brief`)

```text
human brief
  ↓ CreativeDirector(creative_direction) → CreativeBriefResponse
recipe selection (AI choice, deterministic fallback)
  ↓
VisualBible (default, validated, persisted)
  ↓ CreativeDirector(storyboarding) → StoryboardOutline (ModelRetry-validated)
timed beats with ai-brief provenance
  ↓
VideoSpec → ShotPlan → RenderJob[] (same validators as script flow)
```

Transcript-wording preservation applies to provided scripts, not briefs:
brief beats are AI-narrated and flagged `source: "ai-brief"`.

## Phase-0 capability inventory (AutoEvolve side)

- EXISTING AND USABLE: VideoSpec/ShotPlan/RenderJob + validators; SQLite
  lease queue with attempts; `cloud_model` OmniRoute routes; ffprobe QA +
  sha256 manifests; FFmpeg mux/concat (marketing_worker, G2); Bearer
  worker client with status/download; founder-gated API + dashboard auth;
  `.env` config tiers; provenance claim registries (G1 knowledge).
- ALREADY INSTALLED BUT UNUSED: vision route (no reviewer wired it until
  now); `pydantic-ai` output validators beyond scene planning.
- PARTIALLY IMPLEMENTED (completed by this change): prompt compiler
  (was templates), T2V/I2V policy (was implicit), asset registry (was
  ad-hoc job inputs), review/continuity (was ffprobe-only), generation
  history (was single file), brief orchestration (did not exist).
- MISSING (by design, worker/host side): GPU execution, model files,
  download endpoint on the current worker, live OmniRoute key in this
  environment, reference-video reconstruction (future seam documented).
- BROKEN: nothing in this path; 3 pre-existing suite failures are in
  unrelated sales/UI areas.
- DUPLICATED: nothing added; the motion skill (`skills/motion-designer`)
  is a human/GPT prompt pack, this director is its machine-executable
  counterpart — mapped, not forked (see review-gates.md).
