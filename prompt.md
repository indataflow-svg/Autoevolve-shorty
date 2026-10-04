# Implement AutoEvolve VideoSpec → ShotPlan → RenderJob Pipeline

We need to add the first production-ready video generation pipeline to AutoEvolve.

The goal is NOT to build a complete video editor yet.

The goal is to take an already-prepared marketing script and deterministically convert it into renderable jobs that our separate MI300X HunyuanVideo worker can consume.

The pipeline is:

```text
Existing Script
      ↓
VideoSpec
      ↓
ShotPlan
      ↓
RenderJob[]
      ↓
Queue
      ↓
External GPU Worker
      ↓
MP4 + metadata
```

Use the existing AutoEvolve architecture and conventions. Do not rewrite unrelated systems.

---

## 1. SOURCE OF TRUTH

The input is an existing prepared script.

A script may contain:

- title
- target buyer
- duration
- narrative
- timed transcript
- business lesson
- product connection
- source references
- CTA
- transcript-to-visual association map

Example source structure:

```text
0:00–0:06
THE NEW CORRIDOR
NEEDS A RECORD,
NOT JUST A ROAD.

0:06–0:14
Across Eurasia,
trade routes are being reshaped...

...

Transcript-to-visual association:

Beat
What should be visible
Preferred visual type
Stock search / fallback
Portrait composition
Motion
Connection
```

The uploaded InDataFlow script collection is an example of the expected structure.

Do NOT require the LLM to invent missing business claims.

Do NOT change factual claims from the source script.

Do NOT turn InDataFlow into something it does not claim to be.

---

# 2. CREATE VideoSpec

Create a normalized `VideoSpec` object.

Suggested shape:

```typescript
type VideoSpec = {
  id: string;
  projectId: string;
  campaignId?: string;

  title: string;

  brand: {
    name: string;
    visualStyle?: string;
    colors?: string[];
  };

  format: {
    aspectRatio: "4:5" | "9:16" | "16:9" | "1:1";
    width: number;
    height: number;
    durationSeconds: number;
    fps: number;
  };

  audience?: {
    buyer?: string;
    segment?: string;
  };

  narrative?: string;

  transcript: TranscriptBeat[];

  visualRules: {
    preferredStyle?: string;
    footagePriority?: string;
    generatedGraphicsAllowed: boolean;
    fakeDashboardsAllowed: boolean;
    fakeDocumentsAllowed: boolean;
    watermarkAllowed: boolean;
  };

  brandConstraints?: {
    colors?: string[];
    typography?: string;
    logoRequired?: boolean;
  };

  productBoundary?: string;

  cta?: string;

  sources?: {
    title: string;
    url: string;
  }[];

  sourceScriptId?: string;

  status:
    | "draft"
    | "planned"
    | "queued"
    | "rendering"
    | "completed"
    | "failed";
};
```

Transcript:

```typescript
type TranscriptBeat = {
  id: string;
  startSeconds: number;
  endSeconds: number;
  text: string;
};
```

The parser must preserve the original transcript wording.

---

# 3. CREATE ShotPlan

Convert the VideoSpec into a shot-by-shot production plan.

```typescript
type ShotPlan = {
  id: string;
  videoSpecId: string;

  shots: Shot[];

  totalDurationSeconds: number;

  status:
    | "draft"
    | "approved"
    | "queued"
    | "rendering"
    | "completed";
};
```

Each shot:

```typescript
type Shot = {
  id: string;

  index: number;

  startSeconds: number;
  endSeconds: number;
  durationSeconds: number;

  transcriptBeatIds: string[];

  purpose: string;

  visualType:
    | "hunyuan"
    | "stock"
    | "product_capture"
    | "motion_graphics"
    | "source_capture"
    | "brand_end_frame"
    | "mixed";

  visualPrompt?: string;

  negativePrompt?: string;

  camera?: {
    shotType?: string;
    movement?: string;
    lens?: string;
    framing?: string;
  };

  environment?: string;

  subject?: string;

  lighting?: string;

  composition?: string;

  motion?: string;

  continuity?: {
    character?: string;
    location?: string;
    wardrobe?: string;
    props?: string[];
    style?: string;
  };

  assets?: {
    type: string;
    path?: string;
    url?: string;
    required: boolean;
  }[];

  textOverlay?: {
    text: string;
    position?: string;
    animation?: string;
  };

  productConnection?: string;

  renderRequired: boolean;

  renderProfile?: {
    resolution: "480p" | "720p";
    fps: number;
    frames: number;
    steps: number;
    dtype: "bf16" | "fp16";
    seed?: number;
  };
};
```

---

# 4. IMPORTANT: DO NOT SEND EVERYTHING TO HUNYUAN

The planner must decide the cheapest/most appropriate production method per shot.

Use:

```text
HUNYUAN
```

for:

