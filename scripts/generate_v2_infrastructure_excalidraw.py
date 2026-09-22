#!/usr/bin/env python3
"""Generate autoevolve-v2-infrastructure.excalidraw (V2 target state + 24/7 operating loop).

Rows are explicit, and box widths are chosen so every cross-lane arrow runs through a
verified empty corridor instead of through another box.
"""
import json
import textwrap
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "autoevolve-v2-infrastructure.excalidraw"

FONT = 16
PAD = 14
GAP = 35
LANE_X = 40
LANE_W = 1660
INNER_X = LANE_X + 30
LANE_RIGHT = LANE_X + LANE_W - 20

elements = []
_seed = [1000]
BOX = {}


def _nid(prefix):
    _seed[0] += 1
    return f"{prefix}{_seed[0]}"


def _base(kind, x, y, w, h, **kw):
    _seed[0] += 1
    element = {
        "id": kw.pop("id", _nid("e")),
        "type": kind,
        "x": x, "y": y, "width": w, "height": h,
        "angle": 0,
        "strokeColor": kw.pop("strokeColor", "#1e1e1e"),
        "backgroundColor": kw.pop("backgroundColor", "transparent"),
        "fillStyle": kw.pop("fillStyle", "solid"),
        "strokeWidth": kw.pop("strokeWidth", 1),
        "roughness": kw.pop("roughness", 1),
        "opacity": 100,
        "seed": _seed[0],
        "version": 1,
        "versionNonce": _seed[0] + 7,
        "isDeleted": False,
        "groupIds": kw.pop("groupIds", []),
        "frameId": None,
        "roundness": kw.pop("roundness", {"type": 3}),
        "boundElements": kw.pop("boundElements", None),
        "updated": 1,
        "link": None,
        "locked": False,
    }
    element.update(kw)
    return element


def _wrap(text, width_chars):
    out = []
    for para in text.split("\n"):
        out.extend(textwrap.wrap(para, width=max(20, width_chars)) or [""])
    return out


def _height(paragraphs, width, font_size=FONT):
    lines = []
    for para in paragraphs:
        lines.extend(_wrap(para, int((width - 2 * PAD) / (font_size * 0.52))))
    return len(lines) * font_size * 1.25 + 2 * PAD, lines


def make_box(x, y, w, paragraphs, *, stroke="#1e1e1e", bg="#ffffff", key=None):
    h, lines = _height(paragraphs, w)
    rid, tid = _nid("r"), _nid("t")
    rect = _base("rectangle", x, y, w, h, id=rid, strokeColor=stroke, backgroundColor=bg,
                 boundElements=[{"id": tid, "type": "text"}])
    text = _base("text", x + PAD, y + PAD - 1, w - 2 * PAD, h - 2 * PAD, id=tid,
                 strokeColor=stroke, roundness=None)
    full = "\n".join(lines)
    text.update({"text": full, "fontSize": FONT, "fontFamily": 2, "textAlign": "center",
                 "verticalAlign": "middle", "containerId": rid, "originalText": full,
                 "lineHeight": 1.25, "autoResize": True})
    elements.extend([rect, text])
    BOX[key or rid] = (x, y, w, h)
    return key or rid


def lane(name, y, rows, *, start_x=INNER_X, gap_top=52):
    """rows: list of rows; each row is a list of (width, paragraphs, kwargs)."""
    cursor = y + gap_top
    row_h = 0
    for row in rows:
        x = start_x
        for width, paragraphs, kw in row:
            assert x + width <= LANE_RIGHT, f"{name}: box overflows lane at x={x} w={width}"
            h, _ = _height(paragraphs, width)
            make_box(x, cursor, width, paragraphs, **kw)
            row_h = max(row_h, h)
            x += width + GAP
        cursor += row_h + GAP
        row_h = 0
    bottom = cursor - GAP + 24
    rid, tid = _nid("b"), _nid("t")
    rect = _base("rectangle", LANE_X, y, LANE_W, bottom - y, id=rid, strokeColor="#99a1b3",
                 backgroundColor="transparent", strokeWidth=1, roundness={"type": 3})
    text = _base("text", LANE_X + 12, y + 8, 1000, 20, id=tid, strokeColor="#99a1b3",
                 roundness=None)
    text.update({"text": name, "fontSize": 15, "fontFamily": 2, "textAlign": "left",
                 "verticalAlign": "top", "containerId": None, "originalText": name,
                 "lineHeight": 1.25, "autoResize": True})
    elements.extend([rect, text])
    return bottom


