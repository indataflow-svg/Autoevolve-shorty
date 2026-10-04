"""The canonical company context: shape, normalization, completeness, storage.

Onboarding answers become one durable, founder-confirmed object that later
components (workflow prompts, OmniRoute calls, Hermes) read directly instead of
scraping UI fields. This module owns three things:

- the sections (``company`` ... ``state``) and their practical field limits,
- normalization of raw answers: formatting is tidied and known states are mapped,
  but wording and business claims are never rewritten and a missing answer stays
  ``None``,
- persistence in the existing company database (``data/company.db``), reusing the
  ``core.state`` connection so there is no second company database.

Completeness is derived, never stored as a claim: ``status`` and ``missing`` are
recomputed on every validation so they cannot drift from the stored facts.
"""

# NOTE: no ``from __future__ import annotations`` here. The section models build
# their field types through the ``answer_text``/``answer_lines`` helpers below,
# and those expressions must be evaluated by pydantic, not left as source
# strings.

import json
import re
import sqlite3
from collections.abc import Mapping
from functools import partial
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, BeforeValidator, Field, ValidationError, model_validator

from core.state import connect, now_iso


MarketingStage = Literal["starting_from_zero"]
ContextStatus = Literal["context_complete", "context_incomplete"]

# Phase 1 records one starting point only. Later phases add branches here; the
# onboarding form and the API both read this mapping, so nothing else changes.
MARKETING_STAGES: dict[str, str] = {
    "starting_from_zero": "Starting from zero",
}

# Founder wording that means the same thing. Only genuine synonyms belong here;
# anything else is rejected instead of being stored as an unknown state.
_STAGE_SYNONYMS = {
    "zero": "starting_from_zero",
    "from_zero": "starting_from_zero",
    "fromzero": "starting_from_zero",
    "from_scratch": "starting_from_zero",
    "start_from_scratch": "starting_from_zero",
    "starting_from_nothing": "starting_from_zero",
    "nothing_yet": "starting_from_zero",
    "no_customers": "starting_from_zero",
    "no_customers_yet": "starting_from_zero",
    "brand_new": "starting_from_zero",
}

SCHEMA_VERSION = 1
CONTEXT_ROW_ID = 1

_WHITESPACE = re.compile(r"\s+")
_LIST_SPLIT = re.compile(r"[\n\r]+")
_STAGE_KEY = re.compile(r"[^a-z0-9]+")
# A plain hostname with an optional port. Anything with a space, an at sign, or a
# path separator is a sentence that happens to contain dots, not an address.
_HOSTNAME = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$|^localhost$", re.IGNORECASE)


def clean_text(value: Any, *, max_length: int | None = None) -> str | None:
    """Collapse whitespace and trim. Empty, blank, or non-text input is unknown."""
    if value is None or isinstance(value, bool):
        return None
    text = _WHITESPACE.sub(" ", str(value)).strip()
    if not text:
        return None
    if max_length is not None and len(text) > max_length:
        raise ValueError(f"answer is longer than {max_length} characters")
    return text


def clean_lines(value: Any, *, max_items: int | None = None) -> list[str]:
    """Accept a pasted one-per-line block or a list, dropping blanks and repeats.

    Splitting is line-based on purpose: commas are part of the founder's wording
    ("50-500 employees, EU only") and must survive normalization.
    """
    items = _LIST_SPLIT.split(value) if isinstance(value, str) else value if isinstance(value, (list, tuple)) else []
    lines: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = clean_text(item)
        if text is None:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        lines.append(text)
    if max_items is not None and len(lines) > max_items:
        raise ValueError(f"answer has more than {max_items} entries")
    return lines


