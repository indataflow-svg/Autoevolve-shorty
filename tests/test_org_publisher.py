import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from core import publishers_store, state
from services.publishers import catalog, list_publishers
from services.publishers.webhook import load_config


def test_free_org_webhook_is_encrypted_and_isolated():
    with tempfile.TemporaryDirectory() as directory:
        old = state.DB_PATH
        state.DB_PATH = Path(directory) / "company.db"
        try:
            state.init_db()
            free = state.create_org("Free Publisher", "free-publisher", plan="free")
            paid = state.create_org("Paid Publisher", "paid-publisher", plan="paid")
            with patch.dict(os.environ, {
                "APP_ENCRYPTION_KEY": "test-encryption-key",
                "PUBLISHER_WEBHOOK_URL": "https://operator.example.test/hook",
                "PUBLISHER_WEBHOOK_SECRET": "operator-secret",
                "PUBLIC_BASE_URL": "https://app.example.test",
            }, clear=False):
                publishers_store.save_webhook(
                    free["id"],
                    url="https://free.example.test/hook",
                    secret="free-secret-at-least-16",
                    account="free-account",
                    label="Free scheduler",
                    platforms="instagram,x",
                )
                connection = publishers_store.webhook_for_org(free["id"])
                assert connection is not None
                assert connection["secret"] == "free-secret-at-least-16"
                public = publishers_store.public_webhook_for_org(free["id"])
                assert public is not None and "secret" not in public and public["secret_set"] is True

                with state.connect() as db:
                    row = db.execute(
                        "SELECT secret_ciphertext FROM publisher_connections WHERE org_id = ?",
                        (free["id"],),
                    ).fetchone()
                assert row is not None
                assert "free-secret-at-least-16" not in row["secret_ciphertext"]

                free_names = [item["name"] for item in catalog(free["id"])]
                assert "buffer" not in free_names
                assert "webhook" in free_names
                paid_names = [item["name"] for item in catalog(paid["id"])]
                assert "buffer" in paid_names
                assert "webhook" in paid_names  # paid keeps the deployment-level fallback

                assert load_config(paid["id"]).url == "https://operator.example.test/hook"
                assert load_config(free["id"]).url == "https://free.example.test/hook"
                assert publishers_store.webhook_for_org(paid["id"]) is None
                assert [item.name for item in list_publishers(free["id"])] == ["webhook"]

                publishers_store.delete_webhook(free["id"])
                assert publishers_store.webhook_for_org(free["id"]) is None
                assert [item.name for item in catalog(free["id"])] == []
        finally:
            state.DB_PATH = old
