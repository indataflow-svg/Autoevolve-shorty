# AutoEvolve locked API reference

Generated from source by `scripts/gen_api_reference.py` at commit `96d6c8b` on 2026-10-04T05:09:37Z.

Every public constant, function, class and method in the shipped packages, with its real signature. Read this as the contract: if a name here disagrees with the code, the code is authoritative and this file must be regenerated.

## Totals

| modules | public functions | classes | public methods | module constants | HTTP routes | DB tables | CLI verbs |
|---|---|---|---|---|---|---|
| 80 | 803 | 153 | 64 | 236 | 163 | 24 | 7 |

## Core state and models

### `core/__init__.py`

- (no public module-level names)

### `core/branding.py`

- `company_name() -> str`
- `company_public_url() -> str`
- `company_forms_url() -> str`
- `company_logo_url() -> str`

### `core/company_read.py`

- const `SUMMARY_FIELDS`
- `list_company_records(*, page: int, page_size: int, query: str, view: str, sort: str, industry: str='', country: str='') -> tuple[list[dict[str, Any]], int, dict[str, int]]`
- `get_company_record(company_id: str) -> dict[str, Any] | None`

### `core/dashboard.py`

- const `ROOT`
- const `PROJECTS_ROOT`
- `get_dashboard_state() -> dict`
- `get_operations_page_state() -> dict`

### `core/db.py`

- const `BUSY_TIMEOUT_SECONDS`
- `open_db(path: str | Path, *, row_factory: Any=None, timeout: float=BUSY_TIMEOUT_SECONDS) -> sqlite3.Connection`

### `core/marketing_config.py`

- const `ROOT`
- const `WORKSPACE_ROOT`
- class `MarketingConfig`
  - `load(cls) -> 'MarketingConfig'`
  - `diagnostics(self) -> dict`

### `core/marketing_store.py`

- const `TERMINAL_CAMPAIGN_STATES`
- `connect() -> sqlite3.Connection`
- `init_marketing_db() -> None`
- `create_campaign(*, org_id: int, task_id: int, request: str, objective: str, buyer: str, topic: str, social_platforms: list[str], video_platform: str, voice_mode: str='tts', voice_transcript: str | None=None) -> dict`
- `update_campaign(campaign_id: str, **fields: Any) -> None`
- `get_campaign(campaign_id: str, *, include_variants: bool=True) -> dict | None`
- `list_campaigns(limit: int=20, org_id: int | None=None) -> list[dict]`
- `create_variant(campaign_id: str, platform: str, voice: str, speed: float) -> dict`
- `update_variant(variant_id: str, **fields: Any) -> None`
- `get_variant(variant_id: str) -> dict | None`
- `clear_variants(campaign_id: str) -> int`
- `add_event(campaign_id: str, event: str, payload: dict, *, connection: sqlite3.Connection | None=None) -> None`
- `list_events(campaign_id: str) -> list[dict]`
- `create_manual_post(*, org_id: int, platform: str, post_id: str, destination_url: str, tracked_url: str, campaign_id: str | None=None, title: str | None=None, creative: str | None=None, hook: str | None=None, offer: str | None=None, cta: str | None=None, source_detail: str | None=None, asset_dir: str | None=None, assets: list[dict[str, Any]] | None=None, metadata: dict[str, Any] | None=None) -> dict`
- `get_manual_post(post_record_id: str) -> dict | None`
- `list_manual_posts(limit: int=50, org_id: int | None=None) -> list[dict]`
- `update_manual_post(post_record_id: str, **fields: Any) -> dict`

### `core/memory.py`

- `now_iso() -> str`
- `init_memory_db() -> None`
- `write_memory(brand: str, kind: str, title: str, text: str, source_ref: str='') -> dict` — Persist one memory scoped to a brand. Never writes across brands
- `recall(brand: str, query: str, kind: str | None=None, limit: int=5) -> list[dict]` — Keyword recall scoped to one brand. Returns rank-ordered memories
- `list_recent(brand: str, kind: str | None=None, limit: int=10) -> list[dict]`
- `count_by_brand(brand: str) -> dict[str, int]`
- `brand_for_lead(lead: dict | None) -> str | None` — Resolve a lead's brand from its metadata. None when untagged (deferred migration)
- `record_outcome(brand: str | None, kind: str, title: str, text: str, source_ref: str='') -> dict | None` — Best-effort memory write. Never raises; returns None when skipped/failed

### `core/models.py`

- const `OMNIROUTE_BASE_URL`
- const `OMNIROUTE_API_KEY`
- `is_model_configured() -> bool` — True when the user supplied a real model-router key
- `require_model_configured() -> None` — Raise a user-friendly error when an AI action needs a key
- const `ROUTES`
- `cloud_model(route: str='free') -> OpenAIChatModel`

### `core/ops_store.py`

- const `ROOT`
- const `DB_PATH`
- `now_iso() -> str`
- `connect() -> sqlite3.Connection`
- `init_db() -> None`
- `upsert_task(task: dict[str, Any]) -> None`
- `get_task(task_id: str) -> dict[str, Any] | None`
- `list_tasks(limit: int=50) -> list[dict[str, Any]]`
- `upsert_incident(incident: dict[str, Any]) -> None`
- `get_incident(incident_id: str) -> dict[str, Any] | None`
- `list_incidents(limit: int=50) -> list[dict[str, Any]]`

### `core/projects.py`

- const `PROJECTS_ROOT`
- `now_iso() -> str`
- `slugify(text: str) -> str`
- `ensure_project(name: str) -> tuple[dict, Path]` — Create or reuse a project
- `save_research(project_path: Path, report: dict) -> Path`

### `core/sales_store.py`

- const `PIPELINE_STAGES`
- `connect() -> sqlite3.Connection`
- `init_sales_db() -> None`
- `linkedin_url_for_lead(lead: dict | None) -> str | None`
- `linkedin_profile_for_lead_org(lead: dict | None) -> str | None`
- `contact_profile_for_lead(lead: dict | None) -> dict[str, Any]`
- `normalize_company_domain(value: Any) -> str | None`
- `get_company_profile(domain: str | None) -> dict | None`
- `upsert_company_profile(domain: str, *, provider: str, status: str, company_name: str | None=None, summary: dict[str, Any] | None=None, raw: dict[str, Any] | None=None, fetched_at: str | None=None) -> dict`
- `score_lead(lead: dict) -> int`
- `upsert_lead(payload: dict) -> tuple[dict, bool]`
- `get_lead(lead_id: str) -> dict | None`
- `get_lead_by_email(email: str | None) -> dict | None`
- `list_leads(limit: int=50, stage: str | None=None) -> list[dict]`
- `list_contacts_page(*, page: int=1, page_size: int=10, stage: str | None=None, query: str='', sort: str='recent') -> tuple[list[dict], int, dict[str, Any]]` — Read-only, complete pagination over the existing sales leads
- `merge_lead_metadata(lead_id: str, patch: dict[str, Any]) -> dict`
- `record_contact_resolution(lead_id: str, *, provider: str, email: str | None=None, phone: str | None=None, whatsapp_candidate: str | None=None, status: str, details: dict[str, Any] | None=None) -> dict`
- `update_lead(lead_id: str, **fields: Any) -> None`
- `suppress_lead(lead_id: str, reason: str) -> None`
- `create_draft(lead_id: str, subject: str, body: str, channel: str='email', kind: str='first_outreach', in_reply_to: str | None=None) -> dict`
- `get_draft(draft_id: str) -> dict | None`
- `get_draft_by_provider_message_id(provider_message_id: str | None) -> dict | None`
- `update_draft(draft_id: str, *, subject: str | None=None, body: str | None=None) -> dict`
- `approve_draft(draft_id: str) -> dict`
- `claim_draft_for_send(draft_id: str) -> dict`
- `release_send_claim(draft_id: str) -> None`
- `list_sending_drafts() -> list[dict]`
- `mark_send_unknown(draft_id: str, *, reason: str) -> dict` — Park a draft whose send outcome cannot be proven either way
- `list_send_unknown_drafts() -> list[dict]`
- `resolve_send_unknown(draft_id: str, *, delivered: bool, provider_message_id: str | None=None, note: str | None=None) -> dict` — Operator decision for a parked draft: it went out, or it did not
- `mark_sent(draft_id: str, provider_message_id: str, metadata: dict | None=None) -> None`
- `add_interaction(lead_id: str, direction: str, channel: str, kind: str, subject: str | None, body: str | None, provider_message_id: str | None=None, metadata: dict | None=None) -> bool`
- `mark_replied(lead_id: str, subject: str, body: str, provider_message_id: str | None=None, metadata: dict | None=None) -> None`
- `mark_meeting_scheduled(lead_id: str, scheduled_for: str | None=None, note: str | None=None) -> dict`
- `add_event(lead_id: str | None, event: str, payload: dict) -> None`
- `count_company_profile_attempts() -> int`
- `list_events(limit: int=50, lead_id: str | None=None) -> list[dict]`
- `list_interactions(limit: int=50, lead_id: str | None=None) -> list[dict]`
- `summary() -> dict`

### `core/setup_keys.py`

- const `ROOT`
- const `DEFAULT_ENV_FILE`
- const `DEFAULT_G3_ENV_FILE`
- const `ENV_FILE`
- const `G3_ENV_FILE`
- const `SECRET_HINTS`
- `env_file() -> Path`
- `g3_env_file() -> Path`
- const `PROVIDER_GROUPS`
- `group_status() -> dict[str, dict]` — Masked per-group status: which keys are set (never values)
- `validate_group(group: str, values: dict[str, str]) -> dict` — Format-level validation (no credits spent). Live gateway check for ai_gateway
- `save_group(group: str, values: dict[str, str]) -> dict` — Validate, backup, then write. Rolls back the file on any failure

### `core/state.py`