def normalize_website(value: Any) -> str | None:
    """Return a clean public URL, or raise when the value is not an address.

    Credentials, query strings, and fragments are dropped because they can carry
    access tokens; the same rule the settings public links already follow.
    """
    text = clean_text(value)
    if not text:
        return None
    parts = urlsplit(text if "://" in text else f"https://{text}")
    try:
        port = parts.port
    except ValueError as exc:  # e.g. "https://example.com:not-a-port"
        raise ValueError(f"website is not a valid address: {text}") from exc
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError(f"website must be an http or https address: {text}")
    if parts.username or parts.password:
        raise ValueError("website must not contain credentials")
    if not _HOSTNAME.match(parts.hostname):
        raise ValueError(f"website must be an http or https address: {text}")
    host = parts.hostname.lower()
    return urlunsplit((parts.scheme.lower(), f"{host}:{port}" if port else host, parts.path.rstrip("/"), "", ""))


def normalize_marketing_stage(value: Any) -> str | None:
    """Map founder wording onto a known stage, or raise instead of guessing."""
    text = clean_text(value)
    if text is None:
        return None
    key = _STAGE_KEY.sub("_", text.casefold()).strip("_")
    if key in MARKETING_STAGES:
        return key
    if key in _STAGE_SYNONYMS:
        return _STAGE_SYNONYMS[key]
    supported = ", ".join(MARKETING_STAGES)
    raise ValueError(f"unknown marketing stage '{text}'. Supported in this phase: {supported}")


def answer_text(max_length: int) -> Any:
    """A trimmed free-text field. Blank input becomes unknown, never invented.

    The limit is enforced by ``clean_text`` rather than by field metadata so an
    explicit ``null`` stays a legal value: clients may clear any single answer.
    """
    return Annotated[
        str | None,
        BeforeValidator(partial(clean_text, max_length=max_length)),
        Field(default=None, json_schema_extra={"maxLength": max_length}),
    ]


def answer_lines(max_items: int) -> Any:
    """A bounded list field that accepts a pasted one-per-line block."""
    return Annotated[
        list[str],
        BeforeValidator(partial(clean_lines, max_items=max_items)),
        Field(default_factory=list, json_schema_extra={"maxItems": max_items}),
    ]


class CompanyFacts(BaseModel):
    """Who the company is."""

    name: answer_text(120)
    description: answer_text(3000)
    website: Annotated[
        str | None, BeforeValidator(normalize_website), Field(default=None)
    ]
    geography: answer_text(200)


class ProductFacts(BaseModel):
    """What the company sells."""

    name: answer_text(160)
    description: answer_text(3000)
    category: answer_text(160)
    value_proposition: answer_text(2000)


class CustomerFacts(BaseModel):
    """Who buys."""

    ideal_customer: answer_text(2000)
    industry: answer_text(200)
    company_size: answer_lines(10)
    geography: answer_lines(10)
    buyer_roles: answer_lines(12)


class MarketFacts(BaseModel):
    """The market, the problem, and what else is out there."""

    market: answer_text(200)
    segment: answer_text(500)
    problem: answer_text(2000)
    urgency: answer_text(1000)
    alternatives: answer_lines(20)


class EvidenceFacts(BaseModel):
    """Proof the founder already has. Empty lists mean "none yet", not "none exist"."""

    existing_customers: answer_lines(20)
    existing_demand: answer_lines(20)
    previous_marketing: answer_lines(20)
    testimonials: answer_lines(20)
    traction: answer_lines(20)
    other: answer_lines(20)


class OfferFacts(BaseModel):
    """The commercial offer."""

    description: answer_text(2000)
    pricing: answer_text(500)
    business_model: answer_text(500)


class ResourceFacts(BaseModel):
    """What is already available to market with."""

    channels: answer_lines(20)
    assets: answer_lines(20)
    team: answer_lines(20)
    budget: answer_text(500)


class ConstraintFacts(BaseModel):
    """Limits a future workflow must respect."""

    geographic: answer_lines(20)
    brand: answer_lines(20)
    budget: answer_lines(20)
    regulatory: answer_lines(20)
    operational: answer_lines(20)


class ObjectiveFacts(BaseModel):
    """The business outcome the founder is working towards."""

    primary_goal: answer_text(1000)
    desired_outcome: answer_text(2000)


