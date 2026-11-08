# AutoEvolve locked API reference

Generated from source by `scripts/gen_api_reference.py` at commit `506debb` on 2026-10-29T15:29:48Z.

Every public constant, function, class and method in the shipped packages, with its real signature. Read this as the contract: if a name here disagrees with the code, the code is authoritative and this file must be regenerated.

## Totals

| subsystem | modules | functions | classes | methods | constants |
|---|---|---|---|---|---|
| Core state and models | 33 | 250 | 44 | 5 | 94 |
| Support services | 21 | 84 | 22 | 24 | 33 |
| Publisher adapters | 4 | 9 | 7 | 19 | 5 |
| Agents | 8 | 64 | 11 | 0 | 41 |
| HTTP surface | 18 | 210 | 125 | 0 | 56 |
| Operations scripts | 12 | 43 | 2 | 27 | 60 |
| **all** | **96** | **660** | **211** | **75** | **289** |

Plus 218 HTTP routes, 45 database tables and 0 CLI subcommands, listed at the end.

## Core state and models

### `core/__init__.py`

- (no public module-level names)

### `core/auth.py`

- const `EMAIL_RE`
- class `AuthError`(Exception)
- class `SignupResult`
- class `SessionResult`
- `validate_email(email: str) -> str`
- `validate_password(password: str) -> str`
- `public_user(user: dict[str, Any] | None) -> dict[str, Any] | None`
- `public_org(org: dict[str, Any] | None) -> dict[str, Any] | None`
- `signup(email: str, password: str, company_name: str='') -> SignupResult`
- `login(email: str, password: str) -> SessionResult`
- `verify_email(token: str) -> SessionResult`
- `resend_verification(email: str) -> AuthEmailResult` — Always returns a generic result to avoid account enumeration
- `resolve_session(token: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None`
- `me(user_id: str, org_id: int, session_hash: str | None) -> dict[str, Any]`

### `core/auth_context.py`

- `bind_session(*, user_id: str, org_id: int, session_hash: str) -> tuple`
- `reset_session(tokens: tuple) -> None`

### `core/auth_security.py`

- const `SCRYPT_N`
- const `SCRYPT_R`
- const `SCRYPT_P`
- const `SCRYPT_DKLEN`
- `hash_password(password: str) -> str`
- `verify_password(password: str, encoded: str | None) -> bool`
- `new_token() -> str`

### `core/auth_store.py`

- const `SESSION_TTL_DAYS`
- const `VERIFICATION_TTL_HOURS`
- `init_auth_db() -> None`
- `new_id(prefix: str) -> str`
- `normalize_email(email: str) -> str`
- `create_user(email: str, password_hash: str) -> dict[str, Any]`
- `get_user(user_id: str) -> dict[str, Any] | None`
- `get_user_by_email(email: str) -> dict[str, Any] | None`
- `delete_user(user_id: str) -> None`
- `mark_email_verified(user_id: str) -> dict[str, Any] | None`
- `add_membership(org_id: int, user_id: str, role: str='owner') -> None`
- `memberships_for_user(user_id: str) -> list[dict[str, Any]]`
- `primary_org_for_user(user_id: str) -> dict[str, Any] | None`
- `token_hash(token: str) -> str`
- `create_session(user_id: str, org_id: int) -> tuple[str, dict[str, Any]]`
- `get_session(token: str) -> dict[str, Any] | None`
- `delete_session(token: str) -> None`
- `create_verification(user_id: str) -> str`
- `consume_verification(token: str) -> str | None`

### `core/branding.py`

- `company_name() -> str`
- `company_public_url() -> str`
- `company_forms_url() -> str`
- `company_logo_url() -> str`

### `core/channel_benchmarks.py`

- const `MODULE_VERSION`
- const `VINTAGE`
- const `COLD_OUTBOUND_GENERAL`
- const `OPTIN_BY_INDUSTRY`
- const `INDUSTRY_ALIASES`
- `normalize_industry(text: object) -> str` — Map free-text industry to a benchmark key. Unknown -> 'general'
- `cold_reply_benchmark(industry: object=None) -> dict[str, object]` — Cold-outbound reply band for an industry
- `optin_benchmark(industry: object=None) -> dict[str, object]` — Opt-in open/click band for an industry, with honest coverage flag
- `expected_replies(sends: int, industry: object=None) -> dict[str, object]` — Estimate reply counts for a send volume from the world band

### `core/commercial_store.py`

- `connect() -> sqlite3.Connection`
- `new_id(prefix: str) -> str`
- `active_org_id() -> int`
- `init_commercial_db() -> None`
- `evaluate_fit(account: dict, icp: dict) -> dict` — Score account attributes against ICP criteria. No invented positives
- `evaluate_intent(org: int, account_id: str) -> dict` — Intent from recorded interactions only. Never invents from profile

### `core/company_context.py`

- const `MARKETING_STAGES`
- const `SCHEMA_VERSION`
- const `CONTEXT_ROW_ID`
- const `WORKFLOW_READINESS_THRESHOLD`
- `clean_text(value: Any, *, max_length: int | None=None) -> str | None` — Collapse whitespace and trim. Empty, blank, or non-text input is unknown
- `clean_lines(value: Any, *, max_items: int | None=None) -> list[str]` — Accept a pasted one-per-line block or a list, dropping blanks and repeats
- `normalize_website(value: Any) -> str | None` — Return a clean public URL, or raise when the value is not an address
- `normalize_marketing_stage(value: Any) -> str | None` — Map founder wording onto a known stage, or raise instead of guessing
- `answer_text(max_length: int) -> Any` — A trimmed free-text field. Blank input becomes unknown, never invented
- `answer_lines(max_items: int) -> Any` — A bounded list field that accepts a pasted one-per-line block
- class `CompanyFacts`(BaseModel) — Who the company is
- class `ProductFacts`(BaseModel) — What the company sells
- class `CustomerFacts`(BaseModel) — Who buys
- class `MarketFacts`(BaseModel) — The market, the problem, and what else is out there
- class `EvidenceFacts`(BaseModel) — Proof the founder already has. Empty lists mean "none yet", not "none exist"
- class `OfferFacts`(BaseModel) — The commercial offer
- class `ResourceFacts`(BaseModel) — What is already available to market with
- class `ConstraintFacts`(BaseModel) — Limits a future workflow must respect
- class `ObjectiveFacts`(BaseModel) — The business outcome the founder is working towards
- class `ContextState`(BaseModel) — Where the company starts from. Phase 1 records the stage only
- const `REQUIRED_GROUPS`
- const `WORKFLOW_READY_PERCENT`
- `missing_required(context: 'CompanyContextSections') -> list[str]` — Label every required group that is still unknown, in requirement order
- `completeness_ratio(context: 'CompanyContextSections') -> float` — Share of required groups that are known (0.0-1.0)
- `is_workflow_ready(context: 'CompanyContextSections') -> bool` — True when the context is complete enough to prepare a workflow
- class `CompanyContextSections`(BaseModel) — The founder-confirmed facts, grouped the way later consumers read them
- class `CompanyContext`(CompanyContextSections) — The canonical company context
- `normalize_company_context(raw: Mapping[str, Any] | None) -> CompanyContext` — Turn raw onboarding or API answers into the canonical context
- `has_any_fact(context: CompanyContextSections) -> bool` — True when at least one founder answer is known
- `resolve_context_org(org_id: int | None=None) -> int` — Resolve the org for a context read/write
- `init_context_db() -> None` — Create or migrate the org-scoped company context table
- `get_company_context(org_id: int | None=None) -> CompanyContext | None` — Load one org's context, or ``None`` when onboarding has not produced one
- `save_company_context(context: CompanyContextSections, org_id: int | None=None) -> CompanyContext` — Persist one org's context and return exactly what was stored
- `clear_company_context(org_id: int | None=None) -> None` — Remove one org's record. Used by tests and future "start over" flows
- `get_recorded_marketing_stage(org_id: int | None=None) -> str | None` — The stored stage exactly as written, even if it no longer normalizes

### `core/company_read.py`

- const `SUMMARY_FIELDS`
- `list_company_records(*, page: int, page_size: int, query: str, view: str, sort: str, industry: str='', country: str='', org_id: int | None=None) -> tuple[list[dict[str, Any]], int, dict[str, int]]`
- `get_company_record(company_id: str, org_id: int | None=None) -> dict[str, Any] | None`

### `core/dashboard.py`

- const `ROOT`
- const `PROJECTS_ROOT`
- `get_dashboard_state() -> dict`
- `get_operations_page_state() -> dict`

### `core/db.py`

- const `BUSY_TIMEOUT_SECONDS`
- `open_db(path: str | Path, *, row_factory: Any=None, timeout: float=BUSY_TIMEOUT_SECONDS) -> sqlite3.Connection`

### `core/evidence.py`

- const `EVIDENCE_CACHE_SECONDS`
- `collect_evidence(org: int=0) -> dict[str, Any]` — Cached read of the evidence union (see ``_collect_evidence``)
- `resolve_research_terms(org: int=0) -> dict[str, Any]` — Decide what a governed research run searches for, from evidence
- `suggest_accounts(org: int=0, enrich_budget: int=5) -> dict[str, Any]` — Propose accounts from evidence nobody has claimed yet

### `core/form_store.py`

- const `DB_PATH`
- const `SLUG_PATTERN`
- const `FIELD_TYPES`
- const `MAPPED_KEYS`
- const `DEFAULT_FORM`
- `connect() -> sqlite3.Connection`
- `init_form_db() -> None`
- `list_forms() -> list[dict[str, Any]]`
- `get_form(slug: str) -> dict[str, Any] | None`
- `validate_fields(fields: Any) -> list[dict[str, Any]]`
- `create_form(slug: str, name: str, fields: Any, description: str | None=None) -> dict[str, Any]`
- `update_form(slug: str, *, name: str | None=None, description: str | None=None, fields: Any=None, active: bool | None=None) -> dict[str, Any]`
- `map_answers_to_lead(form: dict[str, Any] | None, answers: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]` — Split a submission into a LeadIntake-shaped payload and the clean

