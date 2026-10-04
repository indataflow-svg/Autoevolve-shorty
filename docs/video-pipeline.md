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
.venv/bin/python scripts/video.py direct --brief "A 15-second product film." --project-id demo
.venv/bin/python scripts/video.py queue <shot-plan-id>
.venv/bin/python scripts/video.py profile   # default Hunyuan render profile
```

Two entry points feed the same validators: `plan` (prepared script,
transcript wording preserved verbatim) and `direct` (human brief via the
AI director — needs `OMNIROUTE_API_KEY`; beats carry `ai-brief`
provenance). Both persist the spec, its Visual Bible + motion recipe, its
asset registry, and the shot plan, then build RenderJobs. Details:
`docs/creative-director/`.

The dashboard Video page (`/video`) offers the same choice graphically: a
render-type dropdown (per-shot clips vs full video), a shot-plan picker,
and the queued jobs with status, attempts, outputs and errors. It calls
`POST /company/video/plans/{id}/queue?render_mode=…` with the founder
action token, then polls `GET /company/video/jobs?shot_plan_id=…`.
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

### Phase 1: synchronous MI300X submit (control-plane push)

The validated worker (`http://100.126.189.74:8000`, Tailscale-only) exposes
`GET /health`, `GET /capacity` and synchronous `POST /render`. AutoEvolve
submits one queued hunyuan job at a time:

```bash
make video-worker-status                  # health + capacity, starts no render
make video-submit JOB=<job-id>            # claim -> submit -> QA -> complete/fail
```

Implementation is `services/renderers.py`:

- `Renderer` interface (`check_health`, `check_capacity`, `submit_render`,
  `get_render_status`, `download_render`) with `HunyuanRenderer` posting the
  RenderJob payload (`prompt` required, plus `negative_prompt`,
  `resolution`, explicit `aspect_ratio` derived from the job's width/height,
  `frames`, `fps`, `steps`, `seed`, `dtype`, `output_name`). It never
  implements Hunyuan; the worker owns its validated environment
  (`HUNYUAN_PYTHON=/root/video-lab/.venv/bin/python`).
- Authentication: `RENDER_WORKER_API_TOKEN` is sent as
  `Authorization: Bearer` on every protected request (`/render`, status,
  download — never `/health`, never in errors or logs). Missing/invalid
  credentials surface as terminal `unauthorized`. UFW on the worker allows
  port 8000 only from AutoEvolve's Tailscale IP (`100.113.134.27`).
- Two worker shapes are supported: synchronous bytes/download-URL answers
  are saved directly; a queued/running answer (`job_id` + pending status)
  is polled via `GET /render/{job_id}` (`RENDER_WORKER_POLL_INTERVAL_SECONDS`,
  overall deadline `RENDER_WORKER_TIMEOUT_SECONDS`) and then streamed via
  `GET /render/{job_id}/download` in 64 KiB chunks with Content-Length
  truncation detection and optional worker-checksum comparison — the MP4 is
  never fully loaded into RAM. Job ids are allow-listed client-side, so a
  malicious id cannot turn the download into a path traversal.
- `submit_hunyuan_job` claims the job (one attempt, long lease so the pull
  queue cannot reclaim it mid-render), checks health/capacity, POSTs once,
  saves the MP4 under `data/renders/<job-id>.mp4`, runs ffprobe QA, then
  records `completed` (output path, frames, sha256, worker job id, render
  completion time) or `failed`.
- Failure handling reuses the existing layers, no second retry system:
  connection errors retry the idempotent GETs (bounded, 3 attempts);
  a POST that may have reached the worker is **never re-sent** — the job
  returns to `pending` (`retryable=true`) for an explicit resubmit, while
  `422`/contract mismatches are `retryable=false`. QA failures (missing
  file, ffprobe decode failure, frame/fps mismatch) fail the job with the
  reason preserved in `error_json`; nothing is ever silently completed.
- One credential, in one place: `RENDER_WORKER_API_TOKEN` lives only in
  `.env` (never source, never logs, never committed); the endpoint comes
  only from `RENDER_WORKER_URL`, and nothing render-related is exposed
  through the public UI or compose ports.

### Worker response contract (observed live)

`POST /render` accepts the RenderJob payload (`prompt` required; everything
else defaulted) and answers, on success, with a completion record — **not**
the video bytes:

```json
{"status": "completed", "worker_id": "mi300x-01", "job_id": "...",
 "output_path": "/root/video-lab/outputs/shot_001.mp4", "size_bytes": 782773}
```

`output_path` is worker-local: there is currently no download endpoint
(`GET /outputs/{name}`) and no SSH from the control plane, so a completed
render whose bytes cannot be fetched is recorded as terminal
`output_unavailable` (never silently completed, never blindly re-rendered)
with the worker path + size preserved for manual recovery. For the
production flow the worker needs one of: return the MP4 bytes directly,
serve them for download, or accept an upload target. Until then, recover
the file manually and mark the job complete with its QA metadata
(`qa_render_output` in `services/renderers.py` validates any local MP4).

### Phase 2: worker pull (already built, not yet wired to this worker)

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
