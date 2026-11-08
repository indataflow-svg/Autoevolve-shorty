"""Phase 1 commercial API: offers, ICPs, accounts, pipelines, rules, imports, integrations, onboarding."""
from __future__ import annotations

import csv
import io
import json
import os
from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.ratelimit import rate_limit_intake
from app.sales_api import verify_founder_action
from core import commercial_store as store

router = APIRouter(prefix="/company/commercial", tags=["commercial"])

# The provider calls this back in the founder's browser, so dashboard auth
# cannot apply: the signed state parameter is the authentication. Rate
# limited like the other public intake paths.
oauth_callback_router = APIRouter(
    prefix="/company/commercial/integrations", tags=["oauth"],
    dependencies=[Depends(rate_limit_intake)],
)


@oauth_callback_router.get("/{provider}/callback", include_in_schema=False)
def oauth_callback(provider: str, code: str = Query(""), state: str = Query("")):
    """Finish an OAuth authorization started by POST .../connect.

    Always ends in a redirect to the workspace, never in a token dump: the
    outcome is readable from the catalog state itself, which is the single
    place connection truth lives.
    """
    from services import oauth as oauth_service

    if provider not in oauth_service.PROVIDERS:
        raise HTTPException(404, "unknown provider")
    try:
        org = int((state.split(".")[1] if state.count(".") >= 4 else "0") or 0)
    except ValueError:
        org = 0
    try:
        if not code or not state:
            raise oauth_service.OAuthError("provider returned no code")
        oauth_service.verify_state(provider, state, org)
        oauth_service.exchange_code(provider, code, org)
    except oauth_service.OAuthError as exc:
        with store.connect() as db:
            db.execute(
                "UPDATE integration_connections SET status='action_required',"
                " sync_status='idle', last_error_sanitized=?, updated_at=?"
                " WHERE org_id=? AND provider=?",
                (f"authorization failed: {exc}"[:400], _now(), org, provider))
        return RedirectResponse(f"/commercial?oauth={provider}:error", status_code=303)
    with store.connect() as db:
        existing = db.execute(
            "SELECT id FROM integration_connections WHERE org_id=? AND provider=?",
            (org, provider)).fetchone()
        if existing:
            db.execute(
                "UPDATE integration_connections SET status='healthy', sync_status='idle',"
                " last_error_sanitized='', credential_ref='oauth:vault', updated_at=?"
                " WHERE id=?", (_now(), existing["id"]))
        else:
            rec = {"id": store.new_id("conn"), "org_id": org, "provider": provider,
                   "external_account_ref": "", "scopes_json": "[]", "status": "healthy",
                   "sync_status": "idle", "last_error_sanitized": "",
                   "credential_ref": "oauth:vault", "created_at": _now(), "updated_at": _now()}
            cols, vals = list(rec.keys()), list(rec.values())
            db.execute(f"INSERT INTO integration_connections ({','.join(cols)}) VALUES"
                       f" ({','.join('?' for _ in cols)})", vals)
    return RedirectResponse(f"/commercial?oauth={provider}:connected", status_code=303)


def _org() -> int:
    return store.active_org_id()


def _now() -> str:
    from core.state import now_iso
    return now_iso()


def _save(table: str, data: dict, org: int) -> dict:
    data.update({"org_id": org, "updated_at": _now()})
    cols, vals = list(data.keys()), list(data.values())
    with store.connect() as db:
        db.execute(
            f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            vals,
        )
    return data


def _update(table: str, rid: str, org: int, patch: dict) -> dict:
    current = store._row(table, rid, org)
    if not current:
        raise HTTPException(404, f"{table} record not found")
    patch = {k: v for k, v in patch.items() if v is not None}
    patch["updated_at"] = _now()
    with store.connect() as db:
        db.execute(
            f"UPDATE {table} SET {','.join(f'{k}=?' for k in patch)} WHERE id=? AND org_id=?",
            (*patch.values(), rid, org),
        )
    return {**current, **patch}


# ---------- offers ----------
class OfferIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = ""
    category: str = ""
    target_market: str = ""
    pricing_model: str = ""
    price_info: str = ""
    value_prop: str = ""
    differentiators: list[str] = Field(default_factory=list)
    limitations: str = ""
    status: str = "active"


@router.get("/offers")
def list_offers() -> list[dict]:
    return store._list("offer_profiles", _org())


@router.post("/offers", dependencies=[Depends(verify_founder_action)])
def create_offer(payload: OfferIn) -> dict:
    org = _org()
    return _save("offer_profiles", {
        "id": store.new_id("offer"), **payload.model_dump(),
        "differentiators": json.dumps(payload.differentiators),
        "created_at": _now()}, org)


@router.patch("/offers/{rid}", dependencies=[Depends(verify_founder_action)])
def update_offer(rid: str, payload: dict) -> dict:
    if "differentiators" in payload and isinstance(payload["differentiators"], list):
        payload["differentiators"] = json.dumps(payload["differentiators"])
    return _update("offer_profiles", rid, _org(), payload)


# ---------- ICPs ----------
class ICPIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    segment: str = ""
    offer_id: str | None = None
    criteria: list[dict] = Field(default_factory=list)
    exclusions: list[dict] = Field(default_factory=list)
    weights: dict = Field(default_factory=dict)
    thresholds: dict = Field(default_factory=dict)
    provenance: dict = Field(default_factory=dict)
    evidence_sources: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence: str = "provisional"
    status: str = "provisional"


ICP_TEMPLATES = [
    {"key": "smb_services", "name": "SMB services buyer",
     "criteria": [{"field": "company_size", "operator": "in", "value": ["1-10", "11-50", "51-200"], "weight": 2},
                  {"field": "industry", "operator": "contains", "value": "", "weight": 1}],
     "exclusions": [{"field": "region", "value": "sanctioned"}],
     "note": "Editable starting point. Fill the industry value before validating."},
    {"key": "midmarket_ops", "name": "Midmarket operations",
     "criteria": [{"field": "company_size", "operator": "in", "value": ["51-200", "201-500"], "weight": 2},
                  {"field": "industry", "operator": "contains", "value": "", "weight": 1}],
     "exclusions": [],
     "note": "Editable starting point. A template is never a verified truth."},
]


@router.get("/icp-templates")
def icp_templates() -> list[dict]:
    return ICP_TEMPLATES


@router.post("/icps/{rid}/archive", dependencies=[Depends(verify_founder_action)])
def archive_icp(rid: str) -> dict:
    if not store._row("icp_profiles", rid, _org()):
        raise HTTPException(404, "icp not found")
    return _update("icp_profiles", rid, _org(), {"status": "archived"})


@router.get("/icps")
def list_icps() -> list[dict]:
    return store._list("icp_profiles", _org())


SUGGEST_FIELDS = ("industry", "company_size", "region")


