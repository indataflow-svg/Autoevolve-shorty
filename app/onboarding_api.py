"""First-run orchestration over the existing sales records and setup settings.

The read router is a typed projection. The setup router records user choices and
invokes existing provider/sales services; it does not create another CRM store.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from app.sales_api import verify_founder_action
from core.company_read import get_company_record
from core.sales_store import get_draft, get_lead, merge_lead_metadata, normalize_company_domain
from core.state import get_onboarding_program, save_onboarding_program
from services.sales_service import build_draft, import_domain, research_market_leads

read_router = APIRouter(prefix="/company/ui", tags=["onboarding"])
write_router = APIRouter(prefix="/company/setup/onboarding", tags=["onboarding"])

Rating = Literal["good", "maybe", "bad"]
Reason = Literal[
    "wrong_industry", "too_small", "too_large", "wrong_geography",
    "wrong_buyer", "weak_signal", "existing_customer", "other",
]
Channel = Literal["email", "linkedin", "social"]


class CompanyStart(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    website: HttpUrl
    objective: str = Field(min_length=3, max_length=300)
    market: str = Field(min_length=2, max_length=120)


class CompanyContext(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    website: HttpUrl
    description: str = Field(min_length=10, max_length=3000)
    industry: str = Field(min_length=2, max_length=120)
    positioning: str = Field(min_length=5, max_length=1000)
    offer_summary: str = Field(min_length=5, max_length=1000)


class Icp(BaseModel):
    industry: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=10, max_length=1200)
    company_sizes: list[str] = Field(default_factory=list, max_length=10)


class StrategyInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    objective: str = Field(min_length=3, max_length=300)
    success_metric: str = Field(min_length=3, max_length=300)
    offers: list[str] = Field(min_length=1, max_length=8)
    icp: Icp
    buyer_titles: list[str] = Field(min_length=1, max_length=12)
    markets: list[str] = Field(min_length=1, max_length=12)
    positive_signals: list[str] = Field(min_length=1, max_length=12)
    exclusions: list[str] = Field(default_factory=list, max_length=20)
    tone: str = Field(min_length=3, max_length=300)
    approved_claims: list[str] = Field(default_factory=list, max_length=20)
    prohibited_claims: list[str] = Field(default_factory=list, max_length=20)
    channels: list[Channel] = Field(min_length=1, max_length=3)


class ApprovalPolicy(BaseModel):
    outbound_send_requires_approval: bool = True
    linkedin_manual: bool = True
    publishing_requires_approval: bool = True
    enrichment_after_qualification: bool = True
    followup_generation_allowed: bool = True
    followup_send_requires_approval: bool = True


class ProviderLimits(BaseModel):
    research_per_provider: int = 3
    sample_size: int = 10
    buyers_per_company: int = 1
    enrichment_batch: int = 1


class Feedback(BaseModel):
    rating: Rating
    reason: Reason | None = None


class FeedbackEntry(Feedback):
    lead_id: str


class CalibrationInput(BaseModel):
    feedback: list[FeedbackEntry] = Field(min_length=1, max_length=10)


class RefinementProposal(BaseModel):
    exclusions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RefinementDecision(BaseModel):
    approved: bool


class BuyerRequest(BaseModel):
    candidate_lead_id: str
    provider: Literal["hunter", "apollo"] = "hunter"
    existing_contact_id: str | None = None


class DraftRequest(BaseModel):
    candidate_lead_id: str


class ProgramState(BaseModel):
    id: str
    status: str
    company: CompanyStart
    company_research: dict | None = None
    research_provider: str | None = None
    research_error: str | None = None
    company_context: CompanyContext | None = None
    strategy: StrategyInput | None = None
    approval_policy: ApprovalPolicy = Field(default_factory=ApprovalPolicy)
    provider_limits: ProviderLimits = Field(default_factory=ProviderLimits)
    calibration_status: str = "not_started"
    sample_lead_ids: list[str] = Field(default_factory=list)
    feedback: dict[str, Feedback] = Field(default_factory=dict)
    proposed_refinement: RefinementProposal | None = None
    refinement_decision: Literal["pending", "approved", "rejected"] | None = None
    buyer_leads: dict[str, str] = Field(default_factory=dict)
    draft_ids: dict[str, str] = Field(default_factory=dict)
    research_warnings: list[str] = Field(default_factory=list)
    activated_at: str | None = None


class CalibrationCandidate(BaseModel):
    lead_id: str
    company_id: str
    name: str
    domain: str | None = None
    country: str | None = None
    industry: str | None = None
    lead_score: int
    confidence_band: Literal["high", "medium", "borderline"]
    feedback: Feedback | None = None
    buyer_lead_id: str | None = None
    draft_id: str | None = None


class OnboardingView(BaseModel):
    program: ProgramState | None
    next_step: str
    sample: list[CalibrationCandidate]
    confidence_basis: str = "Existing lead_score only; not a verified ICP fit score."


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _confidence_band(score: int) -> Literal["high", "medium", "borderline"]:
    return "high" if score >= 70 else "medium" if score >= 35 else "borderline"


def _program() -> ProgramState | None:
    raw = get_onboarding_program()
    return ProgramState.model_validate(raw) if raw else None


def _save(program: ProgramState) -> OnboardingView:
    save_onboarding_program(program.model_dump(mode="json"))
    return _view(program)


def _required() -> ProgramState:
    program = _program()
    if not program:
        raise HTTPException(409, "enter company details before continuing onboarding")
    if program.activated_at:
        raise HTTPException(409, "the first-run program is already active")
    return program


def _good_ids(program: ProgramState) -> list[str]:
    return [lead_id for lead_id in program.sample_lead_ids
            if program.feedback.get(lead_id) and program.feedback[lead_id].rating == "good"]


def _next_step(program: ProgramState | None) -> str:
    if not program:
        return "company"
    if program.activated_at:
        return "home"
    if not program.company_context:
        return "confirm_company" if program.company_research else "research_company"
    if not program.strategy:
        return "strategy"
    if not program.sample_lead_ids:
        return "search"
    if len(program.feedback) < len(program.sample_lead_ids):
        return "calibrate"
    if not program.refinement_decision:
        return "refinement"
    good = _good_ids(program)
    if not good:
        return "search"
    if any(lead_id not in program.buyer_leads for lead_id in good):
        return "buyers"
    if any(lead_id not in program.draft_ids for lead_id in good):
        return "drafts"
    return "activate"


def _view(program: ProgramState | None) -> OnboardingView:
    sample = []
    if program:
        for lead_id in program.sample_lead_ids:
            lead = get_lead(lead_id)
            if not lead:
                continue
            domain = normalize_company_domain(lead.get("company_domain"))
            company_id = f"domain:{domain}" if domain else f"lead:{lead_id}"
            company = get_company_record(company_id)
            score = int(lead.get("lead_score") or 0)
            sample.append(CalibrationCandidate(
                lead_id=lead_id, company_id=company_id,
                name=lead.get("company") or lead.get("full_name") or "Unnamed company",
                domain=domain, country=lead.get("country"),
                industry=company.get("industry") if company else None,
                lead_score=score,
                confidence_band=_confidence_band(score),
                feedback=program.feedback.get(lead_id),
                buyer_lead_id=program.buyer_leads.get(lead_id),
                draft_id=program.draft_ids.get(lead_id),
            ))
    return OnboardingView(program=program, next_step=_next_step(program), sample=sample)


@read_router.get("/onboarding", response_model=OnboardingView)
def onboarding_view():
    return _view(_program())


@write_router.post("/company", response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])
def start_company(payload: CompanyStart):
    program = _program()
    if program and program.activated_at:
        raise HTTPException(409, "the first-run program is already active")
    if program and program.company_context:
        raise HTTPException(409, "company context is confirmed; edit the strategy instead")
    value = ProgramState(id=program.id if program else f"program_{uuid.uuid4().hex[:12]}",
                         status="setup_started", company=payload)
    return _save(value)


@write_router.post("/research-company", response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])
def research_company():
    program = _required()
    if program.company_context:
        raise HTTPException(409, "company context is already confirmed")
    domain = normalize_company_domain(str(program.company.website))
    providers = []
    if os.getenv("CE_API_KEY"):
        providers.append("companyenrich")
    if os.getenv("PDL_API_KEY"):
        providers.append("pdl")
    if not providers:
        program.research_error = "No company enrichment provider is configured. Enter verified company context manually."
        _save(program)
        raise HTTPException(409, program.research_error)
    errors = []
    for provider in providers:
        try:
            if provider == "companyenrich":
                from services.company_enrich import CompanyEnrichClient
                client = CompanyEnrichClient()
                payload = client.enrich_company(domain)
            else:
                from services.pdl import PeopleDataLabsClient
                client = PeopleDataLabsClient()
                payload = client.enrich_company(domain)
            summary = client.extract_company_profile(payload)
            if not summary.get("description") and not summary.get("name"):
                raise ValueError("provider returned no usable company facts")
            program.company_research = summary
            program.research_provider = provider
            program.research_error = None
            program.status = "company_researched"
            return _save(program)
        except Exception as exc:  # provider isolation; no invented company facts
            errors.append(f"{provider}: {exc}")
    program.research_error = "; ".join(errors)
    _save(program)
    raise HTTPException(502, f"company research failed: {program.research_error}")


@write_router.post("/company/confirm", response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])
def confirm_company(payload: CompanyContext):
    program = _required()
    requested = normalize_company_domain(str(program.company.website))
    confirmed = normalize_company_domain(str(payload.website))
    if requested != confirmed:
        raise HTTPException(422, "confirmed website must match the company being researched")
    program.company_context = payload
    program.status = "company_confirmed"
    return _save(program)


@write_router.post("/strategy", response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])
def confirm_strategy(payload: StrategyInput):
    program = _required()
    if not program.company_context:
        raise HTTPException(409, "confirm the company context first")
    if "email" not in payload.channels:
        raise HTTPException(422, "email is required for first outreach drafts")
    if program.sample_lead_ids:
        raise HTTPException(409, "calibration has started; complete it before changing the strategy")
    program.strategy = payload
    program.status = "strategy_confirmed"
    return _save(program)


@write_router.post("/search", response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])
def first_search():
    program = _required()
    if not program.strategy:
        raise HTTPException(409, "confirm the strategy before research")
    if program.sample_lead_ids and _good_ids(program):
        raise HTTPException(409, "complete the current calibration before a new search")
    try:
        result = research_market_leads(
            industry=program.strategy.icp.industry,
            location=program.strategy.markets[0],
            limit_per_provider=program.provider_limits.research_per_provider,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"first company search failed: {exc}") from exc
    if not result["results"] and result["warnings"] and len(result["warnings"]) == len(result["providers"]):
        raise HTTPException(502, "company search providers returned no records: " + "; ".join(result["warnings"]))
    ids = []
    for item in result["results"]:
        lead = item.get("lead") if isinstance(item, dict) else None
        metadata = lead.get("metadata") if isinstance(lead, dict) else None
        if isinstance(metadata, dict) and metadata.get("company_candidate") is True and lead.get("id") not in ids:
            ids.append(lead["id"])
    # Represent each band that actually exists in the provider result before filling
    # remaining slots. This never invents a confidence score or extra company.
    by_band = {band: [] for band in ("high", "medium", "borderline")}
    for lead_id in ids:
        lead = get_lead(lead_id)
        if lead:
            by_band[_confidence_band(int(lead.get("lead_score") or 0))].append(lead_id)
    selected = [by_band[band][0] for band in by_band if by_band[band]]
    ids = (selected + [lead_id for lead_id in ids if lead_id not in selected])[:program.provider_limits.sample_size]
    program.sample_lead_ids = ids
    program.feedback = {}
    program.proposed_refinement = None
    program.refinement_decision = None
    program.buyer_leads = {}
    program.draft_ids = {}
    program.research_warnings = result["warnings"]
    program.calibration_status = "started" if ids else "not_started"
    program.status = "calibration_started" if ids else "strategy_confirmed"
    return _save(program)


def _proposal(program: ProgramState) -> RefinementProposal:
    exclusions: list[str] = []
    notes: list[str] = []
    for lead_id, feedback in program.feedback.items():
        if feedback.rating != "bad" or not feedback.reason:
            continue
        lead = get_lead(lead_id)
        if not lead:
            continue
        company = get_company_record(f"domain:{normalize_company_domain(lead.get('company_domain'))}")
        if feedback.reason == "wrong_geography" and lead.get("country"):
            exclusions.append(f"country:{lead['country']}")
        elif feedback.reason == "wrong_industry" and company and company.get("industry"):
            exclusions.append(f"industry:{company['industry']}")
        else:
            notes.append(f"Review {lead.get('company') or lead_id}: {feedback.reason.replace('_', ' ')}")
    return RefinementProposal(exclusions=sorted(set(exclusions)), notes=notes)


@write_router.post("/calibration", response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])
def record_calibration(payload: CalibrationInput):
    program = _required()
    if not program.sample_lead_ids:
        raise HTTPException(409, "run the first company search before calibration")
    for item in payload.feedback:
        if item.lead_id not in program.sample_lead_ids:
            raise HTTPException(422, f"{item.lead_id} is not in the saved calibration sample")
        if item.rating != "bad" and item.reason:
            raise HTTPException(422, "rejection reasons apply only to bad companies")
        program.feedback[item.lead_id] = Feedback(rating=item.rating, reason=item.reason)
    program.refinement_decision = None
    if len(program.feedback) == len(program.sample_lead_ids):
        program.proposed_refinement = _proposal(program)
        program.calibration_status = "reviewed"
        program.status = "calibration_review"
    return _save(program)


@write_router.post("/refinement", response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])
def decide_refinement(payload: RefinementDecision):
    program = _required()
    if not program.sample_lead_ids or len(program.feedback) != len(program.sample_lead_ids):
        raise HTTPException(409, "classify every sampled company first")
    if payload.approved and program.proposed_refinement and program.strategy:
        program.strategy.exclusions = sorted(set(program.strategy.exclusions + program.proposed_refinement.exclusions))
    program.refinement_decision = "approved" if payload.approved else "rejected"
    program.calibration_status = "approved" if payload.approved else "rejected"
    program.status = "calibration_approved"
    return _save(program)


@write_router.post("/buyer", response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])
def resolve_buyer(payload: BuyerRequest):
    program = _required()
    candidate_id = payload.candidate_lead_id
    if not program.refinement_decision or candidate_id not in _good_ids(program):
        raise HTTPException(409, "buyer resolution requires an approved company and completed calibration")
    candidate = get_lead(candidate_id)
    domain = normalize_company_domain(candidate.get("company_domain") if candidate else None)
    if not domain:
        raise HTTPException(409, "the approved company has no domain for contact lookup")
    if candidate_id in program.buyer_leads:
        return _view(program)
    if payload.existing_contact_id:
        lead = get_lead(payload.existing_contact_id)
        if not lead or normalize_company_domain(lead.get("company_domain")) != domain:
            raise HTTPException(422, "existing contact must belong to the approved company domain")
    else:
        try:
            results = import_domain(domain, limit=1, provider=payload.provider)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"buyer lookup failed: {exc}") from exc
        lead = results[0].get("lead") if results else None
    if not lead or not lead.get("email") or lead.get("stage") == "suppressed":
        raise HTTPException(409, "no eligible email contact was confirmed for this company")
    if (lead.get("metadata") or {}).get("company_candidate") is True:
        raise HTTPException(409, "a company candidate is not a buyer contact")
    merge_lead_metadata(lead["id"], {"onboarding_program_id": program.id})
    program.buyer_leads[candidate_id] = lead["id"]
    program.status = "contacts_ready" if len(program.buyer_leads) == len(_good_ids(program)) else "buyers_started"
    return _save(program)


@write_router.post("/draft", response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])
async def create_first_draft(payload: DraftRequest):
    program = _required()
    candidate_id = payload.candidate_lead_id
    if candidate_id not in _good_ids(program) or candidate_id not in program.buyer_leads:
        raise HTTPException(409, "resolve an approved company's buyer before drafting")
    if candidate_id in program.draft_ids:
        return _view(program)
    try:
        draft = await build_draft(program.buyer_leads[candidate_id])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"first draft failed: {exc}") from exc
    if not draft.get("id") or draft.get("status") != "draft":
        raise HTTPException(502, "sales service did not confirm a saved draft")
    program.draft_ids[candidate_id] = draft["id"]
    program.status = "drafts_ready" if len(program.draft_ids) == len(_good_ids(program)) else "drafts_started"
    return _save(program)


@write_router.post("/activate", response_model=OnboardingView, dependencies=[Depends(verify_founder_action)])
def activate_program():
    program = _required()
    if _next_step(program) != "activate":
        raise HTTPException(409, "complete company calibration, buyer lookup, and first drafts before activation")
    for candidate_id in _good_ids(program):
        buyer_id = program.buyer_leads[candidate_id]
        draft = get_draft(program.draft_ids[candidate_id])
        if not draft or draft.get("lead_id") != buyer_id or draft.get("status") != "draft":
            raise HTTPException(409, "a saved first draft is missing or no longer in draft state")
    program.activated_at = _now()
    program.status = "activated"
    return _save(program)
