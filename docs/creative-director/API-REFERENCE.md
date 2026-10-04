# Video pipeline API reference (LOCKED)

Generated from source by AST; regenerate with the command at the bottom. Commit: a5e1e22. Date: 2026-10-04T05:05:18Z.


## `services/video/defs.py`
- const `HUNYUAN_DEFAULT_PROFILE`
- const `FORMAT_SIZES`
- const `DEFAULT_NEGATIVE_PROMPT`
- const `VISUAL_TYPES`
- const `RENDERER_FOR_TYPE`
- const `ROUTE_KEYWORDS`
- const `INFO_DISPLAY_CUES`
- const `MIXED_RENDERER_PRECEDENCE`
- `invalid(errors: list[str])` — 

## `services/video/script_parser.py`
- const `TIMESTAMP_RE`
- const `BEAT_HEADER_RE`
- const `VISUAL_FIELD_RE`
- const `META_FIELD_RE`
- `parse_timestamp(value: str)` — 
- `parse_beat_range(value: str)` — 
- `format_timestamp(seconds: float)` — 
- `parse_script(text: str, source_name: str='script')` — Parse a prepared script into title, metadata and timed visual beats.

## `services/video/spec_builder.py`
- const `KNOWLEDGE_DIR`
- `load_indataflow_context()` — Load brand/product/CTA guardrails from the existing G1 knowledge files.
- `forbidden_phrases(context: dict[str, Any])` — 
- `forbidden_patterns(context: dict[str, Any])` — 
- `build_spec(parsed: dict[str, Any], *, project_id: str, campaign_id: str | None=None, aspect_ratio: str='9:16', fps: int=24, source_path: str | None=None, context: dict[str, Any] | None=None)` — Build an (unsaved) VideoSpec dict from parsed script beats.
- `validate_spec(spec: dict[str, Any])` — Raise ValueError unless the spec satisfies prompt.md section 12.

## `services/video/shot_planner.py`
- `_matched_families(haystack: str)` — 
- `route_visual(beat_text: str, visual: dict[str, Any])` — Return (visual_type, renderer, matched_families) for one beat.
- `primary_renderer(families: list[str])` — 
- `_purpose(beat_text: str, visual: dict[str, Any], visual_type: str)` — 
- `_camera_for(visual_type: str, visual: dict[str, Any])` — Map beat notes onto the template-4 camera record schema.
- `decide_hunyuan_mode(families: list[str], reference_assets: list[str])` — T2V/I2V decision policy: exact identity needs an image reference.
- `select_reference_assets(assets: list[dict[str, Any]], families: list[str], visual: dict[str, Any])` — Resolve registry assets relevant to one shot (deterministic).
- `compile_hunyuan_prompt(bible: dict[str, Any], recipe: dict[str, Any], shot: dict[str, Any])` — Compile Subject + Motion + Scene + ShotType + Camera + Lighting + Style
- `plan_shots(spec: dict[str, Any], context: dict[str, Any] | None=None, use_ai: bool=True, bible: dict[str, Any] | None=None, recipe: dict[str, Any] | None=None)` — Build an (unsaved) ShotPlan dict. Returns (plan, ai_report).
- `_assets_for(visual_type: str, families: list[str], visual: dict[str, Any], beat: dict[str, Any])` — 
- `_attach_continuity(shots: list[dict[str, Any]])` — 
- `validate_plan(spec: dict[str, Any], plan: dict[str, Any])` — 
- `validate_claims(spec: dict[str, Any], plan: dict[str, Any], context: dict[str, Any] | None=None)` — Enforce product-boundary and source-reference rules (prompt.md section 12).
- class `AIEnhancedShot` — 
- class `AIPlanEnhancement` — 
- `_enhance_with_ai(spec: dict[str, Any], shots: list[dict[str, Any]])` — 

## `services/video/job_builder.py`
- `build_render_jobs(spec: dict[str, Any], plan: dict[str, Any], *, priority: int=100, render_mode: str='shots', bible: dict[str, Any] | None=None, recipe: dict[str, Any] | None=None)` — Build RenderJob dicts (unsaved) in the requested render mode.
- `_full_video_job(spec: dict[str, Any], plan: dict[str, Any], *, priority: int=100, bible: dict[str, Any] | None=None, recipe: dict[str, Any] | None=None)` — One whole-video Hunyuan job: no clip division, user-chosen mode.
- `validate_jobs(spec: dict[str, Any], plan: dict[str, Any], jobs: list[dict[str, Any]], *, render_mode: str='shots')` — 

