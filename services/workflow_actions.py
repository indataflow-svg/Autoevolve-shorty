"""Adapters that map workflow steps onto the remaining AutoEvolve capabilities.

Every action is a thin call into an existing system, never a re-implementation:

- ``simulate_outreach``   -> deterministic, side-effect-free validation step
- ``draft_outreach``      -> ``core.sales_store.create_draft`` (founder review)
- ``research_prospects``  -> provider research, candidates stored locally
- ``send_outreach``       -> approved drafts through the production send path

Campaign/media actions were removed with the G1/G2 lanes. Each action receives
the accumulated workflow ``context`` and its own step ``config`` and returns a
mapping shaped like ``core.workflow_store.StepResult``.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from core import sales_store, state
from core.validation_plan import ValidationEventObservation

# Sales events that count as the plan's validation outcome.
VALIDATION_EVENT_NAMES = ("lead.replied", "meeting.scheduled")


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
        # Deliberately None and never 0: a simulation observes nothing, so it
        # must not report a measured zero. The score stays unscored until
        # observe_validation_events() consults a real evidence source.
        "validation_events": None,
        "external_side_effects": False,
        "message_present": bool(message.strip()),
        "results": results,
    }
    return {
        "status": "completed",
        "output": simulated,
        # metrics carries numeric aggregates only; validation_events is an
        # observation attached after the run, not a number this step can sum.
        "metrics": {"targets": len(results), "sent": len(results)},
        "artifacts": [],
        "next_step": None,
    }


def draft_outreach(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Create real outreach drafts for the plan's targets. Nothing is sent.

    A draft is local state: the founder reviews and sends it through the
    existing approved-send path, so this step cannot contact anyone by itself.
    It exists so an experiment produces an artifact, and so the events it
    records carry the plan and workflow ids that make later evidence
    attributable — a count with nothing behind it is not a measurement.

    Targets are lead ids. An id with no stored lead is skipped and reported
    rather than invented, so a mistyped target list can never become a phantom
    prospect. ``max_contacts`` is a hard ceiling: this step writes real records,
    so it under-produces rather than over-produces, and an absent ceiling
    drafts nothing.
    """
    channel = str(config.get("channel") or "email")
    message = str(config.get("message") or "").strip()
    if not message:
        raise ValueError("draft_outreach requires the plan's message")
    call_to_action = str(config.get("call_to_action") or "").strip()
    offer = str(config.get("offer") or "").strip()
    subject = (
        str(config.get("subject") or "").strip() or call_to_action or offer or "Following up"
    )[:200]

    plan_id = str(context.get("plan_id") or "")
    workflow_id = str(context.get("workflow_id") or "")
    targets = [str(item) for item in (config.get("targets") or []) if str(item).strip()]
    ceiling = int(config.get("max_contacts") or 0)
    within = targets[:ceiling] if ceiling > 0 else []

    drafted: list[str] = []
    skipped: list[str] = []
    for lead_id in within:
        if sales_store.get_lead(lead_id) is None:
            skipped.append(lead_id)
            continue
        draft = sales_store.create_draft(lead_id, subject=subject, body=message, channel=channel)
        # Attribution is what makes the run measurable later: without it the
        # evidence store cannot separate this experiment's events from
        # anyone else's, and unrelated meetings would be credited to it.
        sales_store.add_event(lead_id, "outreach.plan_attributed", {
            "plan_id": plan_id,
            "workflow_id": workflow_id,
            "draft_id": draft["id"],
            "channel": channel,
        })
        drafted.append(draft["id"])

    return {
        "status": "completed",
        "output": {
            "action": "draft_outreach",
            "channel": channel,
            "targets": len(targets),
            "within_limit": len(within),
            "drafts_created": len(drafted),
            "skipped": skipped,
            "sent": 0,
            "replies": 0,
            # Nothing is sent and nothing was observed here: null, not 0.
            "validation_events": None,
            "external_side_effects": False,
            "draft_ids": drafted,
        },
        "metrics": {"targets": len(targets), "sent": 0, "drafts_created": len(drafted)},
        "artifacts": [],
        "next_step": None,
    }


