# AutoEvolve — progress of current task plan

_Written: Fri Oct 09 2026. Supersedes the Oct 08 draft — every item that draft
listed as in-flight has since been validated, committed, and reported._

## Goal

Finish the governed video-render pipeline. Directive order: commit everything
first, then 1→5→3, then real rendering, then asset usage and restoration.
Latest steer: polish **plan → video rendering** before any voice or captions,
and prove the pipeline on 5 simple scenarios in multiple styles.

## Done (committed)

| commit | what |
|---|---|
| `1670e7f` | Functionality report refreshed to current source + API reference regenerated |
| `1023af7` | QA gate: SKIPPED is absence of evidence, not failure (4 tests) |
| `57b7134` | Per-film house styles; illustration language routes off the GPU |
| `2ce09eb` | PROGRESS.md state log |
| `471bc80` | Compose deterministic renderers: footage trim/crop/zoom, Pillow caption template |
| `4fec645` | Chunks carry their own story slice; pack routing verdict stored |
| `90ab932` | Pack pipeline: md_pack, ingest, QA gate, compose registration |
| `860bccd` | Workflow preparation at 80% company data, optional company name, workflows-first API names |

**Status of the four items the previous draft flagged as in-flight:**

1. Style thread — **committed** as `57b7134`. `defs.HOUSE_STYLES` (5 styles),
   style travels `spec.extra.style` → plan → `_full_video_chunks`, `--style`
   on the CLI. Nothing reverted; the prompt-distinctness test passes.
2. QA gate SKIPPED wart — **fixed** in `1023af7`, locked by 4 new tests.
3. Envelope record — **corrected** in `docs/FUNCTIONALITY.md` §5.10: 360f
   completes (357 delivered), and long-form is proven by chunked assembly
   (`videos/batch-04-teaser/full.mp4`, 29.25s), not one monolithic render.
4. `--style` wiring — **done** for `plan`/`direct`/`launch`.

## Verification baseline (re-measured today)

- `make test`: **445 passed**, 3 known pre-existing failures unrelated to
  video (`test_operations_ui`, `test_sales_contracts::test_resend_send_marks_draft_sent`,
  `test_sales_workflow_views_api`). This is the accepted baseline.
- Ruff clean on `services/video/`, tests, scripts.
- OpenAPI: 149 operations / 17 prefixes; 28 tables; 448 tests across 41 files.
- Working tree: only the other process's files remain dirty (automation UI,
  service discovery, onboarding) — none of mine.

## Remaining work

1. **Five-scenario render run (the active task).** Five 30s scenarios drafted
   (door / desk / pile / ring / room), each 6 beats, style-tagged
   (noir, warm-real, human-real, flat-graphic, calm-real). Video 5 is
   uniformly calm — the mid-film chaos→calm pivot was dropped as agreed.
   Sequence: delete 24 stale `pending` chunk rows (batch-04 × 4, zero
   attempts) → re-plan all five with styles → show storyboards + prompts for
   sign-off → submit sequentially (~20 min/video, single sync worker) →
   assemble → QA → report paths, durations, frame counts.
   Gate: stop and diagnose if any chunk reaches attempt 3.
2. **Phase 3 residue:** capture-zoom, founder-overlay, stock-wrapper
   renderers; multi-card caption sequencing (currently 2 of 3 lines fit one
   card); `word_sequence` / `field_highlight` / `end_frame` templates.
3. **Phase 4 quality bar:** ≤1 frame cut error, 2-line captions, shared grade,
   −14 LUFS, encode once at the end. None built.
4. **Scale:** re-queue teaser at 360f, unblock the social clip (claims
   validator rejects "seamless"), finish batch-04.
5. **Deferred:** Mode B (restore + re-storyboard), A2 commit surgery (needs
   explicit go-ahead), `cairosvg`, ROCm probe.

## Hot context

- Directory `/home/ubuntu/Autoevolve-shorty`, branch `main`.
- Worker `RENDER_WORKER_URL=http://100.126.189.74:8000` (Tailscale).
  Envelope: 240f≈20min, 360f≈30min, 480f=wall at 60min. After
  step-distillation ~37 f/min. Delivers a constant 3 frames short
  (`FRAME_SHORTFALL_BASE=3` + 2%) and **ignores requested pixel dimensions**
  (~480×848, not 1080×1920) — canvas size is compose's job.
- OmniRoute gateway `http://100.113.134.27:20128/v1` is intermittently down.
  Deterministic paths (pack parse, ingest, compose, footage, QA) work without
  it; `direct`/`launch` do not. Check before promising a plan.
- Pack fixture `tests/fixtures/corridor-pack.md` — 6 beats, 49s, exactly 1
  GPU beat. This is the input format the UI uploads.
- Renders are gitignored (`videos/`, `data/renders/`). `PROGRESS.md`,
  `docs/FUNCTIONALITY.md`, `docs/API-REFERENCE.md` are tracked.
- Regenerate API docs: `.venv/bin/python scripts/gen_api_reference.py`.
