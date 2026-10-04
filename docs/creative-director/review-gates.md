# Review and quality gates (`services/review.py`, `services/quality_gates.py`)

The creator never approves its own work. `technical_review` is fully
deterministic (ffprobe decode, frame/fps/dimension expectations, codec
sanity) and returns PASS | REVISE | REGENERATE with scored issues and
`regeneration_changes` (e.g. next seed, same prompt). `ai_visual_review`
and the AI half of `continuity_review` run through the director's vision
roles and return SKIPPED — never PASS — without a configured model.

`run_gates` reports `ai_schema` (validators incl. bible), `generation`
(job record completeness), `video` (ffprobe per artifact), `visual`,
`brand` (prohibited-claim + source-reference checks) and `assembly`
(artifact coverage, duration reconciliation) as PASS/FAIL/SKIPPED.
`passed` is true only with no FAIL; anything that cannot run honestly
abstains. Deterministic finishing problems yield REVISE (fix without
re-rendering); generation problems yield REGENERATE of that shot only —
every attempt persists under `data/renders/<job>/generation_<n>/`.