class ContextState(BaseModel):
    """Where the company starts from. Phase 1 records the stage only."""

    marketing_stage: Annotated[
        MarketingStage | None,
        BeforeValidator(normalize_marketing_stage),
        Field(default=None),
    ]


# A group counts as known when the founder actually answered it. Group labels are
# what the API reports as missing, so they read as plain business language.
REQUIRED_GROUPS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("company.name",), "company"),
    (("product.name", "product.description"), "product"),
    (("customer.ideal_customer",), "customer"),
    (("market.problem",), "problem"),
    (("objective.primary_goal", "objective.desired_outcome"), "objective"),
    (("state.marketing_stage",), "marketing_stage"),
)


def _resolve(context: "CompanyContextSections", path: str) -> Any:
    value: Any = context
    for part in path.split("."):
        value = getattr(value, part)
    return value


def missing_required(context: "CompanyContextSections") -> list[str]:
    """Label every required group that is still unknown, in requirement order."""
    return [
        label
        for paths, label in REQUIRED_GROUPS
        if not any(_resolve(context, path) for path in paths)
    ]


class CompanyContextSections(BaseModel):
    """The founder-confirmed facts, grouped the way later consumers read them."""

    company: CompanyFacts = Field(default_factory=CompanyFacts)
    product: ProductFacts = Field(default_factory=ProductFacts)
    customer: CustomerFacts = Field(default_factory=CustomerFacts)
    market: MarketFacts = Field(default_factory=MarketFacts)
    evidence: EvidenceFacts = Field(default_factory=EvidenceFacts)
    offer: OfferFacts = Field(default_factory=OfferFacts)
    resources: ResourceFacts = Field(default_factory=ResourceFacts)
    constraints: ConstraintFacts = Field(default_factory=ConstraintFacts)
    objective: ObjectiveFacts = Field(default_factory=ObjectiveFacts)
    state: ContextState = Field(default_factory=ContextState)


class CompanyContext(CompanyContextSections):
    """The canonical company context.

    Every field is optional and every field is normalized on the way in, so this
    object can be built from raw onboarding answers, from an API payload, or from
    the stored record without behaving differently.
    """

    schema_version: int = SCHEMA_VERSION
    updated_at: answer_text(60)
    status: ContextStatus = "context_incomplete"
    missing: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _derive_completeness(self) -> "CompanyContext":
        self.missing = missing_required(self)
        self.status = "context_incomplete" if self.missing else "context_complete"
        return self


def normalize_company_context(raw: Mapping[str, Any] | None) -> CompanyContext:
    """Turn raw onboarding or API answers into the canonical context.

    Formatting is tidied, list blocks are split, websites are cleaned, and known
    states are mapped. Nothing is inferred: an answer the founder did not give
    stays ``None`` and shows up in ``missing``.
    """
    if raw is None:
        return CompanyContext()
    if not isinstance(raw, Mapping):
        raise TypeError("company context input must be a mapping of sections")
    return CompanyContext.model_validate(raw)


def has_any_fact(context: CompanyContextSections) -> bool:
    """True when at least one founder answer is known."""
    return any(
        _has_content(value)
        for value in context.model_dump(mode="json").values()
    )


