"""Workflow suggestions: what to run, when, for how long, and what to expect.

Deterministic ranking over evidence — never a model guess, never an
execution. A suggestion names the method, the schedule, the duration, and an
expected range with its basis. Unknowns stay unknown: without a baseline the
range says so instead of inventing a rate.

The founder still generates, governs, approves, and runs. This answers
"what next", not "go".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from core.evidence import collect_evidence


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def suggest_workflows(org: int = 0, now: datetime | None = None) -> dict[str, Any]:
    """Rank the next governed runs from evidence. Read-only."""
    from core.plan_governance import GovernanceLimits

    moment = now or _now()
    evidence = collect_evidence(org)
    caps = GovernanceLimits.load()
    accounts = evidence.get("accounts") or {}
    leads = evidence.get("leads") or {}
    engagement = evidence.get("engagement") or {}
    history = evidence.get("history") or []
    channels = evidence.get("channels") or {}

    sent_total = sum((c.get("sent") or 0) for c in (engagement.get("channels") or {}).values())
    replies = engagement.get("replies") or 0
    meetings = engagement.get("meetings") or 0
    executed = [h for h in history if h.get("executed")]

    # Schedule: a run inside its window is not due; anything else is.
    due_after: datetime | None = None
    for run in executed:
        at = _parse_ts(run.get("executed_at"))
        window = run.get("duration_days") or 14
        if at and at + timedelta(days=window) > moment:
            end = at + timedelta(days=window)
            if due_after is None or end > due_after:
                due_after = end

    recommendations: list[dict[str, Any]] = []

    def schedule(duration_days: int) -> dict[str, Any]:
        start = due_after if due_after and due_after > moment else moment
        return {"scheduled_for": start.isoformat(),
                "due_now": start <= moment,
                "duration_days": duration_days}

    channel = _best_channel(evidence)

    if accounts.get("total", 0) == 0 and leads.get("total", 0) == 0:
        recommendations.append({
            "rank": 1,
            "method": "prospect_discovery",
            "title": "Find companies first",
            "rationale": ("No accounts and no leads exist yet, so outreach has "
                          "nobody to reach. Research names companies from evidence-backed terms."),
            "evidence_refs": ["accounts:0", "leads:0"],
            **schedule(14),
            "expected_range": {
                "low": 0, "high": caps.max_outreach_contacts,
                "unit": "candidates",
                "basis": "capped by governance; no baseline yet, the first run sets it",
            },
            "channel": channel,
        })
        has_world = False
    else:
        has_world = True

    if has_world:
        unclaimed = len(leads.get("unlinked_domains") or [])
        if unclaimed:
            recommendations.append({
                "rank": 1,
                "method": "prospect_discovery",
                "title": "Research around what already knocked",
                "rationale": (f"{unclaimed} lead domain(s) have no account yet. "
                              "Research adjacent companies while those warm leads exist."),
                "evidence_refs": [f"leads:unclaimed:{unclaimed}"],
                **schedule(14),
                "expected_range": {
                    "low": 0, "high": caps.max_outreach_contacts,
                    "unit": "candidates",
                    "basis": "capped by governance; no baseline yet",
                },
                "channel": channel,
            })
        if sent_total == 0 and not executed:
            recommendations.append({
                "rank": 2,
                "method": "email_outreach",
                "title": "Draft the first outreach",
                "rationale": (f"{accounts.get('total', 0)} account(s) exist and nothing "
                              "has been sent. Drafts are held for founder review, never auto-sent."),
                "evidence_refs": [f"accounts:{accounts.get('total', 0)}", "engagement:sent:0"],
                **schedule(14),
                "expected_range": {
                    "low": min(accounts.get("total", 0), caps.max_outreach_contacts),
                    "high": min(accounts.get("total", 0), caps.max_outreach_contacts),
                    "unit": "drafts",
                    "basis": "one draft per account up to the contact cap",
                },
                "channel": channel or "email",
            })
        elif sent_total > 0 and replies == 0:
            rate, basis = _reply_basis(evidence)
            recommendations.append({
                "rank": 2,
                "method": "targeted_outbound",
                "title": "Change the message, not the volume",
                "rationale": (f"{sent_total} sent with zero replies. More of the same "
                              "is not the answer; test a new angle on a small batch."),
                "evidence_refs": [f"engagement:sent:{sent_total}", "engagement:replies:0"],
                **schedule(14),
                "expected_range": {
                    "low": 0,
                    "high": (round(rate * 10) if rate else caps.max_outreach_contacts),
                    "unit": "replies",
                    "basis": basis,
                },
                "channel": channel,
            })
        if replies > 0 and meetings == 0:
            recommendations.append({
                "rank": 3,
                "method": "direct_sales",
                "title": "Push replies toward meetings",
                "rationale": (f"{replies} replie(s) but no booked meeting. "
                              "Direct follow-up converts attention into calendar."),
                "evidence_refs": [f"engagement:replies:{replies}", "engagement:meetings:0"],
                **schedule(14),
                "expected_range": {
                    "low": 0, "high": replies,
                    "unit": "meetings",
                    "basis": "at most one meeting per existing reply",
                },
                "channel": channel,
            })
    if meetings > 0:
        last_action = next((h.get("action") for h in executed if h.get("action")), None)
        recommendations.append({
            "rank": 4,
            "method": "email_outreach",
            "title": "Raise the bar",
            "rationale": (f"{meetings} meeting(s) booked: validation is working. "
                          "Repeat the working motion against fresh accounts with a higher target."),
            "evidence_refs": [f"engagement:meetings:{meetings}"],
            **schedule(14),
            "expected_range": {
                "low": meetings, "high": meetings * 2,
                "unit": "meetings",
                "basis": "prior result doubled is a goal, not a promise",
            },
            "channel": channel,
            "last_working_action": last_action,
        })

    return {
        "recommendations": recommendations,
        "evidence_summary": {
            "accounts": accounts.get("total", 0),
            "leads": leads.get("total", 0),
            "sent": sent_total,
            "replies": replies,
            "meetings": meetings,
            "past_runs": len(executed),
        },
        "caps": {"max_outreach_contacts": caps.max_outreach_contacts,
                 "max_duration_days": caps.max_duration_days,
                 "max_spend_usd": caps.max_spend_usd},
        "generated_at": moment.isoformat(),
    }


def _best_channel(evidence: dict[str, Any]) -> str | None:
    """The channel with the best recorded reply rate, or the declared one, or None."""
    channels = (evidence.get("engagement") or {}).get("channels") or {}
    best, best_rate = None, 0.0
    for name, stats in channels.items():
        rate = stats.get("reply_rate")
        if rate is not None and rate > best_rate and (stats.get("sent") or 0) >= 3:
            best, best_rate = name, rate
    if best:
        return best
    declared = (evidence.get("channels") or {}).get("declared") or []
    from core.plan_governance import normalize_channel
    for candidate in declared:
        normalized = normalize_channel(candidate)
        if normalized in ("email", "linkedin", "phone", "sms", "whatsapp"):
            return normalized
    return None


def _reply_basis(evidence: dict[str, Any]) -> tuple[float | None, str]:
    """A recorded reply rate if one exists, else an honest unknown."""
    channels = (evidence.get("engagement") or {}).get("channels") or {}
    sent = sum((c.get("sent") or 0) for c in channels.values())
    replied = sum((c.get("replied") or 0) for c in channels.values())
    if sent >= 10:
        return replied / sent, f"recorded rate {replied}/{sent} across channels"
    return None, "no baseline yet: 10+ sends establish one"


def suggest_campaign(org: int = 0) -> dict[str, Any]:
    """Propose the marketing move from evidence: video lines, campaign path, provider.

    Every video line carries its source field; slots with no source are listed
    under omitted with the exact field to fill, never papered over with
    invented copy. The campaign path and provider follow recorded results and
    declared resources, defaulting to honest unknowns.
    """
    from core.company_context import get_company_context

    evidence = collect_evidence(org)
    context = get_company_context()
    fields: dict[str, str] = {}
    if context is not None:
        dump = context.model_dump() if hasattr(context, "model_dump") else {}
        for section in ("company", "product", "customer", "market", "offer"):
            part = dump.get(section) or {}
            if isinstance(part, dict):
                for key, value in part.items():
                    if isinstance(value, str) and value.strip():
                        fields[f"{section}.{key}"] = value.strip()

    wanted = [
        ("hook", [("company.name", "company.description"), ("product.name", "product.value_proposition")]),
        ("audience", [("customer.ideal_customer",)]),
        ("problem", [("market.problem",)]),
        ("offer", [("product.description",), ("offer.description",)]),
    ]
    lines: list[dict[str, str]] = []
    omitted: list[dict[str, str]] = []
    for slot, options in wanted:
        texts = [fields[f] for group in options for f in group if fields.get(f)]
        if texts:
            # First non-empty phrasing wins; its field is the provenance.
            for group in options:
                hit = next((f for f in group if fields.get(f)), None)
                if hit:
                    lines.append({"slot": slot, "text": fields[hit], "source": f"context:{hit}"})
                    break
        else:
            omitted.append({
                "slot": slot,
                "missing_field": options[0][0],
                "note": "add it in company context and the line appears",
            })

    accounts = (evidence.get("accounts") or {}).get("total", 0)
    meetings = (evidence.get("engagement") or {}).get("meetings", 0)
    icps = evidence.get("icps") or []
    validated = [i for i in icps if i.get("status") == "validated"]
    if meetings > 0 and validated:
        path, path_why = ("full", f"{meetings} meeting(s) and a validated ICP: position, produce, and publish")
    elif accounts > 0 and (validated or accounts >= 3):
        path, path_why = ("g1+g2", "enough audience to position and produce for; publishing waits for signal")
    else:
        path, path_why = ("g1", "positioning first: strategy before assets, assets before publishing")

    channel = _best_channel(evidence)
    connected = (evidence.get("channels") or {}).get("connected") or []
    if channel == "email" and "resend" in connected:
        via = "resend"
        via_why = "Resend is connected and email leads the recorded channels."
    elif channel == "email":
        via = "resend-unconfigured"
        via_why = "Email is the channel but Resend is not connected; connect it before planning sends."
    elif channel in ("linkedin", "phone", "sms"):
        via = "manual"
        via_why = f"{channel} has no send API: outreach runs as manual tasks from drafts."
    else:
        via = "undecided"
        via_why = "No channel evidence yet: declare channels in company context first."
    rate, basis = _reply_basis(evidence)

    return {
        "video_prompt": {"lines": lines, "omitted": omitted},
        "campaign": {"path": path, "rationale": path_why,
                     "evidence_refs": [f"accounts:{accounts}",
                                       f"meetings:{meetings}",
                                       f"icps:validated:{len(validated)}"]},
        "provider": {"channel": channel, "via": via, "rationale": via_why,
                     "reply_rate": rate, "rate_basis": basis},
        "evidence_summary": {
            "accounts": accounts,
            "meetings": meetings,
            "validated_icps": len(validated),
        },
    }