## `services/video/pipeline.py`
- class `CreativeBriefResponse` — 
- class `StoryboardBeat` — 
- class `StoryboardOutline` — 
- `assign_durations(beats: list[StoryboardBeat], runtime_seconds: float)` — Split the runtime across beats proportional to narration weight.
- `plan_video(script_path: str | Path, *, project_id: str, campaign_id: str | None=None, aspect_ratio: str='9:16', fps: int=24, use_ai: bool=True, extra_assets: list[dict[str, Any]] | None=None)` — Parse a script file, validate, plan and persist spec + shot plan.
- `_finalize_directed_plan(spec_payload: dict[str, Any], context: dict[str, Any], *, use_ai: bool, recipe_id: str, recipe: dict[str, Any], bible: dict[str, Any])` — Shared persist path: validate, store spec/bible/assets/plan, build jobs.
- `validate_storyboard_generatable(outline: StoryboardOutline)` — Require at least one beat routable to the working renderer.
- `direct_brief(brief: str, *, project_id: str, campaign_id: str | None=None, aspect_ratio: str='9:16', fps: int=24, runtime_seconds: int | None=None)` — Direct a video from a human creative brief (template-4 phase 20).
- `store_spec_payload(spec: dict[str, Any])` — 
- `queue_shot_plan(plan_id: str, *, priority: int=100, render_mode: str='shots')` — Enqueue RenderJobs for a planned shot plan in the requested render mode.
- `store_job_rows(jobs: list[dict[str, Any]])` — 
- `job_counts(jobs: list[dict[str, Any]], plan: dict[str, Any] | None=None)` — 
- `hunyuan_profile()` — The default MI300X render profile (prompt.md section 9).
- `worker_env_example()` — 
- `reference_asset(path: str | Path)` — Build a product-reference registry entry for a user-supplied file.
- `launch(*, brief: str | None=None, script_path: str | Path | None=None, project_id: str, campaign_id: str | None=None, aspect_ratio: str='9:16', fps: int=24, references: list[str | Path] | None=None, submit: bool=True, timeout_seconds: int | None=None, render_mode: str='full', runtime_seconds: int | None=None)` — Run the product-launch pipeline end to end (motion-designer.md).

## `services/creative_director.py`
- const `ROLE_ROUTES`
- class `DirectorUnavailable` — Raised when an AI director role needs a model router key.
- `require_director()` — 
- class `CreativeDirector` — One director role (e.g. ``storyboarding``) backed by an OmniRoute route.
  - `run(self, prompt: str, output_model: type[OutputModel])` — Run the role synchronously; returns a validated output model.
- `director_available(role: str | None=None)` — True when the model router is configured (per-role check is the same).

## `services/visual_bible.py`
- const `REQUIRED_SECTIONS`
- `default_bible(*, brand_name: str='InDataFlow', colors: list[str] | None=None, style: str='restrained blue and indigo, premium commercial cinematography')` — 
- `validate_bible(bible: dict[str, Any])` — 
- `adapt_bible(bible: dict[str, Any], brief_text: str)` — Adapt the default bible environment to the brief's domain.
- `inherit_for_shot(bible: dict[str, Any], shot: dict[str, Any])` — Render the bible sections a shot prompt needs as short strings.

## `services/motion_recipes.py`
- const `RECIPES`
- `list_recipes()` — 
- `select_recipe(text: str)` — Deterministically score recipes by cue overlap; ties break by name.
- `select_recipe_ai(brief: str, *, candidates: list[str] | None=None)` — Let the director pick (and justify) a recipe; falls back deterministically.

## `services/cinematography.py`
- const `SHOT_TYPES`
- const `CAMERA_MOVEMENTS`
- const `LENSES`
- const `LIGHTING`
- const `DEPTH_OF_FIELD`
- const `COMPOSITION`
- const `TRANSITIONS`
- const `MOTION_PATTERNS`
- `validate_camera(camera: dict[str, Any])` — 
- `describe_shot_language(camera: dict[str, Any] | None, lens: dict[str, Any] | None, framing: dict[str, Any] | None)` — Compile camera/lens/framing records into a prompt fragment.

## `services/review.py`
- `technical_review(path: str | Path, job: dict[str, Any])` — Deterministic technical review of one rendered artifact.
- `ai_visual_review(artifact_path: str | Path, shot: dict[str, Any])` — Vision-model review of one render. SKIPPED without a configured model.
- `continuity_review(shots: list[dict[str, Any]], artifacts: dict[str, dict[str, Any]] | None=None)` — Deterministic cross-shot continuity check (codecs, fps, style chain).
- `_skipped(reason: str)` — 