def research_prospects(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Research named companies through the provider ladder. Reads only.

    Terms come from evidence (see ``core.evidence.resolve_research_terms``),
    fixed in the step config at validate time so the audit shows exactly what
    was searched. Suppliers are tried in registry order until ``max_contacts``
    unique candidates are held; providers past the target are logged as
    skipped instead of spending credits. Provider functions store candidates
    as research leads, the same rows interactive research creates; this step
    attributes at most ``max_contacts`` new ones to the plan and counts the
    rest as known or over-ceiling. No prospect is contacted: ``sent`` stays 0
    and nothing observed here is reported as a measured event.
    """
    from services.sales_service import waterfall_company_search

    industry = str(config.get("industry") or "").strip()
    if not industry:
        raise ValueError("research_prospects requires the resolved industry")
    location = str(config.get("location") or "").strip() or None
    ceiling = int(config.get("max_contacts") or 0)
    plan_id = str(context.get("plan_id") or "")
    workflow_id = str(context.get("workflow_id") or "")
    org_id = int(context.get("org_id") or 0)

    if ceiling <= 0:
        return {
            "status": "completed",
            "output": {
                "action": "research_prospects",
                "industry": industry,
                "location": location,
                "providers_queried": {},
                "candidates_found": 0,
                "candidates_new": 0,
                "attributed": 0,
                "skipped_known": 0,
                "over_ceiling": 0,
                "sent": 0,
                "replies": 0,
                "validation_events": None,
                "external_side_effects": False,
            },
            "metrics": {"candidates_new": 0, "provider_calls": 0},
            "artifacts": [],
            "next_step": None,
        }

    limit_per_provider = max(1, min(5, (ceiling + 2) // 3))
    summary = waterfall_company_search(
        industry=industry, location=location, target=ceiling,
        limit_per_provider=limit_per_provider, org_id=org_id)
    providers_queried = dict(summary.get("providers") or {})
    results = summary.get("results") or []

    with state.connect() as connection:
        try:
            known_domains = {
                str(r["domain"]).strip().lower()
                for r in connection.execute(
                    "SELECT domain FROM commercial_accounts "
                    "WHERE org_id=? AND domain IS NOT NULL", (org_id,))
                if str(r["domain"]).strip()
            }
        except Exception:
            known_domains = set()

    attributed = 0
    skipped_known = 0
    over_ceiling = 0
    for item in results:
        lead = item.get("lead") if isinstance(item, dict) else None
        if not isinstance(lead, dict) or not lead.get("id"):
            continue
        domain = str(lead.get("company_domain") or "").strip().lower()
        if not item.get("created", True) or domain in known_domains:
            skipped_known += 1
            continue
        if attributed >= ceiling:
            over_ceiling += 1
            continue
        sales_store.add_event(lead["id"], "outreach.plan_attributed", {
            "plan_id": plan_id,
            "workflow_id": workflow_id,
            "source": "governed_research",
            "industry": industry,
            "location": location,
        })
        attributed += 1

    return {
        "status": "completed",
        "output": {
            "action": "research_prospects",
            "industry": industry,
            "location": location,
            "industry_source": config.get("industry_source"),
            "providers_queried": providers_queried,
            "provider_warnings": summary.get("warnings") or [],
            "waterfall": summary.get("waterfall") or [],
            "candidates_found": len(results),
            "candidates_new": attributed + over_ceiling,
            "attributed": attributed,
            "skipped_known": skipped_known,
            "over_ceiling": over_ceiling,
            "sent": 0,
            "replies": 0,
            # Nothing is sent and nothing was observed here: null, not 0.
            "validation_events": None,
            "external_side_effects": False,
        },
        "metrics": {"candidates_new": attributed,
                    "provider_calls": sum(providers_queried.values())},
        "artifacts": [],
        "next_step": None,
    }


def send_outreach(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Send founder-approved drafts through the existing send path. Nothing else.

    Approval is per draft, never per run: a draft in any status other than
    ``approved`` is skipped and reported, never sent. Dispatch goes through
    ``send_approved()``, so the claim policy, idempotency window, and release
    rules are the production ones, not a workflow reimplementation. A draft
    whose outcome is ambiguous is recorded as failed-with-reason rather than
    failing the whole step, so one bad address cannot sink the batch.
    """
    from services.sales_service import send_approved

    plan_id = str(context.get("plan_id") or "")
    workflow_id = str(context.get("workflow_id") or "")
    targets = [str(item) for item in (config.get("targets") or []) if str(item).strip()]
    ceiling = int(config.get("max_contacts") or 0)

    sent: list[str] = []
    failed: list[dict[str, str]] = []
    skipped_unapproved: list[str] = []
    skipped_unknown: list[str] = []
    over_ceiling = 0
    within = targets[:ceiling] if ceiling > 0 else []
    if len(targets) > len(within):
        over_ceiling = len(targets) - len(within)

    for draft_id in within:
        draft = sales_store.get_draft(draft_id)
        if draft is None:
            skipped_unknown.append(draft_id)
            continue
        if draft.get("status") != "approved":
            skipped_unapproved.append(draft_id)
            continue
        try:
            result = send_approved(draft_id)
        except Exception as exc:  # noqa: BLE001 - recorded per draft, step continues
            failed.append({"draft_id": draft_id, "error": f"{type(exc).__name__}: {exc}"})
            continue
        sales_store.add_event(draft.get("lead_id"), "outreach.governed_sent", {
            "plan_id": plan_id,
            "workflow_id": workflow_id,
            "draft_id": draft_id,
            "provider_message_id": result.get("message_id"),
        })
        sent.append(draft_id)

    return {
        "status": "completed",
        "output": {
            "action": "send_outreach",
            "targets": len(targets),
            "within_limit": len(within),
            "sent": len(sent),
            "failed": failed,
            "skipped_unapproved": skipped_unapproved,
            "skipped_unknown": skipped_unknown,
            "over_ceiling": over_ceiling,
            "replies": 0,
            # Replies arrive later via webhook and are observed then, not here.
            "validation_events": None,
            "external_side_effects": True,
            "sent_draft_ids": sent,
        },
        "metrics": {"targets": len(targets), "sent": len(sent), "failed": len(failed)},
        "artifacts": [],
        "next_step": None,
    }


def observe_validation_events(
    *, plan_id: str | None = None, workflow_id: str | None = None
) -> ValidationEventObservation:
    """Measure the plan's validation events against real, attributable evidence.

    Evidence has to be attributable to *this* plan: leads that already happen to
    sit in a meeting stage were not produced by this experiment, and counting
    them would credit a run that never happened. Attribution comes from
    ``sales_events`` rows carrying the plan or workflow id, which is the write
    the send path performs once outreach actually leaves the process.

    Nothing here fabricates a value in either direction: no attributable
    activity is ``observed=False`` with a reason, and attributable activity with
    no qualifying event is a genuine, reportable zero.
    """
    needles = [f"%{value}%" for value in (plan_id, workflow_id) if value]
    if not needles:
        return ValidationEventObservation(
            observed=False,
            reason="no plan or workflow is attached to this execution",
        )
    try:
        with state.connect() as connection:
            rows = connection.execute(
                "SELECT event FROM sales_events WHERE "
                + " OR ".join("payload_json LIKE ?" for _ in needles),
                needles,
            ).fetchall()
    except sqlite3.Error as exc:
        # A store we could not read is not a store that reported zero.
        return ValidationEventObservation(
            observed=False,
            reason=f"evidence store could not be read: {type(exc).__name__}",
        )
    events = [str(row["event"]) for row in rows]
    source = f"sales_events(plan_id={plan_id or workflow_id})"
    if not events:
        return ValidationEventObservation(
            observed=False,
            source=source,
            reason="no outreach has been recorded for this plan, so nothing was measured",
        )
    return ValidationEventObservation(
        observed=True,
        count=sum(1 for name in events if name in VALIDATION_EVENT_NAMES),
        source=source,
    )