### `core/jobs_store.py`

- `init_jobs_db() -> None`
- `create_publish_job(org_id: int, post_id: str) -> dict[str, Any]`
- `get_publish_job(job_id: str, org_id: int | None=None) -> dict[str, Any] | None`
- `latest_publish_job(org_id: int, post_id: str) -> dict[str, Any] | None`
- `update_publish_job(job_id: str, *, status: str, result: dict[str, Any] | None=None, error: str | None=None) -> dict[str, Any] | None`
- `mark_interrupted_jobs() -> int` — A process restart cannot resume an in-flight provider call

### `core/marketing_config.py`

- const `ROOT`
- const `WORKSPACE_ROOT`
- class `MarketingConfig` — The only engine the app still calls: G3 (Buffer/R2 publishing)
  - `load(cls) -> 'MarketingConfig'`
  - `diagnostics(self) -> dict`

### `core/marketing_routing.py`

- class `UnsupportedMarketingStage`(ValueError) — Raised when a company state has no route. Never replaced by a default
- class `InitialRoute`(BaseModel) — A resolved route: the founder's starting stage and the next state
- const `INITIAL_ROUTES`
- class `RouteState`(BaseModel) — Flat routing fields for typed API views (context route, Get Started, home)
  - `resolved(cls, route: InitialRoute) -> 'RouteState'`
  - `unresolved(cls, error: str | None=None) -> 'RouteState'` — No route is claimed. Either nothing is decided yet, or it failed
- `route_for_stage(stage: str | None) -> InitialRoute` — Return the route for one starting stage, or explain why there is none
- `resolve_initial_route(context: object | None) -> InitialRoute` — Route a stored company context. Raises instead of guessing a branch
- `route_state_for(context: object | None) -> RouteState` — Resolve a context into flat routing fields, or state why there is no route
- `stored_route_state() -> RouteState` — Routing state for the persisted company

### `core/marketing_store.py`

- const `TERMINAL_CAMPAIGN_STATES`
- `connect() -> sqlite3.Connection`
- `init_marketing_db() -> None`
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

### `core/plan_governance.py`

- const `SUPPORTED_CHANNELS`
- const `METHOD_ACTIONS`
- `normalize_channel(value: str | None) -> str` — Fold founder wording onto a channel key: 'Email' and 'e-mail' -> 'email'
- `normalize_method(value: str | None) -> str`
- class `GovernanceLimits`(BaseModel) — Caps the operator has agreed to. Defaults refuse anything costly
  - `load(cls, org_id: int | None=None) -> 'GovernanceLimits'`
- class `ResolvedAction`(BaseModel) — One workflow step governance is willing to authorize
- class `GovernanceDecision`(BaseModel) — The structured result of validating one plan. Always persisted
- `validate_plan(plan: ValidationPlan | dict[str, Any], context: CompanyContext, *, plan_id: str='', limits: GovernanceLimits | None=None, org_id: int=0) -> tuple[GovernanceDecision, ValidationPlan]` — Decide whether a plan may become a workflow. Returns (decision, plan)
- class `GovernanceRecord`(BaseModel) — A persisted governance decision plus the lifecycle it has reached
- `new_governance_id() -> str`
- `record_from_decision(decision: GovernanceDecision, record_id: str | None=None, *, org_id: int=0) -> GovernanceRecord`
- `init_governance_db() -> None` — Create the governance table (idempotent, in the existing company database)
- `save_governance(record: GovernanceRecord) -> GovernanceRecord`
- `get_governance(governance_id: str) -> GovernanceRecord | None`
- `latest_governance(org_id: int=0) -> GovernanceRecord | None` — The most recent decision for one org, so the lifecycle survives a reload

### `core/plan_input.py`

- const `SCHEMA`
- class `PlanInputError`(RuntimeError) — The planner input cannot be built from the recorded company state
- `build_plan_input(org_id: int | None=None) -> dict[str, Any]` — Build the canonical, org-scoped `PlanInput` for today's decision
- `save_plan_input(payload: dict[str, Any]) -> dict[str, Any]`
- `get_plan_input(org_id: int, input_hash: str) -> dict[str, Any] | None`

### `core/projects.py`

- const `PROJECTS_ROOT`
- `now_iso() -> str`
- `slugify(text: str) -> str`
- `ensure_project(name: str) -> tuple[dict, Path]` — Create or reuse a project
- `save_research(project_path: Path, report: dict) -> Path`

### `core/publishers_store.py`

- const `DEFAULT_PLATFORMS`
- `init_publishers_db() -> None`
- `save_webhook(org_id: int, *, url: str, secret: str, account: str='webhook', label: str='Webhook scheduler', platforms: list[str] | str | None=None) -> dict[str, Any]`
- `webhook_for_org(org_id: int) -> dict[str, Any] | None`
- `public_webhook_for_org(org_id: int) -> dict[str, Any] | None`
- `delete_webhook(org_id: int) -> None`

### `core/quotas.py`

- const `FREE_LIMITS`
- const `PAID_DEFAULTS`
- class `QuotaExceeded`(RuntimeError)
- `reset_at(now: datetime | None=None) -> str`
- `org_plan(org_id: int | None=None) -> str`
- `used_today(org_id: int | None, kind: str) -> int`
- `quota_snapshot(org_id: int | None, kind: str) -> dict`
- `enforce_quota(org_id: int | None, kind: str) -> dict`
- `record_usage(org_id: int | None, kind: str, ref: str) -> None`
- `quota_snapshot_all(org_id: int | None) -> dict`
- `retry_after_seconds(exc: QuotaExceeded) -> int`
- `provider_limit(org_id: int | None, provider: str) -> int`
- `provider_remaining(org_id: int | None, provider: str) -> int`
- `claim_provider(org_id: int | None, provider: str, action: str) -> bool`

### `core/sales_store.py`

- const `PIPELINE_STAGES`
- `connect() -> sqlite3.Connection`
- `init_sales_db() -> None`
- `linkedin_url_for_lead(lead: dict | None) -> str | None`
- `linkedin_profile_for_lead_org(lead: dict | None) -> str | None`
- `contact_profile_for_lead(lead: dict | None) -> dict[str, Any]`
- `normalize_company_domain(value: Any) -> str | None`
- `get_company_profile(domain: str | None, org_id: int=0) -> dict | None`
- `upsert_company_profile(domain: str, *, provider: str, status: str, company_name: str | None=None, summary: dict[str, Any] | None=None, raw: dict[str, Any] | None=None, fetched_at: str | None=None, org_id: int=0) -> dict`
- `score_lead(lead: dict) -> int`
- `upsert_lead(payload: dict) -> tuple[dict, bool]`
- `get_lead(lead_id: str, org_id: int | None=None) -> dict | None`
- `get_lead_by_email(email: str | None) -> dict | None`
- `list_leads(limit: int=50, stage: str | None=None, org_id: int | None=None) -> list[dict]`
- `list_contacts_page(*, page: int=1, page_size: int=10, stage: str | None=None, query: str='', sort: str='recent', org_id: int | None=None) -> tuple[list[dict], int, dict[str, Any]]` — Read-only, complete pagination over the existing sales leads
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
- `mark_meeting_scheduled(lead_id: str, scheduled_for: str | None=None, note: str | None=None, source: str='manual') -> dict`
- `mark_meeting_requested(lead_id: str, slots: list[str], note: str | None=None) -> dict` — Record a founder-sent booking request: the offered slots are saved, the
- `add_event(lead_id: str | None, event: str, payload: dict) -> None`
- `count_company_profile_attempts() -> int`
- `list_events(limit: int=50, lead_id: str | None=None, org_id: int | None=None) -> list[dict]`
- `list_interactions(limit: int=50, lead_id: str | None=None, org_id: int | None=None) -> list[dict]`
- `summary(org_id: int | None=None) -> dict`

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
- `read_values(path: Path) -> dict[str, str]` — Public, read-only access to an env file (values never leave the server)
- `group_status() -> dict[str, dict]` — Masked per-group status: which keys are set (never values)
- `validate_group(group: str, values: dict[str, str]) -> dict` — Format-level validation (no credits spent). Live gateway check for ai_gateway
- `write_values(path: Path, values: dict[str, str]) -> dict` — Backup, then update keys in place. Rolls the file back on any failure
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
- `get_network_contribution() -> bool` — Anonymized-pool opt-in. Default opted out: nothing is shared ever
- `set_network_contribution(opt_in: bool) -> bool`
- `claim_service_provider_request(provider: str, action: str, limit_24h: int, org_id: int=0) -> bool` — Reserve one request against a conservative rolling local provider cap
- `create_org(name: str, slug: str, env_prefix: str='BUFFER_', organization_id: str='', domain: str='', plan: str='paid', limits: dict | None=None) -> dict`
- `get_org(org_id: int) -> Optional[dict]`
- const `LIMIT_KEYS`
- `get_org_limits(org_id: int) -> dict`
- `set_org_limits(org_id: int, limits: dict) -> dict`
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

### `core/suggest.py`

- `suggest_workflows(org: int=0, now: datetime | None=None) -> dict[str, Any]` — Rank the next governed runs from evidence. Read-only
- `market_comparison(rate: float | None, industry: str | None=None) -> dict[str, Any] | None` — Your recorded rate against the world band. None without a rate

### `core/validation_plan.py`

