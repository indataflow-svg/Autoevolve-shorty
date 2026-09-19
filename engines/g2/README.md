# G2 Media Engine

G2 consumes a validated G1 campaign and handles media search, acquisition, approved owned assets,
voice generation, subtitles, carousel rendering, and mixed-video rendering.

Install from the repository root with `make setup`. FFmpeg is required for video workflows.

```bash
engines/g2/.venv/bin/company-core-g2 --help
```

Configure stock-media and optional generation providers in the root `.env`. Replace files under
`assets/references/` with licensed brand assets before publishing.

Video discovery federates local approved media, Pexels, Pixabay, Coverr, and Wikimedia. Coverr uses
`COVERR_API_KEY`; G2 resolves its short-lived download URL only for the selected clip. Mixed-video
renders retain native movement for video and apply restrained deterministic push/pan motion to
still backgrounds. Editorial frames contain no persistent logo or review badge; visible branding
is limited to the configured product showcase and premade outro.

Owned footage pool: drop product-demo and face videos in `assets/owned/` (see
`assets/owned/README.md`). `search-media` checks the pool first via
`pool-ingest` / `pool-tag` / `pool-match`; consented, AI-tagged clips win
scenes whose claims and topics they match, stock stays as fallback.