- cinematic environments
- realistic people
- realistic vehicles
- realistic port/logistics scenes
- camera movement
- atmospheric shots
- product-context scenes

Use:

```text
MOTION_GRAPHICS
```

for:

- text
- simple diagrams
- timelines
- route lines
- data relationships
- captions
- transitions
- logos
- CTA cards

Use:

```text
PRODUCT_CAPTURE
```

for:

- actual InDataFlow UI
- approved screenshots
- product recordings

Use:

```text
STOCK
```

for:

- authentic logistics footage
- ships
- trucks
- ports
- documents
- people
- operational environments

Use:

```text
SOURCE_CAPTURE
```

when the script explicitly requires showing an authoritative source.

Do not fabricate government interfaces, official documents, statistics, dashboards or regulatory systems.

---

# 5. AI PLANNING

The planning layer should use the existing AI abstraction in AutoEvolve.

If OmniRoute is already available, use it rather than hardcoding one model/provider.

Separate AI tasks:

```text
SCRIPT → VIDEOSPEC
        ↓
SHOT PLANNER
        ↓
VISUAL PROMPT GENERATOR
        ↓
CONTINUITY CHECK
```

The model should reason about:

- narrative pacing
- visual variety
- shot duration
- visual continuity
- camera language
- product relevance
- authenticity
- brand consistency

The model should NOT be responsible for deterministic operations such as:

- creating folders
- writing queue records
- moving files
- encoding video
- calculating frame counts
- uploading assets
- checking whether files exist

Those should be normal application code.

---

# 6. RENDER JOB

Create a queueable `RenderJob`.

```typescript
type RenderJob = {
  id: string;

  videoSpecId: string;
  shotPlanId: string;
  shotId: string;

  priority: number;

  renderer:
    | "hunyuan"
    | "motion_graphics"
    | "ffmpeg"
    | "asset";

  model?: string;

  prompt?: string;
  negativePrompt?: string;

  inputAssets?: string[];

  outputPath: string;

  resolution?: "480p" | "720p";

  width?: number;
  height?: number;

  fps?: number;
  frames?: number;
  steps?: number;

  dtype?: "bf16" | "fp16";

  seed?: number;

  continuityContext?: {
    previousShot?: string;
    nextShot?: string;
    characters?: string[];
    environment?: string;
    style?: string;
  };

  status:
    | "pending"
    | "leased"
    | "running"
    | "completed"
    | "failed"
    | "cancelled";

  attempts: number;

  maxAttempts: number;

  workerId?: string;

  createdAt: string;
  startedAt?: string;
  completedAt?: string;

  result?: {
    outputPath?: string;
    durationSeconds?: number;
    frames?: number;
    fileSizeBytes?: number;
    metadata?: Record<string, unknown>;
  };

  error?: {
    code?: string;
    message: string;
    retryable: boolean;
  };
};
```

---

# 7. QUEUE

Implement the smallest reliable queue compatible with the existing AutoEvolve infrastructure.

Required operations:

```text
enqueue(job)
leaseNextJob(worker)
heartbeat(job)
complete(job)
fail(job)
retry(job)
cancel(job)
```

A worker must be able to ask:

```http
GET /render-jobs/next
```

or use the existing queue abstraction if one already exists.

Do NOT build another queue system if AutoEvolve already has one.

The important thing is that the GPU worker can:

1. authenticate
2. request a job
3. receive the complete RenderJob payload
4. render it
5. upload/register the result
6. mark the job complete
7. continue to the next job

---

# 8. GPU WORKER CONTRACT

The AutoEvolve application must NOT run Hunyuan directly.

AutoEvolve is the control plane.

The MI300X machine is the rendering worker.

Architecture:

```text
AutoEvolve
    │
    │ RenderJob
    ▼
Render Queue
    │
    ▼
MI300X Worker
    │
    ├── HunyuanVideo
    ├── Motion Renderer
    ├── FFmpeg
    └── QA
    │
    ▼
Rendered Asset
    │
    ▼
AutoEvolve
```

For now the Hunyuan worker only needs to support:

```text
renderer = "hunyuan"
```

with:

```text
prompt
negativePrompt
resolution
fps
frames
steps
dtype
seed
outputPath
```

---

# 9. HUNYUAN DEFAULT PROFILE

Create a default render profile based on the currently working MI300X environment:

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

Do not hardcode the actual filesystem path of the GPU VM into AutoEvolve.

The worker owns its local model path.

Example worker configuration:

```env
HUNYUAN_MODEL_PATH=/models/HunyuanVideo-1.5
AUToeVOLVE_QUEUE_URL=...
WORKER_ID=mi300x-01
```

---

# 10. RENDER JOB PAYLOAD

The worker should receive enough information to render without querying the LLM again.

Example:

