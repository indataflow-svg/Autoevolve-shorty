# Owned footage pool (`assets/owned/`)

Drop real product-usage and face videos here (`.mp4`, `.mov`, `.webm`, `.m4v`).
`search-media` prefers consented pool clips over stock; anything untagged or
unconsented is skipped automatically.

```bash
# 1. register new files (skeleton entries: kind=broll, consent=False)
company-core-g2 pool-ingest

# 2. AI-tag topics/claims/goals from filename + description + transcript
#    (needs CODING_API_KEY; pass --campaign to ground claims against G1 IDs)
company-core-g2 pool-tag --campaign <campaign.json>

# 3. inspect what the pool would serve for a scene
company-core-g2 pool-match <campaign.json> --scene 2
company-core-g2 pool-search "dispatch demo"
```

Then edit `pool.json`: set the right `kind` (`product_demo` | `face` |
`testimonial` | `broll`), add a one-line `description`, paste a `transcript`
when you have one, and flip `consent: true` only for footage cleared for
marketing use. `pool-ingest` never overwrites your edits; it only adds new
files and prunes vanished ones.

Matching connects each storyboard scene's purpose + claim IDs + narration +
campaign goal to clip topics/claims/goals, so a product-demo moment lands on
the slide whose claim it proves and face clips carry trust beats. Stock
remains the automatic fallback wherever the pool has no match.
