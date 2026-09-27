# G3 Publishing Engine

G3 validates G2 handoffs, uploads media to S3-compatible storage such as Cloudflare R2, and creates
drafts or explicitly scheduled posts in Buffer. Scheduling is a separate command and requires the
founder action token at the FastAPI boundary. G3 does not claim that a scheduled post was published.

```bash
cp engines/g3/config/g3.env.example engines/g3/config/g3.env
engines/g3/.venv/bin/company-core-g3 doctor --require instagram --require x
```

Keep `g3.env` private. Configure your bucket, endpoint, public media URL, Buffer token, and channel
IDs before enabling publishing actions.

The `schedule` command supports `--mode queue`, `next`, or `timed` (with `--due-at`). The read-only
`insights POST_ID` command fetches Buffer's current post state and any available metrics. Buffer
currently limits post metrics to personal API keys and describes them as experimental; values can
be absent or delayed. The Content page displays them only for a Buffer post ID saved by a confirmed
schedule response. Neither a successful schedule nor a metrics read implies publication unless the
provider reports the post as sent.
