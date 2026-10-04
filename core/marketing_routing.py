"""The single decision point that turns company state into an initial route.

Layer boundary (implementation.md §13): :mod:`core.company_context` owns *what
the founder confirmed*; this module owns only *what AutoEvolve should do next*.
Nothing here executes anything, calls a provider, or creates a workflow: a route
is a state, and the workflow layer is entered later, explicitly.

This phase ships one branch:

    starting_from_zero -> market_validation

Adding the second branch later is one registry entry plus one member in
``NextStage``; no caller changes. An unsupported or unrecorded stage raises
:class:`UnsupportedMarketingStage` instead of silently defaulting to the first
branch, so a company can never be routed by guesswork.
"""

from typing import Literal

from pydantic import BaseModel

from core.company_context import MarketingStage

# What AutoEvolve does next. Phase 1 of the roadmap only. A later phase adds
# "campaign_optimization" for companies that already run campaigns.
NextStage = Literal["market_validation"]


class UnsupportedMarketingStage(ValueError):
    """Raised when a company state has no route. Never replaced by a default."""


class InitialRoute(BaseModel):
    """A resolved route: the founder's starting stage and the next state."""

    marketing_stage: MarketingStage
    next_stage: NextStage
    label: str
    summary: str


# The whole registry. `starting_from_zero` means the company has no marketing
# motion yet, so AutoEvolve's first responsibility is to validate the strongest
# initial commercial hypothesis before anything is published.
INITIAL_ROUTES: tuple[InitialRoute, ...] = (
    InitialRoute(
        marketing_stage="starting_from_zero",
        next_stage="market_validation",
        label="Market Validation",
        summary="AutoEvolve is preparing your first market-validation experiment.",
    ),
)


class RouteState(BaseModel):
    """Flat routing fields for typed API views (context route, onboarding, home)."""

    marketing_stage: MarketingStage | None = None
    next_stage: NextStage | None = None
    route_label: str | None = None
    route_summary: str | None = None
    routing_error: str | None = None

    @classmethod
    def resolved(cls, route: InitialRoute) -> "RouteState":
        return cls(
            marketing_stage=route.marketing_stage,
            next_stage=route.next_stage,
            route_label=route.label,
            route_summary=route.summary,
        )

    @classmethod
    def unresolved(cls, error: str | None = None) -> "RouteState":
        """No route is claimed. Either nothing is decided yet, or it failed."""
        return cls(routing_error=error)


def route_for_stage(stage: str | None) -> InitialRoute:
    """Return the route for one starting stage, or explain why there is none."""
    if not stage:
        raise UnsupportedMarketingStage(
            "marketing_stage is not recorded yet; complete onboarding to set a starting state"
        )
    for route in INITIAL_ROUTES:
        if route.marketing_stage == stage:
            return route
    supported = ", ".join(route.marketing_stage for route in INITIAL_ROUTES)
    raise UnsupportedMarketingStage(
        f"no initial route for marketing_stage {stage!r}; supported in this phase: {supported}"
    )


def resolve_initial_route(context: object | None) -> InitialRoute:
    """Route a stored company context. Raises instead of guessing a branch.

    ``context`` is a :class:`core.company_context.CompanyContext`. It is typed
    loosely so a caller cannot accidentally pass an unvalidated mapping: a plain
    mapping has no ``state`` and is rejected below.
    """
    if context is None:
        raise LookupError("no company context is stored; complete onboarding first")
    state = getattr(context, "state", None)
    if state is None:
        raise LookupError("company context has no recorded state; complete onboarding first")
    return route_for_stage(state.marketing_stage)


def route_state_for(context: object | None) -> RouteState:
    """Resolve a context into flat routing fields, or state why there is no route.

    This is what read models use. A company that has not recorded a starting
    state yet simply has no route (not an error), while a stage that exists but
    is not supported reports the reason instead of inventing one.
    """
    stage = getattr(getattr(context, "state", None), "marketing_stage", None)
    if not stage:
        return RouteState.unresolved()
    try:
        return RouteState.resolved(resolve_initial_route(context))
    except UnsupportedMarketingStage as exc:
        return RouteState.unresolved(str(exc))


def stored_route_state() -> RouteState:
    """Routing state for the persisted company.

    Every read model calls this rather than resolving routes itself, so one place
    decides what a company's state means. A record whose stored stage this build
    cannot interpret (an older or newer vocabulary) reports the reason instead of
    being routed as if it were the first branch. These two readers are imported
    here to keep storage out of the callers.
    """
    from core.company_context import get_company_context, get_recorded_marketing_stage

    resolved = route_state_for(get_company_context())
    if resolved.next_stage or resolved.routing_error:
        return resolved
    recorded = get_recorded_marketing_stage()
    if not recorded:
        return resolved
    try:
        return RouteState.resolved(route_for_stage(recorded))
    except UnsupportedMarketingStage as exc:
        return RouteState.unresolved(str(exc))