def anchor(key, side):
    x, y, w, h = BOX[key]
    return {
        "top": (x + w / 2, y),
        "bottom": (x + w / 2, y + h),
        "left": (x, y + h / 2),
        "right": (x + w, y + h / 2),
        "top_left": (x, y),
        "top_right": (x + w, y),
        "bottom_left": (x, y + h),
        "bottom_right": (x + w, y + h),
    }[side]


def arrow(start, end, *, label=None, dashed=False, color="#1e1e1e", elbow=None, points=None,
          label_at=None):
    sx, sy = start
    ex, ey = end
    if points is None:
        points = [[0, 0], [ex - sx, ey - sy]]
        if elbow == "v":      # vertical first, then horizontal
            points = [[0, 0], [0, ey - sy], [ex - sx, ey - sy]]
        elif elbow == "h":    # horizontal first, then vertical
            points = [[0, 0], [ex - sx, 0], [ex - sx, ey - sy]]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    elements.append(_base(
        "arrow", sx, sy, max(abs(min(xs)), abs(max(xs))) or 1, max(abs(min(ys)), abs(max(ys))) or 1,
        strokeColor=color, roundness={"type": 2}, strokeWidth=2, points=points,
        lastCommittedPoint=None, startBinding=None, endBinding=None,
        startArrowhead=None, endArrowhead="arrow",
        strokeStyle="dashed" if dashed else "solid",
    ))
    if label:
        lines = _wrap(label, 40)
        text_w = max(len(line) for line in lines) * 13 * 0.52 + 4
        text_h = len(lines) * 13 * 1.25
        if label_at:
            lx, ly = label_at
        else:
            last = points[-1]
            lx = sx + last[0] / 2 - text_w / 2
            ly = sy + last[1] / 2 - text_h / 2
        free_text(lx, ly, text_w, [label], color=color, size=13)


def free_text(x, y, w, paragraphs, *, color="#1e1e1e", size=16, center=False):
    lines = []
    for para in paragraphs:
        lines.extend(_wrap(para, int(w / (size * 0.52))))
    full = "\n".join(lines)
    text = _base("text", x, y, w, len(lines) * size * 1.25, strokeColor=color, roundness=None)
    text.update({"text": full, "fontSize": size, "fontFamily": 2,
                 "textAlign": "center" if center else "left", "verticalAlign": "top",
                 "containerId": None, "originalText": full, "lineHeight": 1.25,
                 "autoResize": True})
    elements.append(text)


GREEN_BG, GREEN_STROKE = "#e8f5e9", "#2e7d32"
RED_BG, RED_STROKE = "#fef3f2", "#b42318"
BLUE_BG, GREY_BG, PALE_BG = "#eaf2ff", "#f4f6fb", "#f8fafc"

# ------------------------------------------------------------------- title
free_text(60, 30, 1660, ["AutoEvolve V2 - target infrastructure, 24/7 operating loop and control gates"],
          size=30)
free_text(60, 78, 1660, [
    "Solid arrows = data and action flow. Dashed arrows = scheduled jobs, remote spawns and signed callbacks. "
    "Red panels = stop and reject conditions. Green panels = new in V2. All runtime state is local SQLite unless explicitly sent to a provider.",
], color="#5c6370", size=15)

# ------------------------------------------------- lane 1: public boundary
# rows: [entry, cb] / [edge, providers, outbound]
y1 = lane(
    "PUBLIC / THIRD-PARTY TRUST BOUNDARY",
    130,
    [
        [(360, ["Public entry points",
                "Website backend, Tally form, inbound email worker. Intake requires email OR phone; Pydantic size caps constrain every field."],
          {"key": "entry", "bg": GREY_BG}),
         (360, ["Signed callbacks",
                "Resend delivery and replies (Svix HMAC over raw body, stale timestamps rejected), Tally HMAC over raw body, external email routing."],
          {"key": "cb", "bg": GREY_BG})],

        [(700, ["Edge: Cloudflare Tunnel / HTTPS / optional Zero Trust, then the FastAPI entrypoint",
                "TLS and reverse proxy live outside the app; the new in-app limiter caps /integrations/* and returns 429 with Retry-After. Never put SALES_INTAKE_SECRET in "
                "browser JS - use a serverless relay. Provider key missing? Dashboard, /health and /docs stay up; only the feature reports disabled."],
          {"key": "edge"}),
         (380, ["Optional external providers",
                "Hunter, Apollo, Prospeo, Lusha, PDL, CE, OpenAI-compatible gateway, Pexels, Pixabay, Coverr, Resend. Missing key never blocks the dashboard."],
          {"key": "providers"}),
         (380, ["Cloudflare R2, Buffer drafts, social platforms",
                "G3 uploads media, verifies it is publicly readable, and creates drafts only. Final publishing stays reviewed by a human in Buffer."],
          {"key": "outbound"})],
    ],
)

