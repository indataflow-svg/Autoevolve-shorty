# Video pipeline: script → VideoSpec → ShotPlan → RenderJob → queue → MI300X worker

The first production-ready video path in AutoEvolve. It turns an already
prepared marketing script into renderable jobs for the external HunyuanVideo
worker. AutoEvolve is the control plane; it never runs Hunyuan itself.

```text
Existing Script
      ↓
VideoSpec
      ↓
ShotPlan
      ↓
RenderJob[]
      ↓
Queue (video_render_jobs table)
      ↓
External GPU Worker (MI300X)
      ↓
MP4 + metadata
```

## Run it

```bash
make video-plan SCRIPT=scripts/indataflow/corridor.md
# prints: VideoSpec, ShotPlan, RenderJob manifest

make video-queue PLAN=<shot-plan-id>
# prints: N jobs queued, per-renderer counts

# Lower level equivalents:
.venv/bin/python scripts/video.py plan --script scripts/indataflow/corridor.md --manifest-out /tmp/manifest.json
.venv/bin/python scripts/video.py queue <shot-plan-id>
.venv/bin/python scripts/video.py profile   # default Hunyuan render profile
```

Planning is deterministic. When `OMNIROUTE_API_KEY` is set, the AI layer
refines shot purposes and visual prompts (and adds continuity notes); when it
is not set — or when the model call fails — the deterministic templates win.
Transcript wording is never rewritten: script → spec parsing is always
deterministic so factual claims survive verbatim.

## Script format

A prepared script is Markdown with timed beat headers (`0:00–0:06`, hyphen /
en dash / em dash, with or without `##`) and per-beat visual association
lines. See `scripts/indataflow/corridor.md`:

```markdown
# The New Corridor Needs a Record

Buyer: Operations Director at a Rwanda freight forwarder
CTA: See how InDataFlow fits your operation. Book a walkthrough.

## 0:00–0:06

THE NEW CORRIDOR
NEEDS A RECORD,
NOT JUST A ROAD.

Visual: Long-distance freight movement at sunrise
Type: cinematic freight scene
Search: cargo truck highway sunrise freight corridor
Motion: Slow cinematic push
Connection: Geography adds cost and time
```

`Visual:` / `Type:` / `Search:` / `Motion:` / `Connection:` / `Source:` lines
form the transcript-to-visual association map; every other line is spoken
text and is preserved word for word. `Buyer:` / `Narrative:` / `CTA:` /
`Product boundary:` lines before the first beat become spec metadata.

## Shot routing (cheapest appropriate method wins)

The planner never sends everything to Hunyuan:

| Cue in beat | Visual type | Queue renderer |
| --- | --- | --- |
| Cinematic env, camera movement, atmospheric shots | `hunyuan` | `hunyuan` |
| Text, diagrams, timelines, route lines, captions, logos | `motion_graphics` | `motion_graphics` |
| Real InDataFlow UI / approved screenshots | `product_capture` | `asset` |
| Authentic logistics footage (ships, trucks, ports, documents) | `stock` | `asset` |
| Explicit authoritative source (IRU, reports) | `source_capture` | `asset` |
| End card / CTA resolution | `brand_end_frame` | `ffmpeg` |
| Beats mixing families | `mixed` | heaviest family wins |

Brand/product guardrails come from the existing G1 knowledge files
(`engines/g1/knowledge/_drafts/indataflow/`): no fake dashboards, documents,
statistics or regulatory interfaces; product text stays inside the approved
claims; source shots retain their references. Validation rejects discontinuous
timestamps, non-positive durations, uncovered beats, missing Hunyuan prompts
and non-unique output paths before anything is persisted or queued.

## Queue and worker contract

There is no separate queue infrastructure: `video_render_jobs` in
`data/company.db` is the queue, with `pending → leased → running →
completed` (`failed` / `cancelled` terminal). Each lease counts as an attempt
(`maxAttempts` 3); expired leases are reclaimed by the next `leaseNextJob`.

The worker only needs the dashboard credentials plus its own identity:

```env
HUNYUAN_MODEL_PATH=/models/HunyuanVideo-1.5   # worker-local, never in AutoEvolve
AUTOEVOLVE_QUEUE_URL=http://127.0.0.1:8787
WORKER_ID=mi300x-01
```

Worker loop against the control plane (all routes under `/company/video`):

1. `GET /render-jobs/next?worker_id=mi300x-01&renderer=hunyuan` → full
   RenderJob payload (prompt, negativePrompt, resolution, fps, frames, steps,
   dtype, seed, outputPath, continuityContext). `job: null` means the queue
   for that renderer is empty.
2. Render locally with HunyuanVideo (default profile below).
3. `POST /render-jobs/{id}/heartbeat?worker_id=…` during long renders to
   extend the lease (`VIDEO_QUEUE_LEASE_SECONDS`, default 300).
4. `POST /render-jobs/{id}/complete?worker_id=…` with
   `{"result": {"outputPath": …, "durationSeconds": …, "frames": …,
   "fileSizeBytes": …, "metadata": {…}}}` — or `POST …/fail` with
   `{"code": …, "message": …, "retryable": true|false}` (retryable failures
   return to `pending` until attempts run out).
5. Back to step 1.

Founder-gated writes (require `X-Founder-Action-Token` like the
sales/marketing action routers): `POST /specs`, `POST /plans`,
`POST /plans/{id}/queue`, `POST /jobs/{id}/retry`, `POST /jobs/{id}/cancel`.
Reads and the worker protocol need dashboard auth only.

## Default Hunyuan profile (working MI300X environment)

```json
{
  "resolution": "480p",
  "fps": 24,
  "steps": 20,
  "dtype": "bf16",
  "seed": 42,
  "rewrite": false,
  "offloading": false,
  "sr": false,
  "cfg_distilled": false,
  "enable_step_distill": false
}
```

Also served at `GET /company/video/hunyuan/profile`. Seeds are
deterministic (`42 + shot index`) unless a job is explicitly re-seeded.

## Reference-video reconstruction (later)

The seam for the planned `REFERENCE VIDEO → BLUEPRINT → VideoSpec` front end
is `services/video_pipeline.py::build_spec` / `plan_shots`: a blueprint
adapter only needs to produce the parsed-script dict (`title`, `meta`,
`beats[]` with `startSeconds`/`endSeconds`/`text`/`visual`) and everything
downstream — validation, queueing, the worker contract — stays unchanged.

## Not built (on purpose)

Full video editor, browser timeline, reference-video reconstruction, stock
marketplace purchasing, social publishing, voice/music generation, multi-GPU
scheduling, autonomous campaign strategy.
