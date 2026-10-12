# Task: MD-with-timestamps to a finished, high-quality video. Additive, deterministic by default, GPU optional per beat.

Direction: our own pipeline, not a clone of any tool. The scenario markdown (timestamps, exact transcript, visual sourcing per beat) is the source of truth. Real assets and real text render deterministically; GPU (HunyuanVideo-1.5 on the MI300X) stays available and is used only where a beat asks for generated footage.

Repo: Autoevolve-shorty-main.

## Non-negotiable: do not break what exists
- Add new modules (suggest `services/video/compose/` and `services/video/md_pack.py`). Do not change default behavior of existing commands, `plan_video`, `direct_brief`, `render_mode="full"`, or the Hunyuan worker path.
- New behavior is opt-in: a new render mode (`composed`) or CLI subcommand. Existing tests must pass unchanged. Run the suite first and record the baseline (it was never run in my analysis sandbox: pydantic missing).
- Small, safe fixes to shared code are allowed only if covered by tests (listed in section 5).

## What the pack gives us (per concept, ~6 beats)
Timestamps (`**0:00–0:06 — label**`), exact on-screen transcript, then per beat: Visible, Preferred visual type, Search terms, Portrait crop, Motion, Connection, and Fallback generated-image prompt (often "Not needed").

## Verified facts to build on
1. `script_parser.parse_script` fails on this format (bold timestamp headers, bold field bullets, transcript and visual map in separate sections joined by beat number). Needs an adapter, old parser untouched.
2. `shot_planner.route_visual` has no founder/footage type (falls to `stock`), uses substring matching ("ship" in "relationship", "port" in "support") and Hunyuan cues like `graphic`, `2d`, `icon`.
3. Non-generated renderers (`asset`, `motion_graphics`, `ffmpeg`) are not dispatched: `services/renderers.py` ~L671 and `services/video/pipeline.py` ~L217 mark them "recorded pending". This is the main gap.
4. Canvas: pipeline/CLI default `9:16`; `video_layers.py` hardcodes 1080x1920; `FORMAT_SIZES` already has `4:5`.
5. `engines/g2/g2_runtime/mixed_video.py` has ffmpeg concat and caption burn but is bound to campaign `MixedScene` objects, not `ShotPlan`. Reuse its ffmpeg helpers, do not fork the logic.
6. Hunyuan side (optional path): i2v is selected by `decide_hunyuan_mode` but the worker payload (`renderers.py` ~L850) carries no image, so everything is effectively t2v; profile is 480p, `sr False`, fixed seed 42. Leave as is unless section 6 is requested.
7. Onboarding, `CompanyContext`, `register_assets`, and `company_research` already exist. The pack path should read brand/constraints from them where available, never hardcode InDataFlow.

## Work

### 1. `md_pack.py`: pack to spec (deterministic, no LLM)
- `parse_pack(text) -> list[Concept]`: split `^## \d+\.`; per concept read title, buyer, target duration; timed transcript beats verbatim; sourcing beats keyed by `**Beat N —`; map `Visible/Preferred visual type/Search/Portrait crop/Motion/Connection/Fallback generated-image prompt` into a beat dict.
- Fail loudly if transcript beats != sourcing beats, if timestamps overlap or leave gaps, or if the end time differs from the stated duration.
- Output a `beats.json` (single source of truth): `{n, t_in, t_out, caption_lines[], source{type,file|search}, crop{focus}, motion[], generate: bool, fallback_prompt}`.
- `generate` is true only if the beat's type says generated/illustrative AND a fallback prompt is present (not "Not needed"). CLI `--gpu auto|off|force-draft` overrides: `off` never renders on GPU, `auto` follows `generate`, `force-draft` renders every beat that has a fallback prompt at draft quality for comparison.
- Test: every caption string equals the source markdown byte for byte.

### 2. Routing (additive)
- New visual types `founder_footage`, `founder_overlay` mapped to renderer `ffmpeg`; route from the `Preferred visual type` text first, keywords second.
- Word-boundary matching in `_matched_families` (tests for "relationship", "support", "report"). Default for unknown stays `stock`, never Hunyuan.

### 3. Compose stage (main work)
Render each non-GPU beat to `videos/<project>/shots/<shot_id>.mp4` at the canvas from `FORMAT_SIZES[aspect]`; take the aspect from the pack (4:5) or `--format`:
- Founder footage / UI capture: trim to `t_in..t_out`, crop by focus (left/right/centre), scale to canvas, optional zoom/pan from `motion`. Footage is mapped from `--footage <dir>` by filename or beat order.
- Founder overlay: UI base + founder clip rounded-rect (<= 25% of frame), mask-in over 0.3s.
- Stock: existing `pexels`/`coverr`/`pixabay` modules with the beat's search terms.
- Motion graphics: HTML/CSS templates rendered to transparent frames, ffmpeg overlay. Templates: `hook_two_line`, `caption_rail`, `word_sequence`, `field_highlight`, `end_frame` (logo unchanged). Colors/fonts from brand config or `CompanyContext.constraints.brand`.
- GPU beats go through the existing Hunyuan shot path unchanged; assembly merges GPU clips and composed clips in timestamp order.
- Hash each shot (spec + source sha256 + canvas); re-render only changed shots.

