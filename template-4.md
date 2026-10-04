# AUTОEVOLVE — UNIVERSAL AI MOTION-DESIGN DIRECTOR
## Higgsfield-like Creative Orchestration for HunyuanVideo-1.5

You are implementing a major production capability inside **AutoEvolve**.

Do NOT treat Claude as a required dependency.

AutoEvolve must expose a **model-agnostic AI creative director** through **OmniRoute**, allowing any suitable connected AI model to perform planning, creative direction, storyboard generation, prompt compilation, asset selection, review, and correction.

The heavy video rendering remains on the existing **AMD MI300X 192 GB GPU worker running HunyuanVideo-1.5**.

The goal is NOT to clone Higgsfield's proprietary implementation.

The goal is to reproduce the important observable behavior:

> human brief → creative direction → visual recipe → visual bible → storyboard → shot specifications → cinematography translation → asset/reference selection → Hunyuan prompt compilation → generation → inspection → correction → deterministic finishing → final production.

Build this as a real production system, not as a collection of prompt templates.

---

# PHASE 0 — INSPECT BEFORE CHANGING ANYTHING

Before installing, modifying, deleting, upgrading, or restructuring anything:

1. Inspect the current AutoEvolve repository.
2. Identify:
   - application architecture
   - existing AI/LLM integrations
   - OmniRoute integration
   - API structure
   - job/queue architecture
   - media pipeline
   - storage
   - configuration
   - existing video-generation code
   - existing FFmpeg usage
   - existing Remotion usage
   - existing image-generation capabilities
   - existing asset handling
   - existing QA/vision capabilities
   - tests
   - deployment configuration
3. Inspect the existing MI300X video worker.
4. Inspect:
   - `~/video-lab/HunyuanVideo-1.5`
   - `~/video-lab/models/HunyuanVideo-1.5`
   - current worker API
   - render endpoint
   - health endpoint
   - capacity endpoint
   - generation scripts
   - current output structure
   - current Python environment
5. Detect installed packages and binaries before installing anything.
6. Detect which capabilities already exist but are unused.
7. Produce an inventory:

```text
EXISTING AND USABLE
ALREADY INSTALLED BUT UNUSED
PARTIALLY IMPLEMENTED
MISSING
BROKEN
DUPLICATED
```

Do not reinstall working dependencies.

Do not upgrade packages merely because newer versions exist.

Do not alter the working MI300X baseline until it has been backed up and benchmarked.

---

# PHASE 1 — PRESERVE THE VERIFIED GPU BASELINE

The current HunyuanVideo-1.5 GPU environment is already operational.

Hardware:

- AMD MI300X
- approximately 191.7 GB VRAM
- gfx942
- ROCm 10
- HIP 7.15.x
- PyTorch ROCm 2.12.0 environment

Existing repository:

```text
~/video-lab/HunyunVideo-1.5
```

Existing model area:

```text
~/video-lab/models/HunyuanVideo-1.5
```

The current validated baseline is approximately:

```text
480p
81 frames
24 fps
20 steps
bf16
no offloading
seed 42
```

A valid H.264 MP4 has already been produced and decoded successfully with FFmpeg.

Treat this as the immutable baseline.

First create a reproducible benchmark record containing:

- command
- model/checkpoint versions
- Python version
- PyTorch version
- ROCm version
- GPU information
- generation time
- peak VRAM
- output dimensions
- frame count
- FPS
- codec
- file size
- FFmpeg decode validation
- seed
- prompt

Do not optimize anything until this baseline can be reproduced.

---

# PHASE 2 — AUDIT THE HUNYUAN INSTALLATION

Inspect the HunyuanVideo-1.5 installation against its official requirements.

Verify all currently required components.

Pay particular attention to the known model/checkpoint requirements, including:

```text
Glyph-SDXL-v2
google/byt5-small
Qwen/Qwen2.5-VL-7B-Instruct
```

and their expected locations/configuration.

Also verify the current `huggingface_hub` compatibility issue.

The environment previously contained an incompatible `huggingface_hub 2.1.1`.

Do not blindly upgrade dependencies.

Determine the exact compatible version required by HunyuanVideo-1.5 and pin it.

Use the repository's own requirements/configuration as the source of truth.

Then test:

1. T2V
2. I2V
3. prompt rewriting
4. model loading
5. checkpoint loading
6. output encoding
7. FFmpeg decoding