@router.get("/icps/suggest-criteria")
def suggest_criteria() -> dict:
    """Propose ICP criteria mined from the founder's own records.

    Read-only and deterministic: the best accounts (customers, else engaged,
    else everything) contribute their most common industry/size/region with
    support counts, and every candidate field reports its fill rate across
    all accounts — so a rule that would score `unknown` everywhere is visible
    before it is saved. Thin evidence warns instead of pretending.
    """
    org = _org()
    with store.connect() as db:
        try:
            rows = [dict(r) for r in db.execute(
                "SELECT company_name, domain, industry, company_size, region,"
                " lifecycle_status FROM commercial_accounts WHERE org_id=?", (org,))]
        except Exception:
            rows = []
    total = len(rows)
    if not total:
        return {"basis": {"set": "none", "count": 0}, "suggestions": [],
                "fill_rates": [], "warnings": ["no accounts yet: add or import accounts first"]}
    customers = [r for r in rows if (r.get("lifecycle_status") or "") == "customer"]
    engaged = [r for r in rows if (r.get("lifecycle_status") or "") == "engaged"]
    if customers:
        best, basis_set = customers, "customers"
    elif engaged:
        best, basis_set = engaged, "engaged"
    else:
        best, basis_set = rows, "all"
    basis = {"set": basis_set, "count": len(best)}
    suggestions = []
    for field in SUGGEST_FIELDS:
        values = [(r.get(field) or "").strip() for r in best]
        values = [v for v in values if v]
        if not values:
            continue
        top = Counter(values).most_common(1)[0]
        suggestions.append({
            "field": field,
            "operator": "equals",
            "value": top[0],
            "weight": 2 if field == "industry" else 1,
            "support": top[1],
            "total": len(best),
            "source": "evidence",
        })
    fill_rates = []
    for field in (*SUGGEST_FIELDS, "domain"):
        known = sum(1 for r in rows if (r.get(field) or "").strip())
        fill_rates.append({"field": field, "known": known, "total": total})
    warnings = []
    if len(best) < 3:
        warnings.append(f"thin evidence: only {len(best)} account(s) in the {basis['set']} set")
    return {"basis": basis, "suggestions": suggestions,
            "fill_rates": fill_rates, "warnings": warnings}


@router.get("/benchmarks")
def world_benchmarks(
    sends: int = Query(100, ge=1, le=100000),
    industry: str | None = Query(None, max_length=120),
) -> dict:
    """World-data predictions for this company's industry. Read-only.

    An explicit `industry` overrides the resolved one (for pages reasoning
    about a planned market); otherwise the industry
    resolves from the founder's own stored data (validated ICP first, else
    top evidence industry). With nothing stored the general-B2B band applies
    and says so. Every figure carries sources and vintage, and recorded
    results elsewhere always take precedence over these bands.
    """
    from core import channel_benchmarks as benchmarks
    from core.suggest import market_comparison

    org = _org()
    industry_source = "none"
    requested = (industry or "").strip() or None
    if requested:
        industry = requested
        industry_source = "requested"
    else:
        industry = None
        try:
            from core.evidence import resolve_research_terms

            terms = resolve_research_terms(org)
            if isinstance(terms.get("industry"), str) and terms["industry"].strip():
                industry = terms["industry"].strip()
                industry_source = terms.get("industry_source") or "evidence"
        except Exception:
            industry = None
    recorded = _recorded_engagement(org)
    rate = (recorded["replied"] / recorded["sent"]) if recorded["sent"] >= 10 else None
    return {
        "industry": industry,
        "industry_source": industry_source,
        "cold": benchmarks.cold_reply_benchmark(industry),
        "optin": benchmarks.optin_benchmark(industry),
        "expected": benchmarks.expected_replies(sends, industry),
        "recorded": recorded,
        "market": market_comparison(rate, industry),
    }


def _recorded_engagement(org: int) -> dict:
    """Own send/reply/meeting counts. Counts only — never names or text."""
    from core.evidence import collect_evidence

    try:
        engagement = collect_evidence(org).get("engagement") or {}
    except Exception:
        return {"sent": 0, "replied": 0, "meetings": 0, "rate": None}
    channels = engagement.get("channels") or {}
    sent = sum((c.get("sent") or 0) for c in channels.values())
    replied = sum((c.get("replied") or 0) for c in channels.values())
    meetings = engagement.get("meetings") or 0
    return {"sent": sent, "replied": replied, "meetings": meetings,
            "rate": (replied / sent) if sent >= 10 else None}


class NetworkContributionIn(BaseModel):
    opt_in: bool = Field(...)


@router.get("/network-stats")
def network_stats() -> dict:
    """This tenant's anonymized contribution payload. Read-only.

    Counts only: industry, per-channel sends/replies, meetings. No names,
    domains, emails, or message text ever leave this shape. The anonymized
    pool does not exist yet, so nothing here is transmitted anywhere — this
    is the contribution contract, and the opt-in flag below governs it.
    """
    from core.state import get_network_contribution

    org = _org()
    industry = None
    try:
        from core.evidence import resolve_research_terms

        terms = resolve_research_terms(org)
        if isinstance(terms.get("industry"), str) and terms["industry"].strip():
            industry = terms["industry"].strip()
    except Exception:
        industry = None
    return {
        "contribution": "opted_in" if get_network_contribution() else "opted_out",
        "industry": industry,
        "engagement": _recorded_engagement(org),
        "pool": "none_yet",
        "note": "Counts only, kept on this server. Opt in to publish this shape when the pool opens.",
    }


@router.post("/network-contribution", dependencies=[Depends(verify_founder_action)])
def network_contribution(payload: NetworkContributionIn) -> dict:
    """Opt the anonymized counts in or out of the future pool. Default out."""
    from core.state import get_network_contribution, set_network_contribution

    set_network_contribution(bool(payload.opt_in))
    return {"contribution": "opted_in" if get_network_contribution() else "opted_out"}


@router.get("/icps/{rid}")
def get_icp(rid: str) -> dict:
    icp = store._row("icp_profiles", rid, _org())
    if not icp:
        raise HTTPException(404, "icp not found")
    return icp


@router.post("/icps", dependencies=[Depends(verify_founder_action)])
def create_icp(payload: ICPIn) -> dict:
    if payload.status not in ("provisional", "validated", "archived"):
        raise HTTPException(422, "status must be provisional|validated|archived")
    return _save("icp_profiles", {
        "id": store.new_id("icp"), "name": payload.name, "segment": payload.segment,
        "offer_id": payload.offer_id, "criteria_json": json.dumps(payload.criteria),
        "exclusions_json": json.dumps(payload.exclusions),
        "weights_json": json.dumps(payload.weights),
        "thresholds_json": json.dumps(payload.thresholds),
        "provenance_json": json.dumps(payload.provenance),
        "evidence_sources_json": json.dumps(payload.evidence_sources),
        "assumptions_json": json.dumps(payload.assumptions),
        "confidence": payload.confidence, "status": payload.status,
        "creator": "founder", "version": 1, "created_at": _now()}, _org())


