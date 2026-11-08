import tempfile
from pathlib import Path

import pytest

from core import sales_store, state
from core.auth_context import current_org_id
from services.sales_service import send_approved


def test_session_org_scopes_lead_reads_and_summaries():
    with tempfile.TemporaryDirectory() as directory:
        old = state.DB_PATH, sales_store.DB_PATH
        state.DB_PATH = sales_store.DB_PATH = Path(directory) / "company.db"
        try:
            state.init_db()
            sales_store.init_sales_db()
            first = state.create_org("Scope One", "scope-one", plan="free")
            second = state.create_org("Scope Two", "scope-two", plan="free")
            one, _ = sales_store.upsert_lead({
                "full_name": "One Lead", "email": "one@one.test", "source": "manual",
                "org_id": first["id"],
            })
            two, _ = sales_store.upsert_lead({
                "full_name": "Two Lead", "email": "two@two.test", "source": "manual",
                "org_id": second["id"],
            })
            token = current_org_id.set(first["id"])
            try:
                assert sales_store.get_lead(one["id"]) is not None
                assert sales_store.get_lead(two["id"]) is None
                assert [row["id"] for row in sales_store.list_leads()] == [one["id"]]
                assert sales_store.summary()["total"] == 1
                assert sales_store.get_company_profile("one.test", org_id=second["id"]) is None
                draft = sales_store.create_draft(one["id"], "Subject", "Body")
                with pytest.raises(PermissionError):
                    send_approved(draft["id"])
            finally:
                current_org_id.reset(token)
        finally:
            state.DB_PATH, sales_store.DB_PATH = old
