# Motion recipes (`services/motion_recipes.py`)

Ten reusable visual grammars (deterministic data, no proprietary code
copied): `footage-plus-graphics`, `product-reveal`, `kinetic-typography`,
`glass-ui-launch`, `blueprint-to-building`, `exploded-product`,
`flat-vector-explainer`, `hyper-motion`, `hybrid-2d-3d`,
`editorial-collage`. Each recipe declares purpose, best-for, composition,
pacing, beats, preferred/prohibited cameras, lens, lighting, motion,
transitions, asset requirements, a Hunyuan prompt strategy, and a
finishing strategy.

Selection: `select_recipe` scores cue overlap deterministically (ties break
by name; empty match falls back to `footage-plus-graphics`);
`select_recipe_ai` lets the director choose with fallback. The AI adapts
subject, environment, story, branding, timing, camera, motion and
transitions; the grammar stays fixed. Shots record the recipe's finishing
strategy in `finishing: {renderer, strategy}`.
