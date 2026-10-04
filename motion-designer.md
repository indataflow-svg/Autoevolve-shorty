# Motion Designer — product-launch pipeline

Turn a human brief (or a prepared script) into a finished product-launch video through the MI300X Hunyuan worker. One command, every stage gated.

## Command

```bash
.venv/bin/python scripts/video.py launch --brief "…" --project-id launch-01 --reference ~/product-tour.mp4
.venv/bin/python scripts/video.py launch --script scripts/indataflow/corridor.md --project-id corridor --no-submit
```

## Pipeline (each stage must pass before the next starts)

1. **Brief/Script in.** `--brief` (needs `OMNIROUTE_API_KEY`) or `--script` (deterministic; transcript preserved verbatim). Empty input is rejected.
2. **Direct.** Creative direction → motion-recipe selection → Visual Bible → storyboard → VideoSpec → ShotPlan → RenderJobs. Beats from a brief carry `ai-brief` provenance.
3. **References in.** `--reference <path>` (repeatable): real product footage or screenshots. Registered with identity priority 10 and preservation rules (`product_shape`, `product_color`, `typography`); resolved to shots by whole-word match. Generated imagery is illustration, never evidence; product UI is never generated.
4. **Queue.** One job per clip (`shots` mode). Re-queueing returns existing rows, never duplicates.
5. **Submit (hunyuan jobs only, skipped without `--no-submit`).** Claim (one attempt) → health/capacity → single POST → poll → stream to `data/renders/<job>/generation_<n>/` → ffprobe QA → `completed`/`failed`. Other renderers are recorded pending — no silent completion, no blind re-POST, attempts bounded by `maxAttempts`.
6. **Gates.** Schema, generation, video (ffprobe per artifact), visual, brand, assembly. Anything unrunnable abstains (SKIPPED); any FAIL stops the launch.
7. **Report.** Job IDs, per-job outcomes, artifact paths, SHA-256 list, gate table.

## Hard rules

- Never invent business claims; never show unreleased UI, fake dashboards, or fabricated statistics.
- Worker contract: `prompt` required; explicit `aspect_ratio` (worker defaults to 16:9); T2V unless product/source identity or a reference asset forces I2V.
- Worker is Tailscale-only (`RENDER_WORKER_URL`); Bearer token from `RENDER_WORKER_API_TOKEN`, never in code, logs, or errors; UFW allows only this host.
- Validated worker envelope is ~81 frames — longer shots render at the worker's discretion and may be rejected.
- Deterministic finishing (text, logos, CTA, data) stays out of generated frames.

## Reference layout

Product footage and screenshots live outside the repo (gitignored runtime state) and are passed per launch with `--reference`. The G2 pool (`engines/g2/assets/references/`) holds style/composition stills only — never production photography, never a substitute for real product capture.