@router.patch("/icps/{rid}", dependencies=[Depends(verify_founder_action)])
def update_icp(rid: str, payload: dict) -> dict:
    cur = store._row("icp_profiles", rid, _org())
    if not cur:
        raise HTTPException(404, "icp not found")
    mapping = {"criteria": "criteria_json", "exclusions": "exclusions_json",
               "weights": "weights_json", "thresholds": "thresholds_json",
               "provenance": "provenance_json", "evidence_sources": "evidence_sources_json",
               "assumptions": "assumptions_json"}
    patch: dict[str, Any] = {}
    for k, v in payload.items():
        patch[mapping.get(k, k)] = json.dumps(v) if k in mapping else v
    patch["version"] = int(cur.get("version") or 1) + 1
    out = _update("icp_profiles", rid, _org(), patch)
    _refit_accounts(rid)
    return out


def _refit_accounts(icp_id: str) -> None:
    org = _org()
    icp = store._row("icp_profiles", icp_id, org)
    if not icp:
        return
    with store.connect() as db:
        rows = db.execute(
            "SELECT * FROM commercial_accounts WHERE org_id=? AND icp_id=?", (org, icp_id)).fetchall()
        for r in rows:
            res = store.evaluate_fit(dict(r), icp)
            db.execute(
                "UPDATE commercial_accounts SET fit_score=?, fit_grade=?,"
                " fit_explanation_json=?, updated_at=? WHERE id=?",
                (res["score"], res["grade"], json.dumps(res["explanations"]), _now(), r["id"]))


@router.post("/icps/{rid}/evaluate", dependencies=[Depends(verify_founder_action)])
def evaluate_icp(rid: str, account: dict) -> dict:
    icp = store._row("icp_profiles", rid, _org())
    if not icp:
        raise HTTPException(404, "icp not found")
    return {"fit": store.evaluate_fit(account, icp),
            "intent": store.evaluate_intent(_org(), str(account.get("id") or ""))}


# ---------- accounts ----------
class AccountIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    domain: str = ""
    industry: str = ""
    company_size: str = ""
    region: str = ""
    source: str = "manual"
    source_ref: str = ""
    icp_id: str | None = None
    verification_status: str = "unverified"
    lifecycle_status: str = "target"
    owner: str = ""
    next_action: str = ""
    attributes: dict = Field(default_factory=dict)


@router.get("/accounts")
def list_accounts(q: str = "", lifecycle_status: str = "", sort: str = "updated",
                  page: int = 1, page_size: int = 20) -> dict:
    org = _org()
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    where = ["org_id=?"]
    vals: list[Any] = [org]
    if lifecycle_status:
        where.append("lifecycle_status=?")
        vals.append(lifecycle_status)
    if q.strip():
        where.append("(company_name LIKE ? OR domain LIKE ? OR industry LIKE ?)")
        vals.extend([f"%{q.strip()}%"] * 3)
    order = {"updated": "updated_at DESC", "name": "company_name ASC",
             "fit": "fit_score DESC"}.get(sort, "updated_at DESC")
    with store.connect() as db:
        total = db.execute(
            f"SELECT COUNT(*) FROM commercial_accounts WHERE {' AND '.join(where)}", vals).fetchone()[0]
        rows = db.execute(
            f"SELECT * FROM commercial_accounts WHERE {' AND '.join(where)}"
            f" ORDER BY {order} LIMIT ? OFFSET ?",
            (*vals, page_size, (page - 1) * page_size)).fetchall()
    return {"items": [dict(r) for r in rows], "total": total,
            "page": page, "page_size": page_size}


@router.post("/accounts", dependencies=[Depends(verify_founder_action)])
def create_account(payload: AccountIn) -> dict:
    org = _org()
    dom = payload.domain.strip().lower() or None
    if dom:
        with store.connect() as db:
            dup = db.execute(
                "SELECT id FROM commercial_accounts WHERE org_id=? AND domain=?", (org, dom)).fetchone()
            if dup:
                raise HTTPException(409, "account with this domain already exists")
    rec = {"id": store.new_id("acct"), "company_name": payload.company_name, "domain": dom,
           "industry": payload.industry, "company_size": payload.company_size, "region": payload.region,
           "source": payload.source, "source_ref": payload.source_ref, "icp_id": payload.icp_id,
           "verification_status": payload.verification_status, "lifecycle_status": payload.lifecycle_status,
           "owner": payload.owner, "next_action": payload.next_action,
           "attributes_json": json.dumps({"industry": payload.industry,
                                          "company_size": payload.company_size,
                                          "region": payload.region, **payload.attributes}),
           "fit_score": None, "fit_grade": "unknown", "fit_explanation_json": "[]",
           "created_at": _now()}
    out = _save("commercial_accounts", rec, org)
    if payload.icp_id:
        icp = store._row("icp_profiles", payload.icp_id, org)
        if icp:
            res = store.evaluate_fit(out, icp)
            out = _update("commercial_accounts", out["id"], org,
                          {"fit_score": res["score"], "fit_grade": res["grade"],
                           "fit_explanation_json": json.dumps(res["explanations"])})
    return out


@router.post("/accounts/suggest")
def suggest_new_accounts() -> dict:
    """Propose accounts from evidence nobody has claimed yet.

    Unclaimed lead domains and research candidates, each with its reasons.
    Nothing is created here: confirming a suggestion is the existing
    POST /accounts, so every account still passes the same validation and
    domain-dedupe as a hand-entered one.
    """
    from core.evidence import suggest_accounts

    return suggest_accounts(_org())


@router.patch("/accounts/{rid}", dependencies=[Depends(verify_founder_action)])
def update_account(rid: str, payload: dict) -> dict:
    return _update("commercial_accounts", rid, _org(), payload)


@router.delete("/accounts/{rid}", dependencies=[Depends(verify_founder_action)])
def delete_account(rid: str) -> dict:
    org = _org()
    if not store._row("commercial_accounts", rid, org):
        raise HTTPException(404, "account not found")
    with store.connect() as db:
        refs = db.execute(
            "SELECT COUNT(*), SUM(outcome='open') FROM commercial_opportunities WHERE account_id=?",
            (rid,)).fetchone()
        total, open_count = (refs[0] or 0), (refs[1] or 0)
        if total:
            raise HTTPException(
                409, f"account has {total} opportunitie(s) on record"
                + (f", {open_count} still open" if open_count else "")
                + "; history is preserved, so accounts with deals cannot be removed")
        db.execute("DELETE FROM commercial_accounts WHERE id=? AND org_id=?", (rid, org))
    # History stays: activities keep their account_id as audit trail, leads
    # keep their domains and relink if the account is ever recreated.
    return {"id": rid, "deleted": True}