- const `DB_PATH`
- `now_iso() -> str`
- `connect() -> sqlite3.Connection`
- `init_db() -> None`
- const `VALID_CAPABILITIES`
- `set_org_capabilities(org_id: int, capabilities: dict[str, bool]) -> dict[str, bool]`
- `get_org_capabilities(org_id: int) -> dict[str, bool]`
- `get_setup_step() -> str`
- `set_setup_step(step: str) -> None`
- `get_onboarding_program() -> dict | None` — The single first-run sales program, stored with existing setup settings
- `save_onboarding_program(program: dict) -> None`
- `get_service_discovery_run(run_id: str) -> dict | None`
- `list_service_discovery_runs(limit: int=10) -> list[dict]`
- `save_service_discovery_run(run: dict) -> None`
- `claim_service_provider_request(provider: str, action: str, limit_24h: int) -> bool` — Reserve one request against a conservative rolling local provider cap
- `create_org(name: str, slug: str, env_prefix: str='BUFFER_', organization_id: str='', domain: str='') -> dict`
- `get_org(org_id: int) -> Optional[dict]`
- `get_org_by_slug(slug: str) -> Optional[dict]`
- `list_orgs() -> list[dict]`
- `set_active_org(org_id: int) -> None`
- `get_active_org() -> Optional[dict]`
- `load_org_key(org_id: int) -> str`
- `create_org_account(org_id: int, platform: str, channel_id: str | None=None, profile_url: str | None=None) -> dict`
- `get_org_accounts(org_id: int) -> list[dict]`
- `get_org_account(org_id: int, platform: str) -> Optional[dict]`
- `linkedin_profile_for_org(org_id: int) -> Optional[str]`
- `create_task(*, org_id: Optional[int], agent: str, task_type: str, input_text: str, priority: str='normal', requires_approval: bool=False) -> dict`
- `update_task_status(task_id: int, status: str) -> None`
- `complete_task(task_id: int, output: str) -> None`
- `fail_task(task_id: int, error: str) -> None`
- `get_recent_tasks(limit: int=20) -> list[dict]`

### `core/video_store.py`

- const `RENDERERS`
- const `JOB_STATUSES`
- const `DEFAULT_LEASE_SECONDS`
- const `DEFAULT_MAX_ATTEMPTS`
- `connect() -> sqlite3.Connection`
- `init_video_db() -> None`
- `create_spec(payload: dict[str, Any]) -> dict[str, Any]`
- `get_spec(spec_id: str) -> dict[str, Any] | None`
- `list_specs(limit: int=50) -> list[dict[str, Any]]`
- `update_spec_status(spec_id: str, status: str) -> dict[str, Any] | None`
- `create_shot_plan(payload: dict[str, Any]) -> dict[str, Any]`
- `get_shot_plan(plan_id: str) -> dict[str, Any] | None`
- `list_shot_plans(spec_id: str | None=None) -> list[dict[str, Any]]`
- `update_plan_status(plan_id: str, status: str) -> dict[str, Any] | None`
- `enqueue_jobs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]` — Insert render jobs. Output paths must be unique across the queue
- `get_job(job_id: str) -> dict[str, Any] | None`
- `list_jobs(shot_plan_id: str | None=None, status: str | None=None, renderer: str | None=None, limit: int=200) -> list[dict[str, Any]]`
- `queue_stats() -> dict[str, Any]`
- `lease_next_job(worker_id: str, renderer: str | None=None, lease_seconds: int=DEFAULT_LEASE_SECONDS) -> dict[str, Any] | None` — Atomically lease the oldest pending job (or reclaim an expired lease)
- `claim_job(job_id: str, worker_id: str, lease_seconds: int=DEFAULT_LEASE_SECONDS) -> dict[str, Any]` — Claim a specific pending job for control-plane dispatch (push model)
- `heartbeat_job(job_id: str, worker_id: str, lease_seconds: int=DEFAULT_LEASE_SECONDS) -> dict[str, Any]`
- `complete_job(job_id: str, worker_id: str, result: dict[str, Any] | None=None) -> dict[str, Any]`
- `fail_job(job_id: str, worker_id: str, code: str | None=None, message: str='', retryable: bool=True) -> dict[str, Any]`
- `retry_job(job_id: str) -> dict[str, Any]` — Operator requeue of a failed or cancelled job with a fresh attempt budget
- `cancel_job(job_id: str) -> dict[str, Any]`
- `save_visual_bible(spec_id: str, bible: dict[str, Any], recipe_id: str | None=None) -> dict[str, Any]`
- `get_visual_bible(spec_id: str) -> dict[str, Any] | None`
- `register_assets(spec_id: str, assets: list[dict[str, Any]]) -> list[dict[str, Any]]`
- `list_assets(spec_id: str) -> list[dict[str, Any]]`

## Support services

### `services/__init__.py`

- (no public module-level names)

### `services/apollo.py`

- class `ApolloError`(RuntimeError)
- class `ApolloClient`
  - `people_search(self, domain: str, limit: int=10) -> list[dict]`
  - `people_market_search(self, *, industry: str, location: str | None=None, limit: int=5) -> list[dict]`
  - `people_service_search(self, *, keywords: list[str], job_titles: list[str], location: str | None=None, limit: int=25) -> list[dict]` — One bounded preview search; this endpoint does not reveal email or phone
  - `bulk_match(self, details: list[dict[str, Any]]) -> list[dict]`
  - `match_person(self, *, email: str | None=None, name: str | None=None, domain: str | None=None, apollo_id: str | None=None) -> dict`

### `services/asset_pack_builder.py`

- const `STOPWORDS`
- const `MAX_CONTENT_SLIDES`
- `split_script_sections(script: str) -> list[str]`
- `build_asset_package(script: str, *, objective: str='awareness', social_platforms: list[str] | None=None, video_platform: str='shorts') -> dict[str, Any]`
- `build_pack_title(script: str) -> str`

### `services/asset_pack_worker.py`

- const `ROOT`
- const `PROJECTS_ROOT`
- `run_asset_pack(project_slug: str, pack_id: str) -> None`
- `spawn_asset_pack(project_slug: str, pack_id: str) -> None`
- `main() -> int`

### `services/asset_scene_planner.py`

- const `MAX_SCENES`
- const `WORDS_PER_MINUTE`
- const `SECONDS_PER_SCENE`
- class `SceneBoundary`(BaseModel)
- class `SceneBoundaryPlan`(BaseModel)
- `plan_script_scenes(script: str) -> dict[str, Any]`

### `services/caption_variants.py`

- const `CTA_BY_PLATFORM`
- `build_short_caption_variants(*, topic: str, buyer: str, transcript: str, platform_copy: dict[str, Any] | None=None) -> dict[str, list[str]]`
- `enrich_platform_copy(platform_copy: dict[str, Any] | None) -> dict[str, Any]`

### `services/cinematography.py`

- const `SHOT_TYPES`
- const `CAMERA_MOVEMENTS`
- const `LENSES`
- const `LIGHTING`
- const `DEPTH_OF_FIELD`
- const `COMPOSITION`
- const `TRANSITIONS`
- const `MOTION_PATTERNS`
- `validate_camera(camera: dict[str, Any]) -> list[str]`
- `describe_shot_language(camera: dict[str, Any] | None, lens: dict[str, Any] | None, framing: dict[str, Any] | None) -> str` — Compile camera/lens/framing records into a prompt fragment

### `services/company_enrich.py`

- class `CompanyEnrichError`(RuntimeError)
- class `CompanyEnrichClient`
  - `me(self) -> dict`
  - `enrich_company(self, domain: str, *, wait_for_enrichment: bool=True) -> dict`
  - `extract_company_profile(self, payload: dict[str, Any]) -> dict[str, Any]`
- `company_usage_profile(company_profile: dict[str, Any] | None) -> dict[str, Any]`

### `services/creative_director.py`

- const `ROLE_ROUTES`
- class `DirectorUnavailable`(RuntimeError) — Raised when an AI director role needs a model router key
- `require_director() -> None`
- class `CreativeDirector` — One director role (e.g. ``storyboarding``) backed by an OmniRoute route
  - `run(self, prompt: str, output_model: type[OutputModel]) -> OutputModel` — Run the role synchronously; returns a validated output model
- `director_available(role: str | None=None) -> bool` — True when the model router is configured (per-role check is the same)

### `services/hunter.py`

- class `HunterError`(RuntimeError)
- class `HunterClient`
  - `domain_search(self, domain: str, limit: int=10) -> list[dict]`
  - `email_finder(self, *, domain: str, full_name: str) -> dict`
  - `verify(self, email: str) -> dict`
  - `account(self) -> dict`

### `services/linkedin_discovery.py`

- `discover_linkedin(lead_id: str, provider: str='auto', force: bool=False) -> dict[str, Any]` — Find and store a lead's LinkedIn profile URL

### `services/lusha.py`

- class `LushaError`(RuntimeError)
- class `LushaClient`
  - `contact_filter_values(self, filter_type: str, query: str | None=None) -> dict`
  - `company_filter_values(self, filter_type: str, query: str | None=None) -> dict`
  - `prospect_contacts(self, *, job_title: str | None=None, service_keywords: list[str] | None=None, location: str | None=None, company_size: str | None=None, limit: int=5) -> dict`
  - `enrich_contacts(self, request_id: str, contact_ids: list[str]) -> dict`

### `services/marketing_worker.py`

- const `ROOT`
- const `G2_CAMPAIGN_FIELDS`
- const `G2_SLIDE_FIELDS`
- const `G2_NESTED_FIELDS`
- `run_pipeline(campaign_id: str) -> None`
- `run_media_pipeline(campaign_id: str, *, campaign: dict | None=None, package: dict | None=None, config: MarketingConfig | None=None, root: Path | None=None, logs: Path | None=None) -> None`
- `run_real_voice_render(campaign_id: str) -> None`
- `run_g3(campaign_id: str) -> None`
- `spawn(campaign_id: str, stage: str='pipeline') -> None`
- `main() -> int`

### `services/monitor.py`

- const `ROOT`
- const `SERVICES_CONFIG`
- `now_iso()`
- `load_services()`
- `shell(cmd: str, timeout=60)`
- `health(service: dict) -> dict`
- `evidence(service: dict, h: dict) -> dict`
- `handle_failure(name: str, service: dict, h: dict) -> dict`
- `check_service(name: str) -> dict`
- `check_all() -> list[dict]`

### `services/motion_recipes.py`

- const `RECIPES`
- `list_recipes() -> list[str]`
- `select_recipe(text: str) -> tuple[str, dict[str, Any]]` — Deterministically score recipes by cue overlap; ties break by name
- `select_recipe_ai(brief: str, *, candidates: list[str] | None=None) -> dict[str, Any]` — Let the director pick (and justify) a recipe; falls back deterministically

### `services/pdl.py`

- class `PeopleDataLabsError`(RuntimeError)
- class `PeopleDataLabsClient`
  - `enrich_company(self, website: str, *, pretty: bool=False) -> dict`
  - `extract_company_profile(self, payload: dict[str, Any]) -> dict[str, Any]`

### `services/prospeo.py`

- class `ProspeoError`(RuntimeError)
- class `ProspeoClient`
  - `search_person(self, filters: dict[str, Any], page: int=1) -> dict`
  - `search_suggestions(self, *, job_title: str | None=None, location: str | None=None, industry: str | None=None) -> dict`
  - `extract_contact_fields(self, payload: dict[str, Any]) -> dict[str, Any]`
  - `enrich_person(self, person_id: str) -> dict`

### `services/quality_gates.py`

- const `GATES`
- `run_gates(spec: dict[str, Any], plan: dict[str, Any], jobs: list[dict[str, Any]], *, artifacts: dict[str, str] | None=None, context: dict[str, Any] | None=None, render_mode: str='shots') -> dict[str, Any]` — Run all quality gates. ``artifacts`` maps shot_id -> local MP4 path