## `services/quality_gates.py`
- const `GATES`
- `run_gates(spec: dict[str, Any], plan: dict[str, Any], jobs: list[dict[str, Any]], *, artifacts: dict[str, str] | None=None, context: dict[str, Any] | None=None, render_mode: str='shots')` — Run all quality gates. ``artifacts`` maps shot_id -> local MP4 path.
- `_pass(reason: str)` — 
- `_fail(reason: str)` — 
- `_skipped(reason: str)` — 

## `services/renderers.py`
- const `REPO`
- const `DEFAULT_RENDER_TIMEOUT_SECONDS`
- const `DEFAULT_CONNECT_TIMEOUT_SECONDS`
- const `HEALTH_TIMEOUT_SECONDS`
- const `PRE_SUBMIT_ATTEMPTS`
- const `DEFAULT_POLL_INTERVAL_SECONDS`
- const `ASYNC_STATUSES`
- const `TERMINAL_WORKER_STATUSES`
- const `CONTROL_PLANE_WORKER_ID`
- class `RenderWorkerError` — A failed render submit. ``retryable`` decides the job's fate.
- class `RenderQAError` — A worker output that failed local validation.
- `render_worker_url()` — 
- `_env_int(name: str, default: int)` — 
- `render_timeout_seconds()` — 
- `poll_interval_seconds()` — 
- `worker_api_token()` — Bearer token for protected worker endpoints (empty = not configured).
- `render_output_dir()` — 
- `aspect_ratio_for(width: int | None, height: int | None)` — Canonical 'W:H' ratio for the worker payload (it defaults to 16:9).
- class `Renderer` — Minimal renderer interface. Submitters only; no local GPU work.
  - `check_health(self)` — Lightweight liveness probe. Raises RenderWorkerError when down.
  - `check_capacity(self)` — Worker availability snapshot. Raises RenderWorkerError when down.
  - `submit_render(self, payload: dict[str, Any])` — Submit one render payload.
  - `get_render_status(self, worker_job_id: str)` — Poll ``GET /render/{job_id}``. Raises RenderWorkerError.
  - `download_render(self, worker_job_id: str, dest_path: str | Path, *, expected_sha256: str | None=None)` — Stream ``GET /render/{job_id}/download`` to disk (no full RAM load).
  - `download_by_name(self, output_name: str, dest_path: str | Path, *, expected_sha256: str | None=None)` — Stream ``GET /video/{output_name}`` to disk (observed worker shape).
- `_safe_filename(name: str)` — Allow only plain filenames (the /video/{name} download shape).
- `_safe_job_id(worker_job_id: str)` — Reject anything that is not a plain job identifier (path traversal).
- `_worker_job_id(body: dict[str, Any])` — First usable worker job identifier in a response body, if any.
- `_auth_headers()` — 
- class `HunyuanRenderer` — Submits RenderJob payloads to the private MI300X worker's POST /render.
  - `close(self)` — 
  - `_get(self, path: str, *, authenticated: bool=False)` — 
  - `check_health(self)` — 
  - `check_capacity(self)` — 
  - `submit_render(self, payload: dict[str, Any])` — 
  - `_extract_output(self, response: httpx.Response, payload: dict[str, Any])` — 
  - `get_render_status(self, worker_job_id: str)` — Poll the authenticated ``GET /render/{job_id}`` status endpoint.
  - `download_render(self, worker_job_id: str, dest_path: str | Path, *, expected_sha256: str | None=None, timeout_seconds: int | None=None)` — Stream ``GET /render/{job_id}/download`` to disk without RAM load.
  - `download_by_name(self, output_name: str, dest_path: str | Path, *, expected_sha256: str | None=None, timeout_seconds: int | None=None)` — Stream the observed ``GET /video/{output_name}`` worker shape.
  - `download_url(self, url: str, dest_path: str | Path, *, expected_sha256: str | None=None, timeout_seconds: int | None=None)` — Stream an absolute http(s) output URL to disk (same guards).
  - `_stream_get(self, url_or_path: str, dest_path: str | Path, *, expected_sha256: str | None=None, timeout_seconds: int)` — 
  - `_json_download_error(response: httpx.Response)` — 