@router.get("/accounts/{rid}")
def get_account(rid: str) -> dict:
    rec = store._row("commercial_accounts", rid, _org())
    if not rec:
        raise HTTPException(404, "account not found")
    intent = store.evaluate_intent(_org(), rid)
    with store.connect() as db:
        acts = db.execute(
            "SELECT * FROM commercial_activities WHERE org_id=? AND account_id=? ORDER BY timestamp DESC LIMIT 50",
            (_org(), rid)).fetchall()
        # Leads reference the registry; they are never merged into it. A lead
        # links by exact domain match only — name-only similarities stay separate.
        linked: list[dict] = []
        if (rec.get("domain") or "").strip():
            rows = db.execute(
                "SELECT id, email, full_name, stage, source FROM sales_leads"
                " WHERE LOWER(company_domain)=LOWER(?) LIMIT 50",
                (rec["domain"].strip(),)).fetchall()
            linked = [dict(r) for r in rows]
    return {**rec, "intent": intent, "activities": [dict(a) for a in acts],
            "linked_leads": linked}


# ---------- pipelines & opportunities ----------
class PipelineIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    stages: list[dict] = Field(min_length=2)
    active: bool = True


DEFAULT_PIPELINE_STAGES = [
    {"key": "prospect", "label": "Prospect", "allowed_next": ["qualified", "disqualified"]},
    {"key": "qualified", "label": "Qualified", "allowed_next": ["proposal", "disqualified"]},
    {"key": "proposal", "label": "Proposal", "allowed_next": ["negotiation", "deferred", "lost"]},
    {"key": "negotiation", "label": "Negotiation", "allowed_next": ["won", "lost", "deferred"]},
    {"key": "won", "label": "Won", "allowed_next": []},
    {"key": "lost", "label": "Lost", "allowed_next": []},
    {"key": "deferred", "label": "Deferred", "allowed_next": ["prospect"]},
    {"key": "disqualified", "label": "Disqualified", "allowed_next": []},
]


@router.get("/pipelines")
def list_pipelines() -> list[dict]:
    rows = store._list("commercial_pipelines", _org())
    if not rows:
        rec = _save("commercial_pipelines", {
            "id": store.new_id("pipe"), "name": "Default sales pipeline",
            "stages_json": json.dumps(DEFAULT_PIPELINE_STAGES),
            "active": 1, "version": 1, "created_at": _now()}, _org())
        return [rec]
    return rows


@router.post("/pipelines", dependencies=[Depends(verify_founder_action)])
def create_pipeline(payload: PipelineIn) -> dict:
    keys = [str(s.get("key") or "") for s in payload.stages]
    if len(set(keys)) != len(keys) or not all(keys):
        raise HTTPException(422, "stages need unique non-empty keys")
    return _save("commercial_pipelines", {
        "id": store.new_id("pipe"), "name": payload.name,
        "stages_json": json.dumps(payload.stages), "active": 1 if payload.active else 0,
        "version": 1, "created_at": _now()}, _org())


class OpportunityIn(BaseModel):
    account_id: str
    contact_ids: list[str] = Field(default_factory=list)
    offer_id: str | None = None
    pipeline_id: str | None = None
    value: float | None = None
    currency: str = "USD"
    expected_close: str | None = None
    next_action: str = ""


