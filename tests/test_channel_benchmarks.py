"""World benchmark data + its wiring into suggestions.

Part 1 acceptance:
- every lookup returns cited ranges with vintage, never a bare number;
- unknown industries fall back to the general band and say so;
- expected_replies() is pure arithmetic over the cited band.
"""
from core.channel_benchmarks import (
    cold_reply_benchmark,
    expected_replies,
    normalize_industry,
    optin_benchmark,
)


def test_normalize_known_aliases():
    assert normalize_industry("SaaS") == "software"
    assert normalize_industry("3PL") == "general"
    assert normalize_industry("Freight Forwarding") == "general"
    assert normalize_industry("") == "general"
    assert normalize_industry(None) == "general"
    assert normalize_industry("logistics") == "general"


def test_cold_benchmark_always_cited():
    bench = cold_reply_benchmark("logistics")
    assert bench["reply_low_pct"] == 1.0
    assert bench["reply_high_pct"] == 5.0
    assert bench["elite_pct"] == 10.0
    assert bench["vintage"] == "2025-2026"
    assert len(bench["sources"]) >= 4
    # Honest fallback: general band, labelled as such.
    assert "general B2B" in bench["coverage"]
    assert bench["industry"] == "logistics"
    assert bench["industry_matched"] is False


def test_optin_benchmark_software_vs_fallback():
    saas = optin_benchmark("saas")
    assert saas["industry_matched"] is True
    assert saas["open_low_pct"] == 35.0
    fallback = optin_benchmark("logistics")
    assert fallback["industry_matched"] is False
    assert "no industry-specific study on file" in fallback["coverage"]


def test_expected_replies_math():
    est = expected_replies(100, "logistics")
    assert est == {
        "low": 1, "high": 5, "unit": "replies", "sends": 100,
        "basis": est["basis"], "sources": est["sources"],
    }
    assert "1-5%" in est["basis"]
    assert expected_replies(0)["high"] == 0
    assert expected_replies(-50)["low"] == 0
    assert expected_replies("junk")["sends"] == 0


def test_reply_basis_prefers_recorded_then_benchmark():
    from core.suggest import _reply_basis

    recorded = {"engagement": {"channels": {"email": {"sent": 20, "replied": 2}}}}
    rate, basis = _reply_basis(recorded, "logistics")
    assert rate == 0.1
    assert "recorded rate 2/20" in basis

    thin = {"engagement": {"channels": {"email": {"sent": 3, "replied": 0}}}}
    rate, basis = _reply_basis(thin, "logistics")
    assert rate is None
    assert "world band 1-5%" in basis
    assert "10+ sends establish your own" in basis


def test_suggest_outputs_carry_benchmarks():
    from core.suggest import suggest_workflows

    workflows = suggest_workflows(0)
    for rec in workflows["recommendations"]:
        if rec["method"] in ("approved_send", "targeted_outbound"):
            assert "benchmark_replies" in rec
            assert rec["benchmark_replies"]["unit"] == "replies"


def test_benchmarks_endpoint_empty_world():
    import os
    import tempfile
    import unittest
    from pathlib import Path
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    import core.state as state
    from app.api import app
    from core import commercial_store, marketing_store, sales_store, workflow_store

    tmp = tempfile.TemporaryDirectory()
    base = Path(tmp.name)
    paths = (state.DB_PATH, commercial_store.DB_PATH, sales_store.DB_PATH,
             workflow_store.DB_PATH, marketing_store.DB_PATH)
    state.DB_PATH = commercial_store.DB_PATH = sales_store.DB_PATH = base / "company.db"
    workflow_store.DB_PATH = base / "workflows.db"
    state.init_db()
    sales_store.init_sales_db()
    commercial_store.init_commercial_db()
    marketing_store.init_marketing_db()
    workflow_store.init_db()
    env = patch.dict(os.environ, {
        "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "pw",
        "SALES_ACTION_TOKEN": "act", "SALES_SEND_RECONCILE_ON_STARTUP": "false",
    }, clear=False)
    env.start()
    try:
        client = TestClient(app)
        res = client.get("/company/commercial/benchmarks?sends=200", auth=("founder", "pw"))
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["industry"] is None
        assert body["industry_source"] == "none"
        assert body["cold"]["reply_low_pct"] == 1.0
        assert body["expected"]["sends"] == 200
        assert body["expected"]["low"] == 2
        assert body["expected"]["high"] == 10
        bad = client.get("/company/commercial/benchmarks", auth=("founder", "pw"))
        assert bad.status_code == 200  # default sends=100
        assert client.get("/company/commercial/benchmarks").status_code == 401
    finally:
        env.stop()
        (state.DB_PATH, commercial_store.DB_PATH, sales_store.DB_PATH,
         workflow_store.DB_PATH, marketing_store.DB_PATH) = paths
        tmp.cleanup()