Do not move forward until the baseline Hunyuan pipeline is clean.

---

# PHASE 3 — BUILD THE MODEL-AGNOSTIC AI DIRECTOR

AutoEvolve must NOT hard-code Claude.

Create a provider-neutral AI interface.

Conceptually:

```text
AIProvider
├── OmniRouteProvider
├── future direct provider
└── future local provider
```

OmniRoute becomes the primary gateway.

The application should ask the AI layer for capabilities such as:

```text
creative_direction
storyboarding
prompt_compilation
asset_selection
visual_review
continuity_review
revision
```

The rest of AutoEvolve must not care whether the underlying model is:

- Claude
- GPT
- Gemini
- Qwen
- another OmniRoute-compatible model
- future local model

The AI model is interchangeable.

The production schema is not.

---

# PHASE 4 — CREATE THE CREATIVE-DIRECTOR SCHEMA

Create a structured `VideoSpec`.

It must contain at minimum:

```yaml
VideoSpec:
  title:
  objective:
  audience:
  message:
  duration:
  aspect_ratio:
  fps:
  platform:
  visual_style:
  emotional_direction:
  brand:
  product:
  constraints:
  audio:
  assets:
```

Then create:

```text
VideoSpec
    ↓
VisualBible
    ↓
StoryPlan
    ↓
ShotPlan
    ↓
RenderJob[]
```

Do NOT allow free-form AI output to directly trigger GPU rendering.

AI output must first pass schema validation.

---

# PHASE 5 — BUILD THE VISUAL BIBLE

Create a persistent project-level Visual Bible.

It must control consistency across every shot.

Include:

```yaml
VisualBible:

brand:
  colors:
  typography:
  logo_rules:
  identity_rules:

cinematography:
  camera_language:
  lens_language:
  framing:
  depth_of_field:

lighting:
  key:
  fill:
  contrast:
  color_temperature:

environment:
  architecture:
  materials:
  atmosphere:

motion:
  intensity:
  rhythm:
  acceleration:
  easing:

editing:
  transition_language:
  pacing:
  shot_duration:

visual_identity:
  realism:
  stylization:
  texture:
  grain:
```

Every generated shot must inherit the Visual Bible.

This is critical for preventing every AI-generated shot from looking like a different film.

---

# PHASE 6 — BUILD THE MOTION-RECIPE LIBRARY

Use the publicly documented Claude Motion Design / Higgsfield workflow as architectural inspiration.

Do not copy proprietary implementation.

Create a reusable AutoEvolve motion recipe library.

Initial recipes should include:

```text
glass-ui-launch
product-reveal
kinetic-typography
blueprint-to-building
exploded-product
flat-vector-explainer
hyper-motion
hybrid-2d-3d
editorial-collage
footage-plus-graphics
```

Each recipe must describe:

```yaml
name:
purpose:
best_for:

composition:
pacing:
beats:

camera:
  preferred:
  prohibited:

lens:
lighting:
motion:
transitions:

asset_requirements:

hunyuan_prompt_strategy:

finishing_strategy:
```

The AI director should select an existing recipe whenever one matches.

Do not reinvent the visual language for every project.

The AI can adapt:

- subject
- environment
- story
- branding
- timing
- camera
- motion
- transitions

while preserving the successful underlying visual grammar.

---

# PHASE 7 — BUILD THE CINEMATOGRAPHY LIBRARY

Create structured libraries for:

```text
cameras
lenses
shot types
camera movements
lighting
depth of field
composition
transitions
motion patterns
```

Examples:

```text
wide_establishing
medium
medium_close
closeup
macro
overhead
low_angle
high_angle
```

Camera movement:

```text
static
dolly_in
dolly_out
tracking
orbit
pan
tilt
crane
push_in
pull_out
macro_push
reveal
parallax
```

Lens profiles:

```text
24mm
35mm
50mm
85mm
100mm_macro
```

Do not pretend Hunyuan physically simulates every cinema lens perfectly.

Instead use lens terminology as a structured compositional and generation prior.

Every shot should have explicit:

```yaml
camera:
  shot_type:
  movement:
  direction:
  speed:

lens:
  focal_length:
  visual_effect:

framing:
  start:
  end:
```

---

# PHASE 8 — BUILD THE ASSET/REFERENCE SYSTEM