```json
{
  "id": "render_001",

  "renderer": "hunyuan",

  "model": "HunyuanVideo-1.5",

  "resolution": "480p",

  "fps": 24,

  "frames": 121,

  "steps": 20,

  "dtype": "bf16",

  "seed": 42,

  "prompt": "Cinematic realistic cargo truck traveling through a long-distance logistics corridor at sunrise, authentic freight environment, premium commercial cinematography, restrained blue and indigo visual language, realistic materials, natural motion, shallow depth of field, smooth camera movement...",

  "negativePrompt": "blurry, low quality, distorted, deformed, malformed hands, extra fingers, duplicated objects, flickering, unstable geometry, temporal inconsistency, camera jitter, text artifacts, watermark, logo artifacts, cartoon, anime",

  "outputPath": "videos/project_123/shots/shot_001.mp4"
}
```

---

# 11. EXAMPLE: USE THE PROVIDED INDATAFLOW SCRIPT

For the script:

```text
THE NEW CORRIDOR
NEEDS A RECORD,
NOT JUST A ROAD.
```

and its subsequent 0:06–0:50 beats, the planner should create approximately:

```text
SHOT 01
0:00–0:06
HUNYUAN / STOCK
Long-distance freight movement.
Slow cinematic push.
Route line begins.

SHOT 02
0:06–0:14
STOCK + MOTION GRAPHICS
Cargo movement + changing corridor.
Map route redraw.

SHOT 03
0:14–0:22
SOURCE_CAPTURE + STOCK
IRU source reference alongside authentic freight footage.

SHOT 04
0:22–0:31
HUNYUAN / MOTION GRAPHICS
Shipment identity remains fixed while route changes.

SHOT 05
0:31–0:41
PRODUCT_CAPTURE / MOTION_GRAPHICS
Shipment record connected to border events, documents,
updates and human actions.

SHOT 06
0:41–0:50
MOTION_GRAPHICS / BRAND_END_FRAME
Complete shipment trail resolves into InDataFlow CTA.
```

This follows the source script's existing visual association map rather than inventing a new narrative.

---

# 12. VALIDATION

Before a VideoSpec can become a ShotPlan:

- transcript timestamps must be continuous
- no negative durations
- total duration must be valid
- every beat must have a visual treatment
- every shot must have a valid renderer
- Hunyuan shots must have a prompt
- generated shots must have a negative prompt
- product claims must remain inside product boundary
- source claims must retain their source references
- no fake official interfaces
- no fake numbers
- no fake product functionality

Before a ShotPlan becomes RenderJobs:

- every render-required shot produces exactly one RenderJob
- frames must correspond to duration × FPS
- output path must be unique
- seed must be deterministic unless explicitly randomized
- all required assets must exist or be marked externally required

---

# 13. DO NOT BUILD YET

Do NOT implement:

- full video editor
- browser video timeline
- advanced reference-video reconstruction
- automatic stock marketplace purchasing
- automatic social publishing
- voice generation
- music generation
- complex multi-GPU scheduling
- autonomous campaign strategy

Those come later.

The first milestone is:

```text
script
  ↓
VideoSpec
  ↓
ShotPlan
  ↓
RenderJob[]
  ↓
queue
  ↓
MI300X worker
```

---

# 14. TEST

Create one integration test using the provided InDataFlow script.

Expected result:

```text
1 VideoSpec
1 ShotPlan
~6 Shots
Hunyuan RenderJobs for cinematic/generated shots
Asset jobs for stock/product/source shots
```

The test should verify:

```text
script timing preserved
shot timing preserved
visual types assigned
render profiles generated
Hunyuan prompts generated
RenderJobs serialized correctly
queue accepts jobs
worker can lease a Hunyuan job
```

Do not mock the entire architecture unnecessarily.

Use real application services wherever they already exist.

---

# 15. DEFINITION OF DONE

The implementation is complete when I can run something conceptually equivalent to:

```bash
autoevolve video plan \
  --script scripts/indataflow/corridor.md
```

and receive:

```text
VideoSpec
ShotPlan
RenderJob manifest
```

Then:

```bash
autoevolve video queue <shot-plan-id>
```

and see:

```text
6 jobs queued
3 Hunyuan jobs
2 asset/motion jobs
1 brand-end-frame job
```

The MI300X worker can then consume the Hunyuan jobs without needing to understand the original script.

Keep the implementation modular so that later we can add:

```text
REFERENCE VIDEO
      ↓
VIDEO RECONSTRUCTION ANALYZER
      ↓
REFERENCE BLUEPRINT
      ↓
VideoSpec
      ↓
ShotPlan
      ↓
RenderJob
```

without changing the queue or Hunyuan worker contract.

Implement this directly in the existing AutoEvolve codebase.
First inspect the existing architecture and reuse its models, database, queue, AI abstraction, configuration, logging and API conventions wherever possible.
Do not create parallel infrastructure when an existing equivalent already exists.
