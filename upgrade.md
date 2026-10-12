# Task: onboarding-driven company video (uploaded assets + company context + website data), deterministic compose, no Hunyuan for proof beats

Repo: Autoevolve-shorty-main. Most of intake already exists. Do NOT rebuild it. Reuse it, then close the gaps below.

## Already built (reuse as-is)
- Onboarding: `app/onboarding_api.py` (`POST /company/setup/onboarding/research-company` scrapes the website via `extract_domain` and stores `company_research`; `/company/confirm` stores confirmed context).
- Canonical facts: `core/company_context.py` (`CompanyContext`: company, product, customer, market, evidence, offer, resources, constraints, objective; `missing` / `status`). Read via `load_company_context()` in `app/company_context_api.py`.
- Asset registry: `core/video_store.py` `register_assets(spec_id, assets)` (type, path, purpose, identity_priority, preserve, allowed_changes) and `list_assets`.
- Video spine: `services/video/` (spec_builder, shot_planner, job_builder, assembly with ffmpeg concat), `FORMAT_SIZES` incl. `4:5`.
- Model router: `core/models.py` (OmniRoute, `is_model_configured()`).

## Verified gaps (read the code before changing)
1. **The storyboard prompt is the source of the irrelevant video.** In `services/video/pipeline.py` `direct_brief`, the storyteller instructions hardcode: "The protagonist is the viewer ... who discovers InDataFlow", open with "an empty desk at dawn, a lone figure on a rooftop, a corridor before the doors open", force 2+ purely cinematic beats, and forbid any UI/dashboard/text. That produces generic door/hall stories for any company and can never show the product. It also never reads `CompanyContext` (grep shows no use in `services/video/`).
2. **Claim validation is single-tenant.** `shot_planner.validate_claims` calls `spec_builder.load_indataflow_context()`, so forbidden phrases and product boundaries come from InDataFlow only, not from the onboarded company's `constraints`.
3. **Non-generated renderers are not dispatched.** `services/renderers.py` (~L671) and `services/video/pipeline.py` (~L217): asset / motion_graphics / ffmpeg shots are "recorded pending". Uploaded footage and captions have nowhere to render. This is the main build.
4. **No video-asset upload path found.** `app/video_api.py` has no upload route; the only `UploadFile` usage found is voice upload in `marketing_api.py`. Check `workspace_api.py` and the onboarding UI before adding one; reuse if it exists.
5. **Router defects** (`shot_planner.route_visual`, `defs.ROUTE_KEYWORDS`): substring matching ("ship" hits "relationship", "port" hits "support"/"report"); broad cues `graphic`, `2d`, `icon`, `illustration` send beats to Hunyuan; no founder/face type, so those fall to `stock`.
6. **Canvas:** CLI/pipeline default `9:16`; `engines/g2/g2_runtime/video_layers.py` hardcodes `(1080, 1920)`.
7. **Chunk bug (low priority, legacy `render_mode="full"`):** `_full_video_chunks` builds every chunk from `purpose` fields only, all shots joined and truncated, never sliced by time, so chunk prompts are identical except "Segment N of M".
8. **Pack parser (optional):** `script_parser.parse_script` fails on the `InDataFlow_Scripts_*.md` format (bold `**0:00–0:06 — label**` headers, `- **Visible:**` fields). Only needed if packs are still used.
9. Not verified: the test suite was never run (pydantic missing in the analysis sandbox). Run it first and record the baseline.

## Work, in order

### 1. Compose stage (main work, gap 3)
Render each non-hunyuan shot to `videos/<project>/shots/<shot_id>.mp4`, canvas from `FORMAT_SIZES[spec.aspectRatio]` (remove the hardcoded size in `video_layers.py`):
- `founder_footage`: trim to beat duration, crop by the beat's focus hint (left / right / centre), scale to canvas.
- `product_capture`: same, with optional zoom/pan keyframe from `motion`.
- `founder_overlay`: UI base plus founder clip as rounded overlay (max 25% of frame, lower-right), 0.3s mask-in.
- `stock`: existing acquisition modules (`pexels`, `coverr`, `pixabay`) using the beat's search terms.
- `motion_graphics`: HTML/CSS templates rendered to transparent frames, then ffmpeg overlay. Templates: `hook_two_line`, `caption_rail`, `word_sequence`, `field_highlight`, `end_frame` (logo unchanged). Colors/fonts from `CompanyContext.constraints.brand` or a brand config; do not hardcode InDataFlow.
- Concat with the existing `assembly.py`. Hash each shot (shot spec + source file sha256); re-render only changed shots.

### 2. Context-grounded beat planning (gap 1)
- Add `plan_from_context(context: CompanyContext, assets: list, aspect_ratio)` that builds the fixed beat template: hook, proof, lesson, CTA end frame.
- Slot filling is deterministic: assets are tagged by the user at upload (`founder`, `ui_capture`, `logo`, `stock`), mapped to slots by tag and order. No tag inference.
- Caption text may come only from (a) text the user typed, (b) `CompanyContext` fields, (c) scraped `company_research` snippets. Store the source id per caption.
- OmniRoute may rephrase for length only if the result still passes the grounding check below; if the model is unavailable, the deterministic text is used. If a slot has no grounded text, leave it empty or return a "needs input" item, never filler.
- Remove the hardcoded protagonist/cinematic/no-UI storyboard instructions from the founder path (leave `direct_brief` for the legacy cinematic path, parameterised by company, not InDataFlow).

### 3. Grounded-claim validation (gap 2)
- Make `validate_claims` take the company's context: forbidden phrases and product boundaries from `CompanyContext.constraints`, falling back to the InDataFlow file only when the company is InDataFlow.
- New rule: every caption must have a source id that resolves to a user input, a `CompanyContext` field, or a stored website snippet. Fail the plan otherwise.

### 4. Upload and tagging (gap 4)
- Reuse an existing upload route if found; otherwise add one multipart route that stores files and calls `register_assets` with `type` = the user's tag.
- Validate with ffprobe (duration, resolution, codec); reject unreadable files; keep originals unchanged.

### 5. Router fixes (gap 5)
- Word-boundary regex in `_matched_families`; tests for "relationship", "support", "report".
- Drop `graphic`, `2d`, `icon`, `illustration` from hunyuan cues unless the beat type is explicitly generated.
- Add `founder_footage` / `founder_overlay` to `VISUAL_TYPES` and `RENDERER_FOR_TYPE`. Unknown still defaults to `stock`, never hunyuan. Hunyuan only for beats with an explicit fallback prompt.

### 6. Optional / later
- Fix `_full_video_chunks` (slice shots by time overlap, per-chunk prompts, test that chunk prompts differ).
- `parse_founder_pack` adapter for the 5-concept markdown (verbatim captions test, beat-count check).

## Acceptance
- From a completed onboarding (context + website research + tagged uploads), one command or API call produces one MP4 in the chosen aspect ratio with zero Hunyuan jobs.
- Every caption has a resolvable source id; a test removes a source and the plan fails.
- Changing one caption re-renders only that beat.
- Existing tests pass; add tests for 1 to 5 (use ffprobe for size/duration).
- No fake dashboards, no generated UI, no invented claims (see `skills/motion-designer/SKILL.md` hard rules).

## Report back
Files changed, test baseline before and after, and anything not verified.
