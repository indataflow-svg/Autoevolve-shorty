"""Real FastAPI with an isolated database for company-context browser tests."""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.update({
    "DASHBOARD_USER": "founder", "DASHBOARD_PASSWORD": "browser-secret",
    "SALES_ACTION_TOKEN": "browser-action", "SALES_SEND_RECONCILE_ON_STARTUP": "false",
    "RATE_LIMIT_ENABLED": "false",
})

from core import marketing_store, ops_store, sales_store, state  # noqa: E402

storage = tempfile.TemporaryDirectory(prefix="onboarding-browser-")
database = Path(storage.name) / "company.db"
state.DB_PATH = sales_store.DB_PATH = marketing_store.DB_PATH = ops_store.DB_PATH = database
state.init_db()
sales_store.init_sales_db()
marketing_store.init_marketing_db()
ops_store.init_db()

from app.api import app  # noqa: E402
import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8791, log_level="warning")