- `get_renderer(name: str, **kwargs: Any)` — Return the submitter for a renderer tag. Only hunyuan has a worker.
- `_run_ffprobe(args: list[str])` — 
- `qa_render_output(path: str | Path, *, expected_frames: int | None=None, expected_fps: int | None=None)` — Validate a worker MP4. Raises RenderQAError with a useful reason.
- `worker_status()` — Failure-tolerant health/capacity snapshot (never raises).
- `submit_hunyuan_job(job_id: str, *, timeout_seconds: int | None=None)` — Submit one queued hunyuan job to the MI300X worker.
- `_poll_until_done(renderer: HunyuanRenderer, worker_job_id: str, deadline: float)` — Poll the worker status endpoint until the job completes or fails.

## `core/video_store.py`
- const `RENDERERS`
- const `JOB_STATUSES`
- const `DEFAULT_LEASE_SECONDS`
- const `DEFAULT_MAX_ATTEMPTS`
- `connect()` — 
- `init_video_db()` — 
- `_ensure_column(connection: sqlite3.Connection, table: str, column: str, ddl: str)` — 
- `_new_id(prefix: str)` — 
- `_decode_json(value: Any, default: Any)` — 
- `_decode_spec(row: sqlite3.Row)` — 
- `_decode_plan(row: sqlite3.Row)` — 
- `_decode_job(row: sqlite3.Row)` — 
- `create_spec(payload: dict[str, Any])` — 
- `get_spec(spec_id: str)` — 
- `list_specs(limit: int=50)` — 
- `update_spec_status(spec_id: str, status: str)` — 
- `create_shot_plan(payload: dict[str, Any])` — 
- `get_shot_plan(plan_id: str)` — 
- `list_shot_plans(spec_id: str | None=None)` — 
- `update_plan_status(plan_id: str, status: str)` — 
- `enqueue_jobs(rows: list[dict[str, Any]])` — Insert render jobs. Output paths must be unique across the queue.
- `get_job(job_id: str)` — 
- `list_jobs(shot_plan_id: str | None=None, status: str | None=None, renderer: str | None=None, limit: int=200)` — 
- `queue_stats()` — 
- `_lease_deadline(lease_seconds: int)` — 
- `lease_next_job(worker_id: str, renderer: str | None=None, lease_seconds: int=DEFAULT_LEASE_SECONDS)` — Atomically lease the oldest pending job (or reclaim an expired lease).
- `claim_job(job_id: str, worker_id: str, lease_seconds: int=DEFAULT_LEASE_SECONDS)` — Claim a specific pending job for control-plane dispatch (push model).
- `_owned_job(job_id: str, worker_id: str, states: tuple[str, ...])` — 
- `heartbeat_job(job_id: str, worker_id: str, lease_seconds: int=DEFAULT_LEASE_SECONDS)` — 
- `complete_job(job_id: str, worker_id: str, result: dict[str, Any] | None=None)` — 
- `fail_job(job_id: str, worker_id: str, code: str | None=None, message: str='', retryable: bool=True)` — 
- `retry_job(job_id: str)` — Operator requeue of a failed or cancelled job with a fresh attempt budget.
- `cancel_job(job_id: str)` — 
- `save_visual_bible(spec_id: str, bible: dict[str, Any], recipe_id: str | None=None)` — 
- `get_visual_bible(spec_id: str)` — 
- `register_assets(spec_id: str, assets: list[dict[str, Any]])` — 
- `list_assets(spec_id: str)` — 

## `app/video_api.py` routes (`/company/video`, dashboard auth; writes need `X-Founder-Action-Token`)

- `GET /specs`, `GET /specs/{id}`, `GET /plans[?spec_id=]`, `GET /plans/{id}`
- `GET /jobs[?shot_plan_id&status&renderer]`, `GET /jobs/{id}`, `GET /queue/stats`, `GET /hunyuan/profile`
- `POST /specs` (script_text), `POST /plans` (spec_id), `POST /plans/{id}/queue?render_mode=shots|full`, `POST /jobs/{id}/retry`, `POST /jobs/{id}/cancel`
- Worker protocol: `GET /render-jobs/next?worker_id&renderer`, `POST /render-jobs/{id}/heartbeat|complete|fail`

## `scripts/video.py` commands

- `plan --script --project-id [--campaign-id --format --fps --no-ai --mode --manifest-out]`
- `direct --brief|--brief-file --project-id [--runtime --format --fps --manifest-out]`
- `launch --brief|--brief-file|--script --project-id [--reference … --no-submit --mode --timeout --manifest-out]`
- `queue <plan-id> [--priority --mode]`, `submit <job-id> [--timeout]`, `worker-status`, `profile`

## Regenerate this file

Run the AST surface script against the modules listed at its top, then append the routes/commands sections above.