Create a project asset registry.

Example:

```text
assets/
├── brand/
├── products/
├── characters/
├── locations/
├── environments/
├── references/
├── storyboards/
├── generated/
└── final/
```

Create metadata for each asset:

```yaml
Asset:
  id:
  type:
  path:
  purpose:
  identity_priority:
  preserve:
  allowed_changes:
```

Examples of preservation rules:

```yaml
preserve:
  - logo
  - product_shape
  - product_color
  - typography
  - proportions
```

The creative director must be able to select assets by semantic purpose.

Do not repeatedly describe a known product in prose when a reference image exists.

Use the actual reference.

---

# PHASE 9 — BUILD THE STORYBOARD ENGINE

Create a structured storyboard.

Each shot must contain:

```yaml
Shot:

id:
start:
end:
duration:

purpose:

subject:
environment:

composition:

camera:
lens:
lighting:

motion:
subject_motion:
environment_motion:
camera_motion:

transition_in:
transition_out:

reference_assets:

hunyuan_mode:
t2v_or_i2v:

prompt:

negative_constraints:

finishing:
```

The storyboard is the authoritative production plan.

No shot is sent to Hunyuan until its specification is valid.

---

# PHASE 10 — BUILD THE HUNYUAN PROMPT COMPILER

Use HunyuanVideo-1.5's documented prompt structure.

Compile:

```text
Subject
+
Motion
+
Scene
+
Shot Type
+
Camera Movement
+
Lighting
+
Style
+
Atmosphere
```

into the final generation prompt.

The compiler should take:

```text
VisualBible
+
MotionRecipe
+
ShotPlan
+
AssetReferences
```

and generate a Hunyuan-specific prompt.

The AI model may assist with semantic rewriting, but the application owns the final schema.

Do not simply send the entire project description to Hunyuan.

Generate a focused shot prompt.

---

# PHASE 11 — SUPPORT BOTH T2V AND I2V

Use T2V when:

- the environment is unconstrained
- no exact identity is required
- concept exploration is appropriate

Use I2V when:

- product identity matters
- a specific composition is required
- a generated keyframe is available
- character/location consistency matters

Build an explicit decision policy.

Example:

```text
exact asset required → I2V
known product → I2V
brand identity → I2V
concept exploration → T2V
environment exploration → T2V
```

Do not force everything through T2V.

---

# PHASE 12 — BUILD THE SHOT RENDER SERVICE

Connect:

```text
AutoEvolve
    ↓
RenderJob
    ↓
queue/API
    ↓
MI300X worker
    ↓
HunyuanVideo-1.5
    ↓
MP4 + metadata
```

The existing worker endpoints such as:

```text
/health
/capacity
/render
```

should be preserved unless inspection proves a change is necessary.

Extend rather than duplicate.

Every render must produce metadata:

```json
{
  "job_id": "",
  "shot_id": "",
  "model": "",
  "prompt": "",
  "seed": 42,
  "width": 0,
  "height": 0,
  "frames": 0,
  "fps": 24,
  "steps": 20,
  "dtype": "bf16",
  "duration_seconds": 0,
  "generation_seconds": 0,
  "peak_vram": 0
}
```

---

# PHASE 13 — BUILD DETERMINISTIC FINISHING

AI video generation must NOT be responsible for everything.

Use deterministic tools for:

- logos
- typography
- UI
- graphs
- captions
- exact product claims
- numerical data
- branding
- transitions where deterministic rendering is superior
- final audio synchronization
- platform exports

Use the existing FFmpeg/Remotion capabilities where already present.

Do not regenerate video simply because text needs to change.

Architecture:

```text
AI-generated footage
        +
deterministic graphics
        +
audio
        +
editing
        ↓
final film
```

This is an essential part of achieving professional output.

---

# PHASE 14 — BUILD THE REVIEWER

Create an independent review stage.

The same AI that created the shot should not automatically approve it.

Review:

```text
creative compliance
visual quality
motion quality
prompt compliance
asset identity
brand consistency
continuity
composition
camera behavior
lighting
artifacts
text correctness
duration
technical encoding
```

Return:

```yaml
Review:

status: PASS | REVISE | REGENERATE

score:
issues:

critical:
major:
minor:

recommendation:

regeneration_changes:
```