def _has_content(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_has_content(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_content(item) for item in value)
    return bool(value)


# Confirmed onboarding answers mapped onto the canonical sections. The source
# keys are the onboarding confirm payload; `None` means the value comes from the
# first onboarding step instead.
_ONBOARDING_SECTIONS: dict[str, dict[str, str | None]] = {
    "company": {
        "name": "name", "description": "description",
        "website": "website", "geography": "geography",
    },
    "product": {
        "name": "product_name", "description": "product_description",
        "category": "product_category", "value_proposition": "positioning",
    },
    "customer": {
        "ideal_customer": "ideal_customer", "industry": "industry",
        "company_size": "company_sizes", "geography": "customer_geography",
        "buyer_roles": "buyer_roles",
    },
    "market": {
        "market": None, "segment": "segment", "problem": "problem",
        "urgency": "urgency", "alternatives": "alternatives",
    },
    "evidence": {
        "existing_customers": "existing_customers", "existing_demand": "existing_demand",
        "previous_marketing": "previous_marketing", "testimonials": "testimonials",
        "traction": "traction", "other": "other_evidence",
    },
    "offer": {
        "description": "offer_summary", "pricing": "pricing",
        "business_model": "business_model",
    },
    "resources": {
        "channels": "channels", "assets": "assets", "team": "team", "budget": "budget",
    },
    "constraints": {
        "geographic": "geographic_constraints", "brand": "brand_constraints",
        "budget": "budget_constraints", "regulatory": "regulatory_constraints",
        "operational": "operational_constraints",
    },
    "objective": {
        "primary_goal": None, "desired_outcome": "desired_outcome",
    },
    "state": {
        "marketing_stage": "marketing_stage",
    },
}


def context_from_onboarding(
    *, start: Mapping[str, Any], confirm: Mapping[str, Any]
) -> CompanyContext:
    """Project confirmed onboarding answers onto the canonical sections.

    The first step already owns the primary market and objective; everything
    else comes from the confirmed company step. Unanswered fields stay unknown.
    """
    step = dict(start or {})
    answers = dict(confirm or {})
    raw: dict[str, dict[str, Any]] = {
        section: {field: answers.get(source) for field, source in mapping.items() if source}
        for section, mapping in _ONBOARDING_SECTIONS.items()
    }
    raw["market"]["market"] = step.get("market")
    raw["objective"]["primary_goal"] = step.get("objective")
    return normalize_company_context(raw)


def init_context_db() -> None:
    """Create the single-row company context table (idempotent, as elsewhere)."""
    with connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS company_context (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                schema_version INTEGER NOT NULL DEFAULT 1,
                context_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def get_company_context() -> CompanyContext | None:
    """Load the stored context, or ``None`` when onboarding has not produced one."""
    init_context_db()
    with connect() as db:
        row = db.execute(
            "SELECT context_json FROM company_context WHERE id = ?", (CONTEXT_ROW_ID,)
        ).fetchone()
    if not row:
        return None
    try:
        return CompanyContext.model_validate(json.loads(row["context_json"]))
    except (json.JSONDecodeError, ValidationError, sqlite3.DatabaseError):
        # An unreadable record is treated as absent: the founder can re-enter it
        # through onboarding or the API instead of the dashboard failing to load.
        return None


def save_company_context(context: CompanyContextSections) -> CompanyContext:
    """Persist the canonical context and return exactly what was stored."""
    init_context_db()
    timestamp = now_iso()
    stored = CompanyContext.model_validate(
        {**context.model_dump(mode="json"), "updated_at": timestamp}
    )
    with connect() as db:
        db.execute(
            "INSERT INTO company_context (id, schema_version, context_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "schema_version = excluded.schema_version, context_json = excluded.context_json, "
            "updated_at = excluded.updated_at",
            (
                CONTEXT_ROW_ID,
                stored.schema_version,
                json.dumps(stored.model_dump(mode="json"), ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
    return stored


def clear_company_context() -> None:
    """Remove the stored record. Used by tests and future "start over" flows."""
    init_context_db()
    with connect() as db:
        db.execute("DELETE FROM company_context WHERE id = ?", (CONTEXT_ROW_ID,))


def get_recorded_marketing_stage() -> str | None:
    """The stored stage exactly as written, even if it no longer normalizes.

    Read models use this to explain a record whose stage this build cannot
    interpret. It never rewrites or defaults the value.
    """
    init_context_db()
    with connect() as db:
        row = db.execute(
            "SELECT context_json FROM company_context WHERE id = ?", (CONTEXT_ROW_ID,)
        ).fetchone()
    if not row:
        return None
    try:
        document = json.loads(row["context_json"])
        stage = document.get("state", {}).get("marketing_stage") if isinstance(document, dict) else None
    except (json.JSONDecodeError, AttributeError):
        return None
    return clean_text(stage) if isinstance(stage, str) else None