- const `WORKFLOW_TEMPLATE`
- const `PLAN_STATUS`
- const `GROUNDING_THRESHOLD`
- class `CommercialHypothesis`(BaseModel) — One primary hypothesis, stated as a testable claim
- class `MarketView`(BaseModel) — Who, what problem, why now, and what they do instead
- class `ValidationStrategy`(BaseModel) — The smallest experiment that can produce the validation event
- class `EvidenceLedger`(BaseModel) — Facts the founder gave, assumptions we made, and what we still need
- class `PlanLimits`(BaseModel) — Limits the plan proposes. A later phase enforces them before any action
- class `ValidationPlan`(BaseModel) — The structured output of one market-validation pass. A plan, not a run
- class `PlanProvenance`(BaseModel) — Where the plan came from, so a stored plan is never anonymous
- class `ValidationPlanRecord`(BaseModel) — A persisted plan. ``planned`` never implies the experiment happened
- class `GroundingReport`(BaseModel) — What the grounding rule did, so the demotion is never silent
- class `ValidationEventObservation`(BaseModel) — Whether the success metric could be measured, and by what
- `grounding_ratio(statement: str, context_text: str) -> float` — Share of a statement's meaningful words that appear in the context
- `is_grounded(statement: str, context_text: str) -> bool` — True when a claimed fact is recognisably the founder's own wording
- `context_text(context: CompanyContext) -> str` — Flatten a context into the text a claim must be traceable to
- `enforce_grounding(plan: ValidationPlan, context: CompanyContext) -> tuple[ValidationPlan, GroundingReport]` — Demote untraceable "facts" to assumptions and report exactly what moved
- `new_plan_id() -> str`
- `init_validation_db() -> None` — Create the plan table (idempotent, in the existing company database)
- `save_validation_plan(record: ValidationPlanRecord) -> ValidationPlanRecord` — Persist a planned record and return exactly what was stored
- `build_plan_record(plan: ValidationPlan, provenance: PlanProvenance, grounding: GroundingReport, *, org_id: int=0) -> ValidationPlanRecord`
- `get_validation_plan(plan_id: str, org_id: int | None=None) -> ValidationPlanRecord | None`
- `get_latest_validation_plan(org_id: int=0) -> ValidationPlanRecord | None` — The newest plan for one org, so the UI can show current thinking

### `core/workflow_store.py`

- const `ROOT`
- const `DB_PATH`
- const `WORKFLOW_ACTIONS`
- const `SIMULATION_ACTIONS`
- const `DRAFT_ACTIONS`
- const `READ_ACTIONS`
- const `SEND_ACTIONS`
- const `GOVERNED_ACTIONS`
- const `EXTERNAL_ACTIONS`
- const `TERMINAL_STATUSES`
- `now_iso() -> str`
- `new_id(prefix: str='wf') -> str`
- class `StrictModel`(BaseModel)
- class `WorkflowTrigger`(StrictModel)
- class `WorkflowStep`(StrictModel)
- class `SuccessMetric`(StrictModel)
- class `StepResult`(StrictModel) — Structured result of one executed step (implementation.md §4)
- class `StepExecution`(StrictModel) — A persisted StepResult plus the observability envelope for it
- class `WorkflowEvaluation`(StrictModel) — The evolution hook (implementation.md §12)
- class `WorkflowState`(StrictModel)
- class `Workflow`(StrictModel)
- `connect() -> sqlite3.Connection`
- `init_db() -> None`
- `save_workflow(workflow: Workflow) -> Workflow` — Persist (insert or replace) a workflow document
- `build_workflow(*, name: str, objective: str='', steps: list[dict[str, Any]] | None=None, trigger: dict[str, Any] | None=None, success_metric: dict[str, Any] | None=None, workflow_id: str | None=None, org_id: int=0) -> Workflow` — Construct (but do not persist) a workflow document; raises ValueError if malformed
- `create_workflow(*, name: str, objective: str='', steps: list[dict[str, Any]] | None=None, trigger: dict[str, Any] | None=None, success_metric: dict[str, Any] | None=None, workflow_id: str | None=None, org_id: int=0) -> Workflow`
- `get_workflow(workflow_id: str) -> Workflow | None`
- `list_workflows(limit: int=50, *, status: str | None=None, org_id: int | None=None) -> list[Workflow]`

### `core/worlddata_store.py`

- `connect() -> sqlite3.Connection`
- `init_worlddata_db() -> None`
- `upsert_record(source: str, kind: str, ref: str, name: str, data: dict[str, Any], vintage: str='') -> None`
- `count_records(source: str | None=None, kind: str | None=None) -> int`
- `sources_summary() -> dict[str, Any]` — Coverage answer for the evidence union: per-source counts + vintages
- `find_records(source: str, kind: str, limit: int=50) -> list[dict[str, Any]]`
- `get_record(source: str, kind: str, ref: str) -> dict[str, Any] | None` — One world record by identity. None when absent or on any error
- `clear_source(source: str, kind: str | None=None) -> int`

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

### `services/auth_email.py`

- const `RESEND_SEND_URL`
- class `AuthEmailResult`
- `verify_url(token: str) -> str`
- `send_verification_email(email: str, token: str, *, company_name: str='') -> AuthEmailResult`
- `dev_token_visible() -> bool`

### `services/buffer_setup.py`

- const `DEFAULT_ACCOUNT`
- const `ACCOUNT_NAME_RE`
- const `SERVICE_TO_PLATFORM`
- const `PLATFORMS`
- `normalize_account_name(value: str | None) -> str`
- `account_keys(name: str) -> dict[str, str]` — Environment key names for one account, matching G3's prefix rules
- `list_accounts() -> list[dict]` — Configured accounts with masked state. Never returns the token
- `discover(account: str, api_key: str | None=None, *, client_factory: ClientFactory | None=None) -> dict` — Read the organizations and channels a token can reach
- `bind(account: str, *, api_key: str | None, organization_id: str, instagram_channel_id: str | None=None, x_channel_id: str | None=None, linkedin_channel_id: str | None=None, client_factory: ClientFactory | None=None) -> dict` — Verify the chosen channel IDs against Buffer, then persist the account

### `services/caption_variants.py`

- const `CTA_BY_PLATFORM`
- `build_short_caption_variants(*, topic: str, buyer: str, transcript: str, platform_copy: dict[str, Any] | None=None) -> dict[str, list[str]]`
- `enrich_platform_copy(platform_copy: dict[str, Any] | None) -> dict[str, Any]`

### `services/company_enrich.py`

- class `CompanyEnrichError`(RuntimeError)
- class `CompanyEnrichClient`
  - `me(self) -> dict`
  - `enrich_company(self, domain: str, *, wait_for_enrichment: bool=True) -> dict`
  - `extract_company_profile(self, payload: dict[str, Any]) -> dict[str, Any]`
- `company_usage_profile(company_profile: dict[str, Any] | None) -> dict[str, Any]`

### `services/g3_cli.py`

- `run(command: list[str], *, cwd: Path, env_file: Path | None, timeout: int, log_path: Path) -> str`
- `last_json(text: str) -> dict`

### `services/gleif.py`

- const `BASE_URL`
- const `TIMEOUT_SECONDS`
- const `PAGE_SIZE`
- class `GleifError`(RuntimeError)
- `search_records(company_name: str, *, page_size: int=PAGE_SIZE) -> list[dict[str, Any]]` — Full-text legal-name search. Raw JSON:API records, may be empty
- `extract_identity(record: dict[str, Any]) -> dict[str, Any]` — Flatten one lei-record into the identity dict the ladder stores
- `fetch_direct_parent(identity: dict[str, Any]) -> dict[str, Any] | None` — Best-effort direct-parent legalName/LEI. None on any failure
- `resolve_identity(company_name: str) -> dict[str, Any] | None` — Free identity for a company name, or None (miss/error → paid ladder)

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
  - `enrich_contacts(self, contact_ids: list[str], *, reveal: tuple[str, ...]=('emails', 'phones')) -> dict`

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

### `services/oauth.py`

- class `OAuthError`(ValueError) — Provider refused, state invalid, or configuration missing
- class `OAuthNotConfigured`(OAuthError) — The external app approval (client id/secret) is not in the environment
- const `PROVIDERS`
- const `STATE_TTL_SECONDS`
- `is_configured(provider: str) -> bool` — External app approval exists when both halves are present. Nothing else counts
- `missing_config(provider: str) -> list[str]`
- `build_authorize_url(provider: str, org_id: int=0) -> str` — Start the provider's official authorization flow. Founder-gated upstream
- `verify_state(provider: str, raw_state: str, org_id: int=0) -> None` — The callback's only authentication. Rejects tampering, expiry, and mismatch
- `store_tokens(provider: str, tokens: dict[str, Any], org_id: int=0) -> None` — Encrypt and persist. Plaintext tokens never reach the database
- `read_tokens(provider: str, org_id: int=0) -> dict[str, Any] | None` — Decrypt for server-side use only. Never returned by any API
- `delete_tokens(provider: str, org_id: int=0) -> None`
- `exchange_code(provider: str, code: str, org_id: int=0) -> dict[str, Any]` — Trade one single-use authorization code for tokens, then persist them
- `refresh_tokens(provider: str, org_id: int=0) -> dict[str, Any]` — Rotate an expiring access token. Failure surfaces as action-required, never silent
- `validate_connection(provider: str, org_id: int=0) -> dict[str, Any]` — Health check used by sync: refresh when expiring, report honestly

### `services/opencorporates.py`

- class `OpenCorporatesError`(RuntimeError)
- const `COUNTRY_JURISDICTIONS`
- `jurisdiction_for_country(country: str | None) -> str | None` — Map a free-text country to an OpenCorporates jurisdiction code
- `normalize_company_name(value: Any) -> str`
- class `OpenCorporatesClient` — OpenCorporates company search (registry verification, not discovery)
  - `search_companies(self, name: str, *, jurisdiction: str | None=None, inactive: bool=False) -> list[dict]` — Raw registry hits for a company name, each with name/number/jurisdiction
  - `verify_company(self, name: str, *, jurisdiction: str | None=None) -> dict | None` — Confirm a candidate exists in the registry under that jurisdiction

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

### `services/provider_registry.py`

