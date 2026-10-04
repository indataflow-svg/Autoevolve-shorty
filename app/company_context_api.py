"""Canonical company context endpoints over the existing onboarding store.

Reading returns the normalized context that onboarding produced (or an empty,
explicitly-incomplete context before onboarding runs) together with the initial
route AutoEvolve resolved for it. Writing replaces that canonical record. Writes
require the founder action token like every other founder-only mutation; reads
require dashboard authentication.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.sales_api import verify_founder_action
from core.company_context import (
    CompanyContext,
    CompanyContextSections,
    ContextStatus,
    context_from_onboarding,
    get_company_context,
    has_any_fact,
    save_company_context,
)
from core.marketing_routing import RouteState, stored_route_state
from core.state import get_onboarding_program

router = APIRouter(prefix="/company", tags=["company-context"])


class CompanyContextView(RouteState):
    """The founder's canonical context plus the route resolved from its state."""

    context: CompanyContext
    status: ContextStatus


def load_company_context() -> CompanyContext:
    """Return the stored context, backfilling from an already-confirmed program.

    Programs confirmed before this layer existed hold the same founder answers in
    the onboarding record, so an existing company is projected into the
    canonical context once instead of being asked to type it again.
    """
    stored = get_company_context()
    if stored:
        return stored
    program = get_onboarding_program()
    confirmed = program.get("company_context") if isinstance(program, dict) else None
    if not isinstance(confirmed, dict):
        return CompanyContext()
    try:
        return save_company_context(context_from_onboarding(
            start=program.get("company") or {}, confirm=confirmed,
        ))
    except ValueError:
        # A stored answer that no longer normalizes is left to the founder to
        # re-enter rather than being repaired by guessing.
        return CompanyContext()


def _context_view(context: CompanyContext) -> CompanyContextView:
    """Attach the initial route resolved from the stored company's state.

    A company that has not reached a starting state yet simply has no route, and
    an unsupported state reports the reason rather than being routed by guesswork.
    """
    return CompanyContextView(
        context=context,
        status=context.status,
        **stored_route_state().model_dump(),
    )


@router.get("/context", response_model=CompanyContextView)
def read_company_context():
    # load_company_context() returns the stored record, backfills an existing
    # confirmed program once, or reports an empty context before onboarding.
    return _context_view(load_company_context())


@router.put("/context", response_model=CompanyContextView, dependencies=[Depends(verify_founder_action)])
def replace_company_context(payload: CompanyContextSections):
    """Replace the canonical context with the submitted sections.

    Omitted fields become explicitly unknown: this is a full replacement, so a
    founder never keeps a claim they just removed.
    """
    if not has_any_fact(payload):
        raise HTTPException(422, "provide at least one company context fact")
    return _context_view(save_company_context(payload))