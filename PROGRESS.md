# AutoEvolve — progress of current task plan

_Written: Thu Oct 08 2026, after the interrupted style-thread branch_

## Goal
Finish the governed video-render pipeline. The user gave the directive:
commit everything first, then 1→5→3, then real rendering, then assets usage,
then restoration.

## Done (committed)
| commit | what |
|---|---|
| `471bc80` | Compose deterministic renderers: footage trim/crop/zoom, Pillow caption template |
| `4fec645` | Chunks carry their own story slice; pack routing verdict stored |
| `90ab932` | Pack pipeline: md_pack, ingest, QA gate, compose registration |
| `860bccd` | Unlock workflow preparation at 80% company data, optional company name, workflows-first API names |
| `d6364d4` | Revert "Document renderer upgrade procedure…" (my misread; reverted) |

## In-flight (uncommitted — style-thread branch A)
Last user instruction was garbled ("gateway up now first delete stale…"), then
"play it safe… let's replan now and… actually now first open pipeline file".

Edits on disk right now:
- `services/video/defs.py` — added `DEFAULT_HOUSE_STYLE`, `HOUSE_STYLES`
  dict (five styles), `GRAPHIC_MOTION_DIRECTION`; removed nothing else.
- `services/video/job_builder.py` — `_full_video_chunks` now resolves style
  from `spec.extra["style"]` with `GRAPHIC_STYLE`/DEFAULT fallback.
- `services/video/pipeline.py` — `direct_brief(..., style=DEFAULT_HOUSE_STYLE)`
  parameter added; storyteller instructions now carry the style block.
- `scripts/launch_briefs.py` (likely modified — verify before committing)

Gateway for OmniRoute is currently DOWN (http=000): `auto/best-fast`
returns Connection error; `auto/best-reasoning` returns 200. `launch`
commands therefore fail at the director stage. This is a hard block on
all AI-directed replanning; nothing new can be planned until it recovers.

Validate nothing is salvageable:
```
python -m pytest tests/test_video_pipeline.py tests/test_creative_director.py -q
python -m ruff check services/video
```
If those pass, diff + commit as one carefully-scoped style-threading commit.
If style regressions break the prompt-distinctness test, revert this branch
with `git restore services/video/defs.py services/video/job_builder.py
services/video/pipeline.py scripts/launch_briefs.py`.

## Remaining work (per user's 1→5→3 order)
1. ✅ Commit everything first (done: the phase commits above; **still open**
   is exactly the style-thread branch listed above).
2. Phase 5 wart: `qa_gate.run_qa_gate(passed=...)` counts SKIPPED as FAIL —
   an audio-skipped all-PASS run reports `passed: False`. Fix next.
3. Envelope record correction: 360f render proven by orphan file
   `job_6c3b95d291fc` — `FUNCTIONALITY.md` §5.5 is now wrong; fix docs.
4. Phase 2b residue: `Preferred visual type` precedence is implemented but
   `scripts/launch_briefs.py` still lacks an explicit `--style` flag — wire
   it through `launch()`/`direct_brief()`.
5. Phase 3 core: compose renderers beyond footage/graphics are still absent
   (founder overlay composite, stock adapter, word_sequence/field_highlight/
   end_frame templates, multi-card caption sequencing).
6. Phase 4: quality bar enforcement (≤1 frame cut error, 2-line captions,
   shared LUT/curve, −14 LUFS audio, encode-once-at-end) — none built yet.
7. Mode B (restore + re-storyboard): deferred per user.
8. A2: the over-broad `08cddec` commit rewrite still needs an explicit user
   go-ahead before any `reset`.

## Hot context for next session
- Working directory: `/home/ubuntu/Autoevolve-shorty`
- Remote worker: `RENDER_WORKER_URL=http://100.126.189.74:8000` (confirmed healthy earlier); worker ignores 1080p request — always delivers ~480×848.
- Orphan render to remember is exactly `videos/…/full.mp4` from
  `job_6c3b95d291fc` (357 frames; QA-clean; job row is `cancelled`).
- Stale pack fixture: `tests/fixtures/corridor-pack.md` (6 beats, 49s, 1 GPU beat).
- 104 tests total in video suite; last good baseline: 137 passed before the
  style branch edits.