- class `ProviderSpec` — Everything the product knows about one tool
- `register(spec: ProviderSpec) -> ProviderSpec` — Declare a provider. Registering twice replaces the entry (tests)
- `get(name: str) -> ProviderSpec | None`
- `providers_for(datapoint: str, order: list[str] | None=None) -> list[ProviderSpec]` — Specs supplying a data point, in explicit order or cost order
- `run_waterfall(steps: list[tuple[str, Callable[[], list[dict[str, Any]]], tuple[type[BaseException], ...]]], target: int | None, key_fn: Callable[[dict[str, Any]], str | None], warn_fn: Callable[[str, Exception], str]) -> dict[str, Any]` — Query suppliers in order until `target` unique results are held

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
- `research_prospeo_market_leads(*, industry: str, location: str | None=None, limit: int=5, widen: bool=False) -> list[dict]` — Company candidates for exactly the industry (and location) requested
- `research_prospeo_suggestions(*, kind: str, query: str) -> list[str]`
- `research_lusha_suggestions(*, kind: str, query: str) -> list[str]`
- `research_lusha_leads(*, job_title: str | None=None, service_keywords: list[str] | None=None, location: str | None=None, company_size: str | None=None, limit: int=5) -> list[dict]`
- `research_lusha_market_leads(*, industry: str, location: str | None=None, limit: int=5) -> list[dict]`
- `research_apollo_market_leads(*, industry: str, location: str | None=None, limit: int=5) -> list[dict]`
- const `COMPANY_SEARCH_ORDER`
- `research_market_leads(*, industry: str, location: str | None=None, limit_per_provider: int=5, org_id: int=0) -> dict[str, Any]`
- `waterfall_company_search(*, industry: str, location: str | None=None, target: int=10, limit_per_provider: int=5, order: list[str] | None=None, org_id: int=0) -> dict[str, Any]` — Company search that stops when it has enough
- `import_domain(domain: str, limit: int=5, provider: str='hunter') -> list[dict]`
- `pull_inbound_leads() -> dict`
- `resolve_company_profile(lead_id: str, provider: str='auto', force: bool=False) -> dict[str, Any]`
- `resolve_contact(lead_id: str, provider: str='prospeo', force: bool=False) -> dict[str, Any]`
- `enrich_lead(lead_id: str, provider: str='hunter') -> dict`
- class `_FallbackDraft`
- `async preview_draft(lead_id: str) -> dict[str, Any]`
- `async build_draft(lead_id: str, *, request_source: str='sales') -> dict`
- const `LINKEDIN_PIECES`
- const `LINKEDIN_KINDS`
- `async preview_linkedin_draft(lead_id: str, piece: str) -> dict[str, Any]`
- `async build_linkedin_draft(lead_id: str, piece: str, *, request_source: str='sales') -> dict`
- `maybe_auto_contact_lead(lead_id: str, *, created: bool) -> dict | None`
- `verify_resend_webhook(payload: str, headers: dict[str, str]) -> dict`
- `ingest_resend_event(payload: dict) -> dict`
- `sync_received_emails(*, limit: int=25, to: str | None=None) -> dict` — Mirror a Resend receiving inbox into inbound replies
- class `ResendAmbiguousError`(RuntimeError) — The provider may or may not have accepted the message
- class `ResendIdempotencyConflictError`(RuntimeError) — The idempotency key was already used with a different payload
- `send_booking_request(lead_id: str, slots: list[str], note: str | None=None) -> dict[str, Any]` — Email the contact a public booking page holding the founder's offered
- `send_approved(draft_id: str) -> dict`
- `reconcile_sending_drafts() -> dict` — Recover drafts stranded in 'sending' after a crash or restart
- `ingest_inbound_email(payload: dict) -> dict`

### `services/workflow_actions.py`

- const `VALIDATION_EVENT_NAMES`
- `simulate_outreach(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]` — Simulate one validation outreach step. Nothing leaves this process
- `draft_outreach(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]` — Create real outreach drafts for the plan's targets. Nothing is sent
- `research_prospects(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]` — Research named companies through the provider ladder. Reads only
- `send_outreach(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]` — Send founder-approved drafts through the existing send path. Nothing else
- `observe_validation_events(*, plan_id: str | None=None, workflow_id: str | None=None) -> ValidationEventObservation` — Measure the plan's validation events against real, attributable evidence

### `services/workflow_runner.py`

- class `WorkflowValidationError`(ValueError) — Raised when a workflow cannot be executed as defined
- `validate_workflow(workflow: Workflow) -> list[str]` — Return the list of problems that block execution (empty means valid)
- `run_workflow(workflow_id: str, *, resume: bool=False) -> Workflow` — Execute a workflow in order, persisting after every step
- `pause_workflow(workflow_id: str) -> Workflow`

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

## Publisher adapters

### `services/publishers/__init__.py`

- `get_publisher(name: str | None=None) -> Publisher`
- `webhook_configured(org_id: int | None=None) -> bool`
- `list_publishers(org_id: int | None=None) -> list[Publisher]`
- `capabilities_dict(publisher: Publisher) -> dict`
- `catalog(org_id: int | None=None) -> list[dict]`

### `services/publishers/base.py`

- class `PublisherCapabilities`
- class `PublisherAccount`
- class `PublisherError`(Exception) — A publisher failure that maps directly onto an HTTP response
- class `Publisher`(Protocol)
  - `capabilities(self) -> PublisherCapabilities`
  - `accounts(self) -> list[PublisherAccount]`
  - `draft(self, post: dict[str, Any], account: str | None=None) -> dict[str, Any]`
  - `schedule(self, post: dict[str, Any], *, account: str | None=None, mode: str='queue', due_at: str | None=None) -> dict[str, Any]`
  - `confirm(self, post: dict[str, Any]) -> dict[str, Any]`
  - `insights(self, post: dict[str, Any], post_id: str) -> dict[str, Any]`

### `services/publishers/buffer.py`

- class `BufferPublisher`
  - `capabilities(self) -> PublisherCapabilities`
  - `accounts(self) -> list[PublisherAccount]`
  - `draft(self, post: dict[str, Any], account: str | None=None) -> dict[str, Any]`
  - `schedule(self, post: dict[str, Any], *, account: str | None=None, mode: str='queue', due_at: str | None=None) -> dict[str, Any]`
  - `confirm(self, post: dict[str, Any]) -> dict[str, Any]`
  - `insights(self, post: dict[str, Any], post_id: str) -> dict[str, Any]`

### `services/publishers/webhook.py`

- const `SCHEMA`
- const `DEFAULT_PLATFORMS`
- class `WebhookConfig`
  - `configured(self) -> bool`
- `load_config(org_id: int | None=None) -> WebhookConfig`
- `asset_token(post_id: str, index: int, expires_at: int, org_id: int | None=None) -> str`
- `verify_asset_token(post_id: str, index: int, expires_at: int, token: str, org_id: int | None=None) -> None`
- `public_asset(post_id: str, index: int, expires_at: int, token: str) -> tuple[Path, str, str]` — Resolve a signed public asset link. Used by the unauthenticated route
- class `WebhookPublisher`
  - `capabilities(self) -> PublisherCapabilities`
  - `accounts(self) -> list[PublisherAccount]`
  - `draft(self, post: dict[str, Any], account: str | None=None) -> dict[str, Any]`
  - `schedule(self, post: dict[str, Any], *, account: str | None=None, mode: str='queue', due_at: str | None=None) -> dict[str, Any]`
  - `confirm(self, post: dict[str, Any]) -> dict[str, Any]`
  - `insights(self, post: dict[str, Any], post_id: str) -> dict[str, Any]`

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

### `agents/hermes.py`

- const `PROMPT_DIR`
- const `PROMPT_PATH`
- const `PROMPT_VERSION`
- const `CONTEXT_TOKEN`
- const `MODEL_ROUTE`
- const `PROVIDER_NAME`
- const `PLAN_TIMEOUT_SECONDS`
- const `REQUEST`
- class `HermesError`(RuntimeError) — Hermes could not produce a plan
- class `HermesOutputError`(HermesError) — The model returned something that is not a valid structured plan
- class `HermesPlanResult`(BaseModel) — A plan plus the provenance needed to judge where it came from
- `load_prompt_template() -> str` — Read the versioned prompt file. Prompts are data, not Python strings
- `build_instructions(context: CompanyContext, method_hint: str | None=None, channel_hint: str | None=None, plan_input: dict | None=None) -> str` — Render the base prompt with the canonical context substituted in
- `async plan_market_validation(context: CompanyContext, method_hint: str | None=None, channel_hint: str | None=None, plan_input: dict | None=None) -> HermesPlanResult` — Run one market-validation pass and return a validated, grounded plan

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

- `async website_session(request: Request, call_next)` — Bind a verified website session to this request's org
- `async security_headers(request: Request, call_next)`
- `async cache_headers(request: Request, call_next)` — Cache policy stated by the app, not only by the proxy
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
- `public_manual_post_asset(post_id: str, index: int, exp: int, token: str)` — Short-lived signed media link for an external webhook scheduler
- `ui_app(request: Request)`
- `missing_page(path: str, request: Request)`

### `app/auth_api.py`

- `session_cookie_name() -> str`
- const `SESSION_COOKIE`
- class `SignupPayload`(BaseModel)
- class `LoginPayload`(BaseModel)
- class `VerifyPayload`(BaseModel)
- class `ResendPayload`(BaseModel)
- `clear_session_cookie(response: Response, request: Request) -> None`
- `signup(payload: SignupPayload, request: Request)` [router.post('/signup', dependencies=[Depends(rate_limit_auth)])]
- `login(payload: LoginPayload, request: Request, response: Response)` [router.post('/login', dependencies=[Depends(rate_limit_auth)])]
- `verify(payload: VerifyPayload, request: Request, response: Response)` [router.post('/verify', dependencies=[Depends(rate_limit_auth)])]
- `resend(payload: ResendPayload)` [router.post('/resend', dependencies=[Depends(rate_limit_auth)])]
- `logout(request: Request, response: Response)` [router.post('/logout')]
- `me()` [router.get('/me')]

### `app/commercial_api.py`

