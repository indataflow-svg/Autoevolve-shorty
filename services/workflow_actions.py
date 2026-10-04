"""Adapters that map workflow steps onto existing AutoEvolve capabilities.

Every action is a thin call into an existing system, never a re-implementation:

- ``g1_strategy``     -> ``services.marketing_worker.run_g1`` + Company Core campaign record
- ``generate_assets`` -> ``services.marketing_worker.run_media_pipeline`` (G2)
- ``publish``         -> ``services.marketing_worker.run_g3`` (G3 draft handoff)
- ``collect_results`` -> existing ``core.sales_store`` / ``core.marketing_store`` data
- ``evaluate``        -> deterministic v1 ranking over the G1 hypotheses (evolution seed)

Each action receives the accumulated workflow ``context`` and its own step
``config`` and returns a mapping shaped like ``core.workflow_store.StepResult``.
The runner resolves actions from this module at call time, so tests can
substitute the underlying service boundary without faking the architecture.
"""

from __future__ import annotations

from typing import Any

from core import marketing_store, sales_store, state
from services import marketing_worker


HYPOTHESIS_FIELDS = ("message", "audience", "angle", "offer", "creative_direction", "success_metric")

# G1's objective is a closed enum; the workflow objective is free-form business
# intent. Map the latter onto the former (never invent a G1 objective).
G1_OBJECTIVES = ("awareness", "education", "walkthrough", "trial")
DEFAULT_G1_OBJECTIVE = "awareness"


def _g1_objective(context: dict[str, Any], config: dict[str, Any]) -> str:
    candidate = str(config.get("objective") or context.get("objective") or "").strip().lower()
    if candidate in G1_OBJECTIVES:
        return candidate
    explicit = str(config.get("g1_objective") or context.get("g1_objective") or "").strip().lower()
    if explicit in G1_OBJECTIVES:
        return explicit
    return DEFAULT_G1_OBJECTIVE


def _campaign_id(context: dict[str, Any], config: dict[str, Any]) -> str:
    value = config.get("campaign_id") or context.get("campaign_id")
    if not value:
        raise RuntimeError("workflow step requires campaign_id (run the g1_strategy step first)")
    return str(value)


def _resolve_org_id(context: dict[str, Any], config: dict[str, Any]) -> int:
    raw = config.get("org_id") or context.get("org_id")
    if raw is not None:
        return int(raw)
    active = state.get_active_org()
    if not active:
        raise RuntimeError(
            "workflow requires org_id in the trigger config or an active org to run G1"
        )
    return int(active["id"])


def _hypothesis_from_concept(concept: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "id": str(concept.get("id") or f"hypothesis_{index + 1}"),
        "message": str(concept.get("hook") or concept.get("thesis") or "").strip(),
        "audience": str(concept.get("buyer") or "").strip(),
        "angle": str(concept.get("thesis") or concept.get("pain") or "").strip(),
        "offer": str(concept.get("cta") or "").strip(),
        "creative_direction": str(concept.get("narrative") or "").strip(),
        "success_metric": "conversion",
        "_scores": {
            "evidence_strength": concept.get("evidence_strength"),
            "buyer_relevance": concept.get("buyer_relevance"),
            "product_fit": concept.get("product_fit"),
        },
    }


