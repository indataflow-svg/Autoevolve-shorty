# Visual Bible (`services/visual_bible.py`, table `video_visual_bibles`)

One bible per spec, selected alongside the motion recipe and inherited by
every generated shot. This is what stops each AI shot from looking like a
different film.

Sections (all required, see `validate_bible`): `brand` (colors, typography,
logo/identity rules), `cinematography` (camera/lens/framing language, depth
of field), `lighting` (key, fill, contrast, color temperature),
`environment` (architecture, materials, atmosphere), `motion` (intensity,
rhythm, acceleration, easing), `editing` (transition language, pacing, shot
duration), `visual_identity` (realism, stylization, texture, grain).

`inherit_for_shot` renders the bible as prompt context (style, lighting,
environment, motion strings) consumed by the Hunyuan prompt compiler, so
the bible flows: spec → shot record → compiled prompt → worker payload.
Shots also carry the full lighting record and a continuity chain
(previous/next/style), checked by `continuity_review`.
