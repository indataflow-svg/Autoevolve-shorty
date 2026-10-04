# Upgrading and backups

Company Core stores operational state under `data/` and generated project
artifacts under `projects/`. Both are intentionally outside Git.

## Back up

Use the backup script. It snapshots every SQLite database with the SQLite
online backup API, so it is safe while the application is running, and it
records checksums, schema hashes and row counts in a manifest:

```bash
make backup
# or: ./scripts/backup.sh --out /path/to/backups
```

The archive lands in `backups/company-core-<timestamp>.tar.gz` with a `.sha256`
sidecar. Never copy a live database with `cp`: WAL frames live in `-wal`/`-shm`
side files and a plain copy of the main file can be torn.

Protect the backup because it can contain credentials, contacts, emails and
campaign media. Set `BACKUP_AGE_RECIPIENT` (age) or `BACKUP_GPG_RECIPIENT`
(gpg) to encrypt every archive on creation. Retain multiple tested restore
points.

Example cron entry (daily at 03:15):

```cron
15 3 * * * cd /srv/company-core && ./scripts/backup.sh --out /srv/backups >> /var/log/company-core-backup.log 2>&1
```

## Verify a backup

```bash
make verify-backup ARCHIVE=backups/company-core-<timestamp>.tar.gz
```

Verification extracts the archive to a temporary directory, recomputes every
checksum, re-reads the schema and compares row counts against the manifest.
Run it after each backup rotation; an archive that does not verify is not a
backup.

## Upgrade

```bash
git fetch --tags
git pull --ff-only
make setup
npm --prefix autoevolve-ui ci
npm --prefix autoevolve-ui run build
make check
```

Read `CHANGELOG.md` before restarting. `make setup` preserves the existing
`.env` and local config. Compare `.env.example` with `.env` manually to
discover newly added settings.

## Restore or roll back

1. Stop the application.
2. Check out the previous known-good tag or commit and reinstall its
   dependencies (`make setup`).
3. Check the archive first:

```bash
./scripts/restore.sh --verify --archive backups/company-core-<timestamp>.tar.gz
```

4. Restore it. The apply mode refuses to run while the target still looks like
   a live instance (`uvicorn app.api` running); use `--force` only after the
   services are actually stopped:

```bash
./scripts/restore.sh --apply --archive backups/company-core-<timestamp>.tar.gz
```

Do not run an older release against data that has undergone an incompatible
migration unless the release notes explicitly allow it.

After any restore, run `make doctor`, start the service, verify `/health`, and
inspect one saved lead and campaign before resuming outbound actions.

---

# Upgrading the video renderer

The renderer is a **separate machine**. AutoEvolve is the control plane; the
MI300X worker owns the model, its environment and its weights. Nothing in this
section applies to the AutoEvolve repository itself, and nothing in the
`git pull` sequence above touches the worker.

## Know the constraints before you change anything

These were measured on `mi300x-01` against HunyuanVideo-1.5 and are the
reasons the pipeline is shaped the way it is. Re-measure after any model or
environment change, and update this table.

| constraint | measured value | consequence |
|---|---|---|
| Native temporal window | **129 frames** (~5.4s @ 24fps) | never request more in one call; the pipeline chunks at 120 |
| Worker render wall | **exactly 3600s**, then HTTP 504 | a longer single job is refused, not slowed |
| Frame loss per render | **constant 3 frames** (141/144, 237/240, 117/120) | tolerated by QA; anything larger is a truncated render |
| Pre-optimisation rate | 12 frames/min | 240 frames took ~20 min |
| Post-optimisation rate | **37 frames/min** | 120 frames takes ~3m16s |
| Output resolution | returns **480×848** regardless of the 1080×1920 request | the request is not honoured; see below |

## Upgrade the model weights

`~/video-lab/HunyuanVideo-1.5` and `~/video-lab/models/HunyuanVideo-1.5`.

1. **Snapshot the current environment before touching it.** A model upgrade
   that fails halfway is worse than no upgrade.

   ```bash
   /root/video-lab/.venv/bin/python -m pip freeze > /root/video-lab/freeze-$(date -u +%Y%m%d).txt
   ```

