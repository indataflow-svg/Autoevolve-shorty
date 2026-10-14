"""Hermes: the AutoEvolve intelligence boundary for planning.

Hermes is the only component that talks to a model. It receives the canonical
CompanyContext plus one versioned workflow prompt and returns a validated
structured plan. It is deliberately **reason → plan**, never reason → act:

- no tools, toolsets, or external accounts are registered on the agent, so it
  cannot publish, message, spend, or schedule anything;
- the only model access is the existing OmniRoute gateway via
  :func:`core.models.cloud_model`, so there is one provider path in the product;
- the output type is a closed pydantic schema, so prose is never parsed later;
- nothing here executes. Acting on a plan is a later phase behind limiters and
  approval.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from core.company_context import CompanyContext
from core.models import ROUTES, cloud_model, require_model_configured
from core.validation_plan import (
    WORKFLOW_TEMPLATE,
    GroundingReport,
    PlanProvenance,
    ValidationPlan,
    enforce_grounding,
)

PROMPT_DIR = Path(__file__).parent.parent / "prompts"
PROMPT_PATH = PROMPT_DIR / "market_validation_v1.md"
PROMPT_VERSION = WORKFLOW_TEMPLATE
CONTEXT_TOKEN = "{{COMPANY_CONTEXT}}"
MODEL_ROUTE = "reasoning"
PROVIDER_NAME = "omniroute"
PLAN_TIMEOUT_SECONDS = 180

REQUEST = (
    "Produce the market validation plan for the company context supplied above. "
    "Return the structured plan only."
)


class HermesError(RuntimeError):
    """Hermes could not produce a plan."""


class HermesOutputError(HermesError):
    """The model returned something that is not a valid structured plan."""


class HermesPlanResult(BaseModel):
    """A plan plus the provenance needed to judge where it came from."""

    plan: ValidationPlan
    provenance: PlanProvenance
    grounding: GroundingReport


def load_prompt_template() -> str:
    """Read the versioned prompt file. Prompts are data, not Python strings."""
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_instructions(
    context: CompanyContext,
    method_hint: str | None = None,
    channel_hint: str | None = None,
) -> str:
    """Render the base prompt with the canonical context substituted in.

    The context is passed as canonical JSON rather than prose so the model reads
    the same representation every downstream component will. An explicit
    founder hint is appended as a request the model may decline with reasons;
    it never edits the versioned prompt file and never overrides the output.
    """
    template = load_prompt_template()
    if CONTEXT_TOKEN not in template:
        raise HermesError(f"prompt {PROMPT_PATH.name} is missing the {CONTEXT_TOKEN} token")
    payload = json.dumps(context.model_dump(mode="json"), ensure_ascii=False, indent=2)
    instructions = template.replace(CONTEXT_TOKEN, payload)
    requests = []
    if (method_hint or "").strip():
        requests.append(
            f"The founder requests the {method_hint.strip()} validation method. "
            "Use it if the context supports it; otherwise choose the method the "
            "context does support and explain why in reasoning."
        )
    if (channel_hint or "").strip():
        requests.append(
            f"The founder requests the {channel_hint.strip()} channel. "
            "Use it if the context supports it; otherwise choose the channel the "
            "context does support and explain why in reasoning."
        )
    if requests:
        instructions += "\n\nFOUNDER REQUEST\n\n" + "\n".join(requests) + "\n"
    return instructions


async def plan_market_validation(
    context: CompanyContext,
    method_hint: str | None = None,
    channel_hint: str | None = None,
) -> HermesPlanResult:
    """Run one market-validation pass and return a validated, grounded plan."""
    require_model_configured()
    from pydantic_ai import Agent

    model = cloud_model(MODEL_ROUTE)
    # Built per call so a key or route change takes effect without a reload.
    hermes = Agent(model, instructions=build_instructions(context, method_hint, channel_hint), output_type=ValidationPlan)
    try:
        result = await asyncio.wait_for(hermes.run(REQUEST), timeout=PLAN_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        raise HermesOutputError(
            f"Hermes did not return within {PLAN_TIMEOUT_SECONDS} seconds"
        ) from exc
    except HermesError:
        raise
    except Exception as exc:
        raise HermesOutputError(f"{type(exc).__name__}: {exc}") from exc

    plan = _coerce_plan(result.output)
    plan, grounding = enforce_grounding(plan, context)
    return HermesPlanResult(
        plan=plan,
        provenance=_provenance(context, model, method_hint, channel_hint),
        grounding=grounding,
    )


def _coerce_plan(output: Any) -> ValidationPlan:
    """Accept only a real structured plan; never assemble a partial one."""
    if isinstance(output, ValidationPlan):
        return output
    if isinstance(output, dict):
        try:
            return ValidationPlan.model_validate(output)
        except ValueError as exc:
            raise HermesOutputError(f"model output failed plan validation: {exc}") from exc
    raise HermesOutputError(
        f"model returned {type(output).__name__}, expected a structured validation plan"
    )


def _provenance(
    context: CompanyContext,
    model: Any,
    method_hint: str | None = None,
    channel_hint: str | None = None,
) -> PlanProvenance:
    """Record the prompt version and the model actually used, when available."""
    return PlanProvenance(
        prompt_version=PROMPT_VERSION,
        prompt_path=f"prompts/{PROMPT_PATH.name}",
        context_updated_at=context.updated_at,
        model_route=MODEL_ROUTE,
        model_name=str(getattr(model, "model_name", ROUTES[MODEL_ROUTE])),
        # The gateway name, never the configured base URL: provenance is shown in
        # the UI and must not publish an internal endpoint.
        model_provider=PROVIDER_NAME,
        method_hint=(method_hint or None),
        channel_hint=(channel_hint or None),
    )