@router.get("/opportunities")
def list_opportunities(stage: str = "", page: int = 1, page_size: int = 20) -> dict:
    org = _org()
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    where = ["org_id=?"]
    vals: list[Any] = [org]
    if stage:
        where.append("stage=?")
        vals.append(stage)
    with store.connect() as db:
        total = db.execute(
            f"SELECT COUNT(*) FROM commercial_opportunities WHERE {' AND '.join(where)}",
            vals).fetchone()[0]
        rows = db.execute(
            f"SELECT * FROM commercial_opportunities WHERE {' AND '.join(where)}"
            " ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (*vals, page_size, (page - 1) * page_size)).fetchall()
    return {"items": [dict(r) for r in rows], "total": total,
            "page": page, "page_size": page_size}


@router.get("/opportunities/{rid}")
def get_opportunity(rid: str) -> dict:
    org = _org()
    opp = store._row("commercial_opportunities", rid, org)
    if not opp:
        raise HTTPException(404, "opportunity not found")
    acct = store._row("commercial_accounts", opp["account_id"], org) or {}
    with store.connect() as db:
        acts = db.execute(
            "SELECT * FROM commercial_activities WHERE org_id=? AND (opportunity_id=? OR account_id=?)"
            " ORDER BY timestamp DESC LIMIT 50",
            (org, rid, opp["account_id"])).fetchall()
    return {**opp, "account": {"id": acct.get("id"), "company_name": acct.get("company_name")},
            "activities": [dict(a) for a in acts]}


@router.patch("/pipelines/{rid}", dependencies=[Depends(verify_founder_action)])
def update_pipeline(rid: str, payload: dict) -> dict:
    org = _org()
    cur = store._row("commercial_pipelines", rid, org)
    if not cur:
        raise HTTPException(404, "pipeline not found")
    patch: dict[str, Any] = {}
    if "name" in payload and payload["name"]:
        patch["name"] = str(payload["name"])[:200]
    if "active" in payload:
        patch["active"] = 1 if payload["active"] else 0
    if "stages" in payload:
        stages = payload["stages"]
        if not isinstance(stages, list) or len(stages) < 2:
            raise HTTPException(422, "a pipeline needs at least 2 stages")
        keys = [str(s.get("key") or "") for s in stages]
        if len(set(keys)) != len(keys) or not all(keys):
            raise HTTPException(422, "stages need unique non-empty keys")
        # Existing opportunities must keep a valid stage.
        with store.connect() as db:
            used = {r["stage"] for r in db.execute(
                "SELECT DISTINCT stage FROM commercial_opportunities WHERE pipeline_id=?", (rid,))}
        unknown = used - set(keys)
        if unknown:
            raise HTTPException(
                422, f"stages in use cannot be removed: {sorted(unknown)}")
        patch["stages_json"] = json.dumps(stages)
        patch["version"] = int(cur.get("version") or 1) + 1
    if not patch:
        raise HTTPException(422, "nothing to update")
    return _update("commercial_pipelines", rid, org, patch)


@router.post("/opportunities", dependencies=[Depends(verify_founder_action)])
def create_opportunity(payload: OpportunityIn) -> dict:
    org = _org()
    acct = store._row("commercial_accounts", payload.account_id, org)
    if not acct:
        raise HTTPException(404, "account not found")
    pipes = store._list("commercial_pipelines", org) or [create_pipeline(
        PipelineIn(name="Default sales pipeline", stages=DEFAULT_PIPELINE_STAGES))]
    pipe = next((p for p in pipes if p["id"] == payload.pipeline_id), pipes[0])
    stages = json.loads(pipe["stages_json"])
    first = stages[0]["key"]
    hist = [{"stage": first, "at": _now(), "by": "founder"}]
    return _save("commercial_opportunities", {
        "id": store.new_id("opp"), "account_id": payload.account_id,
        "contact_ids_json": json.dumps(payload.contact_ids), "offer_id": payload.offer_id,
        "pipeline_id": pipe["id"], "stage": first,
        "stage_history_json": json.dumps(hist), "value": payload.value,
        "currency": payload.currency, "expected_close": payload.expected_close,
        "next_action": payload.next_action, "outcome": "open", "lost_reason": "",
        "created_at": _now()}, org)


class StageMove(BaseModel):
    stage: str
    lost_reason: str = ""
    outcome: str | None = None


@router.post("/opportunities/{rid}/move", dependencies=[Depends(verify_founder_action)])
def move_opportunity(rid: str, payload: StageMove) -> dict:
    org = _org()
    opp = store._row("commercial_opportunities", rid, org)
    if not opp:
        raise HTTPException(404, "opportunity not found")
    pipe = store._row("commercial_pipelines", opp["pipeline_id"], org)
    stages = json.loads(pipe["stages_json"]) if pipe else DEFAULT_PIPELINE_STAGES
    by_key = {s["key"]: s for s in stages}
    if payload.stage not in by_key:
        raise HTTPException(422, f"unknown stage {payload.stage!r}")
    allowed = (by_key.get(opp["stage"], {}) or {}).get("allowed_next", [])
    if payload.stage not in allowed:
        raise HTTPException(422, f"transition {opp['stage']} -> {payload.stage} is not allowed")
    target = by_key[payload.stage]
    for field in target.get("required_fields", []):
        if not opp.get(field):
            raise HTTPException(422, f"stage {payload.stage} requires {field}")
    if payload.stage in ("lost", "deferred", "disqualified") and not payload.lost_reason:
        raise HTTPException(422, f"stage {payload.stage} requires a reason")
    hist = json.loads(opp["stage_history_json"])
    hist.append({"stage": payload.stage, "at": _now(), "by": "founder"})
    patch: dict[str, Any] = {"stage": payload.stage, "stage_history_json": json.dumps(hist)}
    if payload.stage in ("won", "lost", "deferred", "disqualified"):
        patch["outcome"] = payload.stage
    if payload.lost_reason:
        patch["lost_reason"] = payload.lost_reason
    if payload.outcome:
        patch["outcome"] = payload.outcome
    return _update("commercial_opportunities", rid, org, patch)


# ---------- qualification rules ----------
class RuleIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    icp_id: str | None = None
    pipeline_id: str | None = None
    criterion: str = Field(min_length=2, max_length=400)
    rule_type: str = "fit"
    weight: float = 1.0
    threshold: float | None = None
    hard_disqualify: bool = False
    evidence_required: list[str] = Field(default_factory=list)


@router.get("/rules")
def list_rules() -> list[dict]:
    return store._list("qualification_rules", _org())


@router.post("/rules", dependencies=[Depends(verify_founder_action)])
def create_rule(payload: RuleIn) -> dict:
    if payload.rule_type not in ("fit", "intent", "qualification"):
        raise HTTPException(422, "rule_type must be fit|intent|qualification")
    return _save("qualification_rules", {
        "id": store.new_id("rule"), "name": payload.name, "icp_id": payload.icp_id,
        "pipeline_id": payload.pipeline_id, "criterion": payload.criterion,
        "rule_type": payload.rule_type, "weight": payload.weight,
        "threshold": payload.threshold, "hard_disqualify": 1 if payload.hard_disqualify else 0,
        "evidence_required_json": json.dumps(payload.evidence_required),
        "active": 1, "version": 1, "created_at": _now()}, _org())


@router.post("/accounts/{rid}/qualify")
def qualify_account(rid: str) -> dict:
    org = _org()
    acct = store._row("commercial_accounts", rid, org)
    if not acct:
        raise HTTPException(404, "account not found")
    _ensure_default_rules(org)
    fit = store.evaluate_fit(acct, store._row("icp_profiles", acct["icp_id"], org)
                             ) if acct.get("icp_id") else {"score": None, "grade": "unknown",
                                                           "explanations": [], "missing": ["icp_id"]}
    intent = store.evaluate_intent(org, rid)
    evidence = _account_evidence(acct)
    unmet, hard_fail, skipped, evaluated = [], False, [], []
    if fit.get("score") is None:
        # Unknown fit is not a pass: without a linked ICP nothing has judged
        # this account, so it cannot clear qualification. needs_human follows
        # from unmet below.
        unmet.append("no linked ICP: fit is unknown")
    for rule in [r for r in store._list("qualification_rules", org, 200) if r.get("active")]:
        # Scoped rules only judge their own scope: an ICP-scoped rule means
        # nothing to an account on another ICP, and a pipeline-scoped rule
        # cannot be judged without a pipeline in context.
        if rule.get("icp_id") and rule["icp_id"] != acct.get("icp_id"):
            skipped.append({"rule": rule["name"], "reason": "scoped to another ICP"})
            continue
        if rule.get("pipeline_id"):
            skipped.append({"rule": rule["name"], "reason": "needs a pipeline context"})
            continue
        evaluated.append(rule["id"])
        if rule["rule_type"] == "fit" and isinstance(fit.get("score"), int):
            if rule.get("threshold") is not None and fit["score"] < float(rule["threshold"]):
                unmet.append(rule["name"])
                if rule.get("hard_disqualify"):
                    hard_fail = True
        elif rule["rule_type"] == "intent" and rule.get("threshold") is not None:
            if intent["score"] < float(rule["threshold"]):
                unmet.append(rule["name"])
                if rule.get("hard_disqualify"):
                    hard_fail = True
        elif rule["rule_type"] == "qualification":
            # A qualification rule demands evidence: every required item must
            # be present and non-empty on the account record. A rule demanding
            # nothing is vacuously met.
            try:
                required = json.loads(rule.get("evidence_required_json") or "[]")
            except ValueError:
                required = []
            if not isinstance(required, list):
                required = []
            missing_items = [item for item in required
                             if not _has_evidence(evidence, item)]
            if missing_items:
                unmet.append(f"{rule['name']} (missing: {', '.join(missing_items)})")
                if rule.get("hard_disqualify"):
                    hard_fail = True
    qualified = not hard_fail and not unmet
    verdict = {"account_id": rid, "fit": fit, "intent": intent, "unmet": unmet,
               "hard_fail": hard_fail, "qualified": qualified,
               "needs_human": bool(hard_fail or unmet), "skipped": skipped,
               "rules_evaluated": evaluated}
    _save("commercial_activities", {
        "id": store.new_id("act"), "type": "qualification",
        "timestamp": _now(), "outcome": "qualified" if qualified else "not_qualified",
        "owner": "", "account_id": rid, "source": "system",
        "audit_json": json.dumps({
            "fit_score": fit.get("score"), "fit_grade": fit.get("grade"),
            "intent_score": intent.get("score"), "intent_level": intent.get("level"),
            "unmet": unmet, "hard_fail": hard_fail, "rules_evaluated": evaluated,
        }),
        "created_at": _now()}, org)
    return verdict


def _has_evidence(evidence: dict, item: object) -> bool:
    """True when the named evidence exists and is non-empty. Unknown stays unknown."""
    value = evidence.get(item) if isinstance(item, str) else None
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(len(value))
    return True


def _account_evidence(acct: dict) -> dict:
    """Every known fact about the account, flat. Qualification rules check
    their evidence_required items against exactly this mapping."""
    flat: dict = {k: v for k, v in acct.items() if k != "attributes_json"}
    try:
        attrs = json.loads(acct.get("attributes_json") or "{}")
    except ValueError:
        attrs = {}
    if isinstance(attrs, dict):
        flat.update(attrs)
    return flat


def _ensure_default_rules(org: int) -> None:
    """Seed the editable default bar once per org. The old hardcoded floor
    (fit >= 40) lives here now as a normal rule the founder can change or
    delete — behavior is identical until they do."""
    with store.connect() as db:
        count = db.execute(
            "SELECT COUNT(*) FROM qualification_rules WHERE org_id=?", (org,)).fetchone()[0]
        if count:
            return
        db.execute(
            "INSERT INTO qualification_rules (id, org_id, name, criterion, rule_type,"
            " weight, threshold, hard_disqualify, evidence_required_json, active,"
            " version, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (store.new_id("rule"), org, "Minimum fit score 40",
             "fit score reaches 40", "fit", 1.0, 40.0, 0, "[]", 1, 1,
             _now(), _now()),
        )


