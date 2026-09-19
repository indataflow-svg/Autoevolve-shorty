from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from agents.sales import COMPANY_DESCRIPTION, COMPANY_NAME
from core.models import cloud_model


class LinkedInInvite(BaseModel):
    note: str = Field(min_length=3, max_length=300)
    rationale: str = Field(min_length=3, max_length=300)


class LinkedInDM(BaseModel):
    text: str = Field(min_length=20, max_length=1000)
    rationale: str = Field(min_length=3, max_length=300)


PIECES = ("invite", "dm1", "dm2")

_piece_instructions = {
    "invite": (
        "Write a LinkedIn connection-request note of at most 300 characters. "
        "Open with the person's first name, add exactly one grounded observation "
        "from the company context, and close with a plain reason to connect. "
        "No pitch, no link, no fake familiarity."
    ),
    "dm1": (
        "Write a first LinkedIn direct message of at most 120 words for an existing "
        "connection. One grounded observation, one relevance question, one soft "
        "call to action. No link, no pitch deck language, no fake urgency."
    ),
    "dm2": (
        "Write a short LinkedIn follow-up bump of at most 80 words. Reference a "
        "fresh angle from the company context, keep one low-pressure question. "
        "No link unless the lead already engaged."
    ),
}


def _agent_for(piece: str) -> Agent:
    if piece == "invite":
        return Agent(
            cloud_model("fast"),
            instructions=(
                f"You write LinkedIn connection notes for {COMPANY_NAME}: {COMPANY_DESCRIPTION}. "
                "Use only the supplied lead facts and company context. Never invent "
                "familiarity, metrics, customers, or product capabilities. Plain English."
            ),
            output_type=LinkedInInvite,
        )
    return Agent(
        cloud_model("fast"),
        instructions=(
            f"You write LinkedIn direct messages for {COMPANY_NAME}: {COMPANY_DESCRIPTION}. "
            "Use only the supplied lead facts and company context. Never invent "
            "familiarity, metrics, customers, or product capabilities. If company_context "
            "is present, ground one observation in its operational focus, specialties, "
            "or pain points. Plain English, conversational, no email formalities."
        ),
        output_type=LinkedInDM,
    )


async def draft_linkedin_outreach(lead: dict, piece: str) -> LinkedInInvite | LinkedInDM:
    if piece not in _piece_instructions:
        raise ValueError("linkedin piece must be invite, dm1, or dm2")
    safe = {
        key: lead.get(key)
        for key in (
            "full_name", "job_title", "company", "company_domain", "country",
            "source", "source_detail", "campaign_id", "message", "lead_score",
            "contact_profile", "company_context",
        )
    }
    result = await _agent_for(piece).run(
        _piece_instructions[piece] + " Lead facts:\n" + repr(safe)
    )
    return result.output