### 4. Quality bar (what "good quality" means, enforced in code)
- Timing: cuts land exactly on pack timestamps (<= 1 frame error); total duration matches the pack.
- Typography: safe margins for the 4:5 canvas, max 2 caption lines, no overflow, no orphan words (auto-fit, then fail if it still overflows); caption timing follows the beat window.
- Motion: one easing set (ease-out for entrances, ease-in-out for moves), consistent durations; no default-looking transitions.
- Image: single consistent grade across footage, stock and GPU clips (shared LUT or curve); no double upscaling; encode once at the end (high-quality H.264, yuv420p, faststart); avoid re-encoding intermediate files (use intermediate codec like ProRes/FFV1 or lossless x264 for shot files).
- Audio: keep the founder audio, loudness-normalize to about -14 LUFS, no clipping, short fades at cuts.
- Rules from `skills/motion-designer/SKILL.md` stay in force (no fake dashboards or invented claims).

### 5. QA gate (a render fails if any check fails)
- ffprobe: resolution, fps, duration within tolerance, audio present.
- Contact sheet of one frame per beat saved next to the output for review.
- Caption overflow check, caption-equals-markdown check, no leftover `pending` shots.
- Tests: pack parser, router word boundaries, compose per type (ffprobe size/duration), hash-based partial re-render, `--gpu off` yields zero Hunyuan jobs, `--gpu auto` creates jobs only for `generate` beats.

### 6. Optional GPU upgrades (separate PR, only after sections 1 to 5 land)
- Feed a keyframe/last frame to the worker (`image_path` in payload) so i2v is real; continuity chaining; per-shot seeds; draft (480p, distilled) vs final (720p, `sr` if the worker supports it) tiers. Verify what the worker supports before coding and report it.

## Acceptance
- `python scripts/video.py compose --pack <pack>.md --concept 1 --footage <dir> --format 4:5 --gpu off` writes one MP4 of about 49s from the pack's timestamps, passes the QA gate, and leaves existing commands untouched.
- Same command with `--gpu auto` adds GPU clips only for beats with `generate: true`.
- Existing test suite passes; new tests included.

## Report back
Files changed/added, test baseline before and after, QA gate output for concept 1, and anything not verified.

---

# Addendum: Mode B, rebuild a real product video into a high-quality marketing video

Use case: the founder has a real product/demo recording (low quality, weak storytelling) and wants a polished, precisely told version for the website or marketing. Same pipeline, new front end. Additive, no changes to existing behavior.

## Principle: the product stays real, the presentation gets rebuilt
Never regenerate UI pixels with a diffusion model: it garbles text, invents features and breaks claims. Treat source UI footage as `preserve` (the registry already has `preserve` / `allowed_changes` on assets). Allowed changes: crop, zoom/pan, speed, cleanup, upscale, framing, overlays. GPU is used for (a) quality restoration of the real footage and (b) optional generated non-UI shots (intro/outro/mood), never for the UI itself.

## Stages
1. **Ingest and analyse (deterministic, no free-form model output):**
   - ffprobe the source; scene/segment detection (cut + idle-time detection from frame difference).
   - Transcribe audio with the repo's existing transcription (check `engines/g2` / `services/` first; use faster-whisper if present, else report).
   - OCR a keyframe per segment to record what is actually on screen (screen titles, button labels, numbers). Store as `segments.json`: `{t_in, t_out, ocr_text[], transcript, activity: click|scroll|idle|typing, ui_region_of_interest}`.
2. **Re-story (OmniRoute free model, constrained):**
   - Input: `segments.json` + `CompanyContext` (problem, buyer, value proposition, brand constraints). Output: a beat plan in the same `beats.json` schema (hook, problem, action, result, CTA), where every beat references source segment ids and every caption has a `source_id` (transcript line, OCR text, or context field).
   - Hard rules: no claim that the footage does not show or the context does not state; no invented numbers or features; if the video lacks a needed moment, emit a `needs_input` item instead of filler. Deterministic validator rejects any beat without a resolvable segment or source id. If the model is unavailable, fall back to a rule-based plan (segment order, idle removal, transcript captions).
3. **Restore the real footage:**
   - Remove idle time and dead air (cut or speed ramp); stabilise cursor motion; hold on result frames.
   - Denoise/deblock, then 2x upscale of the UI region (use the worker's SR if verified; otherwise a ROCm-compatible upscaler, report what runs on the MI300X); frame interpolation to a smooth 30/60 fps for scroll and animation; sharpen text edges conservatively.
   - Re-crop to the fixed canvas (4:5 or 9:16): cursor/ROI-follow zoom into the active region with eased motion, so small UI text becomes readable.
4. **Present (existing compose templates):** device or window frame, brand background, callouts and field highlights on real UI regions, kinetic captions, step labels, end frame with logo and CTA. Founder clip overlay if provided.
5. **Optional GPU shots:** a generated opener or atmospheric b-roll from a shot card, only for beats the plan marks `generate: true`; rendered through the existing Hunyuan shots path; all text still an overlay.
6. **Finish and QA:** same quality bar and QA gate as sections 4 and 5 above, plus: every on-screen UI text shown in the output must appear in the source OCR (fails if the render shows UI text that the source never had).

## Acceptance for Mode B
- `python scripts/video.py rebuild --source <demo.mp4> --company-context --format 4:5 --gpu off` outputs a restored, re-paced, captioned MP4 whose UI frames all come from the source footage.
- Every caption and callout resolves to a transcript line, OCR text or a context field.
- Before/after comparison saved (contact sheet + duration, resolution, idle-time removed).
- Report which restoration tools actually run on the MI300X (upscaler, interpolator) and which were not verified.