- `oauth_callback(provider: str, code: str=Query(''), state: str=Query(''))` [oauth_callback_router.get('/{provider}/callback', include_in_schema=False)] — Finish an OAuth authorization started by POST .../connect
- class `OfferIn`(BaseModel)
- `list_offers() -> list[dict]` [router.get('/offers')]
- `create_offer(payload: OfferIn) -> dict` [router.post('/offers', dependencies=[Depends(verify_founder_action)])]
- `update_offer(rid: str, payload: dict) -> dict` [router.patch('/offers/{rid}', dependencies=[Depends(verify_founder_action)])]
- class `ICPIn`(BaseModel)
- const `ICP_TEMPLATES`
- `icp_templates() -> list[dict]` [router.get('/icp-templates')]
- `archive_icp(rid: str) -> dict` [router.post('/icps/{rid}/archive', dependencies=[Depends(verify_founder_action)])]
- `list_icps() -> list[dict]` [router.get('/icps')]
- const `SUGGEST_FIELDS`
- `suggest_criteria() -> dict` [router.get('/icps/suggest-criteria')] — Propose ICP criteria mined from the founder's own records
- `world_benchmarks(sends: int=Query(100, ge=1, le=100000), industry: str | None=Query(None, max_length=120)) -> dict` [router.get('/benchmarks')] — World-data predictions for this company's industry. Read-only
- class `NetworkContributionIn`(BaseModel)
- `network_stats() -> dict` [router.get('/network-stats')] — This tenant's anonymized contribution payload. Read-only
- `network_contribution(payload: NetworkContributionIn) -> dict` [router.post('/network-contribution', dependencies=[Depends(verify_founder_action)])] — Opt the anonymized counts in or out of the future pool. Default out
- `get_icp(rid: str) -> dict` [router.get('/icps/{rid}')]
- `create_icp(payload: ICPIn) -> dict` [router.post('/icps', dependencies=[Depends(verify_founder_action)])]
- `update_icp(rid: str, payload: dict) -> dict` [router.patch('/icps/{rid}', dependencies=[Depends(verify_founder_action)])]
- `evaluate_icp(rid: str, account: dict) -> dict` [router.post('/icps/{rid}/evaluate', dependencies=[Depends(verify_founder_action)])]
- class `AccountIn`(BaseModel)
- `list_accounts(q: str='', lifecycle_status: str='', sort: str='updated', page: int=1, page_size: int=20) -> dict` [router.get('/accounts')]
- `create_account(payload: AccountIn) -> dict` [router.post('/accounts', dependencies=[Depends(verify_founder_action)])]
- `suggest_new_accounts() -> dict` [router.post('/accounts/suggest')] — Propose accounts from evidence nobody has claimed yet
- `update_account(rid: str, payload: dict) -> dict` [router.patch('/accounts/{rid}', dependencies=[Depends(verify_founder_action)])]
- `delete_account(rid: str) -> dict` [router.delete('/accounts/{rid}', dependencies=[Depends(verify_founder_action)])]
- `get_account(rid: str) -> dict` [router.get('/accounts/{rid}')]
- class `PipelineIn`(BaseModel)
- const `DEFAULT_PIPELINE_STAGES`
- `list_pipelines() -> list[dict]` [router.get('/pipelines')]
- `create_pipeline(payload: PipelineIn) -> dict` [router.post('/pipelines', dependencies=[Depends(verify_founder_action)])]
- class `OpportunityIn`(BaseModel)
- `list_opportunities(stage: str='', page: int=1, page_size: int=20) -> dict` [router.get('/opportunities')]
- `get_opportunity(rid: str) -> dict` [router.get('/opportunities/{rid}')]
- `update_pipeline(rid: str, payload: dict) -> dict` [router.patch('/pipelines/{rid}', dependencies=[Depends(verify_founder_action)])]
- `create_opportunity(payload: OpportunityIn) -> dict` [router.post('/opportunities', dependencies=[Depends(verify_founder_action)])]
- class `StageMove`(BaseModel)
- `move_opportunity(rid: str, payload: StageMove) -> dict` [router.post('/opportunities/{rid}/move', dependencies=[Depends(verify_founder_action)])]
- class `RuleIn`(BaseModel)
- `list_rules() -> list[dict]` [router.get('/rules')]
- `create_rule(payload: RuleIn) -> dict` [router.post('/rules', dependencies=[Depends(verify_founder_action)])]
- `qualify_account(rid: str) -> dict` [router.post('/accounts/{rid}/qualify')]
- class `ActivityIn`(BaseModel)
- `log_activity(payload: ActivityIn) -> dict` [router.post('/activities', dependencies=[Depends(verify_founder_action)])]
- const `CANONICAL_FIELDS`
- const `MAX_CSV_BYTES`
- const `MAX_CSV_ROWS`
- `list_imports() -> list[dict]` [router.get('/imports')]
- `async preview_import(entity_type: str='account', file: UploadFile=File(...)) -> dict` [router.post('/imports/preview', dependencies=[Depends(verify_founder_action)])]
- class `ImportCommit`(BaseModel)
- `commit_import(rid: str, payload: ImportCommit) -> dict` [router.post('/imports/{rid}/commit', dependencies=[Depends(verify_founder_action)])]
- const `CATALOG_ORDER`
- `integration_catalog() -> list[dict]` [router.get('/integrations')]
- class `ConnectIn`(BaseModel)
- `connect_provider(provider: str, payload: ConnectIn) -> dict` [router.post('/integrations/{provider}/connect', dependencies=[Depends(verify_founder_action)])]
- `disconnect_provider(provider: str) -> dict` [router.post('/integrations/{provider}/disconnect', dependencies=[Depends(verify_founder_action)])]
- `sync_provider(provider: str) -> dict` [router.post('/integrations/{provider}/sync', dependencies=[Depends(verify_founder_action)])]
- class `SessionIn`(BaseModel)
- `list_sessions() -> list[dict]` [router.get('/onboarding-sessions')]
- `create_session(payload: SessionIn) -> dict` [router.post('/onboarding-sessions', dependencies=[Depends(verify_founder_action)])]
- `update_session(rid: str, payload: dict) -> dict` [router.patch('/onboarding-sessions/{rid}', dependencies=[Depends(verify_founder_action)])]

### `app/companies_api.py`

- class `CompanyContact`(BaseModel)
- class `CompanySummary`(BaseModel)
- class `CompanyMetrics`(BaseModel)
- class `CompaniesPage`(BaseModel)
- class `CompanyDetail`(CompanySummary)
- `companies(page: int=Query(default=1, ge=1), page_size: int=Query(default=10, ge=1, le=100), q: str=Query(default='', max_length=200), industry: str=Query(default='', max_length=100), country: str=Query(default='', max_length=100), view: CompanyView='all', sort: CompanySort='recent')` [router.get('', response_model=CompaniesPage)]
- class `CompanyVerification`(BaseModel)
- `verify_company(domain: str=Query(default='', max_length=253), name: str=Query(default='', max_length=200))` [router.get('/verify/lookup', response_model=CompanyVerification)] — Free verification state for a prospect company. Read-only, no writes
- `company(company_id: str)` [router.get('/{company_id:path}', response_model=CompanyDetail)]

### `app/company_context_api.py`

- class `CompanyContextView`(RouteState) — The founder's canonical context plus the route resolved from its state
- `load_company_context() -> CompanyContext`
- `read_company_context()` [router.get('/context', response_model=CompanyContextView)]
- `replace_company_context(payload: CompanyContextSections)` [router.put('/context', response_model=CompanyContextView, dependencies=[Depends(verify_founder_action)])] — Replace the canonical context with the submitted sections

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

### `app/forms_api.py`

- `hosted_form(slug: str, request: Request, sent: int=0)` [public_router.get('/f/{slug}', response_class=HTMLResponse)]
- `async hosted_form_submit(slug: str, request: Request)` [public_router.post('/f/{slug}', response_class=HTMLResponse, dependencies=[Depends(rate_limit_intake)])]
- `booking_page(lead_id: str, request: Request)` [public_router.get('/book/{lead_id}', response_class=HTMLResponse)]
- `async booking_confirm(lead_id: str, request: Request)` [public_router.post('/book/{lead_id}', response_class=HTMLResponse, dependencies=[Depends(rate_limit_intake)])]
- `async external_form_intake(request: Request, x_company_core_lead_secret: str | None=Header(default=None, alias='X-Company-Core-Lead-Secret'))` [intake_router.post('/leads/form', dependencies=[Depends(rate_limit_intake)])] — Shared submission endpoint for external form tools
- class `FormFieldPayload`(BaseModel)
- class `FormCreatePayload`(BaseModel)
- class `FormUpdatePayload`(BaseModel)
- `intake_config() -> dict[str, Any]` [router.get('/config')] — Everything an external form tool needs, on one screen
- `list_forms()` [router.get('')]
- `create_form(payload: FormCreatePayload)` [router.post('', dependencies=[Depends(verify_founder_action)])]
- `update_form(slug: str, payload: FormUpdatePayload)` [router.patch('/{slug}', dependencies=[Depends(verify_founder_action)])]

### `app/marketing_api.py`