If a deterministic finishing problem exists, do not regenerate the video.

If a generation problem exists, regenerate the shot.

---

# PHASE 15 — BUILD CONTINUITY REVIEW

For multi-shot videos compare adjacent shots.

Check:

```text
subject identity
product identity
environment
lighting
color language
camera language
motion language
story progression
visual style
```

The reviewer must detect:

> Shot 1 and Shot 2 technically work individually but do not look like they belong to the same film.

That is a failure.

---

# PHASE 16 — BUILD ITERATIVE CORRECTION

The pipeline should be:

```text
PLAN
 ↓
STORYBOARD
 ↓
GENERATE
 ↓
REVIEW
 ↓
CORRECT
 ↓
REGENERATE ONLY FAILED SHOTS
 ↓
REVIEW AGAIN
 ↓
ASSEMBLE
 ↓
FINAL QA
```

Never regenerate the entire project when only one shot failed.

Persist every generation.

Maintain:

```text
shot_01/
  generation_001/
  generation_002/
  generation_003/
  selected/

shot_02/
  generation_001/
  selected/
```

This gives AutoEvolve reproducibility and rollback.

---

# PHASE 17 — BUILD QUALITY GATES

Nothing reaches final output without passing all gates.

## AI gate

- valid structured output
- valid VideoSpec
- valid VisualBible
- valid Storyboard
- valid ShotPlan

## Generation gate

- model loaded
- generation completed
- expected frame count
- expected dimensions
- valid output

## Video gate

Run FFmpeg/ffprobe.

Verify:

- container
- codec
- dimensions
- frame count
- FPS
- duration
- decodability
- audio if present

## Visual gate

Review:

- artifacts
- subject integrity
- motion
- composition
- lighting
- continuity

## Brand gate

Verify:

- logo
- colors
- typography
- product identity
- required claims

## Final assembly gate

Verify:

- correct aspect ratio
- correct duration
- audio sync
- no corrupted frames
- no unintended black frames
- no missing assets

---

# PHASE 18 — TEST EVERYTHING

Testing is mandatory.

Create tests at every level.

## Unit tests

Test:

```text
VideoSpec validation
VisualBible validation
StoryPlan validation
ShotPlan validation
recipe loading
asset resolution
camera translation
lens translation
prompt compilation
metadata generation
```

## Integration tests

Test:

```text
AutoEvolve → OmniRoute
AutoEvolve → worker
worker → Hunyuan
Hunyuan → MP4
MP4 → FFmpeg
reviewer → correction
```

## End-to-end test

Run:

```text
brief
→ AI director
→ VisualBible
→ storyboard
→ 3 shots
→ Hunyuan
→ review
→ correction
→ final assembly
→ QA
```

Use a small inexpensive test first.

Do not immediately render a long campaign.

---

# PHASE 19 — PERFORMANCE BENCHMARKING

After correctness is established, benchmark:

### Baseline

```text
480p
81 frames
24fps
20 steps
bf16
no offloading
seed 42
```

Then separately test:

```text
720p
step distillation
CFG distillation
sparse attention
SageAttention
torch compile
cache
offloading
```

Do not enable optimizations simply because they exist.

Benchmark each individually.

Record:

```text
generation time
VRAM
quality
stability
memory behavior
```

Choose optimizations based on measured results.

Do not sacrifice output quality merely to reduce generation time.

---

# PHASE 20 — EXPOSE IT AS AN AUTOEVOLVE CAPABILITY

The user-facing interface should eventually support something conceptually like:

```text
/autoevolve video

Create a 15-second vertical product film.

Objective:
Show how logistics teams move from shipment chaos
to operational visibility.

Style:
premium cinematic product reveal.

Assets:
use the InDataFlow brand assets.

Requirements:
no narration
music + sound design
9:16
social-ready
```

The system should automatically perform:

```text
brief analysis
↓
recipe selection
↓
VisualBible
↓
asset selection
↓
storyboard
↓
shot planning
↓
Hunyuan prompt compilation
↓
rendering
↓
review
↓
correction
↓
assembly
↓
QA
```

The user should NOT need to manually write cinematography prompts.

---

# PHASE 21 — OMNIROUTE MODEL AGNOSTICISM

This is a hard requirement.

Do not write:

```text
if claude:
```

throughout the application.

Instead:

```text
CreativeDirector
PromptPlanner
StoryboardPlanner
VisualReviewer
ContinuityReviewer
```

call a generic AI interface.

OmniRoute chooses the actual model.

Allow different models to perform different roles if useful:

```text
Planner → strong reasoning model
Storyboard → multimodal/vision-capable model
Prompt compiler → fast model
Reviewer → independent vision-capable model
```

The application must remain model-independent.

If OmniRoute changes the underlying model, AutoEvolve should continue working.

---

# PHASE 22 — USE EXISTING CAPABILITIES BEFORE ADDING NEW ONES

Before installing anything, explicitly check whether AutoEvolve already contains or has access to:

```text
FFmpeg
Remotion
image generation
vision models
LLM routing
OmniRoute
queues
Redis
PostgreSQL
object storage
asset management
FastAPI
Python
Node
Docker
ComfyUI
Hunyuan
LoRA support
upscaling
audio generation
```

If already present:

```text
reuse
integrate
test
```

Do not create a duplicate implementation.

If installed but unused:

```text
document it
test it
integrate it where appropriate
```

Only install missing components after the inventory.

---

# PHASE 23 — DOCUMENT EVERYTHING

Create:

```text
docs/
  architecture/
  creative-director/
  motion-recipes/
  cinematography/
  assets/
  hunyuan/
  worker/
  testing/
  troubleshooting/
```

Document:

1. Architecture
2. Installation
3. Model requirements
4. GPU requirements
5. OmniRoute configuration
6. Motion recipes
7. Visual Bible
8. Storyboard schema
9. Hunyuan prompt compiler
10. Worker API
11. QA
12. Benchmark results
13. Known limitations
14. Recovery procedures

---

# PHASE 24 — FINAL VALIDATION

Before declaring completion:

Run the complete system from a clean project.

The test must prove:

```text
USER BRIEF
    ↓
OMNIROUTE
    ↓
CREATIVE DIRECTOR
    ↓
MOTION RECIPE
    ↓
VISUAL BIBLE
    ↓
ASSET REGISTRY
    ↓
STORYBOARD
    ↓
SHOT PLAN
    ↓
HUNYUAN PROMPT COMPILER
    ↓
MI300X HUNYUAN WORKER
    ↓
GENERATED SHOTS
    ↓
INDEPENDENT REVIEW
    ↓
CORRECTION
    ↓
FINAL ASSEMBLY
    ↓
FFMPEG/FFPROBE QA
    ↓
FINAL MP4
```

Produce a final test report containing:

```text
PASS/FAIL for every phase

Installed dependencies
Reused dependencies
Unused existing capabilities
New files
Modified files
GPU benchmark
Generation benchmark
Quality benchmark
Known limitations
Remaining work
```

---

# NON-NEGOTIABLE ENGINEERING RULES

1. Inspect before modifying.
2. Reuse before installing.
3. Do not break the existing MI300X Hunyuan baseline.
4. Do not make Claude a dependency.
5. OmniRoute must abstract model selection.
6. AI output must be schema validated.
7. Storyboard precedes generation.
8. Every shot has an explicit production specification.
9. Visual Bible persists across the entire film.
10. Asset references are first-class inputs.
11. Hunyuan is the renderer, not the director.
12. Deterministic graphics remain deterministic.
13. Failed shots are regenerated individually.
14. Every generation is reproducible.
15. Every stage has tests.
16. Every final video passes technical QA.
17. Do not enable performance optimizations without benchmarking.
18. Do not claim a feature works until it has been tested.
19. Do not hide installation failures.
20. Do not replace working components merely for architectural purity.

---

# DEFINITION OF DONE

The feature is complete only when AutoEvolve can accept a normal human creative brief and autonomously transform it into a professional multi-shot video production plan, use OmniRoute to obtain the necessary AI reasoning, select a visual production recipe, maintain a Visual Bible, select references/assets, create a structured storyboard, compile HunyuanVideo-1.5-compatible prompts, render shots on the MI300X, independently review them, regenerate failed shots, assemble deterministic graphics/audio/video, and produce a technically validated final MP4.

The system must behave like a **model-agnostic AI motion-design production director**, not like a prompt generator.

Do not stop after creating schemas or documentation.

Implement it.

Test it.

Fix failures.

Test again.

Only report completion after the complete end-to-end pipeline has actually executed successfully.
