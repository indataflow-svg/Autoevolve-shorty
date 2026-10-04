We have now successfully validated the production GPU rendering side.

GPU WORKER STATUS

The MI300X worker is operational.

Known-good rendering environment:

AMD MI300X

ROCm 10

HunyuanVideo-1.5

81 frames

24 fps

3.38 seconds

848×480

H.264 MP4

FFmpeg decoded all 81 frames successfully

No corruption/errors

The Hunyuan installation is already validated and MUST NOT be modified, upgraded, reinstalled, or redownloaded.

The worker API is running through FastAPI/systemd.

Worker Tailscale address:

100.126.189.74

Worker API:

http://100.126.189.74:8000

Endpoints currently available:

GET /health
GET /capacity
POST /render

The /render endpoint successfully invokes Hunyuan and produces an MP4.

The worker uses the existing proven Hunyuan Python environment through:

HUNYUAN_PYTHON=/root/video-lab/.venv/bin/python

Do not replace this with the CUDA worker environment.

YOUR TASK

Inspect the ENTIRE AutoEvolve repository first.

Do not immediately modify code.

Determine:

Current architecture

Existing script generation pipeline

Existing VideoSpec / ShotPlan implementation

Existing RenderJob implementation

Existing queue implementation

Existing renderer abstraction

Existing FFmpeg/video composition code

Existing QA/validation

Existing API/server

Existing environment/configuration system

Existing frontend/dashboard if present

Existing deployment configuration

Existing tests

Existing product/demo generation workflow

Then report exactly where the MI300X worker should integrate.

Do not duplicate functionality that already exists.

REQUIRED ARCHITECTURE

The intended pipeline is:

Script
↓
VideoSpec
↓
ShotPlan
↓
RenderJob[]
↓
Render Queue
↓
Renderer selection
↓
MI300X Hunyuan worker for cinematic shots
↓
Other renderers for other shot types
↓
FFmpeg composition
↓
QA
↓
Final MP4

AutoEvolve remains the CONTROL PLANE.

The GPU machine is a PRIVATE RENDER WORKER.

Do not move business logic or LLM/script logic onto the GPU machine.

IMPORTANT WORKER DESIGN

For the initial integration, AutoEvolve should be able to communicate with:

http://100.126.189.74:8000

through Tailscale only.

However, do not hard-code this IP throughout the codebase.

Create configuration such as:

RENDER_WORKER_URL=http://100.126.189.74:8000

or the repository's existing configuration equivalent.

Document that this is a Tailscale-only private address.

The renderer must be configurable so the worker IP can later be changed without code modifications.

FIRST: VERIFY EXISTING AUTOEVOLVE CAPABILITIES

Before implementing anything, search the repository for:

RenderJob

ShotPlan

VideoSpec

renderer

render queue

ffmpeg

Hunyuan

video generation

worker

job status

retry

heartbeat

completed

failed

QA

composition

output_path

Determine whether these already exist.

Reuse existing abstractions wherever possible.

RENDERER ABSTRACTION

If AutoEvolve already has a renderer abstraction, add Hunyuan as a renderer.

If it does not, create a minimal renderer interface.

Conceptually:

Renderer
├── HunyuanRenderer
├── RemotionRenderer
├── FFmpegRenderer
└── future renderers

HunyuanRenderer should NOT implement Hunyuan itself.

It should submit a RenderJob to the private GPU worker.

RENDER JOB CONTRACT

Create or adapt the existing RenderJob model so it can represent:

job_id

shot_id

renderer

prompt

negative_prompt

resolution

aspect_ratio

frames

fps

steps

seed

dtype

output_name

status

worker_id

output_path

error

timestamps

Do not add unnecessary fields if equivalent fields already exist.

The existing AutoEvolve data model takes precedence.

INITIAL WORKER FLOW

For now:

AutoEvolve
↓
POST /render
↓
MI300X
↓
Hunyuan
↓
MP4
↓
AutoEvolve receives result
↓
QA

The existing worker API can remain synchronous for this initial integration.

Do NOT prematurely rewrite the GPU worker.

After the integration is proven, we will replace this with the production queue model:

GET /render-jobs/next
POST /render-jobs/{id}/heartbeat
POST /render-jobs/{id}/complete
POST /render-jobs/{id}/failed

That queue work comes AFTER the current integration works.

HEALTH / CAPACITY

AutoEvolve should be able to check:

GET /health

and:

GET /capacity

before submitting a render.

Do not make the system depend on continuous health polling.

Health checking should be lightweight and failure-tolerant.

FAILURE HANDLING

Implement proper handling for:

worker unreachable

Tailscale unavailable

HTTP timeout

HTTP 500

render timeout

malformed worker response

missing output file

invalid MP4

QA failure

Do not silently mark a failed render as completed.

Preserve useful error information.

Use the existing AutoEvolve retry architecture if one exists.

Do not invent a second retry system.

SECURITY

The GPU worker is PRIVATE.

It must NOT become publicly exposed.

AutoEvolve should connect through Tailscale.

Do not add authentication credentials to source code.

Use environment variables/configuration for the worker endpoint.

Do not expose the worker through a public reverse proxy.