- `get_manual_post(post_id: str)` — Read a post inside the request's org boundary
- const `ROOT`
- class `ManualPostSessionRequest`(BaseModel)
- class `ManualPostPreviewRequest`(BaseModel)
- class `BufferScheduleRequest`(BaseModel)
- class `PublishRequest`(BaseModel)
- class `BufferAccountInfo`(BaseModel)
- class `BufferAccountsView`(BaseModel)
- class `BufferMetric`(BaseModel)
- class `BufferInsightsView`(BaseModel)
- class `MarketingOrgActionRecord`(BaseModel)
- class `MarketingOrgCreateResult`(BaseModel)
- class `MarketingOrgActiveResult`(BaseModel)
- class `OrgCapabilitiesResult`(BaseModel)
- class `ManualPostActionRecord`(BaseModel)
- class `ManualPostCreateResult`(BaseModel)
- class `ManualPostPreviewView`(BaseModel) — What a manual post will look like before anything is persisted
- class `BufferScheduleResult`(BaseModel)
- class `BufferSendConfirmation`(BaseModel)
- class `BufferConfirmResult`(BaseModel)
- const `BUFFER_ACCOUNT_RE`
- const `MAX_BUFFER_ACCOUNTS`
- const `PROJECTS_ROOT`
- `doctor()` [router.get('/doctor')]
- const `R2_MEDIA_KEYS`
- `preview_manual_post(payload: ManualPostPreviewRequest)` [router.post('/manual-posts/preview', response_model=ManualPostPreviewView)] — Preview the caption and tracking link a manual post will receive
- `create_manual_post_session(payload: ManualPostSessionRequest)` [router.post('/manual-posts/session')]
- `async upload_manual_post_asset(post_record_id: str, asset: UploadFile=File(...))` [router.post('/manual-posts/{post_record_id}/assets')]
- `finalize_manual_post(post_record_id: str)` [router.post('/manual-posts/{post_record_id}/finalize')]
- `async create_manual_post_from_ui(platform: str=Form(...), post_type: str=Form(default='carousel'), destination_url: str | None=Form(default=None), link_label: str | None=Form(default=None), org_id: int | None=Form(default=None), buffer_account: str | None=Form(default=None), publisher: str | None=Form(default=None), assets: list[UploadFile]=File(default=[]))` [router.post('/manual-posts', response_model=ManualPostCreateResult)]
- `publishers()` [router.get('/publishers')]
- `publisher_accounts(publisher: str | None=None)` [router.get('/publisher-accounts')]
- `publish_manual_post(post_record_id: str, payload: PublishRequest)` [router.post('/manual-posts/{post_record_id}/publish', dependencies=[Depends(verify_founder_action)])] — Schedule a finalized manual post through its configured publisher
- `queue_manual_post_publish(post_record_id: str, payload: PublishRequest, background_tasks: BackgroundTasks)` [router.post('/manual-posts/{post_record_id}/publish/async', status_code=202, dependencies=[Depends(verify_founder_action)])] — Queue a provider schedule so Cloudflare's ~125s edge timeout cannot
- `get_publish_job_status(job_id: str)` [router.get('/publish-jobs/{job_id}')]
- `draft_manual_post(post_record_id: str, payload: PublishRequest)` [router.post('/manual-posts/{post_record_id}/publish/draft')] — Create a provider draft. Buffer supports this; the webhook does not
- `confirm_manual_post_publish(post_record_id: str)` [router.post('/manual-posts/{post_record_id}/publish/confirm', dependencies=[Depends(verify_founder_action)])] — Ask the configured publisher for the fate of every saved provider post
- `manual_post_publish_insights(post_record_id: str, post_id: str | None=None)` [router.get('/manual-posts/{post_record_id}/publish/insights')]
- `buffer_accounts()` [router.get('/buffer-accounts', response_model=BufferAccountsView)] — Named Buffer accounts configured in g3.env (keys never leave the server)
- `manual_post_buffer_insights(post_record_id: str, post_id: str | None=None)` [router.get('/manual-posts/{post_record_id}/buffer-insights', response_model=BufferInsightsView)] — Read one saved Buffer post's provider state and optional personal-key metrics
- `confirm_manual_post_send(post_record_id: str)` [router.post('/manual-posts/{post_record_id}/buffer-confirm', response_model=BufferConfirmResult, dependencies=[Depends(verify_founder_action)])] — Ask Buffer for the fate of every scheduled post ID and persist the verdict
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

### `app/ratelimit.py`

- const `WINDOW_SECONDS`
- const `WEBHOOK_PATHS`
- `reset() -> None` — Drop all recorded hits (tests)
- `enabled() -> bool`
- `client_ip(request: Request) -> str`
- `rate_limit_intake(request: Request) -> None` — Router dependency for /integrations routes: webhooks and form intake
- `rate_limit_auth(request: Request) -> None` — Coarse per-IP budget for public signup, login, verify, and resend
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
- class `MeetingRequestPayload`(BaseModel)
- class `MeetingRequestResult`(BaseModel)
- `request_meeting(lead_id: str, payload: MeetingRequestPayload)` [action_router.post('/leads/{lead_id}/meeting-request', response_model=MeetingRequestResult, dependencies=[Depends(verify_founder_action)])] — Founder action: offer slots to the contact by email. The request is
- `suppress(lead_id: str, reason: str='founder_request')` [action_router.post('/leads/{lead_id}/suppress', dependencies=[Depends(verify_founder_action)])]
- class `InboxSyncPayload`(BaseModel)
- `sync_inbox(payload: InboxSyncPayload)` [action_router.post('/inbox/sync', dependencies=[Depends(verify_founder_action)])] — Founder action: mirror recent Resend received emails into inbound replies
- `hunter_account()` [router.get('/hunter/account')]

### `app/security.py`

- `require_operator() -> None` — Deployment-level engineering/monitor routes are not tenant features
- `authenticate(request: Request, credentials: HTTPBasicCredentials | None=Depends(security)) -> str`

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
- class `BufferAccountView`(BaseModel)
- class `BufferSetupAccountsView`(BaseModel)
- class `BufferChannelView`(BaseModel)
- class `BufferOrganizationView`(BaseModel)
- class `BufferDiscoveryView`(BaseModel)
- class `BufferDiscoverPayload`(BaseModel)
- class `BufferConnectPayload`(BaseModel)
- class `BufferConnectResult`(BaseModel)
- `buffer_setup_accounts()` [router.get('/buffer/accounts', response_model=BufferSetupAccountsView)]
- `discover_buffer_channels(payload: BufferDiscoverPayload, _: None=Depends(verify_founder_action))` [router.post('/buffer/discover', response_model=BufferDiscoveryView)]
- `connect_buffer_account(payload: BufferConnectPayload, _: None=Depends(verify_founder_action))` [router.post('/buffer/connect', response_model=BufferConnectResult)]

### `app/validation_api.py`

- class `WorkflowFromPlan`(BaseModel) — Optional plan to govern. Defaults to the most recent generated plan
- class `ApprovalPayload`(BaseModel)
- class `PlanHint`(BaseModel) — Founder-requested direction for plan generation. A request Hermes may
- class `SimulationRun`(BaseModel) — Execution request. `targets` are identifiers the founder chose at run
- `async create_validation_plan()` [router.post('/plan', response_model=ValidationPlanRecord, dependencies=[Depends(verify_founder_action)])] — Plan the first market-validation experiment. Nothing is executed
- `async create_workflows_validation_plan(hints: PlanHint | None=None)` [automation_router.post('/plan', response_model=ValidationPlanRecord, dependencies=[Depends(verify_founder_action)])] — Canonical automation name for plan creation. Same behavior as /plan above
- `read_validation_plan()` [router.get('/plan', response_model=ValidationPlanRecord)] — The most recent plan, or 404 when none has been generated yet
- `read_evidence() -> dict` [automation_router.get('/evidence')] — Everything the business has told or shown us, in one place
- `suggest_next_runs() -> dict` [automation_router.post('/suggest')] — Rank the next governed runs from evidence. Advisory only
- `read_workflows_validation_plan()` [automation_router.get('/plan', response_model=ValidationPlanRecord)] — Canonical automation name for reading the latest plan
- `read_governance()` [router.get('/workflow', response_model=GovernanceRecord, deprecated=True)] — Legacy name. Prefer GET /company/automation/governance
- `read_workflows_governance()` [automation_router.get('/governance', response_model=GovernanceRecord)] — The latest governance decision and the lifecycle it has reached
- `create_workflow_from_plan(payload: WorkflowFromPlan | None=None)` [router.post('/workflow', response_model=GovernanceRecord, dependencies=[Depends(verify_founder_action)], deprecated=True)] — Legacy name. Prefer POST /company/automation/governance
- `create_workflows_governance(payload: WorkflowFromPlan | None=None)` [automation_router.post('/governance', response_model=GovernanceRecord, dependencies=[Depends(verify_founder_action)])] — Validate a plan and, only if governance allows it, create the workflow
- `approve_workflow(payload: ApprovalPayload | None=None)` [router.post('/workflow/approve', response_model=GovernanceRecord, dependencies=[Depends(verify_founder_action)], deprecated=True)] — Legacy name. Prefer POST /company/automation/governance/approve
- `approve_workflows_governance(payload: ApprovalPayload | None=None)` [automation_router.post('/governance/approve', response_model=GovernanceRecord, dependencies=[Depends(verify_founder_action)])] — Record the founder's approval. Execution stays locked until this exists
- `run_workflow_from_plan(payload: SimulationRun | None=None)` [router.post('/workflow/run', response_model=GovernanceRecord, dependencies=[Depends(verify_founder_action)], deprecated=True)] — Legacy name. Prefer POST /company/automation/governance/run
- `run_workflows_governance(payload: SimulationRun | None=None)` [automation_router.post('/governance/run', response_model=GovernanceRecord, dependencies=[Depends(verify_founder_action)])] — Run the approved workflow through the existing runner
- class `AutomationWorkflowView`(BaseModel) — One governed workflow with its decision, plan link, and engine state
- `list_automation_workflows(limit: int=20)` [automation_router.get('/workflows', response_model=list[AutomationWorkflowView])] — All governed workflows, newest first, each with its engine document

### `app/workflow_views_api.py`