# ----------------------------------- lane 2: private application boundary
y2 = lane(
    "PRIVATE APPLICATION BOUNDARY - FastAPI operator cockpit (exactly one process while SQLite is primary)",
    y1 + 30,
    [
        [(330, ["Dashboard and API authentication",
                "HTTP Basic with DASHBOARD_USER and DASHBOARD_PASSWORD, constant-time compare. Company, sales, marketing, setup and ops routers are all protected."],
          {"key": "auth"}),
         (400, ["Mutating operator-action gate: X-Founder-Action-Token = SALES_ACTION_TOKEN",
                "Required for resolving, draft change, approve, send, suppress, research and setup writes. V2 closes the holes: setup step write, coding create and apply, "
                "monitor run, marketing approve, regenerate, variant select, G3 create and Buffer schedule."],
          {"key": "gate", "bg": BLUE_BG}),
         (330, ["NEW rate limiter on public routes",
                "Per-IP sliding window plus auth-failure counting on /integrations/*; configurable and fail-closed."],
          {"key": "limiter", "bg": GREEN_BG, "stroke": GREEN_STROKE}),
         (370, ["Control gates 1-7 hold",
                "Provider calls optional and scoped; model output is a draft with approval and sending separate; suppressed leads cannot be enriched or contacted; "
                "auto contact off by default; G1 knowledge gates G2; G3 draft-only; setup reads never return secrets."],
          {"key": "gates"})],

        [(440, ["Sales service",
                "Intake upsert with attribution passthrough, cached company and contact resolution, enrichment, qualification, model-backed editable draft, human edit then "
                "approve then send, Resend delivery and reply ingest, meeting, suppression. NEW follow-up state: next_follow_up_at and follow_up_count, cleared by reply, "
                "bounce, meeting or suppression."],
          {"key": "sales"}),
         (440, ["Marketing orchestration",
                "Campaign and manual-post APIs, per-org capabilities and accounts, G1 content package and claim validation, G2 asset search, voice and FFmpeg render, "
                "variant choice, G3 R2 upload plus Buffer draft only. Tracks campaign_id, post_id and UTM. Pending review: approve or regenerate - retry is rejected."],
          {"key": "mkt"}),
         (440, ["Operations, coding and monitoring",
                "Task queue and project workspaces, optional OpenHands coding gateway, service monitor to incidents, unified queues, direct actions, immutable history. "
                "Access model: private operator routes; production guidance adds IAP or reverse proxy, TLS, service-account file permissions and log rotation or disk limits."],
          {"key": "ops"})],

        [(760, ["NEW scheduler service - jobs table, advisory-only batches",
                "Deep research, scoring, enrichment batches for qualified accounts only, draft generation, follow-up generation, daily priority-card build, provider health "
                "via check_all, cost digest. Jobs may write drafts, tasks and suggestions - they never send, publish, execute LinkedIn actions or change suppression state."],
          {"key": "sched", "bg": GREEN_BG, "stroke": GREEN_STROKE}),
         (370, ["NEW priority card: GET /company/operations/priority",
                "TODAY: drafts awaiting approval, follow-ups due, LinkedIn actions suggested, positive replies, meeting requests, campaigns in review, critical incidents. "
                "YESTERDAY: delivered, replies, positive replies, provider spend."],
          {"key": "card", "bg": GREEN_BG, "stroke": GREEN_STROKE}),
         (370, ["NEW notifier - webhook, SMTP or ntfy",
                "Positive replies, meeting requests, incidents and the daily digest. Fired after the event response is written; a notification failure never fails an event."],
          {"key": "notify", "bg": GREEN_BG, "stroke": GREEN_STROKE})],
    ],
)