# ---------- activities ----------
class ActivityIn(BaseModel):
    type: str = Field(min_length=2, max_length=80)
    outcome: str = ""
    owner: str = ""
    account_id: str | None = None
    contact_id: str | None = None
    lead_id: str | None = None
    opportunity_id: str | None = None
    campaign_id: str | None = None
    source: str = "manual"


@router.post("/activities", dependencies=[Depends(verify_founder_action)])
def log_activity(payload: ActivityIn) -> dict:
    return _save("commercial_activities", {
        "id": store.new_id("act"), "type": payload.type, "timestamp": _now(),
        "outcome": payload.outcome, "owner": payload.owner, "account_id": payload.account_id,
        "contact_id": payload.contact_id, "lead_id": payload.lead_id,
        "opportunity_id": payload.opportunity_id, "campaign_id": payload.campaign_id,
        "source": payload.source, "audit_json": "{}", "created_at": _now()}, _org())


# ---------- CSV import ----------
CANONICAL_FIELDS = {"company_name", "domain", "email", "full_name", "job_title",
                    "industry", "company_size", "region", "phone", "country", "source"}
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CSV_ROWS = 2000


def _parse_csv(raw: bytes) -> tuple[list[str], list[dict]]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "CSV must be UTF-8 encoded")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(422, "CSV has no header row")
    rows = [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in reader]
    rows = [r for r in rows if any(v for v in r.values())]
    if len(rows) > MAX_CSV_ROWS:
        raise HTTPException(422, f"CSV exceeds {MAX_CSV_ROWS} rows")
    return [h.strip() for h in reader.fieldnames], rows


def _suggest_mapping(headers: list[str]) -> dict:
    norm = {h.lower().replace(" ", "_"): h for h in headers}
    mapping = {}
    for field in CANONICAL_FIELDS:
        if field in norm:
            mapping[norm[field]] = field
        for h, orig in norm.items():
            if field in h or h in field:
                mapping.setdefault(orig, field)
    return mapping


@router.get("/imports")
def list_imports() -> list[dict]:
    rows = store._list("csv_imports", _org(), 50)
    return [{k: v for k, v in r.items() if k != "rows_json"} for r in rows]


@router.post("/imports/preview", dependencies=[Depends(verify_founder_action)])
async def preview_import(entity_type: str = "account", file: UploadFile = File(...)) -> dict:
    if entity_type not in ("account", "contact", "lead"):
        raise HTTPException(422, "entity_type must be account|contact|lead")
    raw = await file.read()
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(422, "CSV exceeds 2MB")
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(422, "only .csv files are supported")
    headers, rows = _parse_csv(raw)
    org = _org()
    with store.connect() as db:
        existing_domains = {r["domain"] for r in db.execute(
            "SELECT domain FROM commercial_accounts WHERE org_id=?", (org,)).fetchall()} if entity_type == "account" else set()
        try:
            existing_emails = {r["email"] for r in db.execute(
                "SELECT email FROM sales_leads").fetchall()} if entity_type != "account" else set()
        except Exception:
            existing_emails = set()
    exact, ambiguous = 0, []
    sample = rows[:10]
    for idx, row in enumerate(rows):
        low = {k.lower(): v for k, v in row.items()}
        dom = (low.get("domain") or "").lower()
        email = (low.get("email") or "").lower()
        if (dom and dom in existing_domains) or (email and email in existing_emails):
            exact += 1
        elif not row.get("company_name") and not email and entity_type == "account":
            ambiguous.append({"row": idx + 1, "reason": "missing company_name"})
    rec = _save("csv_imports", {
        "id": store.new_id("imp"), "entity_type": entity_type, "filename": file.filename or "upload.csv",
        "status": "preview", "mapping_json": json.dumps(_suggest_mapping(headers)),
        "totals_json": json.dumps({"rows": len(rows), "exact_duplicates": exact,
                                   "ambiguous": len(ambiguous), "to_create": len(rows) - exact}),
        "row_errors_json": json.dumps(ambiguous[:50]), "rows_json": json.dumps(rows[:MAX_CSV_ROWS]),
        "created_at": _now()}, org)
    return {"import_id": rec["id"], "headers": headers, "suggested_mapping": json.loads(rec["mapping_json"]),
            "totals": json.loads(rec["totals_json"]), "sample": sample, "ambiguous": ambiguous[:20]}


class ImportCommit(BaseModel):
    mapping: dict
    resolutions: dict = Field(default_factory=dict)
    # Rows (1-based) the user chose to skip after reviewing ambiguous matches.
    skip_rows: list[int] = Field(default_factory=list)
    # create_only keeps existing records untouched; upsert refreshes matched
    # accounts with the incoming non-empty fields.
    mode: str = "create_only"