- class `ReplyItem`(BaseModel)
- class `RepliesPage`(BaseModel)
- `replies_view(page: int=Query(1, ge=1), page_size: int=Query(10, ge=1, le=50), q: str=Query('', max_length=200), view: Literal['all', 'latest', 'submissions', 'suppressed']='all', sort: Literal['recent', 'oldest', 'company']='recent')` [router.get('/replies', response_model=RepliesPage)]
- `reply_detail(reply_id: int)` [router.get('/replies/{reply_id}', response_model=ReplyItem)]
- class `MeetingMarker`(BaseModel)
- class `MeetingsPage`(BaseModel)
- `meetings_view(page: int=Query(1, ge=1), page_size: int=Query(10, ge=1, le=50), q: str=Query('', max_length=200), view: Literal['all', 'dated', 'undated', 'awaiting']='all', sort: Literal['recent', 'oldest', 'company']='recent')` [router.get('/meetings', response_model=MeetingsPage)]
- `meeting_detail(lead_id: str)` [router.get('/meetings/{lead_id}', response_model=MeetingMarker)]
- class `OutreachItem`(BaseModel)
- class `OutreachPage`(BaseModel)
- `outreach_view(page: int=Query(1, ge=1), page_size: int=Query(10, ge=1, le=50), q: str=Query('', max_length=200), status: str=Query('', max_length=40), sort: Literal['recent', 'oldest', 'company']='recent')` [router.get('/outreach', response_model=OutreachPage)]
- `outreach_detail(draft_id: str)` [router.get('/outreach/{draft_id}', response_model=OutreachItem)]
- class `ContentItem`(BaseModel)
- class `ContentView`(BaseModel)
- `content_view()` [router.get('/content', response_model=ContentView)]
- class `RecentContact`(BaseModel)
- class `HomeView`(RouteState)
- `home_view()` [router.get('/home', response_model=HomeView)]

### `app/workflows_api.py`

- class `WorkflowCreateRequest`(BaseModel)
- class `WorkflowRunRequest`(BaseModel)
- `create_workflow(payload: WorkflowCreateRequest)` [router.post('', response_model=Workflow, status_code=201, dependencies=[Depends(verify_founder_action)])]
- `list_workflows(limit: int=Query(50, ge=1, le=200), status: str | None=Query(None))` [router.get('', response_model=list[Workflow])]
- `get_workflow(workflow_id: str)` [router.get('/{workflow_id}', response_model=Workflow)]
- `run(workflow_id: str, payload: WorkflowRunRequest | None=None)` [router.post('/{workflow_id}/run', response_model=Workflow, dependencies=[Depends(verify_founder_action)])]
- `pause(workflow_id: str)` [router.post('/{workflow_id}/pause', response_model=Workflow, dependencies=[Depends(verify_founder_action)])]
- `get_state(workflow_id: str)` [router.get('/{workflow_id}/state', response_model=WorkflowState)]

### `app/workspace_api.py`

- class `SessionStatus`(BaseModel)
- `session_status()` [router.get('/session', response_model=SessionStatus)] — Validate dashboard Basic credentials without reading a product domain
- const `GROUP_CATEGORIES`
- const `GROUP_CAPABILITIES`
- class `ConnectionSummary`(BaseModel) — A canonical connection row, sans secrets. The registry owns state;
- class `ProviderAccountSummary`(BaseModel) — One named Buffer account, masked. Channels are the bound platforms
- class `ProviderGroup`(BaseModel)
- class `IntegrationsView`(BaseModel)
- `integrations_view()` [router.get('/integrations', response_model=IntegrationsView)]
- class `WorkspaceOrg`(BaseModel)
- class `PublicLink`(BaseModel)
- class `SettingsView`(BaseModel)
- `settings_view()` [router.get('/settings', response_model=SettingsView)]
- class `GovernanceLimitsView`(BaseModel)
- class `GovernanceLimitsPayload`(BaseModel)
- `limits_view()` [router.get('/limits', response_model=GovernanceLimitsView)]
- `save_limits(payload: GovernanceLimitsPayload)` [router.put('/limits', response_model=GovernanceLimitsView, dependencies=[Depends(verify_founder_action)])]
- class `QuotaItem`(BaseModel)
- class `QuotasView`(BaseModel)
- `quotas_view()` [router.get('/quotas', response_model=QuotasView)]
- class `WebhookConnectionPayload`(BaseModel)
- `publisher_connections_view()` [router.get('/publishers')]
- `save_webhook_connection(payload: WebhookConnectionPayload)` [router.put('/publishers/webhook', dependencies=[Depends(verify_founder_action)])]
- `delete_webhook_connection()` [router.delete('/publishers/webhook', dependencies=[Depends(verify_founder_action)])]

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

### `scripts/ingest_worlddata.py`

- const `ROOT`
- `ingest_edgar(limit: int) -> int`
- `ingest_commoncrawl(domains: list[str]) -> tuple[int, str]`
- `ingest_companieshouse(queries: list[str]) -> int`
- `main(argv: list[str] | None=None) -> int`

### `scripts/publisher_webhook_dev.py`

- const `SECRET`
- const `PORT`
- const `PATH`
- class `Handler`(BaseHTTPRequestHandler)
  - `do_POST(self) -> None`
  - `log_message(self, format: str, *args) -> None`

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

## HTTP routes

Extracted from route decorators, so a path served by two routers is listed once per router. The authoritative operation count is the OpenAPI contract (`/openapi.json`), which collapses these to unique path+method pairs.