def _benchmarks_client():
    import os
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    import core.state as state
    from app.api import app
    from core import commercial_store, marketing_store, sales_store, workflow_store

    tmp = tempfile.TemporaryDirectory()
    base = Path(tmp.name)
    paths = (state.DB_PATH, commercial_store.DB_PATH, sales_store.DB_PATH,
             workflow_store.DB_PATH, marketing_store.DB_PATH)
    state.DB_PATH = commercial_store.DB_PATH = sales_store.DB_PATH = base / "company.db"
    marketing_store.DB_PATH = base / "company.db"
    workflow_store.DB_PATH = base / "workflows.db"
    state.init_db()
    sales_store.init_sales_db()
    commercial_store.init_commercial_db()
    marketing_store.init_marketing_db()
    workflow_store.init_db()
    env = patch.dict(os.environ, {
        "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "pw",
        "SALES_ACTION_TOKEN": "act", "SALES_SEND_RECONCILE_ON_STARTUP": "false",
    }, clear=False)
    env.start()
    return tmp, paths, env, TestClient(app), ("founder", "pw")


def _benchmarks_teardown(tmp, paths, env):
    import core.state as state
    from core import commercial_store, marketing_store, sales_store, workflow_store

    env.stop()
    (state.DB_PATH, commercial_store.DB_PATH, sales_store.DB_PATH,
     workflow_store.DB_PATH, marketing_store.DB_PATH) = paths
    tmp.cleanup()


def test_outreach_page_carries_benchmark():
    tmp, paths, env, client, auth = _benchmarks_client()
    try:
        res = client.get("/company/ui/outreach", auth=auth)
        assert res.status_code == 200, res.text
        bench = res.json()["benchmark"]
        assert bench["sendable"] == 0
        assert bench["expected"] == {
            "low": 0, "high": 0, "unit": "replies", "sends": 0,
            "basis": bench["expected"]["basis"], "sources": bench["expected"]["sources"]}
        assert bench["cold"]["reply_low_pct"] == 1.0
    finally:
        _benchmarks_teardown(tmp, paths, env)


def test_market_comparison_verdicts():
    from core.suggest import _reply_basis, market_comparison

    assert market_comparison(None, "logistics") is None
    assert market_comparison(0.005, "logistics")["verdict"] == "below market"
    assert market_comparison(0.03, "logistics")["verdict"] == "within market"
    assert market_comparison(0.08, "logistics")["verdict"] == "above market"
    assert market_comparison(0.08, "saas")["industry"] == "saas"

    recorded = {"engagement": {"channels": {"email": {"sent": 100, "replied": 8}}}}
    rate, basis = _reply_basis(recorded, "logistics")
    assert rate == 0.08
    assert "above market" in basis
    assert "8/100" in basis


def test_benchmarks_endpoint_reports_recorded_and_market():
    from core import sales_store

    tmp, paths, env, client, auth = _benchmarks_client()
    try:
        lead, _ = sales_store.upsert_lead(
            {"email": "a@x.test", "company": "X", "source": "manual"})
        draft = sales_store.create_draft(lead["id"], "Subject line here", "A complete message body here.")
        sales_store.approve_draft(draft["id"])
        res = client.get("/company/commercial/benchmarks", auth=auth)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["recorded"]["sent"] == 0
        assert body["market"] is None
    finally:
        _benchmarks_teardown(tmp, paths, env)


def test_network_stats_anonymized_and_opt_in_gated():
    tmp, paths, env, client, auth = _benchmarks_client()
    try:
        stats = client.get("/company/commercial/network-stats", auth=auth)
        assert stats.status_code == 200, stats.text
        body = stats.json()
        assert body["contribution"] == "opted_out"
        assert body["pool"] == "none_yet"
        dumped = stats.text.lower()
        for forbidden in ("email", "domain", "company_name", "subject", "body"):
            assert f'"{forbidden}"' not in dumped, forbidden
        denied = client.post("/company/commercial/network-contribution",
                             auth=auth, json={"opt_in": True})
        assert denied.status_code in (401, 403), denied.status_code
        headers = {"X-Founder-Action-Token": "act"}
        flipped = client.post("/company/commercial/network-contribution",
                              auth=auth, headers=headers, json={"opt_in": True})
        assert flipped.status_code == 200, flipped.text
        assert flipped.json() == {"contribution": "opted_in"}
        assert client.get("/company/commercial/network-stats", auth=auth).json()["contribution"] == "opted_in"
        back = client.post("/company/commercial/network-contribution",
                           auth=auth, headers=headers, json={"opt_in": False})
        assert back.json() == {"contribution": "opted_out"}
    finally:
        _benchmarks_teardown(tmp, paths, env)


def test_benchmarks_industry_override():
    tmp, paths, env, client, auth = _benchmarks_client()
    try:
        res = client.get("/company/commercial/benchmarks?industry=logistics", auth=auth)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["industry"] == "logistics"
        assert body["industry_source"] == "requested"
        assert "general B2B" in body["cold"]["coverage"]
    finally:
        _benchmarks_teardown(tmp, paths, env)