# ------------------------- lane 3: optional compute (boxes right, left is corridor)
y3 = lane(
    "OPTIONAL COMPUTE - separate nodes only when contention or strategy justifies them",
    y2 + 30,
    [
        [(350, ["Media worker node (WORKER_MODE=remote, 4 vCPU / 8 GB)",
                "FFmpeg rendering and asset packs. Spawns over a configured transport instead of local subprocess.Popen, and writes through the app API because SQLite stays "
                "single-writer."],
          {"key": "media"})],
        [(350, ["Local-model node (16-32 GB RAM)",
                "Only if Ollama becomes strategically useful; not required initially. No GPU for the default API-first deployment."],
          {"key": "ollama"})],
        [(350, ["Future scale path",
                "Postgres plus a separate queue and worker layer, only after single-node concurrency or multi-instance need justifies it."],
          {"key": "future", "stroke": "#99a1b3", "bg": PALE_BG})],
    ],
    start_x=1320,
)

# -------------------------------- lane 4: private persistence boundary
y4 = lane(
    "PRIVATE PERSISTENCE / ASSETS - mounted Docker volumes: data/, projects/, config/",
    y3 + 30,
    [
        [(400, ["NEW programs - one deployment, two programs",
                "autoevolve ICP: B2B companies of 5-100 employees, broad market monitoring, moderate depth. foundry ICP: AI and software buyers of verified engineering "
                "output, low volume, deep intelligence. Separate scoring rubrics and ICP knowledge, shared claims - never a second deployment."],
          {"key": "prog", "bg": GREEN_BG, "stroke": GREEN_STROKE}),
         (370, ["SQLite data/company.db - one writer",
                "Leads, companies, contacts, enrichment, drafts, delivery and reply events, suppression, campaigns, posts, assets, attribution, tasks, orgs, settings and "
                "history. V2 columns: program_id, next_follow_up_at, follow_up_count, last_outbound_at."],
          {"key": "db"}),
         (350, ["SQLite data/company_ops.db",
                "Coding tasks and incidents with evidence and resolution JSON."],
          {"key": "opsdb"}),
         (360, ["NEW provider_calls ledger",
                "Provider, operation, program, lead, units, cost_usd and ok. Cost is stored against the opportunity so unit economics stay measurable: dollar per qualified "
                "lead, dollar per meeting, revenue per API dollar."],
          {"key": "cost", "bg": GREEN_BG, "stroke": GREEN_STROKE})],

        [(400, ["projects/ campaign workspaces",
                "G1 package and approved package, G2 source assets, manifests and renders, voice handoff, selected variant, campaign event history. Private runtime data, "
                "excluded from Git."],
          {"key": "projects"}),
         (400, [".env and engines/g3/config/g3.env",
                "Dashboard, action, intake and webhook secrets, provider API keys and model routes, brand and sender configuration, G3 Buffer and R2 configuration. Never "
                "committed, service-account readable only, rotate leaked values."],
          {"key": "secrets"}),
         (360, ["G1 knowledge source of truth",
                "Brand profile, per-program ICP registry, narratives, product claims, approved exemplars, CTA registry, platform rules and prohibited claims. Replace "
                "examples and verify approved facts before publishable media."],
          {"key": "knowledge"}),
         (290, ["STOP - backup and restore",
                "Back up with scripts/backup.sh using sqlite3 .backup, never cp a live database. Restore only with scripts/restore.sh --verify. A suppressed lead cannot "
                "move on any path, including scheduler jobs."],
          {"key": "stop", "bg": RED_BG, "stroke": RED_STROKE})],
    ],
)

# ------------------------------------------------------------------ arrows
# public entry into the application
arrow(anchor("entry", "bottom"), anchor("edge", "top"), label="validated intake")
arrow(anchor("cb", "bottom"), anchor("edge", "top"), dashed=True, label="signed callback")
arrow(anchor("edge", "bottom"), anchor("auth", "top"), label="HTTPS entry",
      label_at=(270, y1 + 7))
arrow(anchor("edge", "bottom_right"), anchor("limiter", "top"), elbow="h",
      label="intake and webhooks", label_at=(700, y1 + 7))
arrow(anchor("limiter", "top"), anchor("providers", "bottom"), label="scoped provider calls")
arrow(anchor("gates", "top"), anchor("outbound", "bottom"), label="draft-only publish path")