@router.post("/imports/{rid}/commit", dependencies=[Depends(verify_founder_action)])
def commit_import(rid: str, payload: ImportCommit) -> dict:
    org = _org()
    imp = store._row("csv_imports", rid, org)
    if not imp:
        raise HTTPException(404, "import not found")
    if imp["status"] == "committed":
        return {"import_id": rid, "replayed": True, "totals": json.loads(imp["totals_json"])}
    rows = json.loads(imp["rows_json"])
    mapping = payload.mapping
    unknown = set(mapping.values()) - CANONICAL_FIELDS
    if unknown:
        raise HTTPException(422, f"unknown canonical fields: {sorted(unknown)}")
    if payload.mode not in ("create_only", "upsert"):
        raise HTTPException(422, "mode must be create_only|upsert")
    skipped_rows = set(payload.skip_rows or [])
    created, updated, skipped, errors = 0, 0, 0, []
    with store.connect() as db:
        for idx, row in enumerate(rows, start=1):
            if idx in skipped_rows:
                skipped += 1
                continue
            try:
                mapped = {dst: row.get(src, "") for src, dst in mapping.items()}
                # Type check the one numeric field imports may carry.
                if "hunter_score" in mapped and mapped["hunter_score"] not in ("", None):
                    try:
                        int(str(mapped["hunter_score"]))
                    except ValueError:
                        errors.append({"row": idx, "error": "hunter_score must be an integer"})
                        continue
                if imp["entity_type"] == "account":
                    if not mapped.get("company_name"):
                        skipped += 1
                        errors.append({"row": idx, "error": "company_name is required"})
                        continue
                    dom = (mapped.get("domain") or "").lower() or None
                    existing = db.execute(
                        "SELECT id FROM commercial_accounts WHERE org_id=? AND domain=?",
                        (org, dom)).fetchone() if dom else None
                    if existing:
                        if payload.mode == "upsert":
                            fresh = {k: v for k, v in {
                                "company_name": mapped.get("company_name"),
                                "industry": mapped.get("industry"),
                                "company_size": mapped.get("company_size"),
                                "region": mapped.get("region")}.items() if v}
                            if fresh:
                                fresh["updated_at"] = _now()
                                db.execute(
                                    f"UPDATE commercial_accounts SET {','.join(f'{k}=?' for k in fresh)}"
                                    " WHERE id=?",
                                    (*fresh.values(), existing["id"]))
                                updated += 1
                            else:
                                skipped += 1
                        else:
                            skipped += 1
                        continue
                    db.execute(
                        "INSERT INTO commercial_accounts (id, org_id, company_name, domain,"
                        " industry, company_size, region, source, source_ref, attributes_json,"
                        " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (store.new_id("acct"), org, mapped.get("company_name", ""), dom,
                         mapped.get("industry", ""), mapped.get("company_size", ""),
                         mapped.get("region", ""), f"csv:{imp['filename']}", f"row:{idx}",
                         json.dumps(mapped), _now(), _now()))
                    created += 1
                else:
                    email = (mapped.get("email") or "").lower()
                    if not email:
                        skipped += 1
                        errors.append({"row": idx, "error": "email is required"})
                        continue
                    if db.execute("SELECT 1 FROM sales_leads WHERE email=?", (email,)).fetchone():
                        skipped += 1
                        continue
                    db.execute(
                        "INSERT INTO sales_leads (id, email, full_name, job_title, company,"
                        " company_domain, phone, country, source, source_detail, stage,"
                        " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (store.new_id("lead"), email, mapped.get("full_name", ""),
                         mapped.get("job_title", ""), mapped.get("company_name", ""),
                         mapped.get("domain", ""), mapped.get("phone", ""),
                         mapped.get("country", ""), f"csv:{imp['filename']}", f"row:{idx}",
                         "new", _now(), _now()))
                    created += 1
            except Exception as exc:
                errors.append({"row": idx, "error": f"{type(exc).__name__}: {exc}"})
    totals = {"rows": len(rows), "created": created, "updated": updated,
              "skipped": skipped, "errors": len(errors)}
    _update("csv_imports", rid, org, {"status": "committed", "mapping_json": json.dumps(mapping),
                                      "totals_json": json.dumps(totals),
                                      "row_errors_json": json.dumps(errors[:200])})
    return {"import_id": rid, "totals": totals, "errors": errors[:50]}


# ---------- integrations ----------
CATALOG_ORDER = ["resend", "hunter", "apollo", "prospeo", "buffer"]


def _catalog() -> list[dict]:
    """The connectable provider list, generated from the registries.

    Fixed order, fixed membership: unknown names (including test doubles)
    never appear. Display metadata only — behavior dispatches through the
    specs themselves, so this list cannot drift from what connect/sync do.
    """
    from services import oauth as oauth_service
    from services import provider_registry as registry

    items = []
    for name in CATALOG_ORDER:
        spec = registry.get(name)
        if spec is None or not spec.catalog:
            continue
        items.append({"provider": spec.name, "label": spec.label,
                      "keys": list(spec.keys), "auth": spec.auth, "sync": spec.sync})
    for provider, meta in oauth_service.PROVIDERS.items():
        items.append({"provider": provider, "label": meta["label"],
                      "keys": [f"{provider.upper()}_CLIENT_ID",
                               f"{provider.upper()}_CLIENT_SECRET"],
                      "auth": "oauth", "sync": meta.get("sync", "pull"),
                      "oauth": True})
    return items


@router.get("/integrations")
def integration_catalog() -> list[dict]:
    org = _org()
    stored = {r["provider"]: r for r in store._list("integration_connections", org, 100)}
    out = []
    for item in _catalog():
        conn = stored.get(item["provider"])
        configured = all(os.getenv(k) for k in item["keys"])
        if conn:
            out.append({**item, "connection": {k: conn[k] for k in (
                "status", "sync_status", "last_sync_at", "last_error_sanitized",
                "external_account_ref", "credential_ref")}, "configured": configured})
            continue
        if item.get("oauth"):
            # OAuth readiness is the external app approval, not a button.
            # Configured credentials flip the provider to connectable with
            # no code change; anything less stays honestly unavailable.
            from services import oauth as oauth_service
            if oauth_service.is_configured(item["provider"]):
                out.append({**item, "connection": None, "state": "available",
                            "configured": True})
            else:
                out.append({**item, "connection": None, "state": "coming_soon",
                            "configured": False,
                            "blocker": "provider app approval is not configured: set "
                            f"{', '.join(oauth_service.missing_config(item['provider']))}. "
                            + oauth_service.PROVIDERS[item["provider"]]["docs"]})
            continue
        if item.get("coming_soon"):
            out.append({**item, "connection": None, "state": "coming_soon",
                        "configured": configured,
                        "blocker": "provider app approval and OAuth credentials are not configured"})
        elif configured:
            out.append({**item, "connection": None, "state": "available",
                        "configured": True})
        else:
            out.append({**item, "connection": None, "state": "unavailable",
                        "configured": False,
                        "blocker": f"missing {', '.join(item['keys'])}"})
    return out


class ConnectIn(BaseModel):
    external_account_ref: str = ""
    scopes: list[str] = Field(default_factory=list)