### `services/renderers.py`

- const `REPO`
- const `DEFAULT_RENDER_TIMEOUT_SECONDS`
- const `DEFAULT_CONNECT_TIMEOUT_SECONDS`
- const `HEALTH_TIMEOUT_SECONDS`
- const `PRE_SUBMIT_ATTEMPTS`
- const `DEFAULT_POLL_INTERVAL_SECONDS`
- const `ASYNC_STATUSES`
- const `TERMINAL_WORKER_STATUSES`
- class `RenderWorkerError`(Exception) — A failed render submit. ``retryable`` decides the job's fate
- class `RenderQAError`(Exception) — A worker output that failed local validation
- `render_worker_url() -> str`
- `render_timeout_seconds() -> int`
- `poll_interval_seconds() -> int`
- `worker_api_token() -> str` — Bearer token for protected worker endpoints (empty = not configured)
- `render_output_dir() -> Path`
- `aspect_ratio_for(width: int | None, height: int | None) -> str` — Canonical 'W:H' ratio for the worker payload (it defaults to 16:9)
- class `Renderer`(ABC) — Minimal renderer interface. Submitters only; no local GPU work
  - `check_health(self) -> dict[str, Any]` — Lightweight liveness probe. Raises RenderWorkerError when down
  - `check_capacity(self) -> dict[str, Any]` — Worker availability snapshot. Raises RenderWorkerError when down
  - `submit_render(self, payload: dict[str, Any]) -> dict[str, Any]` — Submit one render payload
  - `get_render_status(self, worker_job_id: str) -> dict[str, Any]` — Poll ``GET /render/{job_id}``. Raises RenderWorkerError
  - `download_render(self, worker_job_id: str, dest_path: str | Path, *, expected_sha256: str | None=None) -> dict[str, Any]` — Stream ``GET /render/{job_id}/download`` to disk (no full RAM load)
  - `download_by_name(self, output_name: str, dest_path: str | Path, *, expected_sha256: str | None=None) -> dict[str, Any]` — Stream ``GET /video/{output_name}`` to disk (observed worker shape)
- class `HunyuanRenderer`(Renderer) — Submits RenderJob payloads to the private MI300X worker's POST /render
  - `close(self) -> None`
  - `check_health(self) -> dict[str, Any]`
  - `check_capacity(self) -> dict[str, Any]`
  - `submit_render(self, payload: dict[str, Any]) -> dict[str, Any]`
  - `get_render_status(self, worker_job_id: str) -> dict[str, Any]` — Poll the authenticated ``GET /render/{job_id}`` status endpoint
  - `download_render(self, worker_job_id: str, dest_path: str | Path, *, expected_sha256: str | None=None, timeout_seconds: int | None=None) -> dict[str, Any]` — Stream ``GET /render/{job_id}/download`` to disk without RAM load
  - `download_by_name(self, output_name: str, dest_path: str | Path, *, expected_sha256: str | None=None, timeout_seconds: int | None=None) -> dict[str, Any]` — Stream the observed ``GET /video/{output_name}`` worker shape
  - `download_url(self, url: str, dest_path: str | Path, *, expected_sha256: str | None=None, timeout_seconds: int | None=None) -> dict[str, Any]` — Stream an absolute http(s) output URL to disk (same guards)
- `get_renderer(name: str, **kwargs: Any) -> Renderer` — Return the submitter for a renderer tag. Only hunyuan has a worker
- `qa_render_output(path: str | Path, *, expected_frames: int | None=None, expected_fps: int | None=None) -> dict[str, Any]` — Validate a worker MP4. Raises RenderQAError with a useful reason
- const `CONTROL_PLANE_WORKER_ID`
- `worker_status() -> dict[str, Any]` — Failure-tolerant health/capacity snapshot (never raises)
- `submit_hunyuan_job(job_id: str, *, timeout_seconds: int | None=None) -> dict[str, Any]` — Submit one queued hunyuan job to the MI300X worker

### `services/review.py`

- `technical_review(path: str | Path, job: dict[str, Any]) -> dict[str, Any]` — Deterministic technical review of one rendered artifact
- `ai_visual_review(artifact_path: str | Path, shot: dict[str, Any]) -> dict[str, Any]` — Vision-model review of one render. SKIPPED without a configured model
- `continuity_review(shots: list[dict[str, Any]], artifacts: dict[str, dict[str, Any]] | None=None) -> dict[str, Any]` — Deterministic cross-shot continuity check (codecs, fps, style chain)

### `services/sales_service.py`

- const `RESEND_SEND_URL`
- const `RESEND_IDEMPOTENCY_WINDOW_SECONDS`
- const `RESEND_CONCURRENT_RETRY_DELAYS`
- const `RESEND_RECEIVING_URL`
- const `RESEND_USER_AGENT`
- const `RESEND_WEBHOOK_TOLERANCE_SECONDS`
- `import_hunter_domain(domain: str, limit: int=5) -> list[dict]`
- `import_apollo_domain(domain: str, limit: int=5) -> list[dict]`
- `research_prospeo_leads(*, job_title: str, service_keywords: list[str] | None=None, location: str | None=None, company_size: str | None=None, limit: int=5) -> list[dict]`
- `research_prospeo_market_leads(*, industry: str, location: str | None=None, limit: int=5) -> list[dict]`
- `research_prospeo_suggestions(*, kind: str, query: str) -> list[str]`
- `research_lusha_suggestions(*, kind: str, query: str) -> list[str]`
- `research_lusha_leads(*, job_title: str | None=None, service_keywords: list[str] | None=None, location: str | None=None, company_size: str | None=None, limit: int=5) -> list[dict]`
- `research_lusha_market_leads(*, industry: str, location: str | None=None, limit: int=5) -> list[dict]`
- `research_apollo_market_leads(*, industry: str, location: str | None=None, limit: int=5) -> list[dict]`
- `research_market_leads(*, industry: str, location: str | None=None, limit_per_provider: int=5) -> dict[str, Any]`
- `import_domain(domain: str, limit: int=5, provider: str='hunter') -> list[dict]`
- `pull_inbound_leads() -> dict`
- `resolve_company_profile(lead_id: str, provider: str='auto', force: bool=False) -> dict[str, Any]`
- `resolve_contact(lead_id: str, provider: str='prospeo', force: bool=False) -> dict[str, Any]`
- `enrich_lead(lead_id: str, provider: str='hunter') -> dict`
- class `_FallbackDraft`
- `async preview_draft(lead_id: str) -> dict[str, Any]`
- `async build_draft(lead_id: str) -> dict`
- const `LINKEDIN_PIECES`
- const `LINKEDIN_KINDS`
- `async preview_linkedin_draft(lead_id: str, piece: str) -> dict[str, Any]`
- `async build_linkedin_draft(lead_id: str, piece: str) -> dict`
- `maybe_auto_contact_lead(lead_id: str, *, created: bool) -> dict | None`
- `verify_resend_webhook(payload: str, headers: dict[str, str]) -> dict`
- `ingest_resend_event(payload: dict) -> dict`
- class `ResendAmbiguousError`(RuntimeError) — The provider may or may not have accepted the message
- class `ResendIdempotencyConflictError`(RuntimeError) — The idempotency key was already used with a different payload
- `send_approved(draft_id: str) -> dict`
- `reconcile_sending_drafts() -> dict` — Recover drafts stranded in 'sending' after a crash or restart
- `ingest_inbound_email(payload: dict) -> dict`

### `services/service_prospecting.py`

- `search_service_contacts(*, keywords: list[str], buyer_titles: list[str], market: str | None, desired_contacts: int) -> dict[str, Any]` — Search providers once each, then save at most the requested contact previews

### `services/visual_bible.py`

- const `REQUIRED_SECTIONS`
- `default_bible(*, brand_name: str='InDataFlow', colors: list[str] | None=None, style: str='restrained blue and indigo, premium commercial cinematography') -> dict[str, Any]`
- `validate_bible(bible: dict[str, Any]) -> None`
- `adapt_bible(bible: dict[str, Any], brief_text: str) -> dict[str, Any]` — Adapt the default bible environment to the brief's domain
- `inherit_for_shot(bible: dict[str, Any], shot: dict[str, Any]) -> dict[str, str]` — Render the bible sections a shot prompt needs as short strings

### `services/worktrees.py`

- const `ROOT`
- const `WORKTREES`
- const `PATCHES`
- `run(cmd: str, cwd: str, timeout: int=120)`
- `create(repo: str, task_id: str) -> dict`
- `make_patch(worktree: str, task_id: str) -> str`
- `changed_files(worktree: str) -> list[str]`
- `discard(repo: str, task_id: str, branch: str) -> None`
- `apply_patch(repo: str, patch_path: str) -> dict`

## Video pipeline package

### `services/video/__init__.py`

- (no public module-level names)

### `services/video/defs.py`

- `invalid(errors: list[str]) -> None`
- const `HUNYUAN_DEFAULT_PROFILE`
- const `FORMAT_SIZES`
- const `DEFAULT_NEGATIVE_PROMPT`
- const `VISUAL_TYPES`
- const `RENDERER_FOR_TYPE`
- const `ROUTE_KEYWORDS`
- const `INFO_DISPLAY_CUES`
- const `MIXED_RENDERER_PRECEDENCE`

### `services/video/job_builder.py`

- `build_render_jobs(spec: dict[str, Any], plan: dict[str, Any], *, priority: int=100, render_mode: str='shots', bible: dict[str, Any] | None=None, recipe: dict[str, Any] | None=None) -> list[dict[str, Any]]` — Build RenderJob dicts (unsaved) in the requested render mode
- `validate_jobs(spec: dict[str, Any], plan: dict[str, Any], jobs: list[dict[str, Any]], *, render_mode: str='shots') -> None`

### `services/video/pipeline.py`

