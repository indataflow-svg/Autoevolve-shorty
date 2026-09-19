import json

import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel
from pydantic_ai import Agent

from agents.researcher import run_research
from agents.growth import prepare_campaign_brief

from core.models import cloud_model

from core.projects import (
    ensure_project,
    save_research,
)

from core.state import (
    init_db,
    get_active_org,
    create_task,
    update_task_status,
    complete_task,
    fail_task,
)
from core.marketing_store import create_campaign
from services.marketing_worker import spawn as spawn_marketing_worker


PROMPT = (
    Path(__file__).parent.parent
    / "prompts"
    / "founder.md"
).read_text()


class FounderDecision(BaseModel):
    action: Literal[
        "answer",
        "research",
        "future_coding",
        "future_marketing",
        "future_sales",
    ]

    reasoning: str

    task: str

    response: str

    org_name: Optional[str] = None

    use_active_org: bool = False

    priority: Literal[
        "low",
        "normal",
        "high",
    ] = "normal"

    requires_approval: bool = False


founder_agent = Agent(
    cloud_model("fast"),
    instructions=PROMPT,
    output_type=FounderDecision,
)


init_db()


async def run_founder(
    message: str,
):
    active_org = (
        get_active_org()
    )

    org_context = (
        json.dumps(
            active_org,
            indent=2,
        )
        if active_org
        else "No active org."
    )

    founder_prompt = f"""
Founder request:

{message}

CURRENT ACTIVE ORG:

{org_context}

Rules:

- If the request clearly continues the active org,
  set use_active_org=true.

- If this is a genuinely new initiative,
  set use_active_org=false and provide a concise
  org_name.

- org_name should describe the initiative itself.

GOOD:
Document Data Analysis

BAD:
Document Data Analysis Research Report

BAD:
Research About Document Data Analysis

Do not create a new org merely because the founder
asks another question about an existing org.
"""

    decision_result = (
        await founder_agent.run(
            founder_prompt
        )
    )

    decision = (
        decision_result.output
    )

    org_record = None
    org_path = None

    if (
        decision.use_active_org
        and active_org
    ):
        org_record = active_org

        org_path = (
            Path(__file__).parent.parent
            / "projects"
            / active_org["slug"]
        )

    elif decision.org_name:
        (
            org_record,
            org_path,
        ) = ensure_project(
            decision.org_name
        )

    if decision.action == "research":

        # Research should belong to an org.
        #
        # If the Founder failed to select one,
        # create a reasonable org from the task.
        if org_record is None:
            fallback_name = (
                decision.org_name
                or "General Research"
            )

            (
                org_record,
                org_path,
            ) = ensure_project(
                fallback_name
            )

        task = create_task(
            org_id=org_record["id"],
            agent="research",
            task_type="research",
            input_text=decision.task,
            priority=decision.priority,
            requires_approval=False,
        )

        update_task_status(
            task["id"],
            "running",
        )

        try:
            report = await run_research(
                decision.task
            )

            artifact = save_research(
                org_path,
                report.model_dump(),
            )

            task_output = json.dumps(
                {
                    "artifact": str(
                        artifact
                    ),
                    "decision": (
                        report.decision
                    ),
                    "summary": (
                        report.executive_summary
                    ),
                },
                ensure_ascii=False,
            )

            complete_task(
                task["id"],
                task_output,
            )

            return {
                "type": "research",

                "org": {
                    "id": org_record["id"],
                    "name": org_record["name"],
                    "slug": org_record["slug"],
                    "path": str(
                        org_path
                    ),
                },

                "task": {
                    "id": task["id"],
                    "agent": "research",
                    "status": "done",
                    "priority": (
                        decision.priority
                    ),
                },

                "artifact": str(
                    artifact
                ),

                "founder": (
                    decision.model_dump()
                ),

                "research": (
                    report.model_dump()
                ),
            }

        except Exception as exc:
            fail_task(
                task["id"],
                f"{type(exc).__name__}: {exc}",
            )

            raise

    if decision.action == "future_marketing":
        if org_record is None:
            (
                org_record,
                org_path,
            ) = ensure_project(
                decision.org_name
                or (active_org or {}).get("name")
                or os.getenv("COMPANY_NAME", "Company Core")
            )

        brief = await prepare_campaign_brief(
            decision.task or message,
            brand=(org_record or {}).get("slug") or (active_org or {}).get("slug"),
        )
        task = create_task(
            org_id=org_record["id"],
            agent="growth",
            task_type="campaign",
            input_text=brief.execution_summary,
            priority=decision.priority,
            requires_approval=False,
        )
        campaign = create_campaign(
            org_id=org_record["id"],
            task_id=task["id"],
            request=message,
            objective=brief.objective,
            buyer=brief.buyer,
            topic=brief.topic,
            social_platforms=brief.social_platforms,
            video_platform=brief.video_platform,
        )
        spawn_marketing_worker(campaign["id"])
        return {
            "type": "marketing_queued",
            "org": org_record,
            "campaign": {
                "id": campaign["id"],
                "status": "queued",
                "objective": brief.objective,
                "buyer": brief.buyer,
                "topic": brief.topic,
                "social_platforms": brief.social_platforms,
                "video_platform": brief.video_platform,
            },
            "founder": decision.model_dump(),
            "message": (
                "Campaign accepted. Growth, Media, and rendering now run in the "
                "background. Video variants will appear in the campaign review panel."
            ),
        }

    return {
        "type": decision.action,

        "org": (
            org_record
            if org_record
            else active_org
        ),

        "founder": (
            decision.model_dump()
        ),
    }
