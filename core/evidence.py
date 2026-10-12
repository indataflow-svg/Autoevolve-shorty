"""Unified evidence reader: everything the business has told or shown us, in one place.

Every suggester (accounts, workflows, campaigns) reads from here instead of
from one favoured source. Manual input, CSV imports, research runs, inbound
leads, replies, meetings, and past governed runs are all evidence; an empty
slot is reported as unknown, never filled in.

Read-only by construction: this module has no INSERT/UPDATE path.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any


def _safe_json(text: Any, default: Any) -> Any:
    try:
        parsed = json.loads(text or "")
    except (ValueError, TypeError):
        return default
    return parsed if isinstance(parsed, type(default)) else default


def collect_evidence(org: int = 0) -> dict[str, Any]:
    """Assemble the evidence union for one organization. Never raises on
    missing tables: a store that is absent is unknown evidence, not zero."""
    from core import commercial_store
    from core.company_context import get_company_context
    from core.state import connect

    evidence: dict[str, Any] = {"org_id": org}

    context = get_company_context()
    if context is None:
        evidence["context"] = {"present": False}
    else:
        company = context.company.model_dump() if hasattr(context.company, "model_dump") else {}
        evidence["context"] = {
            "present": True,
            "company_name": company.get("name") or None,
            "industry": company.get("industry") or None,
            "market": getattr(context.market, "market", None) or None,
            "known_groups": [g for g in ("company", "product", "customer", "problem",
                                         "objective", "marketing_stage")
                             if g not in (context.missing or [])],
            "missing": list(context.missing or []),
            "completeness_percent": context.completeness_percent,
        }

    with connect() as db:
        def table(name: str) -> bool:
            return db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
            ).fetchone() is not None

        # Commercial registry.
        offers, icps, accounts = [], [], []
        if table("offer_profiles"):
            offers = [dict(r) for r in db.execute(
                "SELECT id, name, status FROM offer_profiles WHERE org_id=?", (org,))]
        if table("icp_profiles"):
            icps = [dict(r) for r in db.execute(
                "SELECT id, name, status, version, criteria_json FROM icp_profiles WHERE org_id=?",
                (org,))]
        account_domains: set[str] = set()
        if table("commercial_accounts"):
            accounts = [dict(r) for r in db.execute(
                "SELECT id, company_name, domain, industry, lifecycle_status,"
                " fit_score, fit_grade FROM commercial_accounts WHERE org_id=?", (org,))]
            account_domains = {(a.get("domain") or "").strip().lower()
                               for a in accounts if (a.get("domain") or "").strip()}
        evidence["offers"] = offers
        evidence["icps"] = [
            {**i, "criteria_count": len(_safe_json(i.get("criteria_json"), []))} for i in icps
        ]
        industries = Counter(a.get("industry") or "unknown" for a in accounts)
        evidence["accounts"] = {
            "total": len(accounts),
            "by_lifecycle": dict(Counter(a.get("lifecycle_status") or "target" for a in accounts)),
            "by_fit": dict(Counter(a.get("fit_grade") or "unknown" for a in accounts)),
            "top_industries": [{"industry": k, "count": v}
                               for k, v in industries.most_common(5)],
        }

        # Leads: stages, sources, and the domains nobody has claimed yet.
        leads = {"total": 0, "by_stage": {}, "by_source": {}, "unlinked_domains": [],
                 "candidates": 0, "candidate_domains": []}
        if table("sales_leads"):
            rows = [dict(r) for r in db.execute(
                "SELECT id, email, full_name, company, company_domain, stage,"
                " source, metadata_json FROM sales_leads")]
            leads["total"] = len(rows)
            leads["by_stage"] = dict(Counter(r.get("stage") or "new" for r in rows))
            leads["by_source"] = dict(Counter(r.get("source") or "unknown" for r in rows))
            by_domain: dict[str, list[dict]] = {}
            for r in rows:
                meta = _safe_json(r.get("metadata_json"), {})
                if isinstance(meta, dict) and meta.get("company_candidate"):
                    leads["candidates"] += 1
                dom = (r.get("company_domain") or "").strip().lower()
                if dom and dom not in account_domains:
                    by_domain.setdefault(dom, []).append(r)
            ordered = sorted(by_domain.items(), key=lambda kv: -len(kv[1]))[:50]
            for dom, members in ordered:
                names = sorted({(m.get("company") or "").strip() for m in members if (m.get("company") or "").strip()})
                leads["unlinked_domains"].append({
                    "domain": dom,
                    "lead_count": len(members),
                    "lead_ids": [m["id"] for m in members],
                    "company_names": names[:3],
                    "stages": sorted({m.get("stage") or "new" for m in members}),
                    "sources": sorted({(m.get("source") or "unknown") for m in members}),
                    "has_candidate": any(
                        isinstance(_safe_json(m.get("metadata_json"), {}), dict)
                        and _safe_json(m.get("metadata_json"), {}).get("company_candidate")
                        for m in members),
                })
            leads["candidate_domains"] = sorted({
                (r.get("company_domain") or "").strip().lower()
                for r in rows
                if isinstance(_safe_json(r.get("metadata_json"), {}), dict)
                and _safe_json(r.get("metadata_json"), {}).get("company_candidate")
                and (r.get("company_domain") or "").strip()
                and (r.get("company_domain") or "").strip().lower() not in account_domains
            })
        evidence["leads"] = leads

        # Imports that actually landed.
        imports: list[dict] = []
        if table("csv_imports"):
            imports = [dict(r) for r in db.execute(
                "SELECT id, entity_type, filename, status, totals_json FROM csv_imports"
                " WHERE org_id=? ORDER BY updated_at DESC LIMIT 20", (org,))]
        evidence["imports"] = [
            {**i, "totals": _safe_json(i.get("totals_json"), {})} for i in imports
        ]

        # Engagement: what the market said back, per channel where known.
        engagement = {"replies": 0, "meetings": 0, "inbound": 0, "channels": {}}
        if table("sales_events"):
            for row in db.execute(
                    "SELECT event, COUNT(*) AS n FROM sales_events GROUP BY event"):
                if row["event"] == "lead.replied":
                    engagement["replies"] = row["n"]
                elif row["event"] == "meeting.scheduled":
                    engagement["meetings"] = row["n"]
        if table("sales_interactions"):
            out: Counter = Counter()
            inn: Counter = Counter()
            for row in db.execute("SELECT direction, channel FROM sales_interactions"):
                channel = (row["channel"] or "unknown").strip().lower() or "unknown"
                if row["direction"] == "inbound":
                    inn[channel] += 1
                    engagement["inbound"] += 1
                else:
                    out[channel] += 1
            for channel in sorted(set(out) | set(inn)):
                sent, got = out.get(channel, 0), inn.get(channel, 0)
                engagement["channels"][channel] = {
                    "sent": sent, "replied": got,
                    "reply_rate": (got / sent) if sent else None,
                }
        evidence["engagement"] = engagement

        # Governed history: what we tried and what it measured.
        history: list[dict] = []
        plan_limits: dict[str, Any] = {}
        if table("validation_plans"):
            for row in db.execute("SELECT id, plan_json FROM validation_plans"):
                try:
                    limits = (json.loads(row["plan_json"] or "{}").get("limits") or {})
                except ValueError:
                    limits = {}
                plan_limits[row["id"]] = limits
        if table("validation_workflows"):
            for row in db.execute(
                    "SELECT id, plan_id, status, workflow_id, approved_at,"
                    " executed_at, execution_json FROM validation_workflows"
                    " ORDER BY created_at DESC, rowid DESC LIMIT 20"):
                execution = _safe_json(row["execution_json"], {})
                observation = (execution.get("validation_events")
                               if isinstance(execution, dict) else None) or {}
                steps = execution.get("steps", []) if isinstance(execution, dict) else []
                history.append({
                    "governance_id": row["id"],
                    "plan_id": row["plan_id"],
                    "status": row["status"],
                    "workflow_id": row["workflow_id"],
                    "approved": bool(row["approved_at"]),
                    "executed": bool(row["executed_at"]),
                    "action": (steps[0].get("action") if steps else None),
                    "targets": ((steps[0].get("output") or {}).get("targets")
                                if steps else None),
                    "events_observed": bool(observation.get("observed")),
                    "events_count": observation.get("count", 0),
                    "duration_days": (plan_limits.get(row["plan_id"]) or {}).get("duration_days"),
                    "executed_at": row["executed_at"],
                })
        evidence["history"] = history

        # Channels the founder declared, plus what is actually connected.
        channels = {"declared": [], "connected": []}
        if context is not None:
            resources = getattr(context, "resources", None)
            declared = getattr(resources, "channels", None) if resources else None
            channels["declared"] = list(declared or [])
        if table("integration_connections"):
            channels["connected"] = sorted({
                r["provider"] for r in db.execute(
                    "SELECT provider FROM integration_connections WHERE org_id=?"
                    " AND status IN ('healthy','connected')", (org,))
            })
        evidence["channels"] = channels

    return evidence


def resolve_research_terms(org: int = 0) -> dict[str, Any]:
    """Decide what a governed research run searches for, from evidence.

    Order: validated ICP industry first; else the most common industry across
    accounts and leads, recorded as an assumption in the rationale rather than
    a fact. Location likewise from regions, else the context market, else none
    (the provider ladder accepts a location-less query). Raises ValueError
    with a founder-actionable reason when nothing is resolvable, so governance
    blocks instead of guessing silently.
    """
    from core import commercial_store

    evidence = collect_evidence(org)
    industry: str | None = None
    industry_source = ""
    with commercial_store.connect() as db:
        try:
            icps = db.execute(
                "SELECT id, name, criteria_json FROM icp_profiles WHERE org_id=?"
                " AND status='validated' ORDER BY updated_at DESC LIMIT 5",
                (org,)).fetchall()
        except Exception:
            icps = []
    for row in icps:
        for rule in _safe_json(row["criteria_json"], []):
            if not isinstance(rule, dict):
                continue
            if str(rule.get("field") or "").lower() == "industry" and str(rule.get("value") or "").strip():
                industry = str(rule["value"]).strip()
                industry_source = f"validated_icp:{row['id']}"
                break
        if industry:
            break
    if industry is None:
        top = (evidence["accounts"].get("top_industries") or [{}])[0]
        if top.get("industry") and top["industry"] != "unknown":
            industry = top["industry"]
            industry_source = "top_evidence_industry"
    if not industry:
        raise ValueError(
            "no industry to research: validate an ICP or save accounts first, "
            "so the run searches for something real")
    location: str | None = None
    location_source = ""
    regions = Counter()
    with commercial_store.connect() as db:
        try:
            for row in db.execute(
                    "SELECT region FROM commercial_accounts WHERE org_id=? AND region<>''",
                    (org,)):
                if row["region"].strip():
                    regions[row["region"].strip()] += 1
        except Exception:
            pass
    if regions:
        location, _ = regions.most_common(1)[0]
        location_source = "top_evidence_region"
    elif (evidence.get("context") or {}).get("market"):
        location = evidence["context"]["market"]
        location_source = "context_market"
    return {"industry": industry, "industry_source": industry_source,
            "location": location, "location_source": location_source}


def suggest_accounts(org: int = 0) -> dict[str, Any]:
    """Propose accounts from evidence nobody has claimed yet.

    Sources, in order: lead domains with no account (strongest first by lead
    count and engagement), then research-candidate domains. Exact domain match
    against the registry excludes; similar names without a shared domain are
    never merged, only proposed side by side with their reasons.
    """
    evidence = collect_evidence(org)
    known = {(a.get("domain") or "").strip().lower() for a in
             _accounts_full(org) if (a.get("domain") or "").strip()}
    suggestions: list[dict[str, Any]] = []
    for entry in evidence["leads"]["unlinked_domains"]:
        if entry["domain"] in known:
            continue
        names = entry["company_names"]
        suggestions.append({
            "company_name": names[0] if names else entry["domain"],
            "domain": entry["domain"],
            "industry": None,
            "evidence": {
                "lead_count": entry["lead_count"],
                "lead_ids": entry["lead_ids"],
                "stages": entry["stages"],
                "sources": entry["sources"],
                "research_candidate": entry["has_candidate"],
            },
            "reason": _reason_for(entry),
        })
    return {
        "suggestions": suggestions,
        "total": len(suggestions),
        "generated_from": {
            "unclaimed_lead_domains": len(evidence["leads"]["unlinked_domains"]),
            "research_candidates": evidence["leads"]["candidates"],
        },
    }


def _reason_for(entry: dict[str, Any]) -> str:
    bits = [f"{entry['lead_count']} lead(s)"]
    if "replied" in entry["stages"]:
        bits.append("including replies")
    if "scheduled" in entry["stages"]:
        bits.append("including a booked meeting")
    bits.append(f"via {', '.join(entry['sources'])}")
    if entry["has_candidate"]:
        bits.append("flagged by research")
    return " ".join(bits) + "; no account yet."


def _accounts_full(org: int) -> list[dict]:
    from core.state import connect

    with connect() as db:
        try:
            rows = db.execute(
                "SELECT id, company_name, domain FROM commercial_accounts WHERE org_id=?",
                (org,)).fetchall()
        except Exception:
            return []
    return [dict(r) for r in rows]