# authentication then the action gate
gate_bottom = BOX["gate"][1] + BOX["gate"][3]
row3_bottom = max(BOX[k][1] + BOX[k][3] for k in ("sched", "card", "notify"))
band_a = BOX["media"][1] + 6      # empty band left of the compute boxes
band_b = BOX["ollama"][1] + 6

arrow(anchor("auth", "right"), anchor("gate", "left"), label="authenticated",
      label_at=(405, gate_bottom + 9))
arrow(anchor("gate", "right"), anchor("limiter", "left"), label="mutating action",
      label_at=(840, gate_bottom + 9))

# gate fans out into the three service columns
arrow(anchor("gate", "bottom_left"), anchor("sales", "top"), label="gated sales actions",
      label_at=(250, gate_bottom + 9))
arrow(anchor("gate", "bottom"), anchor("mkt", "top"), label="gated marketing actions")
arrow(anchor("gate", "bottom_right"), anchor("ops", "top"), label="gated ops actions")

# scheduler, priority card, notifier
arrow(anchor("sched", "top"), anchor("sales", "bottom"), dashed=True, label="scheduled batches")
arrow(anchor("sched", "top_right"), anchor("mkt", "bottom"), dashed=True, label="drafts only")
arrow(anchor("sched", "right"), anchor("card", "left"), label="build card",
      label_at=(835, row3_bottom + 9))
arrow(anchor("card", "right"), anchor("notify", "left"), label="alerts",
      label_at=(1240, row3_bottom + 9))
arrow(anchor("ops", "bottom"), anchor("notify", "top"), dashed=True, label="incidents")

# cross-lane routing: verticals use verified corridors between boxes
# corridor A: x=58 (left margin) -> programs box top-left corner
sx, sy = anchor("sales", "bottom_left")
ex, ey = anchor("prog", "top_left")
arrow((sx, sy), (ex, ey), label="program_id, lead state", label_at=(80, band_a),
      points=[[0, 0], [-12, 0], [-12, ey - sy], [0, ey - sy]])

# corridor B: x=847 (gap between scheduler and card) -> company.db
arrow((847, BOX["mkt"][1] + BOX["mkt"][3]), (847, BOX["db"][1]),
      label="campaign state, tasks, attribution", label_at=(760, band_a))

# corridor C: x=1252 (gap between card and notifier) -> company_ops.db
arrow((1252, BOX["ops"][1] + BOX["ops"][3]), (1252, BOX["opsdb"][1]),
      label="coding tasks and incidents", label_at=(1090, band_a))

# media node -> cost ledger via the corridor at x=1280 (between opsdb and cost)
mx, my = anchor("media", "left")
cx, cy = anchor("cost", "left")
arrow((mx, my), (cx, cy), label="render and provider spend", label_at=(1090, band_b),
      points=[[0, 0], [-40, 0], [-40, cy - my], [cx - mx, cy - my]])

# scheduler spawns the remote media worker; card reaches the model gateway
arrow(anchor("sched", "bottom"), anchor("media", "left"), dashed=True, elbow="v",
      label="spawn media worker", label_at=(450, band_a))
arrow(anchor("card", "bottom"), anchor("ollama", "left"), elbow="v",
      label="model gateway", label_at=(800, band_b))

# notifier -> future scale note via the right margin (x=1685, clear of the compute boxes)
sx, sy = anchor("notify", "right")
fx, fy = anchor("future", "right")
arrow((sx, sy), (fx, fy), dashed=True, label="scale only when measured",
      label_at=(1410, BOX["ollama"][1] - 25),
      points=[[0, 0], [45, 0], [45, fy - sy], [fx - sx, fy - sy]])

free_text(60, y4 + 40, 1660, [
    "Data governance boundary: lead and email records may be personal data. Operators - not the software - own lawful collection, consent, retention, deletion, suppression and "
    "provider compliance. Never place real lead payloads in public issues, fixtures, screenshots or logs. Repository guidance excludes .env, SQLite, generated media, provider "
    "payloads, contact exports and agent history from Git.",
], color="#5c6370", size=14)

doc = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://github.com/excalidraw/excalidraw",
    "elements": elements,
    "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
    "files": {},
}
OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"wrote {OUT} with {len(elements)} elements")
