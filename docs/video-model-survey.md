# Local video model survey — and why the model may be the wrong lever

Written 2026-10-04, after the MI300X worker proved a 129-frame ceiling and we
discovered the payload was sending out-of-distribution frame counts at full
sampling cost.

Hardware available: **AMD MI300X, 192 GB VRAM**. VRAM is not a constraint for
any model below.

---

## 0. The finding that matters most

**No diffusion video model can make the thing we actually asked for.**

The request was *"SVG and icon animation with dynamics."* Every model in this
survey — Hunyuan, Wan, LTX, CogVideoX, Mochi — is a raster diffusion model. It
emits pixels. It cannot emit vector geometry, cannot hold a crisp edge, and
cannot spell. Requesting an icon animation from one produces a soft, painterly
impression of an icon animation. That is why our first successful render "failed
only on typography," and it will fail on geometry too.

The repo already knows this:

```python
# services/motion_recipes.py
"flat-vector-explainer": {
    "hunyuan_prompt_strategy": "not a Hunyuan recipe; use motion graphics end to end",
    "finishing_strategy": "fully deterministic vector/motion render",
}
```

So there are two genuinely different products here, and the model choice only
matters for one of them:

| Product | Right tool | Status |
|---|---|---|
| **Flat graphic / icon animation** launch video | deterministic vector render — Lottie, SVG, FFmpeg | ~60% of plumbing already in `engines/g2` |
| **Cinematic footage-style** launch video | diffusion model on the MI300X | working, 120f chunks, ~3.3 min each |

Everything below is for the second row.

---

## 1. For the deterministic path (icon animation, typography-safe)

**This is the recommendation for the actual brief.** No model, no GPU, no
timeouts, and text is correct by construction.

| Option | What it is | Already here? |
|---|---|---|
| **Lottie** | JSON-authored vector animation, crisp at any size, tiny, scriptable | **Yes** — `engines/g2/g2_runtime/lordicon.py` downloads Lottie/SVG, and `media_intelligence.py` accepts `lottie` as a first-class media type |
| **SVG + FFmpeg** | hand-authored or generated vector, rasterized per frame | FFmpeg present; `cairosvg` **not** installed |
| **Pillow/FFmpeg compositing** | deterministic layers, motion, captions | **Yes** — `engines/g2/g2_runtime/mixed_video.py` does layer composition, `_concat`, caption burn-in |
| **Remotion** | React components as video frames; TS ecosystem, templates | Not present; would add a Node render step |
| **Manim** | programmatic vector animation, strong on data/diagram motion | Not present; Python, would fit the stack |

`lordicon.py` is the quiet find: animated icon sets already download and validate
as Lottie/SVG in this codebase. "SVG and icon animation with dynamics" is
literally Lottie's use case, and the integration already exists.

**Cost:** near zero, runs on CPU in seconds. Removes the 60-minute wall, the
frame-shortfall problem, and the typography problem permanently.

**Cost of the honest caveat:** you get what you design. No emergent imagery, no
photographic realism. For an explainer-style product video that is a feature.

---

## 2. Diffusion models — fit for cinematic footage

### The shortlist for an MI300X

| model | params | max clip | native audio | license | notes |
|---|---|---|---|---|---|
| **HunyuanVideo 1.5** *(current)* | 8.3B | ~8s (121–129f window) | no | Tencent Community / Apache 2.0 (sources disagree) | best motion physics; 480p step-distilled I2V ≈ 75s on a 4090 |
| **LTX-2.3** | 22B (14B video + 5B audio) | **20s** | **yes** | LTX-2 tiered (free under $10M ARR) | 4K@50fps, IC-LoRA pose/depth, vertical-native |
| **Wan 2.7** | MoE | ~10s | no | Apache 2.0 | 9-grid image input, first/last frame control, 5000-char prompts |
| **Wan 2.2 TI2V-5B** | 5B | ~10s | no | Apache 2.0 | 8–12GB VRAM, 64× VAE, 720p@24fps in ~9 min on a 4090 |
| CogVideoX-5B | 5B | short | no | CogVideoX License | strongest prompt adherence, lowest floor |
| Mochi 1 | — | short | no | Apache 2.0 | smoothest motion, open training code |

### Three that would genuinely improve us

**LTX-2.3 — the biggest lever, and it fixes a gap we have.**
It is the only one generating synchronized audio in a single pass, and it does
**20-second clips**. That would:
- cut a 30s video from **6 chunks to 2**
- give us sound, which we currently do not have at all — every render to date is
  a silent MP4, which is not a shippable launch asset

**Wan 2.7 — best licensing and best control.**
Apache 2.0 with no commercial strings attached, plus first/last-frame control
and multi-image conditioning. First/last-frame control is what would let chunked
renders join without a visible seam. Note Wan is also the one line reported to
render Chinese and English text in-frame — still not something to depend on, but
it narrows our typography gap.

**HunyuanVideo 1.5 — keep it, but configure it.**
It is already installed, it has the best motion quality of the three, and our
3× speedup came from flags we simply weren't sending. The remaining upside is
`resolution`: we requested 1080×1920 and got 480×848 every time. Getting real
1080p out is a worker configuration question, not a pipeline one.

### The gating question we have not answered

**ROCm support.** Every model above is CUDA-first. Wan's kernels, LTX's
attention implementations, and ComfyUI's node graphs assume NVIDIA. On an
MI300X the realistic options are:
- ROCm ports where they exist, with unknown feature gaps
- **DirectML** as a Vulkan/ROCm-adjacent path
- CPU offload for the attention-heavy parts (we already do this via `offloading`)

I could not verify current ROCm maturity for Wan 2.7 or LTX-2.3 from public
sources, and I am not going to guess. **This must be tested before committing**,
because it is the difference between "swap the model" and "port the model."

A cheap test: pull the 5B Wan TI2V-5B checkpoint (8–12GB) and run a single
480p/121-frame text-to-video on the worker. If it produces a file, ROCm works
and the models are swappable. If it does not, the whole survey is academic and
we stay on Hunyuan.

---

## 3. Recommendation

**Split the work, because the two products need opposite tools.**

1. **Build the deterministic Lottie/SVG renderer for the five launch videos.**
   They are flat graphic explainers with icon animation — exactly Lottie's use
   case, already integrated in `engines/g2`, free, instant, and typo-proof. This
   is what actually ships.
2. **Keep Hunyuan for cinematic footage**, now that the payload and chunking are
   fixed (120f chunks, 8 distilled steps, ~3.3 min each).
3. **Spend one hour testing ROCm with Wan TI2V-5B** before anyone proposes a
   model migration. If it works, LTX-2.3 is the one to chase, for the audio and
   the 20s clips. If it does not, this document is a footnote.
4. **Install `cairosvg`** regardless — it unblocks SVG rasterization in the
   deterministic path, which is the path we want.

### What I would not do

- **Not** switch models to get vector output. No model provides it.
- **Not** prompt harder for typography. Wan can render *some* text; none can do
  it reliably. The typography gate stays regardless of which model we run.
- **Not** raise the chunk size back toward 480f. The 129-frame window is a model
  property; chunking is the correct architecture, not a workaround.

---

## Sources

Vendor and community material, cross-checked where they conflicted. Where
licensing claims disagree (HunyuanVideo 1.5 is described as both Tencent
Community License and Apache 2.0), the conflict is flagged rather than
resolved — check the repo before any commercial use.
