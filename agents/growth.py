from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from core.models import cloud_model


class CampaignBrief(BaseModel):
    objective: Literal["awareness", "education", "walkthrough", "trial"] = "awareness"
    buyer: str = Field(min_length=2, max_length=80)
    topic: str = Field(min_length=5, max_length=300)
    social_platforms: list[Literal["instagram", "x"]] = Field(min_length=1, max_length=2)
    video_platform: Literal["shorts", "tiktok", "youtube"] = "shorts"
    execution_summary: str = Field(min_length=5, max_length=240)


PROMPT = (Path(__file__).parent.parent / "prompts" / "growth.md").read_text(encoding="utf-8")

growth_agent = Agent(
    cloud_model("reasoning"),
    instructions=PROMPT,
    output_type=CampaignBrief,
)


async def prepare_campaign_brief(request: str, brand: str | None = None) -> CampaignBrief:
    memory_note = _brand_memory_note(brand, request)
    result = await growth_agent.run(
        "Create an executable campaign brief from this founder request:\n\n" + request + memory_note
    )
    brief = result.output
    brief.buyer = brief.buyer.strip().lower().replace(" ", "_")
    brief.social_platforms = list(dict.fromkeys(brief.social_platforms))
    return brief


def _brand_memory_note(brand: str | None, request: str) -> str:
    """Best-effort brand lessons/wins so briefs evolve with sales outcomes."""
    try:
        if not brand:
            return ""
        from core.memory import recall

        hits = recall(brand.strip().lower(), request[:300], limit=3)
        if not hits:
            return ""
        lines = [f"- {(h.get('title') or h.get('kind'))}: {(h.get('text') or '')[:280]}" for h in hits]
        return "\nBrand memory (same brand, past sales/marketing outcomes — respect it):\n" + "\n".join(lines) + "\n"
    except Exception:
        return ""