2. **Pin the dependency versions the model requires.** The environment
   previously carried an incompatible `huggingface_hub 2.1.1`. Do **not**
   blindly upgrade — use the model's own `requirements.txt` as the source of
   truth and pin what it asks for.

3. **Verify the auxiliary checkpoints are present.** A missing
   `Glyph-SDXL-v2`, `google/byt5-small` or `Qwen/Qwen2.5-VL-7B-Instruct` fails
   late, after the denoise has already started, which burns the whole render
   budget.

4. **Prove each capability separately before trusting the whole:**
   model load, checkpoint load, T2V, I2V, prompt rewriting, output encoding,
   FFmpeg decoding.

5. **Render one 120-frame probe and QA it before touching the queue.**

   ```bash
   # AutoEvolve side
   .venv/bin/python scripts/video.py plan --script <script.md> --project-id probe
   .venv/bin/python scripts/video.py queue <plan-id> --mode full
   .venv/bin/python scripts/video.py submit <job-id> --timeout 1800
   ```

   Expect 117 frames delivered against 120 requested. A different number means
   the behaviour changed and the QA tolerance needs revisiting.

## Change render settings from AutoEvolve, not from the worker

Sampling effort, distillation and memory strategy live in
`services/video/defs.py::HUNYUAN_DEFAULT_PROFILE` and are sent on every
`POST /render`. Edit that profile; do not hard-code flags worker-side.

Two settings carry most of the speed:

```python
"enable_step_distill": True,   # collapses ~20 steps into a handful
"offloading": True,            # VRAM headroom; failures died mid-sampling without it
```

If a flag you add is rejected or silently ignored, remember the transport is a
**single synchronous `POST /render`**: one job at a time, and a request that
may have started GPU work is never retried automatically.

## Known defect to fix before trusting the output

`_full_video_chunks` in `services/video/job_builder.py` builds every chunk
prompt from the shots' `purpose` strings, so all chunks receive the same
storyboard summary and differ only by `Segment N of M`. The rich per-shot
`visualPrompt` — the actual scene description — is never sent.

Consequence: repeated near-identical segments and visible seams, rather than
progression through the story. Fix it by slicing the beat list per chunk and
using `visualPrompt`. Until then, judge renders as pipeline data, not as
finished assets.

## Assembly is deterministic, so it is safe to re-run

```bash
.venv/bin/python scripts/video.py assemble <plan-id> --out videos/<project>/full.mp4
```

Stream copy, no re-encode. It refuses to emit a file unless every chunk is
`completed`, present on disk, geometrically matched, and its ffprobe frame
count agrees with what the job row claims. That last check is deliberate: it
stops a stale job row from smuggling a truncated artifact into a finished
video.

Re-running assembly is harmless. Re-*rendering* costs GPU — a job returns to
`pending` and only re-renders when someone submits it.

## If you change models

Read [Video Model Survey](video-model-survey.md) first. Before migrating:

1. **Test ROCm.** Every leading open video model is CUDA-first. Pull a small
   one (Wan TI2V-5B, 8–12GB) and render a single 480p/121-frame clip on the
   worker. No file means no migration, and the survey becomes a footnote.
2. **Re-measure the temporal window.** The 129-frame figure is
   HunyuanVideo-1.5's. `MAX_FRAMES_PER_RENDER` in `services/video/job_builder.py`
   must be updated to the new model's window or chunks become out-of-distribution
   again — the exact failure this chunking was built to fix.
3. **Re-measure the frame loss.** Update `FRAME_SHORTFALL_BASE` in
   `services/renderers.py` from observation, not assumption.
4. **Budget for audio.** Every render so far is silent. Only LTX-2.3 among the
   surveyed models generates synchronized audio in one pass, so this gap closes
   only by changing models.
5. **Keep the deterministic path as the fallback.** Lottie and SVG rendering
   (`engines/g2/g2_runtime/lordicon.py`, `mixed_video.py`) does not depend on
   any diffusion model and has no timeout, no frame drift and no typography
   failure. It stays the correct tool for icon animation regardless of which
   model is installed.

## Rollback

Restore the environment snapshot from step 1, restore the previous weights
directory, then re-run the 120-frame probe. Because the pipeline is
deterministic per seed, a restored environment can be compared against the
stored `generation_NNN` artifacts for the same job id rather than judged from
memory.

