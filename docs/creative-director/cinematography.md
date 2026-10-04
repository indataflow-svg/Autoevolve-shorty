# Cinematography (`services/cinematography.py`) and the prompt compiler

Libraries: shot types (`wide_establishing` … `aerial`), movements
(`static` … `parallax`), lens profiles (`24mm`–`100mm_macro` with
plain-language effects), lighting setups, depths of field, compositions,
transitions, motion patterns. Lens terms are a generation prior, not a
physical claim about Hunyuan optics.

Every shot record carries `camera: {shot_type, movement, direction,
speed}`, `lens: {focal_length, visual_effect}`, `motion_detail:
{subject_motion, environment_motion, camera_motion}` and
`transition_in/out`; `validate_camera` rejects unknown vocabularies during
`validate_plan`.

The compiler (`compile_hunyuan_prompt`) assembles Subject + Motion + Scene
+ Shot Type + Camera Movement + Lighting + Style + Atmosphere from the
shot, its bible inheritance, and the recipe strategy — never the whole
project description. Deterministic finishing (text, logos, UI, data)
is excluded by construction and enforced by the negative prompt.
T2V/I2V (`decide_hunyuan_mode`): product/source identity or a matched
reference asset means `i2v`, otherwise `t2v`; persisted per job.
