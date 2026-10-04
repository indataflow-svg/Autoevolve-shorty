"""Model-agnostic AI creative director (template-4 phases 3 and 21).

Every role calls the same generic interface; OmniRoute chooses the actual
model, so the application never branches on provider names::

    CreativeDirector (role)
    ├── creative_direction  -> reasoning route
    ├── storyboarding       -> reasoning route
    ├── prompt_compilation  -> fast route
    ├── asset_selection     -> fast route
    ├── visual_review       -> vision route
    ├── continuity_review   -> vision route
    └── revision            -> reasoning route

Structured outputs are pydantic models validated before use (the same
pattern as ``services/asset_scene_planner.py``): AI output can never reach
GPU rendering without passing schema validation. All roles raise
``DirectorUnavailable`` when no model router key is configured instead of
failing obscurely; deterministic callers treat that as "AI assist skipped".
"""
from __future__ import annotations

import asyncio
from typing import Any, TypeVar

from pydantic import BaseModel

from core.models import cloud_model, is_model_configured

ROLE_ROUTES = {
    "creative_direction": "reasoning",
    "storyboarding": "reasoning",
    "prompt_compilation": "fast",
    "asset_selection": "fast",
    "visual_review": "vision",
    "continuity_review": "vision",
    "revision": "reasoning",
}

OutputModel = TypeVar("OutputModel", bound=BaseModel)


class DirectorUnavailable(RuntimeError):
    """Raised when an AI director role needs a model router key."""


def require_director() -> None:
    if not is_model_configured():
        raise DirectorUnavailable(
            "Model router is not configured. Set OMNIROUTE_API_KEY in .env. "
            "Deterministic planning continues without AI assistance."
        )


class CreativeDirector:
    """One director role (e.g. ``storyboarding``) backed by an OmniRoute route."""

    def __init__(
        self,
        role: str,
        *,
        instructions: str,
        retries: int = 2,
        output_validator: Any = None,
    ) -> None:
        if role not in ROLE_ROUTES:
            raise ValueError(f"unknown director role: {role!r}")
        self.role = role
        self.route = ROLE_ROUTES[role]
        self.instructions = instructions
        self.retries = retries
        self.output_validator = output_validator

    def run(
        self,
        prompt: str,
        output_model: type[OutputModel],
    ) -> OutputModel:
        """Run the role synchronously; returns a validated output model."""
        require_director()
        from pydantic_ai import Agent

        agent = Agent(
            cloud_model(self.route),
            output_type=output_model,
            instructions=self.instructions,
            retries=self.retries,
        )
        if self.output_validator is not None:
            agent.output_validator(self.output_validator)
        result = asyncio.run(agent.run(prompt))
        return result.output


def director_available(role: str | None = None) -> bool:
    """True when the model router is configured (per-role check is the same)."""
    if role is not None and role not in ROLE_ROUTES:
        raise ValueError(f"unknown director role: {role!r}")
    return is_model_configured()