- class `CreativeBriefResponse`(BaseModel)
- class `StoryboardBeat`(BaseModel)
- class `StoryboardOutline`(BaseModel)
- `assign_durations(beats: list[StoryboardBeat], runtime_seconds: float) -> list[float]` — Split the runtime across beats proportional to narration weight
- `plan_video(script_path: str | Path, *, project_id: str, campaign_id: str | None=None, aspect_ratio: str='9:16', fps: int=24, use_ai: bool=True, extra_assets: list[dict[str, Any]] | None=None) -> dict[str, Any]` — Parse a script file, validate, plan and persist spec + shot plan
- `validate_storyboard_generatable(outline: StoryboardOutline) -> str | None` — Require at least one beat routable to the working renderer
- `direct_brief(brief: str, *, project_id: str, campaign_id: str | None=None, aspect_ratio: str='9:16', fps: int=24, runtime_seconds: int | None=None) -> dict[str, Any]` — Direct a video from a human creative brief (template-4 phase 20)
- `store_spec_payload(spec: dict[str, Any]) -> dict[str, Any]`
- `queue_shot_plan(plan_id: str, *, priority: int=100, render_mode: str='shots') -> dict[str, Any]` — Enqueue RenderJobs for a planned shot plan in the requested render mode
- `store_job_rows(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]`
- `job_counts(jobs: list[dict[str, Any]], plan: dict[str, Any] | None=None) -> dict[str, Any]`
- `hunyuan_profile() -> dict[str, Any]` — The default MI300X render profile (prompt.md section 9)
- `worker_env_example() -> dict[str, str]`
- `reference_asset(path: str | Path) -> dict[str, Any]` — Build a product-reference registry entry for a user-supplied file
- `launch(*, brief: str | None=None, script_path: str | Path | None=None, project_id: str, campaign_id: str | None=None, aspect_ratio: str='9:16', fps: int=24, references: list[str | Path] | None=None, submit: bool=True, timeout_seconds: int | None=None, render_mode: str='full', runtime_seconds: int | None=None) -> dict[str, Any]` — Run the product-launch pipeline end to end (motion-designer.md)

### `services/video/script_parser.py`

- const `TIMESTAMP_RE`
- const `BEAT_HEADER_RE`
- const `VISUAL_FIELD_RE`
- const `META_FIELD_RE`
- `parse_timestamp(value: str) -> float`
- `parse_beat_range(value: str) -> tuple[float, float]`
- `format_timestamp(seconds: float) -> str`
- `parse_script(text: str, source_name: str='script') -> dict[str, Any]` — Parse a prepared script into title, metadata and timed visual beats

### `services/video/shot_planner.py`

- `route_visual(beat_text: str, visual: dict[str, Any]) -> tuple[str, str, list[str]]` — Return (visual_type, renderer, matched_families) for one beat
- `primary_renderer(families: list[str]) -> str`
- `decide_hunyuan_mode(families: list[str], reference_assets: list[str]) -> str` — T2V/I2V decision policy: exact identity needs an image reference
- `select_reference_assets(assets: list[dict[str, Any]], families: list[str], visual: dict[str, Any]) -> list[str]` — Resolve registry assets relevant to one shot (deterministic)
- `compile_hunyuan_prompt(bible: dict[str, Any], recipe: dict[str, Any], shot: dict[str, Any]) -> tuple[str, str]` — Compile Subject + Motion + Scene + ShotType + Camera + Lighting + Style
- `plan_shots(spec: dict[str, Any], context: dict[str, Any] | None=None, use_ai: bool=True, bible: dict[str, Any] | None=None, recipe: dict[str, Any] | None=None) -> tuple[dict[str, Any], dict[str, Any]]` — Build an (unsaved) ShotPlan dict. Returns (plan, ai_report)
- `validate_plan(spec: dict[str, Any], plan: dict[str, Any]) -> None`
- `validate_claims(spec: dict[str, Any], plan: dict[str, Any], context: dict[str, Any] | None=None) -> None` — Enforce product-boundary and source-reference rules (prompt.md section 12)
- class `AIEnhancedShot`(BaseModel)
- class `AIPlanEnhancement`(BaseModel)

### `services/video/spec_builder.py`

- const `KNOWLEDGE_DIR`
- `load_indataflow_context() -> dict[str, Any]` — Load brand/product/CTA guardrails from the existing G1 knowledge files
- `forbidden_phrases(context: dict[str, Any]) -> list[str]`
- `forbidden_patterns(context: dict[str, Any]) -> list['re.Pattern[str]']`
- `build_spec(parsed: dict[str, Any], *, project_id: str, campaign_id: str | None=None, aspect_ratio: str='9:16', fps: int=24, source_path: str | None=None, context: dict[str, Any] | None=None) -> dict[str, Any]` — Build an (unsaved) VideoSpec dict from parsed script beats
- `validate_spec(spec: dict[str, Any]) -> None` — Raise ValueError unless the spec satisfies prompt.md section 12

## Agents

### `agents/__init__.py`

- (no public module-level names)

### `agents/coder.py`

- const `ROOT`
- const `WORKSPACE_CONFIG`
- const `CONVERSATIONS_DIR`
- const `REPAIR_CONVERSATIONS_DIR`
- const `CHAT_INDEX`
- const `TASKS_DIR`
- const `CHECKPOINTS_DIR`
- const `DEFAULT_MODEL`
- const `CONTEXT_COMPACT_AFTER`
- const `MAX_REPAIR_CYCLES`
- const `CATEGORY_MODEL_MAP`
- const `EXCLUDED_PREFIXES`
- const `EXCLUDED_NAMES`
- const `PROTECTED_REPAIR_PREFIXES`
- const `PROTECTED_REPAIR_NAMES`
- const `VALIDATION_FILE_RE`
- `now_iso() -> str`
- `load_workspaces() -> dict`
- `get_workspace(alias: str) -> dict`
- `load_chat_index() -> dict`
- `save_chat_index(data: dict) -> None`
- `create_chat(workspace_alias: str, name: str, default_model: str='auto', default_category: str='auto') -> dict`
- `get_chat(chat_id: str) -> dict`
- `update_chat(chat_id: str, **changes: Any) -> dict`
- `list_chats() -> list[dict]`
- `list_omniroute_models() -> list[str]`
- `search_omniroute_models(query: str) -> list[str]`
- `openhands_model_name(model_id: str) -> str`
- `classify_task(message: str) -> str`
- `resolve_category(chat: dict, message: str, override: str | None) -> str`
- `resolve_model(chat: dict, category: str, override: str | None) -> str`
- `build_coding_agent(model_id: str) -> Agent`
- `build_conversation(workspace_path: str, model_id: str, conversation_id: str, persistence_dir: Path) -> Conversation`
- `run_command(command: str, cwd: str, timeout: int=180) -> dict`
- `repo_files(repo: str) -> list[str]`
- `git_status(repo: str) -> str`
- `git_diff_stat_for_files(repo: str, files: list[str]) -> str`
- `git_diff_for_files(repo: str, files: list[str]) -> str`
- `sha256_file(path: Path) -> str | None`
- `snapshot_repo(repo: str) -> dict`
- `changed_since_snapshot(repo: str, before: dict) -> list[str]`
- `create_checkpoint(task_id: str, repo: str) -> dict`
- `finalize_checkpoint(task_id: str, repo: str, changed_files: list[str]) -> None`
- `task_file(task_id: str) -> Path`
- `undo_task(task_id: str) -> dict`
- `validation_commands(workspace: dict) -> list[str]`
- `run_validations(workspace: dict) -> list[dict]`
- `validation_passed(results: list[dict]) -> bool`
- `validation_failure_text(results: list[dict]) -> str`
- `validation_error_files(results: list[dict]) -> list[str]`
- `coding_system_context(chat: dict, task: str, category: str, model_id: str, compact_memory: str='') -> str`
- `repair_prompt(task_id: str, original_request: str, validation_results: list[dict], previous_changed_files: list[str], cycle: int) -> str`
- `recent_task_records(chat_id: str, limit: int=6) -> list[dict]`
- `build_compact_memory(chat: dict) -> str`
- `maybe_compact_chat(chat: dict) -> tuple[dict, str]`
- `restore_file_from_task_checkpoint(task_id: str, relative: str, repo: str) -> None`
- `send_coding_message(chat_id: str, message: str, *, category_override: str | None=None, model_override: str | None=None) -> dict`
- `get_task(task_id: str) -> dict`
- `get_last_task(chat_id: str) -> dict | None`

### `agents/coding_orchestrator.py`

- const `ROOT`
- const `WORKSPACE_CONFIG`
- const `CONVERSATIONS`
- const `MODEL_MAP`
- `now_iso()`
- `load_workspace(alias: str) -> dict`
- `validations(workspace: dict, cwd: str) -> list[dict]`
- `architect_plan(task: str, repo_map: dict, incident: dict | None=None) -> dict`
- `editor_prompt(task: str, plan: dict, repo_map: dict, repair: bool=False) -> str`
- `run_editor(worktree: str, task_id: str, task: str, plan: dict, repo_map: dict, model: str, repair=False)`
- `execute_task(workspace_alias: str, request: str, *, source: str='founder', incident: dict | None=None, model_override: str | None=None) -> dict`
- `apply_task(task_id: str) -> dict`

### `agents/founder.py`

- const `PROMPT`
- class `FounderDecision`(BaseModel)
- `async run_founder(message: str)`

### `agents/growth.py`

- class `CampaignBrief`(BaseModel)
- const `PROMPT`
- `async prepare_campaign_brief(request: str, brand: str | None=None) -> CampaignBrief`

### `agents/linkedin.py`

- class `LinkedInInvite`(BaseModel)
- class `LinkedInDM`(BaseModel)
- const `PIECES`
- `async draft_linkedin_outreach(lead: dict, piece: str) -> LinkedInInvite | LinkedInDM`

### `agents/researcher.py`

- const `PROMPT`
- class `Source`(BaseModel)
- class `ResearchReport`(BaseModel)
- class `SearchPlan`(BaseModel) — Planner output: bounded fan-out of focused queries (cheap fast model)
- `async plan_queries(question: str) -> list[str]` — Stage 1 (planner): cheap fast-model query fan-out
- `async gather_evidence(queries: list[str], max_pages: int=8) -> list[dict]` — Stage 2 (reader/verifier): no-LLM fetch + verify. Latency tail lives here
- `async web_search(query: str) -> list[dict]` [research_agent.tool_plain] — Search the public web
- `async read_web_page(url: str) -> dict` [research_agent.tool_plain] — Read a source discovered during web research
- `async run_research(question: str) -> ResearchReport` — Orchestrates planner -> reader/verifier -> synthesizer
- `async synthesize_report(question: str, evidence: list[dict]) -> ResearchReport` — Stage 3 (synthesizer): reasoning model over gathered evidence, no tools

### `agents/sales.py`

- class `OutreachDraft`(BaseModel)
- class `SalesCommand`(BaseModel)
- const `COMPANY_NAME`
- const `COMPANY_DESCRIPTION`
- `async draft_outreach(lead: dict) -> OutreachDraft`
- `async prepare_sales_command(request: str) -> SalesCommand`

## HTTP surface

### `app/__init__.py`

- (no public module-level names)

### `app/api.py`

- `home(request: Request)`
- `operations(request: Request)`
- `operations_sales(request: Request)`
- `operations_sales_email(request: Request)`
- `operations_marketing(request: Request)`
- `operations_marketing_assets(request: Request)`
- `modern_operations(request: Request)`
- `modern_outreach(request: Request)`
- `modern_campaigns(request: Request)`
- `modern_content(request: Request)`
- `operations_marketing_publishing(request: Request)`
- `operations_history(request: Request)`
- `async meet(request: Request)`
- `async calendar_page(request: Request)`
- `async health()`
- `ui_app(request: Request)`
- `missing_page(path: str, request: Request)`

