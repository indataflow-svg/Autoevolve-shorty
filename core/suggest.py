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