@router.post("/integrations/{provider}/connect", dependencies=[Depends(verify_founder_action)])
def connect_provider(provider: str, payload: ConnectIn) -> dict:
    org = _org()
    item = next((c for c in _catalog() if c["provider"] == provider), None)
    if not item:
        raise HTTPException(404, "unknown provider")
    if item.get("coming_soon"):
        raise HTTPException(422, f"{provider} is catalog-only: OAuth app approval is not configured")
    if item.get("oauth"):
        # OAuth never completes here: this returns the provider's official
        # authorization URL and the callback finishes the connection.
        from services import oauth as oauth_service
        try:
            return {"provider": provider,
                    "authorization_url": oauth_service.build_authorize_url(provider, org)}
        except oauth_service.OAuthNotConfigured as exc:
            raise HTTPException(422, str(exc))
        except oauth_service.OAuthError as exc:
            raise HTTPException(502, f"authorization could not start: {exc}")
    if not all(os.getenv(k) for k in item["keys"]):
        raise HTTPException(422, f"{provider} credentials are not configured")
    # Validation dispatches through the provider spec: hunter runs its live
    # check, everything else declares key presence honestly.
    from services import provider_registry as registry
    spec = registry.get(provider)
    if spec is not None and spec.validate is not None:
        healthy, note = spec.validate()
    else:
        healthy, note = True, "key presence only; sync validates on first run"
    with store.connect() as db:
        existing = db.execute(
            "SELECT id FROM integration_connections WHERE org_id=? AND provider=?",
            (org, provider)).fetchone()
        status = "healthy" if healthy else "action_required"
        if existing:
            db.execute(
                "UPDATE integration_connections SET status=?, sync_status='idle',"
                " last_error_sanitized=?, external_account_ref=?, credential_ref=?,"
                " updated_at=? WHERE id=?",
                (status, note[:400], payload.external_account_ref,
                 item["keys"][0], _now(), existing["id"]))
            return store._row("integration_connections", existing["id"], org) or {}
        rec = {"id": store.new_id("conn"), "org_id": org, "provider": provider,
               "external_account_ref": payload.external_account_ref,
               "scopes_json": json.dumps(payload.scopes), "status": status,
               "sync_status": "idle", "last_error_sanitized": note[:400],
               "credential_ref": item["keys"][0], "created_at": _now(), "updated_at": _now()}
        cols, vals = list(rec.keys()), list(rec.values())
        db.execute(f"INSERT INTO integration_connections ({','.join(cols)}) VALUES"
                   f" ({','.join('?' for _ in cols)})", vals)
        return rec


@router.post("/integrations/{provider}/disconnect", dependencies=[Depends(verify_founder_action)])
def disconnect_provider(provider: str) -> dict:
    org = _org()
    item = next((c for c in _catalog() if c["provider"] == provider), None)
    if item and item.get("oauth"):
        # Revocation is local-first: tokens are destroyed even if the
        # provider's revoke call fails, so disconnect never strands secrets.
        from services import oauth as oauth_service
        oauth_service.delete_tokens(provider, org)
    with store.connect() as db:
        db.execute(
            "UPDATE integration_connections SET status='disconnected', sync_status='idle',"
            " updated_at=? WHERE org_id=? AND provider=?", (_now(), org, provider))
    return {"provider": provider, "status": "disconnected"}


@router.post("/integrations/{provider}/sync", dependencies=[Depends(verify_founder_action)])
def sync_provider(provider: str) -> dict:
    org = _org()
    conn = None
    with store.connect() as db:
        row = db.execute(
            "SELECT * FROM integration_connections WHERE org_id=? AND provider=?",
            (org, provider)).fetchone()
        if not row:
            raise HTTPException(404, "not connected")
        conn = dict(row)
        if conn["status"] not in ("healthy", "connected"):
            raise HTTPException(422, "connection needs attention before sync")
        db.execute(
            "UPDATE integration_connections SET sync_status='in_progress', updated_at=?"
            " WHERE id=?", (_now(), conn["id"]))
    # Read-only sync where supported; never writes to the provider here.
    synced, error = 0, ""
    try:
        from services import provider_registry as registry
        spec = registry.get(provider)
        if spec is not None and spec.sync_check is not None:
            spec.sync_check()
            synced = 1
        elif (next((c for c in _catalog() if c["provider"] == provider), {}) or {}).get("oauth"):
            # OAuth sync validates credentials (refreshing when expiring)
            # rather than moving data: connection health is the sync product.
            from services import oauth as oauth_service
            outcome = oauth_service.validate_connection(provider, org)
            if outcome.get("healthy"):
                synced = 1
            else:
                error = outcome.get("reason") or "connection is not healthy"
        else:
            synced = 0
            error = "sync not implemented for this provider; recorded as pending"
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
    with store.connect() as db:
        db.execute(
            "UPDATE integration_connections SET sync_status=?, last_sync_at=?,"
            " last_error_sanitized=?, updated_at=? WHERE id=?",
            ("succeeded" if not error and synced else "failed" if error else "pending",
             _now(), error[:400], _now(), conn["id"]))
        if error and (next((c for c in _catalog() if c["provider"] == provider), {}) or {}).get("oauth"):
            # An unhealthy OAuth connection must not keep presenting as
            # healthy: validation failure demotes it until reconnected.
            db.execute(
                "UPDATE integration_connections SET status='action_required', updated_at=?"
                " WHERE id=?", (_now(), conn["id"]))
    return {"provider": provider, "synced": synced, "error": error}


# ---------- adaptive onboarding sessions ----------
class SessionIn(BaseModel):
    path: str = "A"
    current_step: str = "company"


@router.get("/onboarding-sessions")
def list_sessions() -> list[dict]:
    rows = store._list("onboarding_sessions", _org(), 20)
    # Progress rides along so the UI can resume exactly, including which
    # track (self-guided or research flow) the session is on.
    out = []
    for row in rows:
        try:
            progress = json.loads(row.get("progress_json") or "{}")
        except ValueError:
            progress = {}
        out.append({**row, "progress": progress})
    return out


@router.post("/onboarding-sessions", dependencies=[Depends(verify_founder_action)])
def create_session(payload: SessionIn) -> dict:
    if payload.path not in ("A", "B"):
        raise HTTPException(422, "path must be A (from zero) or B (already operating)")
    return _save("onboarding_sessions", {
        "id": store.new_id("obs"), "path": payload.path,
        "current_step": payload.current_step, "progress_json": json.dumps({}),
        "completed": 0, "created_at": _now()}, _org())


@router.patch("/onboarding-sessions/{rid}", dependencies=[Depends(verify_founder_action)])
def update_session(rid: str, payload: dict) -> dict:
    patch: dict[str, Any] = {}
    if "current_step" in payload:
        patch["current_step"] = str(payload["current_step"])
    if "progress" in payload and isinstance(payload["progress"], dict):
        cur = store._row("onboarding_sessions", rid, _org()) or {}
        merged = {**json.loads(cur.get("progress_json") or "{}"), **payload["progress"]}
        patch["progress_json"] = json.dumps(merged)
    if "completed" in payload:
        patch["completed"] = 1 if payload["completed"] else 0
    return _update("onboarding_sessions", rid, _org(), patch)
