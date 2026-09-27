"""Export the FastAPI contract for the React client without starting a server."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "autoevolve-ui" / "openapi.json"
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app.api import app  # noqa: E402

target.write_text(json.dumps(app.openapi(), indent=2) + "\n")
