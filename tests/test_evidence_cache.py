"""The evidence union is cached per (org, database fingerprint).

Every suggester and both Commercial benchmark endpoints rebuild this union; it
was the most expensive thing a page load did. The cache must never serve stale
counts after a write and must never cross organizations.
"""
from __future__ import annotations

import time

import core.evidence as evidence
import core.state as state


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "DB_PATH", tmp_path / "company.db")
    state.init_db()
    calls = {"n": 0}

    def fake_collect(org: int = 0):
        calls["n"] += 1
        return {"org_id": org, "accounts": {"total": calls["n"]}, "leads": {"total": 0}}

    monkeypatch.setattr(evidence, "_collect_evidence", fake_collect)
    monkeypatch.setattr(evidence, "EVIDENCE_CACHE_SECONDS", 5.0)
    evidence._evidence_cache.clear()
    return calls


def _write():
    """Any committed write must invalidate: the fingerprint is db mtime+size."""
    time.sleep(0.01)
    with state.connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS probe (id INTEGER)")
        db.execute("INSERT INTO probe (id) VALUES (1)")


def test_second_read_is_served_from_cache(tmp_path, monkeypatch):
    calls = _setup(tmp_path, monkeypatch)
    first = evidence.collect_evidence(0)
    second = evidence.collect_evidence(0)
    assert first == second
    assert calls["n"] == 1


def test_a_write_invalidates_immediately(tmp_path, monkeypatch):
    calls = _setup(tmp_path, monkeypatch)
    evidence.collect_evidence(0)
    _write()
    fresh = evidence.collect_evidence(0)
    assert calls["n"] == 2
    assert fresh["accounts"]["total"] == 2


def test_organizations_never_share_an_entry(tmp_path, monkeypatch):
    calls = _setup(tmp_path, monkeypatch)
    evidence.collect_evidence(0)
    other = evidence.collect_evidence(7)
    assert other["org_id"] == 7
    assert calls["n"] == 2


def test_cached_value_is_not_exposed_for_mutation(tmp_path, monkeypatch):
    calls = _setup(tmp_path, monkeypatch)
    first = evidence.collect_evidence(0)
    first["accounts"]["total"] = 999
    second = evidence.collect_evidence(0)
    assert second["accounts"]["total"] == 1
    assert calls["n"] == 1


def test_cache_can_be_disabled(tmp_path, monkeypatch):
    calls = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(evidence, "EVIDENCE_CACHE_SECONDS", 0.0)
    evidence.collect_evidence(0)
    evidence.collect_evidence(0)
    assert calls["n"] == 2
