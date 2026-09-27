"""Generate the editable architecture map from inspected runtime components.

Run: python3 scripts/generate_system_architecture_excalidraw.py
The diagram is intentionally high-level; docs/system-architecture.md has exact routes.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "system-architecture.excalidraw"
elements: list[dict] = []
next_id = 0


def ident(prefix: str) -> str:
    global next_id
    next_id += 1
    return f"architecture-{prefix}-{next_id}"


def common(kind: str, x: float, y: float, w: float, h: float, *, stroke: str, fill: str) -> dict:
    return {
        "id": ident(kind), "type": kind, "x": x, "y": y, "width": w, "height": h,
        "angle": 0, "strokeColor": stroke, "backgroundColor": fill,
        "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": {"type": 3} if kind == "rectangle" else None,
        "seed": next_id * 7919, "version": 1, "versionNonce": next_id * 104729,
        "isDeleted": False, "boundElements": [], "updated": 0,
        "link": None, "locked": False,
    }


def label(value: str, x: float, y: float, *, size: int = 20, color: str = "#e2e8f0", bold: bool = False) -> None:
    lines = value.split("\n")
    height = len(lines) * size * 1.35
    width = max(len(line) for line in lines) * size * 0.57 + 8
    item = common("text", x, y, width, height, stroke=color, fill="transparent")
    item.update({
        "text": value, "originalText": value, "fontSize": size,
        "fontFamily": 2, "textAlign": "left", "verticalAlign": "top",
        "baseline": int(size * 0.9), "containerId": None, "autoResize": True,
        "lineHeight": 1.35, "bold": bold,
    })
    elements.append(item)


def box(x: float, y: float, w: float, h: float, title: str, detail: str, *, fill: str, stroke: str) -> None:
    elements.append(common("rectangle", x, y, w, h, stroke=stroke, fill=fill))
    label(title, x + 18, y + 13, size=21, color="#f8fafc", bold=True)
    label(detail, x + 18, y + 49, size=16, color="#cbd5e1")


def arrow(x1: float, y1: float, x2: float, y2: float, *, color: str = "#6ea8db", via: list[tuple[float, float]] | None = None) -> None:
    vertices = [(x1, y1), *(via or []), (x2, y2)]
    item = common("arrow", x1, y1, max(x for x, _ in vertices) - min(x for x, _ in vertices), max(y for _, y in vertices) - min(y for _, y in vertices), stroke=color, fill="transparent")
    item.update({
        "points": [[x - x1, y - y1] for x, y in vertices],
        "startBinding": None, "endBinding": None,
        "startArrowhead": None, "endArrowhead": "arrow",
        "lastCommittedPoint": None, "elbowed": False,
    })
    elements.append(item)


COLORS = {
    "client": ("#172b43", "#5b9bd5"),
    "frontend": ("#1d3447", "#68c9d4"),
    "api": ("#23324c", "#8c9ff0"),
    "domain": ("#2c324d", "#c0a2f1"),
    "state": ("#2c3c40", "#8dd3aa"),
    "warning": ("#3c342d", "#e8bb72"),
}


def node(col: str, y: int, h: int, title: str, detail: str, tone: str) -> None:
    x = {"client": 60, "frontend": 560, "api": 1060, "domain": 1560, "state": 2060}[col]
    fill, stroke = COLORS[tone]
    box(x, y, 420, h, title, detail, fill=fill, stroke=stroke)


label("AutoEvolve · implemented system architecture", 60, 34, size=34, color="#f8fafc", bold=True)
label("2026-09-27 source snapshot  |  editable map  |  exact routes and caveats in system-architecture.md", 60, 86, size=19, color="#aebfd0")

for x, title, subtitle in [
    (60, "ENTRY", "operator + external events"),
    (560, "REACT / VITE", "twelve operator pages"),
    (1060, "FASTAPI", "one application process"),
    (1560, "DOMAIN LOGIC", "services + engines"),
    (2060, "STATE / PROVIDERS", "authoritative records + effects"),
]:
    label(title, x, 155, size=24, color="#f8fafc", bold=True)
    label(subtitle, x, 189, size=16, color="#8fa4bb")

node("client", 250, 137, "Operator browser", "Home, Onboarding, Contacts,\nCompanies, Research, Outreach,\nReplies, Meetings, Campaigns,\nContent, Integrations, Settings", "client")
node("client", 486, 120, "External intake", "Website / Tally leads; Cloudflare\nEmail Routing; Resend events", "warning")
node("client", 688, 103, "Entry + public utilities", "/ → React Home; legacy redirects;\n/meet, /calendar; /health", "client")

node("frontend", 250, 137, "AuthGate + API transport", "GET /company/ui/session; Basic auth;\noptional founder action token;\n401/403/422/429/5xx handling", "frontend")
node("frontend", 486, 137, "React page layer", "URL filters / selection; drawers;\nTanStack Query + Table; typed API\nadapters and OpenAPI schema", "frontend")
node("frontend", 688, 103, "Static build", "Vite dist served by FastAPI\nat page routes and /assets", "frontend")

node("api", 250, 137, "app/api.py gateway", "FastAPI startup; router mounts;\nBasic auth for /company/*;\nReact operator + booking utilities", "api")
node("api", 486, 137, "Typed read projections", "/company/ui/*; /company/sales/\ncontacts; /companies; Pydantic\nresponse models, no new writes", "api")
node("api", 688, 130, "Existing action routers", "/company/sales; /company/marketing;\n/company/setup; /company coding +\nmonitoring", "api")
node("api", 914, 112, "Intake router", "/integrations/*: rate limit +\nwebhook secret/signature; no Basic", "warning")

node("domain", 250, 137, "Sales services", "Research, prospect, enrich, draft,\napprove/send/reconcile; inbound\nreply + meeting metadata", "domain")
node("domain", 486, 137, "Marketing services + engines", "Campaign worker → G1 scripts →\nG2 media → G3 Buffer drafts;\nmanual post scheduling + insights", "domain")
node("domain", 688, 130, "Setup + operations", "Provider-key validation; own-brand\nsettings; coding tasks and\nmonitor incident services", "domain")

node("state", 250, 137, "data/company.db", "Sales leads/drafts/interactions/\nprofiles; own orgs; campaigns;\nmanual posts; tasks; memories", "state")
node("state", 486, 137, "projects/ and .env", "Scripts, videos, asset packs,\nresearch files; provider keys\nand deployment settings", "state")
node("state", 688, 130, "External providers", "Hunter / Apollo / Prospeo /\nLusha; Resend; Buffer; model\nand media providers as configured", "state")
node("state", 914, 112, "data/company_ops.db", "Coding tasks + incidents; separate\nfrom the main company database", "state")

# Primary request paths. Read projections reach the store directly; action
# routers pass through the existing services and state guards.
arrow(480, 320, 560, 320)
arrow(980, 320, 1060, 320)
arrow(980, 555, 1060, 555)
arrow(980, 585, 1060, 755)
arrow(1480, 520, 2060, 320, via=[(1520, 520), (1520, 225), (2020, 225), (2020, 320)])
arrow(1480, 735, 1560, 320)
arrow(1480, 755, 1560, 555)
arrow(1480, 755, 1560, 755)
arrow(1980, 320, 2060, 320)
arrow(1980, 555, 2060, 555)
arrow(1980, 755, 2060, 555)
arrow(1980, 785, 2060, 962)
# Intake bypasses dashboard Basic but does not bypass its own security checks.
arrow(480, 550, 1060, 970, color="#e8bb72", via=[(520, 550), (520, 1070), (1030, 1070), (1030, 970)])
arrow(1480, 970, 1560, 380, color="#e8bb72")
arrow(480, 738, 1060, 380, color="#5b9bd5", via=[(520, 738), (520, 850), (1030, 850), (1030, 380)])

label("SECURITY BOUNDARIES", 60, 1135, size=24, color="#f8fafc", bold=True)
box(60, 1184, 770, 132, "Dashboard reads", "HTTP Basic on /company/*; React shell/assets load independently.\nCredentials are held in React memory; a reload signs out.", fill="#1c3445", stroke="#68c9d4")
box(860, 1184, 770, 132, "Gated actions", "Selected mutations require Basic + X-Founder-Action-Token.\nOther Basic-only writes keep their existing route-specific gate.", fill="#27344b", stroke="#8c9ff0")
box(1660, 1184, 820, 132, "Inbound webhooks", "No dashboard Basic; per-route shared secret/signature + rate limit.\nCloudflare Email Routing worker is deployed separately.", fill="#3c342d", stroke="#e8bb72")

label("SEMANTIC GUARDS", 60, 1385, size=24, color="#f8fafc", bold=True)
box(60, 1432, 770, 121, "Company identity", "Company list = lead/domain/profile projection.\nNo canonical company table; own-brand org ≠ prospect company.", fill="#2c3c40", stroke="#8dd3aa")
box(860, 1432, 770, 121, "Outreach + meetings", "Draft ≠ approved ≠ sent ≠ delivered.\nMeeting metadata marker ≠ confirmed calendar booking.", fill="#2c3c40", stroke="#8dd3aa")
box(1660, 1432, 820, 121, "Buffer lifecycle", "Campaign G3 handoff creates drafts; manual scheduling is explicit.\nScheduled ≠ published; insights require a saved Buffer post ID.", fill="#2c3c40", stroke="#8dd3aa")
label("Arrows summarize request and state relationships; the Markdown map lists the exact route and storage contracts.", 60, 1580, size=17, color="#8fa4bb")

document = {
    "type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
    "elements": elements,
    "appState": {
        "viewBackgroundColor": "#101d2e", "gridSize": None,
        "currentItemFontFamily": 2, "currentItemFontSize": 20,
        "scrollX": 0, "scrollY": 0, "zoom": {"value": 0.35},
    },
    "files": {},
}
OUTPUT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {OUTPUT.relative_to(ROOT)} ({len(elements)} editable elements)")
