import json
from pathlib import Path

from core.state import (
    get_active_org,
    get_recent_tasks,
)


ROOT = Path(__file__).parent.parent
PROJECTS_ROOT = ROOT / "projects"


def _research_history(active_org: dict | None) -> list[dict]:
    history = []
    if not active_org:
        return history

    research_dir = PROJECTS_ROOT / active_org["slug"] / "research"
    if not research_dir.exists():
        return history

    files = sorted(
        [path for path in research_dir.glob("research-*.json") if path.is_file()],
        reverse=True,
    )[:8]

    for path in files:
        try:
            data = json.loads(path.read_text())
            history.append({
                "file": path.name,
                "title": data.get("title", "Research"),
                "summary": data.get("executive_summary", ""),
                "decision": data.get("decision", ""),
            })
        except Exception:
            continue
    return history


def get_dashboard_state() -> dict:
    active_org = get_active_org()
    return {
        "active_org": active_org,
        "tasks": get_recent_tasks(limit=20),
        "research_history": _research_history(active_org),
    }


def get_operations_page_state() -> dict:
    return {
        "active_org": get_active_org(),
    }