| route | module |
|---|---|
| `DELETE /accounts/{rid}` | `app/commercial_api.py` |
| `DELETE /publishers/webhook` | `app/workspace_api.py` |
| `GET /` | `app/api.py` |
| `GET /accounts/{rid}` | `app/commercial_api.py` |
| `GET /accounts` | `app/commercial_api.py` |
| `GET /benchmarks` | `app/commercial_api.py` |
| `GET /book/{lead_id}` | `app/forms_api.py` |
| `GET /buffer-accounts` | `app/marketing_api.py` |
| `GET /buffer/accounts` | `app/setup_api.py` |
| `GET /calendar` | `app/api.py` |
| `GET /coding/tasks/{task_id}` | `app/company_ops_api.py` |
| `GET /coding/tasks` | `app/company_ops_api.py` |
| `GET /commercial/` | `app/api.py` |
| `GET /commercial` | `app/api.py` |
| `GET /companies/` | `app/api.py` |
| `GET /companies` | `app/api.py` |
| `GET /config` | `app/forms_api.py` |
| `GET /contacts/` | `app/api.py` |
| `GET /contacts` | `app/api.py` |
| `GET /content/` | `app/api.py` |
| `GET /content` | `app/api.py` |
| `GET /content` | `app/workflow_views_api.py` |
| `GET /context` | `app/company_context_api.py` |
| `GET /doctor` | `app/marketing_api.py` |
| `GET /doctor` | `app/sales_api.py` |
| `GET /drafts/reconcile` | `app/sales_api.py` |
| `GET /evidence` | `app/validation_api.py` |
| `GET /f/{slug}` | `app/forms_api.py` |
| `GET /governance` | `app/validation_api.py` |
| `GET /health` | `app/api.py` |
| `GET /home/` | `app/api.py` |
| `GET /home` | `app/api.py` |
| `GET /home` | `app/workflow_views_api.py` |
| `GET /hunter/account` | `app/sales_api.py` |
| `GET /icp-templates` | `app/commercial_api.py` |
| `GET /icps/suggest-criteria` | `app/commercial_api.py` |
| `GET /icps/{rid}` | `app/commercial_api.py` |
| `GET /icps` | `app/commercial_api.py` |
| `GET /imports` | `app/commercial_api.py` |
| `GET /incidents/{incident_id}` | `app/company_ops_api.py` |
| `GET /incidents` | `app/company_ops_api.py` |
| `GET /integrations/` | `app/api.py` |
| `GET /integrations` | `app/api.py` |
| `GET /integrations` | `app/commercial_api.py` |
| `GET /integrations` | `app/workspace_api.py` |
| `GET /leads/{lead_id}` | `app/sales_api.py` |
| `GET /leads` | `app/sales_api.py` |
| `GET /legacy/operations/marketing/assets` | `app/api.py` |
| `GET /legacy/operations/marketing/campaigns` | `app/api.py` |
| `GET /legacy/operations/marketing` | `app/api.py` |
| `GET /legacy/operations/sales/email` | `app/api.py` |
| `GET /legacy/operations` | `app/api.py` |
| `GET /limits` | `app/workspace_api.py` |
| `GET /manual-posts/{post_record_id}/assets/{asset_index}` | `app/marketing_api.py` |
| `GET /manual-posts/{post_record_id}/buffer-insights` | `app/marketing_api.py` |
| `GET /manual-posts/{post_record_id}/publish/insights` | `app/marketing_api.py` |
| `GET /manual-posts` | `app/marketing_api.py` |
| `GET /me` | `app/auth_api.py` |
| `GET /meet` | `app/api.py` |
| `GET /meetings/` | `app/api.py` |
| `GET /meetings/{lead_id}` | `app/workflow_views_api.py` |
| `GET /meetings` | `app/api.py` |
| `GET /meetings` | `app/workflow_views_api.py` |
| `GET /network-stats` | `app/commercial_api.py` |
| `GET /offers` | `app/commercial_api.py` |
| `GET /onboarding-sessions` | `app/commercial_api.py` |
| `GET /onboarding/` | `app/api.py` |
| `GET /onboarding` | `app/api.py` |
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
| `GET /opportunities/{rid}` | `app/commercial_api.py` |
| `GET /opportunities` | `app/commercial_api.py` |
| `GET /orgs/{org_id}/capabilities` | `app/marketing_api.py` |
| `GET /orgs` | `app/marketing_api.py` |
| `GET /outreach/` | `app/api.py` |
| `GET /outreach/{draft_id}` | `app/workflow_views_api.py` |
| `GET /outreach` | `app/api.py` |
| `GET /outreach` | `app/workflow_views_api.py` |
| `GET /pipelines` | `app/commercial_api.py` |
| `GET /plan` | `app/validation_api.py` |
| `GET /providers` | `app/setup_api.py` |
| `GET /public/manual-posts/{post_id}/assets/{index}` | `app/api.py` |
| `GET /publish-jobs/{job_id}` | `app/marketing_api.py` |
| `GET /publisher-accounts` | `app/marketing_api.py` |
| `GET /publishers` | `app/marketing_api.py` |
| `GET /publishers` | `app/workspace_api.py` |
| `GET /quotas` | `app/workspace_api.py` |
| `GET /replies/` | `app/api.py` |
| `GET /replies/{reply_id}` | `app/workflow_views_api.py` |
| `GET /replies` | `app/api.py` |
| `GET /replies` | `app/workflow_views_api.py` |
| `GET /research/` | `app/api.py` |
| `GET /research` | `app/api.py` |
| `GET /rules` | `app/commercial_api.py` |
| `GET /session` | `app/workspace_api.py` |
| `GET /settings/` | `app/api.py` |
| `GET /settings` | `app/api.py` |
| `GET /settings` | `app/workspace_api.py` |
| `GET /step` | `app/setup_api.py` |
| `GET /validation/` | `app/api.py` |
| `GET /validation` | `app/api.py` |
| `GET /verify/lookup` | `app/companies_api.py` |
| `GET /workflow` | `app/validation_api.py` |
| `GET /workflows/` | `app/api.py` |
| `GET /workflows` | `app/api.py` |
| `GET /workflows` | `app/validation_api.py` |
| `GET /{company_id:path}` | `app/companies_api.py` |
| `GET /{contact_id}` | `app/contacts_api.py` |
| `GET /{path:path}` | `app/api.py` |
| `GET /{provider}/callback` | `app/commercial_api.py` |
| `GET /{workflow_id}/state` | `app/workflows_api.py` |
| `GET /{workflow_id}` | `app/workflows_api.py` |
| `PATCH /accounts/{rid}` | `app/commercial_api.py` |
| `PATCH /icps/{rid}` | `app/commercial_api.py` |
| `PATCH /offers/{rid}` | `app/commercial_api.py` |
| `PATCH /onboarding-sessions/{rid}` | `app/commercial_api.py` |
| `PATCH /pipelines/{rid}` | `app/commercial_api.py` |
| `PATCH /{slug}` | `app/forms_api.py` |
| `POST /accounts/suggest` | `app/commercial_api.py` |
| `POST /accounts/{rid}/qualify` | `app/commercial_api.py` |
| `POST /accounts` | `app/commercial_api.py` |
| `POST /activities` | `app/commercial_api.py` |
| `POST /book/{lead_id}` | `app/forms_api.py` |
| `POST /buffer/connect` | `app/setup_api.py` |
| `POST /buffer/discover` | `app/setup_api.py` |
| `POST /coding/tasks/{task_id}/apply` | `app/company_ops_api.py` |
| `POST /coding/tasks` | `app/company_ops_api.py` |
| `POST /drafts/{draft_id}/approve` | `app/sales_api.py` |
| `POST /drafts/{draft_id}/reconcile` | `app/sales_api.py` |
| `POST /drafts/{draft_id}/send` | `app/sales_api.py` |
| `POST /drafts/{draft_id}/update` | `app/sales_api.py` |
| `POST /email/sales` | `app/sales_api.py` |
| `POST /f/{slug}` | `app/forms_api.py` |
| `POST /governance/approve` | `app/validation_api.py` |
| `POST /governance/run` | `app/validation_api.py` |
| `POST /governance` | `app/validation_api.py` |
| `POST /icps/{rid}/archive` | `app/commercial_api.py` |
| `POST /icps/{rid}/evaluate` | `app/commercial_api.py` |
| `POST /icps` | `app/commercial_api.py` |
| `POST /imports/preview` | `app/commercial_api.py` |
| `POST /imports/{rid}/commit` | `app/commercial_api.py` |
| `POST /inbox/sync` | `app/sales_api.py` |
| `POST /integrations/{provider}/connect` | `app/commercial_api.py` |
| `POST /integrations/{provider}/disconnect` | `app/commercial_api.py` |
| `POST /integrations/{provider}/sync` | `app/commercial_api.py` |
| `POST /keys/test` | `app/setup_api.py` |
| `POST /keys` | `app/setup_api.py` |
| `POST /leads/form` | `app/forms_api.py` |
| `POST /leads/tally` | `app/sales_api.py` |
| `POST /leads/website` | `app/sales_api.py` |
| `POST /leads/{lead_id}/discover-linkedin` | `app/sales_api.py` |
| `POST /leads/{lead_id}/draft-preview` | `app/sales_api.py` |
| `POST /leads/{lead_id}/draft` | `app/sales_api.py` |
| `POST /leads/{lead_id}/enrich` | `app/sales_api.py` |
| `POST /leads/{lead_id}/linkedin-draft` | `app/sales_api.py` |
| `POST /leads/{lead_id}/linkedin-preview` | `app/sales_api.py` |
| `POST /leads/{lead_id}/meeting-request` | `app/sales_api.py` |
| `POST /leads/{lead_id}/resolve-company` | `app/sales_api.py` |
| `POST /leads/{lead_id}/resolve-contact` | `app/sales_api.py` |
| `POST /leads/{lead_id}/schedule-meeting` | `app/sales_api.py` |
| `POST /leads/{lead_id}/suppress` | `app/sales_api.py` |
| `POST /leads` | `app/sales_api.py` |
| `POST /login` | `app/auth_api.py` |
| `POST /logout` | `app/auth_api.py` |
| `POST /manual-posts/preview` | `app/marketing_api.py` |
| `POST /manual-posts/session` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/ai-caption` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/assets` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/buffer-confirm` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/buffer-draft` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/buffer-schedule` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/finalize` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/org` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/publish/async` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/publish/confirm` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/publish/draft` | `app/marketing_api.py` |
| `POST /manual-posts/{post_record_id}/publish` | `app/marketing_api.py` |
| `POST /manual-posts` | `app/marketing_api.py` |
| `POST /monitor/run/{service}` | `app/company_ops_api.py` |
| `POST /monitor/run` | `app/company_ops_api.py` |
| `POST /network-contribution` | `app/commercial_api.py` |
| `POST /offers` | `app/commercial_api.py` |
| `POST /onboarding-sessions` | `app/commercial_api.py` |
| `POST /opportunities/{rid}/move` | `app/commercial_api.py` |
| `POST /opportunities` | `app/commercial_api.py` |
| `POST /orgs/active` | `app/marketing_api.py` |
| `POST /orgs/{org_id}/capabilities` | `app/marketing_api.py` |
| `POST /orgs` | `app/marketing_api.py` |
| `POST /pipelines` | `app/commercial_api.py` |
| `POST /plan` | `app/validation_api.py` |
| `POST /prospect/domain` | `app/sales_api.py` |
| `POST /research/leads` | `app/sales_api.py` |
| `POST /research/suggestions` | `app/sales_api.py` |
| `POST /resend/sales` | `app/sales_api.py` |
| `POST /resend` | `app/auth_api.py` |
| `POST /rules` | `app/commercial_api.py` |
| `POST /signup` | `app/auth_api.py` |
| `POST /step` | `app/setup_api.py` |
| `POST /suggest` | `app/validation_api.py` |
| `POST /verify` | `app/auth_api.py` |
| `POST /workflow/approve` | `app/validation_api.py` |
| `POST /workflow/run` | `app/validation_api.py` |
| `POST /workflow` | `app/validation_api.py` |
| `POST /{workflow_id}/pause` | `app/workflows_api.py` |
| `POST /{workflow_id}/run` | `app/workflows_api.py` |
| `PUT /context` | `app/company_context_api.py` |
| `PUT /limits` | `app/workspace_api.py` |
| `PUT /publishers/webhook` | `app/workspace_api.py` |

## CLI verbs

| verb | module |
|---|---|

## Database tables

| table | declared in |
|---|---|
| `auth_sessions` | `core/auth_store.py` |
| `buffer_org_accounts` | `core/state.py` |
| `buffer_orgs` | `core/state.py` |
| `coding_tasks` | `core/ops_store.py` |
| `commercial_accounts` | `core/commercial_store.py` |
| `commercial_activities` | `core/commercial_store.py` |
| `commercial_opportunities` | `core/commercial_store.py` |
| `commercial_pipelines` | `core/commercial_store.py` |
| `company_context_org` | `core/company_context.py` |
| `company_context` | `core/company_context.py` |
| `csv_imports` | `core/commercial_store.py` |
| `email_verifications` | `core/auth_store.py` |
| `form_definitions` | `core/form_store.py` |
| `icp_profiles` | `core/commercial_store.py` |
| `incidents` | `core/ops_store.py` |
| `integration_connections` | `core/commercial_store.py` |
| `integration_secrets` | `core/commercial_store.py` |
| `marketing_campaigns` | `core/marketing_store.py` |
| `marketing_events` | `core/marketing_store.py` |
| `marketing_manual_posts` | `core/marketing_store.py` |
| `marketing_variants` | `core/marketing_store.py` |
| `memories` | `core/memory.py` |
| `offer_profiles` | `core/commercial_store.py` |
| `onboarding_sessions` | `core/commercial_store.py` |
| `org_capabilities` | `core/state.py` |
| `org_memberships` | `core/auth_store.py` |
| `plan_inputs` | `core/plan_input.py` |
| `publish_jobs` | `core/jobs_store.py` |
| `publisher_connections` | `core/publishers_store.py` |
| `qualification_rules` | `core/commercial_store.py` |
| `sales_company_profiles_org` | `core/sales_store.py` |
| `sales_company_profiles` | `core/sales_store.py` |
| `sales_drafts` | `core/sales_store.py` |
| `sales_events` | `core/sales_store.py` |
| `sales_interactions` | `core/sales_store.py` |
| `sales_leads` | `core/sales_store.py` |
| `service_provider_requests` | `core/state.py` |
| `settings` | `core/state.py` |
| `tasks` | `core/state.py` |
| `usage_events` | `core/quotas.py` |
| `users` | `core/auth_store.py` |
| `validation_plans` | `core/validation_plan.py` |
| `validation_workflows` | `core/plan_governance.py` |
| `workflows` | `core/workflow_store.py` |
| `world_records` | `core/worlddata_store.py` |

## Regenerate

```bash
.venv/bin/python scripts/gen_api_reference.py
```