### `app/companies_api.py`

- class `CompanyContact`(BaseModel)
- class `CompanySummary`(BaseModel)
- class `CompanyMetrics`(BaseModel)
- class `CompaniesPage`(BaseModel)
- class `CompanyDetail`(CompanySummary)
- `companies(page: int=Query(default=1, ge=1), page_size: int=Query(default=10, ge=1, le=100), q: str=Query(default='', max_length=200), industry: str=Query(default='', max_length=100), country: str=Query(default='', max_length=100), view: CompanyView='all', sort: CompanySort='recent')` [router.get('', response_model=CompaniesPage)]
- `company(company_id: str)` [router.get('/{company_id:path}', response_model=CompanyDetail)]

### `app/company_ops_api.py`

- class `CodingTaskRequest`(BaseModel)
- class `IncidentRecord`(BaseModel)
- class `IncidentsView`(BaseModel)
- `create_coding_task(body: CodingTaskRequest)` [router.post('/coding/tasks', dependencies=[Depends(verify_founder_action)])]
- `coding_tasks(limit: int=30)` [router.get('/coding/tasks')]
- `coding_task(task_id: str)` [router.get('/coding/tasks/{task_id}')]
- `coding_apply(task_id: str)` [router.post('/coding/tasks/{task_id}/apply', dependencies=[Depends(verify_founder_action)])]
- `incidents(limit: int=30)` [router.get('/incidents', response_model=IncidentsView)]
- `incident(incident_id: str)` [router.get('/incidents/{incident_id}')]
- `monitor_all()` [router.post('/monitor/run', dependencies=[Depends(verify_founder_action)])]
- `monitor_service(service: str)` [router.post('/monitor/run/{service}', dependencies=[Depends(verify_founder_action)])]
- `operations_overview()` [router.get('/operations/overview')]

### `app/contacts_api.py`

- class `ContactProfile`(BaseModel)
- class `Contact`(BaseModel)
- class `ContactMetrics`(BaseModel)
- class `ContactsPage`(BaseModel)
- class `CompanyProfile`(BaseModel)
- class `DraftSummary`(BaseModel)
- class `InteractionSummary`(BaseModel)
- class `EventSummary`(BaseModel)
- class `ContactDetail`(Contact)
- `contacts(page: int=Query(default=1, ge=1), page_size: int=Query(default=10, ge=1, le=100), stage: Stage | None=None, q: str=Query(default='', max_length=200), sort: Sort='recent')` [router.get('', response_model=ContactsPage)]
- `contact(contact_id: str)` [router.get('/{contact_id}', response_model=ContactDetail)]

### `app/marketing_api.py`

- const `ROOT`
- class `CampaignLaunchRequest`(BaseModel)
- class `ManualPostSessionRequest`(BaseModel)
- class `AssetPackRequest`(BaseModel)
- class `BufferScheduleRequest`(BaseModel)
- class `BufferAccountInfo`(BaseModel)
- class `BufferAccountsView`(BaseModel)
- class `BufferMetric`(BaseModel)
- class `BufferInsightsView`(BaseModel)
- class `AssetPackActionRecord`(BaseModel)
- class `AssetPackCreateResult`(BaseModel)
- class `CampaignActionRecord`(BaseModel)
- class `CampaignCreateResult`(BaseModel)
- class `CampaignTransitionResult`(BaseModel)
- class `MarketingOrgActionRecord`(BaseModel)
- class `MarketingOrgCreateResult`(BaseModel)
- class `MarketingOrgActiveResult`(BaseModel)
- class `OrgCapabilitiesResult`(BaseModel)
- class `ManualPostActionRecord`(BaseModel)
- class `ManualPostCreateResult`(BaseModel)
- class `BufferScheduleResult`(BaseModel)
- const `BUFFER_ACCOUNT_RE`
- const `MAX_BUFFER_ACCOUNTS`
- const `PROJECTS_ROOT`
- const `MAX_ARTIFACT_BYTES`
- const `VOICE_UPLOAD_EXTENSIONS`
- `doctor()` [router.get('/doctor')]
- `list_asset_packs(*, project_slug: str, limit: int=20) -> list[dict[str, Any]]`
- `create_asset_pack(payload: AssetPackRequest)` [router.post('/asset-packs', response_model=AssetPackCreateResult)]
- `asset_packs(limit: int=20)` [router.get('/asset-packs')]
- `asset_pack_file(pack_id: str, relative_path: str)` [router.get('/asset-packs/{pack_id}/files/{relative_path:path}')]
- `create_manual_post_session(payload: ManualPostSessionRequest)` [router.post('/manual-posts/session')]
- `async upload_manual_post_asset(post_record_id: str, asset: UploadFile=File(...))` [router.post('/manual-posts/{post_record_id}/assets')]
- `finalize_manual_post(post_record_id: str)` [router.post('/manual-posts/{post_record_id}/finalize')]
- `async create_manual_post_from_ui(platform: str=Form(...), post_type: str=Form(default='carousel'), destination_url: str | None=Form(default=None), link_label: str | None=Form(default=None), org_id: int | None=Form(default=None), assets: list[UploadFile]=File(default=[]))` [router.post('/manual-posts', response_model=ManualPostCreateResult)]
- `buffer_accounts()` [router.get('/buffer-accounts', response_model=BufferAccountsView)] — Named Buffer accounts configured in g3.env (keys never leave the server)
- `manual_post_buffer_insights(post_record_id: str, post_id: str | None=None)` [router.get('/manual-posts/{post_record_id}/buffer-insights', response_model=BufferInsightsView)] — Read one saved Buffer post's provider state and optional personal-key metrics
- `create_manual_post_buffer_draft(post_record_id: str, buffer_account: str | None=None)` [router.post('/manual-posts/{post_record_id}/buffer-draft')]
- `schedule_manual_post_buffer(post_record_id: str, payload: BufferScheduleRequest, buffer_account: str | None=None)` [router.post('/manual-posts/{post_record_id}/buffer-schedule', response_model=BufferScheduleResult, dependencies=[Depends(verify_founder_action)])]
- `marketing_orgs()` [router.get('/orgs')]
- class `MarketingOrgCreateRequest`(BaseModel)
- `create_marketing_org(payload: MarketingOrgCreateRequest)` [router.post('/orgs', response_model=MarketingOrgCreateResult)]
- class `OrgCapabilitiesRequest`(BaseModel)
- `get_org_capabilities_route(org_id: int)` [router.get('/orgs/{org_id}/capabilities')]
- `set_org_capabilities_route(org_id: int, payload: OrgCapabilitiesRequest)` [router.post('/orgs/{org_id}/capabilities', response_model=OrgCapabilitiesResult)]
- `set_active(payload: ManualPostOrgRequest)` [router.post('/orgs/active', response_model=MarketingOrgActiveResult)]
- class `ManualPostOrgRequest`(BaseModel)
- `assign_manual_post_org(post_record_id: str, payload: ManualPostOrgRequest)` [router.post('/manual-posts/{post_record_id}/org')]
- const `AI_CAPTION_MAX_SLIDES`
- const `AI_CAPTION_MAX_DIM`
- `generate_manual_post_ai_caption(post_record_id: str)` [router.post('/manual-posts/{post_record_id}/ai-caption')]
- `manual_posts(limit: int=50)` [router.get('/manual-posts')]
- `manual_post_asset(post_record_id: str, asset_index: int)` [router.get('/manual-posts/{post_record_id}/assets/{asset_index}')]
- `create_campaign_from_ui(payload: CampaignLaunchRequest)` [router.post('/campaigns', response_model=CampaignCreateResult)]
- `campaigns(limit: int=20)` [router.get('/campaigns')]
- `campaign(campaign_id: str)` [router.get('/campaigns/{campaign_id}')]
- `campaign_voice_handoff(campaign_id: str)` [router.get('/campaigns/{campaign_id}/voice-handoff')]
- `async upload_campaign_voice_recording(campaign_id: str, recording: UploadFile=File(...))` [router.post('/campaigns/{campaign_id}/voice-recording')]
- `variant_video(campaign_id: str, variant_id: str)` [router.get('/campaigns/{campaign_id}/variants/{variant_id}/video')]
- `select_variant(campaign_id: str, variant_id: str)` [router.post('/campaigns/{campaign_id}/variants/{variant_id}/select', dependencies=[Depends(verify_founder_action)])]
- `create_drafts(campaign_id: str)` [router.post('/campaigns/{campaign_id}/drafts', dependencies=[Depends(verify_founder_action)])]
- `approve_script(campaign_id: str)` [router.post('/campaigns/{campaign_id}/approve-script', response_model=CampaignTransitionResult, dependencies=[Depends(verify_founder_action)])]
- `regenerate_script(campaign_id: str, payload: dict=Body(default={}))` [router.post('/campaigns/{campaign_id}/regenerate-script', dependencies=[Depends(verify_founder_action)])]
- `retry_campaign(campaign_id: str)` [router.post('/campaigns/{campaign_id}/retry', response_model=CampaignTransitionResult, dependencies=[Depends(verify_founder_action)])]

### `app/onboarding_api.py`

- class `CompanyStart`(BaseModel)
- class `CompanyContext`(BaseModel)
- class `Icp`(BaseModel)
- class `StrategyInput`(BaseModel)
- class `AiIcp`(Icp)
- class `AiStrategyDraft`(StrategyInput) — Require a complete model draft; the founder may then edit the suggestions
- class `ApprovalPolicy`(BaseModel)
- class `ProviderLimits`(BaseModel)
- class `Feedback`(BaseModel)
- class `FeedbackEntry`(Feedback)
- class `CalibrationInput`(BaseModel)
- class `RefinementProposal`(BaseModel)
- class `RefinementDecision`(BaseModel)
- class `BuyerRequest`(BaseModel)
- class `DraftRequest`(BaseModel)
- class `ProgramState`(BaseModel)
- class `CalibrationCandidate`(BaseModel)
- class `OnboardingView`(BaseModel)
- `onboarding_view()` [read_router.get('/onboarding', response_model=OnboardingView)]
- `start_company(payload: CompanyStart)` [write_router.post('/company', response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])]
- `research_company()` [write_router.post('/research-company', response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])]
- `confirm_company(payload: CompanyContext)` [write_router.post('/company/confirm', response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])]
- `async suggest_strategy()` [write_router.post('/strategy/draft', response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])]
- `confirm_strategy(payload: StrategyInput)` [write_router.post('/strategy', response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])]
- `first_search()` [write_router.post('/search', response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])]
- `record_calibration(payload: CalibrationInput)` [write_router.post('/calibration', response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])]
- `decide_refinement(payload: RefinementDecision)` [write_router.post('/refinement', response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])]
- `resolve_buyer(payload: BuyerRequest)` [write_router.post('/buyer', response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])]
- `async create_first_draft(payload: DraftRequest)` [write_router.post('/draft', response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])]
- `activate_program()` [write_router.post('/activate', response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])]

