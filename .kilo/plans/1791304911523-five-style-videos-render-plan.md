# Plan: Render Five Style-Tagged Videos via Per-Video Style Pipeline

## Goal

Render five short promotional videos, each in a distinct house style, using the
per-video style threading already implemented across the video pipeline.

## Style Map (from user)

| # | Project ID (slug) | Title          | Style       | Notes                          |
|---|-------------------|----------------|-------------|--------------------------------|
| 1 | `teaser-door`     | "The door"     | `noir`      | chiaroscuro, single light shaft |
| 2 | `desk-warm`       | "The desk"     | `warm-real` | cold → morning daylight        |
| 3 | `pile-human`      | "The pile"     | `human-real`| single lamp, unpolished        |
| 4 | `ring-graphic`    | "The ring"     | `flat-graphic` | blue/indigo geometric silhouettes |
| 5 | `room-calm`       | "The room"     | `calm-real` | **uniform calm**, no chaos→calm switch |

## Code Changes Already Completed

All code changes are in place and tests pass (64/64 video tests, ruff clean):

1. **`services/video/defs.py`** — `HOUSE_STYLES` with `direction` + `prompt_head` per style already existed.
2. **`services/video/spec_builder.py`** — `build_spec()` accepts `style` param, writes to `spec["extra"]["style"]`.
3. **`services/video/pipeline.py`** — `plan_video()`, `direct_brief()`, and `launch()` accept `style`; `direct_brief()` injects `HOUSE_STYLES[style]["direction"]` into the storyteller's instructions (beats authored IN the style); `DEFAULT_HOUSE_STYLE` added to top-level imports.
4. **`services/video/shot_planner.py`** — `_attach_continuity()` takes and uses the spec's style for the continuity context.
5. **`services/video/job_builder.py`** — Fixed `GRAPHIC_STYLE` import bug (was trying to import from `defs.py` where it doesn't exist); `_full_video_chunks()` uses the resolved style name for `continuityContext.style` instead of a hardcoded string.
6. **`app/video_api.py`** — `SpecCreate` model gains `style` field; `create_spec` passes it through.
7. **`scripts/video.py`** — `--style` flag added to `plan`, `direct`, and `launch` subcommands with choices matching `HOUSE_STYLES`.

## Pre-Existing Render Status (not produced by this plan)

- `splan_fce96624ca97`: "Welcome to InDataFlow" — 6/6 chunks completed on Oct 4–5,
  assembled to `videos/batch-04-teaser/full.mp4`. **Pre-existing, style=noir.**
- `splan_5ce1d5a99910`: "One shipment, many borders" — 1 shot completed on Oct 5.
  **Pre-existing, style=noir.**
- 53 pending/queued jobs all tagged `style=noir` — pre-existing queue.

## Implementation Steps

### Step 1: Prepare briefs

Write five one-paragraph creative briefs (50–200 chars each) — one per project.
Each brief describes the concept in the project's voice and ends with the
spoken line **"This will change your operation."** (the closing grammar
constraint is enforced by the deterministic finishing layer, not the model).

Brief files go in `~/.kilo/tmp/video-briefs/`:

| File          | Style       | Concept summary                              |
|---------------|-------------|----------------------------------------------|
| `teaser.txt`  | noir        | Door in an industrial hall, light shaft, dust |
| `desk.txt`    | warm-real   | Problem visible at a desk, daylight resolves it |
| `pile.txt`    | human-real  | Overnight pile of work transformed calmly    |
| `ring.txt`    | flat-graphic| Interlocking rings show product functions     |
| `room.txt`    | calm-real   | A busy room settling into calm order          |

### Step 2: Launch each video (GPU budget: ~20 min/video, sequential)

```bash
# Video 1 — noir teaser
.venv/bin/python scripts/video.py launch \
  --brief-file ~/.kilo/tmp/video-briefs/teaser.txt \
  --project-id teaser-door \
  --style noir \
  --mode full

# Video 2 — warm-real desk
.venv/bin/python scripts/video.py launch \
  --brief-file ~/.kilo/tmp/video-briefs/desk.txt \
  --project-id desk-warm \
  --style warm-real \
  --mode full

# Video 3 — human-real pile
.venv/bin/python scripts/video.py launch \
  --brief-file ~/.kilo/tmp/video-briefs/pile.txt \
  --project-id pile-human \
  --style human-real \
  --mode full

# Video 4 — flat-graphic ring
.venv/bin/python scripts/video.py launch \
  --brief-file ~/.kilo/tmp/video-briefs/ring.txt \
  --project-id ring-graphic \
  --style flat-graphic \
  --mode full

# Video 5 — calm-real room
.venv/bin/python scripts/video.py launch \
  --brief-file ~/.kilo/tmp/video-briefs/room.txt \
  --project-id room-calm \
  --style calm-real \
  --mode full
```

### Step 3: Monitor and assemble each

After each launch completes (check `data/renders/` for chunk outputs,
or poll `GET /company/video/queue/stats`), assemble the chunks:

```bash
# Get the plan ID for each project
.venv/bin/python -c "
from core import video_store
import json
for spec in video_store.list_specs():
    if spec['projectId'] in ('teaser-door','desk-warm','pile-human','ring-graphic','room-calm'):
        plans = video_store.list_shot_plans(spec_id=spec['id'])
        for p in plans:
            print(f'{spec[\"projectId\"]}: plan={p[\"id\"]}')
"
```

Then assemble each (replace `<plan_id>`):

```bash
.venv/bin/python scripts/video.py assemble <plan_id>
```

The deterministic finishing layer appends the logo card and the spoken
closing line "This will change your operation." as the final frame.

### Step 4: Verify style enforcement

After rendering, verify each video's spec carries the correct style:

```bash
.venv/bin/python -c "
from core import video_store
for spec in video_store.list_specs():
    extra = spec.get('extra') or {}
    if extra.get('style'):
        print(f'{spec[\"projectId\"]}: style={extra[\"style\"]}')
"
```

Expected output:
```
teaser-door: style=noir
desk-warm: style=warm-real
pile-human: style=human-real
ring-graphic: style=flat-graphic
room-calm: style=calm-real
```

## Constraints Enforced

1. **Typography ban is style-independent** — the lettering gate (`_asks_for_lettering`
   in `pipeline.py`) scans every beat regardless of style. No beat in any video
   may describe visible words, signs, headlines, or UI.
2. **Same closing grammar** — all five end with "This will change your operation."
   + deterministic logo card.
3. **GPU budget unchanged** — ~20 min per video, sequential rendering only.

## Risks / Open Questions

- The `direct_brief` path requires `OMNIROUTE_API_KEY` to be set (the user confirmed
  the gateway is up). If the director is unavailable, `launch` raises `RuntimeError`.
- Video 4 (`flat-graphic`) is the only one that routes visual beats to
  `motion_graphics` renderer rather than `hunyuan` — this path is deterministic
  (not GPU-rendered) and is not dispatched in the current phase. The spec will
  still plan and queue, but motion_graphics jobs will remain pending.