def hypotheses_from_g1(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Map the existing G1 ``concepts`` (exactly three) into experiment hypotheses."""
    concepts = [item for item in (result.get("concepts") or []) if isinstance(item, dict)]
    hypotheses = [_hypothesis_from_concept(concept, index) for index, concept in enumerate(concepts)]
    if hypotheses:
        return hypotheses
    package = result.get("campaign") or {}
    return [{
        "id": "hypothesis_1",
        "message": str(package.get("narrative") or package.get("title") or "campaign direction"),
        "audience": str(package.get("buyer") or "ai_selected"),
        "angle": str(package.get("narrative") or ""),
        "offer": "",
        "creative_direction": "",
        "success_metric": "conversion",
        "_scores": {},
    }]


def _mean_score(scores: dict[str, Any]) -> float:
    values = [float(value) for value in scores.values() if isinstance(value, (int, float))]
    return sum(values) / len(values) if values else 0.0


def evaluate_hypotheses(
    hypotheses: list[dict[str, Any]],
    metrics: dict[str, Any],
    *,
    selected_id: str | None,
) -> dict[str, Any]:
    """Deterministic v1 evaluation: seed the feedback loop, no optimizer yet."""
    if not hypotheses:
        return {"winner": None, "losers": [], "metrics": metrics, "reason": "no hypotheses recorded", "next_action": None}
    ranked = sorted(
        hypotheses,
        key=lambda item: _mean_score(item.get("_scores") or {}),
        reverse=True,
    )
    winner = next((item for item in ranked if item.get("id") == selected_id), ranked[0])
    losers = [str(item.get("id")) for item in hypotheses if item.get("id") != winner.get("id")]
    target = metrics.get("target")
    measured = metrics.get("conversion")
    reached = isinstance(target, (int, float)) and isinstance(measured, (int, float)) and measured >= target
    return {
        "winner": winner.get("id"),
        "losers": losers,
        "metrics": metrics,
        "reason": (
            "selected hypothesis carried the measured campaign; ranked by G1 concept prior"
            if winner.get("id") == selected_id
            else "no selected hypothesis; ranked by G1 concept evidence/buyer-fit/product-fit prior"
        ),
        "next_action": "expand_winner" if reached else "create_variation",
    }


def g1_strategy(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Create a Company Core campaign record and run the existing G1 strategy."""
    org_id = _resolve_org_id(context, config)
    objective = _g1_objective(context, config)
    topic = str(config.get("topic") or context.get("topic") or context.get("objective") or "campaign direction")
    buyer = str(config.get("buyer") or context.get("buyer") or "ops_manager")
    platforms = list(config.get("social_platforms") or context.get("social_platforms") or ["instagram", "x"])
    video_platform = str(config.get("video_platform") or context.get("video_platform") or "shorts")
    request = str(config.get("request") or f"{context.get('workflow_id')}: {topic}")

    task = state.create_task(
        org_id=org_id, agent="growth", task_type="workflow_campaign", input_text=request,
    )
    campaign = marketing_store.create_campaign(
        org_id=org_id, task_id=task["id"], request=request, objective=objective,
        buyer=buyer, topic=topic, social_platforms=platforms, video_platform=video_platform,
    )
    fresh_research = bool(config.get("fresh_research", context.get("fresh_research", True)))
    result = marketing_worker.run_g1(campaign["id"], fresh_research=fresh_research)
    package = result.get("campaign") or {}
    if package.get("status") != "ready_for_media":
        raise RuntimeError(
            "G1 package did not pass the media gate; founder review is required before assets"
        )
    hypotheses = hypotheses_from_g1(result)
    selected = result.get("selected_concept") or {}
    artifacts = [{"type": "g1_package", "path": result.get("package_path")}]
    return {
        "status": "completed",
        "output": {
            "campaign_id": campaign["id"],
            "g1_campaign_id": package.get("campaign_id"),
            "hypotheses": hypotheses,
            "selected_hypothesis_id": str(selected.get("id") or ""),
        },
        "metrics": {"hypotheses": len(hypotheses)},
        "artifacts": artifacts,
        "next_step": "generate_assets",
    }


def generate_assets(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Run the existing G2 media pipeline and record the ready assets."""
    campaign_id = _campaign_id(context, config)
    marketing_worker.run_media_pipeline(campaign_id)
    campaign = marketing_store.get_campaign(campaign_id) or {}
    variants = [item for item in (campaign.get("variants") or []) if item.get("status") == "ready"]
    if not variants:
        raise RuntimeError(
            f"G2 produced no ready media variant (campaign status={campaign.get('status')!r})"
        )
    selected = campaign.get("selected_variant_id") or variants[0]["id"]
    if not campaign.get("selected_variant_id"):
        marketing_store.update_campaign(campaign_id, selected_variant_id=selected)
    assets = [
        {
            "variant_id": item["id"],
            "platform": item.get("platform"),
            "video_path": item.get("video_path"),
            "sha256": item.get("sha256"),
            "duration_seconds": item.get("duration_seconds"),
        }
        for item in variants
    ]
    artifacts = []
    if campaign.get("asset_manifest_path"):
        artifacts.append({"type": "asset_manifest", "path": campaign["asset_manifest_path"]})
    return {
        "status": "completed",
        "output": {
            "assets": assets,
            "selected_variant_id": selected,
            "asset_manifest_path": campaign.get("asset_manifest_path"),
        },
        "metrics": {"assets": len(assets)},
        "artifacts": artifacts,
        "next_step": "publish",
    }


def _publications(campaign: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    g3 = campaign.get("g3_result") or {}
    results = g3.get("results") if isinstance(g3, dict) else None
    publications = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        publications.append({
            "campaign_id": campaign.get("id"),
            "workflow_id": context.get("workflow_id"),
            "asset_variant_id": campaign.get("selected_variant_id"),
            "platform": item.get("platform"),
            "post_id": item.get("post_id"),
            "status": item.get("status"),
            "provider": g3.get("provider") if isinstance(g3, dict) else None,
            "publish_allowed": g3.get("publish_allowed") if isinstance(g3, dict) else None,
        })
    return publications


def publish(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Hand the selected asset to the existing G3 draft-publishing pipeline."""
    campaign_id = _campaign_id(context, config)
    campaign = marketing_store.get_campaign(campaign_id) or {}
    if not campaign.get("selected_variant_id"):
        raise RuntimeError("publish requires a selected media variant")
    marketing_worker.run_g3(campaign_id)
    campaign = marketing_store.get_campaign(campaign_id) or {}
    if campaign.get("g3_status") == "failed":
        raise RuntimeError(campaign.get("error") or "G3 publishing failed")
    publications = _publications(campaign, context)
    return {
        "status": "completed",
        "output": {
            "publications": publications,
            "g3_status": campaign.get("g3_status"),
            "g3_handoff_path": campaign.get("g3_handoff_path"),
        },
        "metrics": {"publications": len(publications)},
        "artifacts": [{"type": "g3_handoff", "path": campaign.get("g3_handoff_path")}],
        "next_step": "collect_results",
    }


_QUALIFIED_STAGES = {"qualified", "meeting", "meeting_scheduled", "opportunity"}
_MEETING_STAGES = {"meeting", "meeting_scheduled"}


def collect_results(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Collect available campaign + sales outcomes from the existing stores."""
    campaign_id = context.get("campaign_id")
    campaign = marketing_store.get_campaign(campaign_id) if campaign_id else {}
    metrics_config = context.get("success_metric") or {}

    summary = sales_store.summary()
    by_stage = summary.get("by_stage") or {}
    leads = int(summary.get("total") or 0)
    qualified = sum(int(count) for stage, count in by_stage.items() if stage in _QUALIFIED_STAGES)
    meetings = sum(int(count) for stage, count in by_stage.items() if stage in _MEETING_STAGES)
    publications = context.get("publications") or []
    variants = campaign.get("variants") or []

    results = {
        "campaign_id": campaign_id,
        "campaign_status": campaign.get("status"),
        "g3_status": campaign.get("g3_status"),
        "assets": len(variants),
        "publications": len(publications),
        "metrics": {
            "engagement": len(publications),
            "leads": leads,
            "qualified_leads": qualified,
            "meetings": meetings,
            "conversion": (qualified / leads) if leads else 0.0,
            "target": metrics_config.get("target"),
        },
    }
    return {
        "status": "completed",
        "output": {"results": results},
        "metrics": results["metrics"],
        "artifacts": [],
        "next_step": "evaluate",
    }


def evaluate(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Score the hypotheses and store the winner for the evolution loop."""
    hypotheses = [item for item in (context.get("hypotheses") or []) if isinstance(item, dict)]
    results = context.get("results") or {}
    metrics = results.get("metrics") or context.get("metrics") or {}
    selected_id = str(context.get("selected_hypothesis_id") or "") or None
    evaluation = evaluate_hypotheses(hypotheses, metrics, selected_id=selected_id)
    return {
        "status": "completed",
        "output": {"evaluation": evaluation},
        "metrics": metrics,
        "artifacts": [],
        "next_step": None,
    }


def simulate_outreach(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Simulate one validation outreach step. Nothing leaves this process.

    No provider is called, no lead is created, and no message is sent: the step
    records what the governed plan *would* do so the existing workflow runner can
    execute a workflow end to end without a real-world side effect. The output is
    deterministic (no clock, no randomness, no I/O), so the same plan always
    produces the same simulation.
    """
    supplied = [str(item) for item in (config.get("targets") or []) if str(item).strip()]
    max_contacts = int(config.get("max_contacts") or len(supplied))
    targets = supplied or [f"sim_target_{index + 1}" for index in range(max(0, max_contacts))]
    channel = str(config.get("channel") or "")
    message = str(config.get("message") or "")
    results = [
        {"prospect_id": prospect_id, "channel": channel, "status": "simulated",
         "delivered": False, "reply": None}
        for prospect_id in targets
    ]
    simulated = {
        "status": "simulated",
        "action": "outreach",
        "channel": channel,
        "targets": len(results),
        "sent": len(results),
        "replies": 0,
        "validation_events": 0,
        "external_side_effects": False,
        "message_present": bool(message.strip()),
        "results": results,
    }
    return {
        "status": "completed",
        "output": simulated,
        "metrics": {"targets": len(results), "sent": len(results), "validation_events": 0},
        "artifacts": [],
        "next_step": None,
    }