### `app/ratelimit.py`

- const `WINDOW_SECONDS`
- const `WEBHOOK_PATHS`
- `reset() -> None` — Drop all recorded hits (tests)
- `enabled() -> bool`
- `client_ip(request: Request) -> str`
- `rate_limit_intake(request: Request) -> None` — Router dependency for /integrations routes: webhooks and form intake
- `check_auth_failure(request: Request) -> None` — Count failed dashboard sign-ins per IP (separate bucket, counts only

### `app/sales_api.py`

- class `LeadIntake`(BaseModel)
- class `MeetingMetadata`(BaseModel)
- class `SalesMetadata`(BaseModel)
- class `SalesLeadRecord`(BaseModel) — Stable fields consumed by React; extra persisted sales facts pass through
- class `SalesDraftRecord`(BaseModel)
- class `LeadCreateResult`(BaseModel)
- class `ProspectResult`(BaseModel)
- class `ProspectActionResult`(BaseModel)
- class `ResearchActionResult`(BaseModel)
- class `CompanyProfileRecord`(BaseModel)
- class `CompanyResolutionResult`(BaseModel)
- class `SendActionResult`(BaseModel)
- class `MeetingActionResult`(BaseModel)
- class `ProspectRequest`(BaseModel)
- class `LeadResearchRequest`(BaseModel)
- class `LeadResearchSuggestionsRequest`(BaseModel)
- class `DraftUpdatePayload`(BaseModel)
- class `MeetingScheduledPayload`(BaseModel)
- class `InboundEmailPayload`(BaseModel)
- class `TallyWebhookPayload`(BaseModel)
- `verify_founder_action(x_founder_action_token: str | None=Header(default=None)) -> None`
- `website_intake(payload: LeadIntake, x_company_core_lead_secret: str | None=Header(default=None, alias='X-Company-Core-Lead-Secret'))` [intake_router.post('/leads/website')]
- `async tally_intake(request: Request, x_company_core_lead_secret: str | None=Header(default=None, alias='X-Company-Core-Lead-Secret'), tally_signature: str | None=Header(default=None))` [intake_router.post('/leads/tally')]
- `inbound_email(payload: InboundEmailPayload, x_sales_email_webhook_secret: str | None=Header(default=None))` [intake_router.post('/email/sales')]
- `async resend_sales_webhook(request: Request)` [intake_router.post('/resend/sales')]
- `doctor()` [router.get('/doctor')]
- `leads(limit: int=50, stage: str | None=None)` [router.get('/leads')]
- `lead(lead_id: str)` [router.get('/leads/{lead_id}')]
- `manual_lead(payload: LeadIntake)` [action_router.post('/leads', response_model=LeadCreateResult, dependencies=[Depends(verify_founder_action)])]
- `prospect_domain(payload: ProspectRequest)` [action_router.post('/prospect/domain', response_model=ProspectActionResult, dependencies=[Depends(verify_founder_action)])]
- `research_suggestions(payload: LeadResearchSuggestionsRequest)` [action_router.post('/research/suggestions', dependencies=[Depends(verify_founder_action)])]
- `research_leads(payload: LeadResearchRequest)` [action_router.post('/research/leads', response_model=ResearchActionResult, dependencies=[Depends(verify_founder_action)])]
- `resolve_lead_company(lead_id: str, provider: str='auto', force: bool=False)` [action_router.post('/leads/{lead_id}/resolve-company', response_model=CompanyResolutionResult, dependencies=[Depends(verify_founder_action)])]
- `resolve_lead_contact(lead_id: str, provider: str='prospeo', force: bool=False)` [action_router.post('/leads/{lead_id}/resolve-contact', dependencies=[Depends(verify_founder_action)])]
- `enrich(lead_id: str, provider: str='hunter')` [action_router.post('/leads/{lead_id}/enrich', dependencies=[Depends(verify_founder_action)])]
- `async draft_preview(lead_id: str)` [action_router.post('/leads/{lead_id}/draft-preview', dependencies=[Depends(verify_founder_action)])]
- `async draft(lead_id: str)` [action_router.post('/leads/{lead_id}/draft', response_model=SalesDraftRecord, dependencies=[Depends(verify_founder_action)])]
- `discover_lead_linkedin(lead_id: str, provider: str='auto', force: bool=False)` [action_router.post('/leads/{lead_id}/discover-linkedin', dependencies=[Depends(verify_founder_action)])]
- `async linkedin_draft_preview(lead_id: str, piece: str='invite')` [action_router.post('/leads/{lead_id}/linkedin-preview', dependencies=[Depends(verify_founder_action)])]
- `async linkedin_draft(lead_id: str, piece: str='invite')` [action_router.post('/leads/{lead_id}/linkedin-draft', dependencies=[Depends(verify_founder_action)])]
- `update_saved_draft(draft_id: str, payload: DraftUpdatePayload)` [action_router.post('/drafts/{draft_id}/update', response_model=SalesDraftRecord, dependencies=[Depends(verify_founder_action)])]
- `approve(draft_id: str)` [action_router.post('/drafts/{draft_id}/approve', response_model=SalesDraftRecord, dependencies=[Depends(verify_founder_action)])]
- `send(draft_id: str)` [action_router.post('/drafts/{draft_id}/send', response_model=SendActionResult, dependencies=[Depends(verify_founder_action)])]
- class `SendReconcilePayload`(BaseModel)
- `list_reconcile_drafts()` [router.get('/drafts/reconcile')] — Drafts whose send outcome is unknown and need an operator decision
- `reconcile_draft(draft_id: str, payload: SendReconcilePayload)` [action_router.post('/drafts/{draft_id}/reconcile', dependencies=[Depends(verify_founder_action)])]
- `schedule_meeting(lead_id: str, payload: MeetingScheduledPayload)` [action_router.post('/leads/{lead_id}/schedule-meeting', response_model=MeetingActionResult, dependencies=[Depends(verify_founder_action)])]
- `suppress(lead_id: str, reason: str='founder_request')` [action_router.post('/leads/{lead_id}/suppress', dependencies=[Depends(verify_founder_action)])]
- `hunter_account()` [router.get('/hunter/account')]

### `app/security.py`

- `authenticate(request: Request, credentials: HTTPBasicCredentials=Depends(security)) -> str`

### `app/service_discovery_api.py`

- class `ServiceInput`(BaseModel)
- class `ServiceSearchPlan`(BaseModel)
- class `ServiceTargetEdit`(BaseModel)
- class `ServiceRun`(BaseModel)
- class `ServiceContact`(BaseModel)
- class `ServiceRunView`(ServiceRun)
- class `ServiceDiscoveryView`(BaseModel)
- `service_discovery()` [read_router.get('/service-discovery', response_model=ServiceDiscoveryView)]
- `async start_service_search(payload: ServiceInput)` [write_router.post('/search', response_model=ServiceDiscoveryView, dependencies=[Depends(verify_founder_action)])]
- `retarget_service_search(run_id: str, payload: ServiceTargetEdit)` [write_router.post('/{run_id}/search', response_model=ServiceDiscoveryView, dependencies=[Depends(verify_founder_action)])]

### `app/setup_api.py`

- `setup_providers()` [router.get('/providers')]
- class `SetupKeysPayload`(BaseModel)
- class `SetupKeyTestResult`(BaseModel)
- class `SetupKeySaveResult`(BaseModel)
- `test_setup_keys(payload: SetupKeysPayload, _: None=Depends(verify_founder_action))` [router.post('/keys/test', response_model=SetupKeyTestResult)]
- `save_setup_keys(payload: SetupKeysPayload, _: None=Depends(verify_founder_action))` [router.post('/keys', response_model=SetupKeySaveResult)]
- `get_setup_step_route()` [router.get('/step')]
- class `SetupStepPayload`(BaseModel)
- `set_setup_step_route(payload: SetupStepPayload, _: None=Depends(verify_founder_action))` [router.post('/step')]

### `app/video_api.py`

- class `SpecCreate`(BaseModel)
- class `PlanCreate`(BaseModel)
- class `JobComplete`(BaseModel)
- class `JobFail`(BaseModel)
- `list_specs(limit: int=Query(default=50, ge=1, le=200)) -> dict[str, Any]` [router.get('/specs')]
- `read_spec(spec_id: str) -> dict[str, Any]` [router.get('/specs/{spec_id}')]
- `list_plans(spec_id: str | None=None) -> dict[str, Any]` [router.get('/plans')]
- `read_plan(plan_id: str) -> dict[str, Any]` [router.get('/plans/{plan_id}')]
- `list_render_jobs(shot_plan_id: str | None=None, status: str | None=None, renderer: str | None=None) -> dict[str, Any]` [router.get('/jobs')]
- `read_job(job_id: str) -> dict[str, Any]` [router.get('/jobs/{job_id}')]
- `read_queue_stats() -> dict[str, Any]` [router.get('/queue/stats')]
- `read_hunyuan_profile() -> dict[str, Any]` [router.get('/hunyuan/profile')]
- `create_spec(payload: SpecCreate) -> dict[str, Any]` [action_router.post('/specs', dependencies=[Depends(verify_founder_action)])]
- `create_plan(payload: PlanCreate) -> dict[str, Any]` [action_router.post('/plans', dependencies=[Depends(verify_founder_action)])]
- `queue_plan(plan_id: str, render_mode: str=Query(default='shots', max_length=16)) -> dict[str, Any]` [action_router.post('/plans/{plan_id}/queue', dependencies=[Depends(verify_founder_action)])]
- `retry_render_job(job_id: str) -> dict[str, Any]` [action_router.post('/jobs/{job_id}/retry', dependencies=[Depends(verify_founder_action)])]
- `cancel_render_job(job_id: str) -> dict[str, Any]` [action_router.post('/jobs/{job_id}/cancel', dependencies=[Depends(verify_founder_action)])]
- `lease_next_render_job(worker_id: str=Query(min_length=1, max_length=120), renderer: str | None=Query(default=None, max_length=32)) -> dict[str, Any]` [worker_router.get('/render-jobs/next')]
- `heartbeat_render_job(job_id: str, worker_id: str=Query(min_length=1, max_length=120)) -> dict[str, Any]` [worker_router.post('/render-jobs/{job_id}/heartbeat')]
- `complete_render_job(job_id: str, payload: JobComplete, worker_id: str=Query(min_length=1, max_length=120)) -> dict[str, Any]` [worker_router.post('/render-jobs/{job_id}/complete')]
- `fail_render_job(job_id: str, payload: JobFail, worker_id: str=Query(min_length=1, max_length=120)) -> dict[str, Any]` [worker_router.post('/render-jobs/{job_id}/fail')]

### `app/workflow_views_api.py`

- class `ReplyItem`(BaseModel)
- class `RepliesPage`(BaseModel)
- `replies_view(page: int=Query(1, ge=1), page_size: int=Query(10, ge=1, le=50), q: str=Query('', max_length=200), view: Literal['all', 'latest', 'suppressed']='all', sort: Literal['recent', 'oldest', 'company']='recent')` [router.get('/replies', response_model=RepliesPage)]
- `reply_detail(reply_id: int)` [router.get('/replies/{reply_id}', response_model=ReplyItem)]
- class `MeetingMarker`(BaseModel)
- class `MeetingsPage`(BaseModel)
- `meetings_view(page: int=Query(1, ge=1), page_size: int=Query(10, ge=1, le=50), q: str=Query('', max_length=200), view: Literal['all', 'dated', 'undated']='all', sort: Literal['recent', 'oldest', 'company']='recent')` [router.get('/meetings', response_model=MeetingsPage)]
- `meeting_detail(lead_id: str)` [router.get('/meetings/{lead_id}', response_model=MeetingMarker)]
- class `OutreachItem`(BaseModel)
- class `OutreachPage`(BaseModel)
- `outreach_view(page: int=Query(1, ge=1), page_size: int=Query(10, ge=1, le=50), q: str=Query('', max_length=200), status: str=Query('', max_length=40), sort: Literal['recent', 'oldest', 'company']='recent')` [router.get('/outreach', response_model=OutreachPage)]
- `outreach_detail(draft_id: str)` [router.get('/outreach/{draft_id}', response_model=OutreachItem)]
- class `CampaignItem`(BaseModel)
- class `CampaignVariant`(BaseModel)
- class `CampaignDetail`(CampaignItem)
- class `CampaignsPage`(BaseModel)
- `campaigns_view(page: int=Query(1, ge=1), page_size: int=Query(10, ge=1, le=50), q: str=Query('', max_length=200), status: str=Query('', max_length=40), org_id: int | None=Query(None, ge=1), sort: Literal['recent', 'oldest', 'name']='recent')` [router.get('/campaigns', response_model=CampaignsPage)]
- `campaign_detail(campaign_id: str)` [router.get('/campaigns/{campaign_id}', response_model=CampaignDetail)]
- class `ContentItem`(BaseModel)
- class `ContentView`(BaseModel)
- `content_view()` [router.get('/content', response_model=ContentView)]
- class `RecentContact`(BaseModel)
- class `HomeView`(BaseModel)
- `home_view()` [router.get('/home', response_model=HomeView)]

### `app/workspace_api.py`

- class `SessionStatus`(BaseModel)
- `session_status()` [router.get('/session', response_model=SessionStatus)] — Validate dashboard Basic credentials without reading a product domain
- const `GROUP_CATEGORIES`
- const `GROUP_CAPABILITIES`
- class `ProviderGroup`(BaseModel)
- class `IntegrationsView`(BaseModel)
- `integrations_view()` [router.get('/integrations', response_model=IntegrationsView)]
- class `WorkspaceOrg`(BaseModel)
- class `PublicLink`(BaseModel)
- class `SettingsView`(BaseModel)
- `settings_view()` [router.get('/settings', response_model=SettingsView)]

## Operations scripts

### `scripts/backup.py`

- const `PLAIN_DIRS`
- const `PLAIN_FILES`
- `make_backup(root: Path, out_dir: Path) -> Path`
- `main(argv: list[str] | None=None) -> int`

### `scripts/backup_lib.py`

- const `FORMAT`
- const `MANIFEST_NAME`
- const `DB_SUFFIXES`
- const `DB_SIDECAR_SUFFIXES`
- const `PLAIN_PATTERNS`
- const `REPORT_TABLES`
- `sha256_file(path: Path) -> str`
- `discover_databases(root: Path) -> list[Path]`
- `sqlite_snapshot(src: Path, dst: Path) -> None`
- `database_info(path: Path, rel: str) -> dict`
- `build_manifest(staging: Path, db_rels: list[str]) -> dict`
- `extract_archive(archive_path: Path, dest: Path) -> None`
- `load_manifest(archive_dir: Path) -> dict`
- `verify_extracted(archive_dir: Path) -> list[str]` — Open the extracted archive and assert schema and row counts
- `report_counts(archive_dir: Path) -> list[str]` — Human-readable row counts for the key tables
- `copy_into_target(source: Path, target: Path) -> int` — Merge an extracted archive into a target root. Returns file count
- `make_archive(staging: Path, archive_path: Path) -> None`
- `workdir(prefix: str) -> Path`

### `scripts/doctor.py`

- const `ROOT`
- `configured(name: str) -> bool`
- `main() -> int`

### `scripts/export_openapi.py`

- const `ROOT`

### `scripts/gen_api_reference.py`

- const `ROOT`
- const `GROUPS`
- const `SKIP_DIR_PARTS`
- const `ROUTE_DECORATORS`
- const `CLI_SUBCOMMANDS`
- `build() -> str`
- `main() -> int`

### `scripts/generate_system_architecture_excalidraw.py`

- const `ROOT`
- const `OUTPUT`
- `ident(prefix: str) -> str`
- `common(kind: str, x: float, y: float, w: float, h: float, *, stroke: str, fill: str) -> dict`
- `label(value: str, x: float, y: float, *, size: int=20, color: str='#e2e8f0', bold: bool=False) -> None`
- `box(x: float, y: float, w: float, h: float, title: str, detail: str, *, fill: str, stroke: str) -> None`
- `arrow(x1: float, y1: float, x2: float, y2: float, *, color: str='#6ea8db', via: list[tuple[float, float]] | None=None) -> None`
- const `COLORS`
- `node(col: str, y: int, h: int, title: str, detail: str, tone: str) -> None`

### `scripts/generate_v2_infrastructure_excalidraw.py`

- const `OUT`
- const `FONT`
- const `PAD`
- const `GAP`
- const `LANE_X`
- const `LANE_W`
- const `INNER_X`
- const `LANE_RIGHT`
- const `BOX`
- `make_box(x, y, w, paragraphs, *, stroke='#1e1e1e', bg='#ffffff', key=None)`
- `lane(name, y, rows, *, start_x=INNER_X, gap_top=52)` — rows: list of rows; each row is a list of (width, paragraphs, kwargs)
- `anchor(key, side)`
- `arrow(start, end, *, label=None, dashed=False, color='#1e1e1e', elbow=None, points=None, label_at=None)`
- `free_text(x, y, w, paragraphs, *, color='#1e1e1e', size=16, center=False)`

### `scripts/restore.py`

- const `DEFAULT_LIVE_PATTERN`
- `verify(args: argparse.Namespace) -> int`
- `apply(args: argparse.Namespace) -> int`
- `main(argv: list[str] | None=None) -> int`

### `scripts/smoke_actions.py`

- const `REPO`
- const `GATED_ROUTES`
- const `TOKEN_FALLS_THROUGH`
- class `Runner`
  - `http(self, method: str, path: str, *, body=None, auth: str | None='dash', token: bool=False, timeout: float=15.0)`
  - `header_value(self, headers: dict, name: str) -> str | None` — Case-insensitive header lookup (uvicorn delivers `retry-after`)
  - `health(self, timeout: float=3.0) -> bool`
  - `record(self, name: str, status: str, expected: str, got: str, note: str='') -> None`
  - `check(self, name: str, expected: str, fn, *, needs_token: bool=False)` — Run fn() -> (ok: bool, got: str, optional note); exceptions become FAIL
  - `skip(self, name: str, expected: str, reason: str) -> None`
  - `seed_send_unknown(self, tag: str) -> tuple[str, str]`
  - `seed_stranded_sending(self, tag: str) -> tuple[str, str]`
  - `seed_draft(self, tag: str) -> tuple[str, str]`
  - `cleanup(self) -> None`
  - `ensure_server(self) -> None`
  - `stop_server(self) -> None`
  - `run_checks(self) -> None`
  - `reconcile_checks(self) -> None`
  - `resume_park_check(self) -> None`
  - `backup_check(self)`
  - `webhook_budget_check(self)`
  - `intake_burst_check(self)`
  - `auth_burst_check(self)`
  - `startup_reconcile_check(self) -> None` — Phase 1, while the server is alive: GET the seeded lead and confirm
  - `startup_reconcile_log_check(self) -> None` — Phase 2, after the child is reaped so its stdout can be read
  - `lead_total(self) -> int`
  - `summarize(self) -> dict[str, int]`
  - `print_table(self) -> None`
  - `write_report(self, path: Path) -> None`
- `basic(value: str) -> str`
- `port_of(url: str) -> int`
- `load_dotenv_file(path: Path) -> None`
- `env_value(key: str) -> str`
- `main(argv: list[str] | None=None) -> int`

### `scripts/verify_backup.py`

- `verify_archive(archive_path: Path) -> tuple[list[str], list[str]]`
- `main(argv: list[str] | None=None) -> int`

### `scripts/video.py`

- const `REPO`
- `command_plan(args: argparse.Namespace) -> int`
- `command_queue(args: argparse.Namespace) -> int`
- `command_profile(_args: argparse.Namespace) -> int`
- `command_submit(args: argparse.Namespace) -> int`
- `command_worker_status(_args: argparse.Namespace) -> int`
- `command_launch(args: argparse.Namespace) -> int`
- `command_direct(args: argparse.Namespace) -> int`
- `main(argv: list[str] | None=None) -> int`

## HTTP routes

| route | module |
|---|---|
| `GET /` | `app/api.py` |
| `GET /asset-packs/{pack_id}/files/{relative_path:path}` | `app/marketing_api.py` |
| `GET /asset-packs` | `app/marketing_api.py` |
| `GET /buffer-accounts` | `app/marketing_api.py` |
| `GET /calendar` | `app/api.py` |
| `GET /campaigns/` | `app/api.py` |
| `GET /campaigns/{campaign_id}/variants/{variant_id}/video` | `app/marketing_api.py` |
| `GET /campaigns/{campaign_id}/voice-handoff` | `app/marketing_api.py` |
| `GET /campaigns/{campaign_id}` | `app/marketing_api.py` |
| `GET /campaigns/{campaign_id}` | `app/workflow_views_api.py` |
| `GET /campaigns` | `app/api.py` |
| `GET /campaigns` | `app/marketing_api.py` |
| `GET /campaigns` | `app/workflow_views_api.py` |
| `GET /coding/tasks/{task_id}` | `app/company_ops_api.py` |
| `GET /coding/tasks` | `app/company_ops_api.py` |
| `GET /companies/` | `app/api.py` |
| `GET /companies` | `app/api.py` |
| `GET /contacts/` | `app/api.py` |
| `GET /contacts` | `app/api.py` |
| `GET /content/` | `app/api.py` |
| `GET /content` | `app/api.py` |
| `GET /content` | `app/workflow_views_api.py` |
| `GET /doctor` | `app/marketing_api.py` |
| `GET /doctor` | `app/sales_api.py` |
| `GET /drafts/reconcile` | `app/sales_api.py` |
| `GET /health` | `app/api.py` |
| `GET /home/` | `app/api.py` |
| `GET /home` | `app/api.py` |
| `GET /home` | `app/workflow_views_api.py` |
| `GET /hunter/account` | `app/sales_api.py` |
| `GET /hunyuan/profile` | `app/video_api.py` |
| `GET /incidents/{incident_id}` | `app/company_ops_api.py` |
| `GET /incidents` | `app/company_ops_api.py` |
| `GET /integrations/` | `app/api.py` |
| `GET /integrations` | `app/api.py` |
| `GET /integrations` | `app/workspace_api.py` |
| `GET /jobs/{job_id}` | `app/video_api.py` |
| `GET /jobs` | `app/video_api.py` |
| `GET /leads/{lead_id}` | `app/sales_api.py` |
| `GET /leads` | `app/sales_api.py` |
| `GET /legacy/operations/marketing/assets` | `app/api.py` |
| `GET /legacy/operations/marketing/campaigns` | `app/api.py` |
| `GET /legacy/operations/marketing` | `app/api.py` |
| `GET /legacy/operations/sales/email` | `app/api.py` |
| `GET /legacy/operations` | `app/api.py` |
| `GET /manual-posts/{post_record_id}/assets/{asset_index}` | `app/marketing_api.py` |
| `GET /manual-posts/{post_record_id}/buffer-insights` | `app/marketing_api.py` |
| `GET /manual-posts` | `app/marketing_api.py` |
| `GET /meet` | `app/api.py` |
| `GET /meetings/` | `app/api.py` |
| `GET /meetings/{lead_id}` | `app/workflow_views_api.py` |
| `GET /meetings` | `app/api.py` |
| `GET /meetings` | `app/workflow_views_api.py` |
| `GET /onboarding/` | `app/api.py` |
| `GET /onboarding` | `app/api.py` |
| `GET /onboarding` | `app/onboarding_api.py` |
| `GET /operations/history` | `app/api.py` |
| `GET /operations/marketing/assets` | `app/api.py` |
| `GET /operations/marketing/campaigns` | `app/api.py` |
| `GET /operations/marketing/publishing` | `app/api.py` |
| `GET /operations/marketing` | `app/api.py` |
| `GET /operations/overview` | `app/company_ops_api.py` |
| `GET /operations/sales/discovery` | `app/api.py` |
| `GET /operations/sales/email` | `app/api.py` |
| `GET /operations/sales` | `app/api.py` |
| `GET /operations` | `app/api.py` |
| `GET /orgs/{org_id}/capabilities` | `app/marketing_api.py` |
| `GET /orgs` | `app/marketing_api.py` |
| `GET /outreach/` | `app/api.py` |
| `GET /outreach/{draft_id}` | `app/workflow_views_api.py` |
| `GET /outreach` | `app/api.py` |
| `GET /outreach` | `app/workflow_views_api.py` |
| `GET /plans/{plan_id}` | `app/video_api.py` |
| `GET /plans` | `app/video_api.py` |
| `GET /providers` | `app/setup_api.py` |
| `GET /queue/stats` | `app/video_api.py` |
| `GET /render-jobs/next` | `app/video_api.py` |
| `GET /replies/` | `app/api.py` |
| `GET /replies/{reply_id}` | `app/workflow_views_api.py` |
| `GET /replies` | `app/api.py` |
| `GET /replies` | `app/workflow_views_api.py` |
| `GET /research/` | `app/api.py` |
| `GET /research` | `app/api.py` |
| `GET /service-discovery` | `app/service_discovery_api.py` |
| `GET /session` | `app/workspace_api.py` |
| `GET /settings/` | `app/api.py` |
| `GET /settings` | `app/api.py` |
| `GET /settings` | `app/workspace_api.py` |
| `GET /specs/{spec_id}` | `app/video_api.py` |
| `GET /specs` | `app/video_api.py` |
| `GET /step` | `app/setup_api.py` |
| `GET /{company_id:path}` | `app/companies_api.py` |
| `GET /{contact_id}` | `app/contacts_api.py` |
| `GET /{path:path}` | `app/api.py` |
| `POST /activate` | `app/onboarding_api.py` |
| `POST /asset-packs` | `app/marketing_api.py` |
| `POST /buyer` | `app/onboarding_api.py` |
| `POST /calibration` | `app/onboarding_api.py` |
| `POST /campaigns/{campaign_id}/approve-script` | `app/marketing_api.py` |
| `POST /campaigns/{campaign_id}/drafts` | `app/marketing_api.py` |
| `POST /campaigns/{campaign_id}/regenerate-script` | `app/marketing_api.py` |
| `POST /campaigns/{campaign_id}/retry` | `app/marketing_api.py` |
| `POST /campaigns/{campaign_id}/variants/{variant_id}/select` | `app/marketing_api.py` |
| `POST /campaigns/{campaign_id}/voice-recording` | `app/marketing_api.py` |
| `POST /campaigns` | `app/marketing_api.py` |
| `POST /coding/tasks/{task_id}/apply` | `app/company_ops_api.py` |
| `POST /coding/tasks` | `app/company_ops_api.py` |
| `POST /company/confirm` | `app/onboarding_api.py` |
| `POST /company` | `app/onboarding_api.py` |
| `POST /draft` | `app/onboarding_api.py` |
| `POST /drafts/{draft_id}/approve` | `app/sales_api.py` |
| `POST /drafts/{draft_id}/reconcile` | `app/sales_api.py` |
| `POST /drafts/{draft_id}/send` | `app/sales_api.py` |
| `POST /drafts/{draft_id}/update` | `app/sales_api.py` |
| `POST /email/sales` | `app/sales_api.py` |
| `POST /jobs/{job_id}/cancel` | `app/video_api.py` |
| `POST /jobs/{job_id}/retry` | `app/video_api.py` |
| `POST /keys/test` | `app/setup_api.py` |
| `POST /keys` | `app/setup_api.py` |
| `POST /leads/tally` | `app/sales_api.py` |
| `POST /leads/website` | `app/sales_api.py` |
| `POST /leads/{lead_id}/discover-linkedin` | `app/sales_api.py` |
| `POST /leads/{lead_id}/draft-preview` | `app/sales_api.py` |
| `POST /leads/{lead_id}/draft` | `app/sales_api.py` |
| `POST /leads/{lead_id}/enrich` | `app/sales_api.py` |
| `POST /leads/{lead_id}/linkedin-draft` | `app/sales_api.py` |
| `POST /leads/{lead_id}/linkedin-preview` | `app/sales_api.py` |
| `POST /leads/{lead_id}/resolve-company` | `app/sales_api.py` |
| `POST /leads/{lead_id}/resolve-contact` | `app/sales_api.py` |
| `POST /leads/{lead_id}/schedule-meeting` | `app/sales_api.py` |
| `POST /leads/{lead_id}/suppress` | `app/sales_api.py` |
| `POST /leads` | `app/sales_api.py` |
| `POST /manual-posts/session` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/ai-caption` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/assets` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/buffer-draft` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/buffer-schedule` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/finalize` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/org` | `app/marketing_api.py` |
| `POST /manual-posts` | `app/marketing_api.py` |
| `POST /monitor/run/{service}` | `app/company_ops_api.py` |
| `POST /monitor/run` | `app/company_ops_api.py` |
| `POST /orgs/active` | `app/marketing_api.py` |
| `POST /orgs/{org_id}/capabilities` | `app/marketing_api.py` |
| `POST /orgs` | `app/marketing_api.py` |
| `POST /plans/{plan_id}/queue` | `app/video_api.py` |
| `POST /plans` | `app/video_api.py` |
| `POST /prospect/domain` | `app/sales_api.py` |
| `POST /refinement` | `app/onboarding_api.py` |
| `POST /render-jobs/{job_id}/complete` | `app/video_api.py` |
| `POST /render-jobs/{job_id}/fail` | `app/video_api.py` |
| `POST /render-jobs/{job_id}/heartbeat` | `app/video_api.py` |
| `POST /research-company` | `app/onboarding_api.py` |
| `POST /research/leads` | `app/sales_api.py` |
| `POST /research/suggestions` | `app/sales_api.py` |
| `POST /resend/sales` | `app/sales_api.py` |
| `POST /search` | `app/onboarding_api.py` |
| `POST /search` | `app/service_discovery_api.py` |
| `POST /specs` | `app/video_api.py` |
| `POST /step` | `app/setup_api.py` |
| `POST /strategy/draft` | `app/onboarding_api.py` |
| `POST /strategy` | `app/onboarding_api.py` |
| `POST /{run_id}/search` | `app/service_discovery_api.py` |

## CLI verbs

| verb | module |
|---|---|
| `direct` | `scripts/video.py` |
| `launch` | `scripts/video.py` |
| `plan` | `scripts/video.py` |
| `profile` | `scripts/video.py` |
| `queue` | `scripts/video.py` |
| `submit` | `scripts/video.py` |
| `worker-status` | `scripts/video.py` |

## Database tables

| table | declared in |
|---|---|
| `buffer_org_accounts` | `core/state.py` |
| `buffer_orgs` | `core/state.py` |
| `coding_tasks` | `core/ops_store.py` |
| `incidents` | `core/ops_store.py` |
| `marketing_campaigns` | `core/marketing_store.py` |
| `marketing_events` | `core/marketing_store.py` |
| `marketing_manual_posts` | `core/marketing_store.py` |
| `marketing_variants` | `core/marketing_store.py` |
| `memories` | `core/memory.py` |
| `org_capabilities` | `core/state.py` |
| `sales_company_profiles` | `core/sales_store.py` |
| `sales_drafts` | `core/sales_store.py` |
| `sales_events` | `core/sales_store.py` |
| `sales_interactions` | `core/sales_store.py` |
| `sales_leads` | `core/sales_store.py` |
| `service_discovery_runs` | `core/state.py` |
| `service_provider_requests` | `core/state.py` |
| `settings` | `core/state.py` |
| `tasks` | `core/state.py` |
| `video_assets` | `core/video_store.py` |
| `video_render_jobs` | `core/video_store.py` |
| `video_shot_plans` | `core/video_store.py` |
| `video_specs` | `core/video_store.py` |
| `video_visual_bibles` | `core/video_store.py` |

## Regenerate

```bash
.venv/bin/python scripts/gen_api_reference.py
```
