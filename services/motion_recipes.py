"""Reusable motion recipe library (template-4 phase 6).

Architectural inspiration from the documented motion-design/Higgsfield
workflow; no proprietary implementation is copied. The AI director selects
an existing recipe whenever one matches instead of reinventing the visual
language per project; deterministic keyword scoring picks the recipe when
no model is configured.
"""
from __future__ import annotations

from typing import Any

RECIPES: dict[str, dict[str, Any]] = {
    "footage-plus-graphics": {
        "purpose": "Authentic footage carries the story; graphics explain it.",
        "best_for": ("logistics corridors", "route changes", "operational explainers"),
        "composition": "full-bleed footage with lower-third graphics and map overlays",
        "pacing": "6-10 second shots matched to narration beats",
        "beats": ("establish place", "show movement", "overlay explanation", "resolve"),
        "camera": {"preferred": ("slow push", "tracking", "aerial"), "prohibited": ("whip pan", "shaky cam")},
        "lens": "natural perspective, shallow depth of field",
        "lighting": "soft directional daylight, neutral-cool",
        "motion": "one clear camera move per shot; graphics fade, never bounce",
        "transitions": "cuts; map routes draw on across the cut",
        "asset_requirements": ("stock freight footage", "route data for overlays"),
        "hunyuan_prompt_strategy": "cinematic environment and camera movement only; no text, maps, or UI in the frame",
        "finishing_strategy": "route lines, captions and CTA composited deterministically in FFmpeg/G2",
        "cues": ("corridor", "route", "freight", "cargo", "truck", "shipment", "map", "footage"),
    },
    "product-reveal": {
        "purpose": "Introduce a product record as the answer to a visible problem.",
        "best_for": ("product launches", "control-layer stories", "record-vs-chaos narratives"),
        "composition": "problem footage first; product capture enters after the problem is visible",
        "pacing": "problem beats run long; reveal lands on a single beat",
        "beats": ("problem", "consequence", "reveal", "proof", "cta"),
        "camera": {"preferred": ("slow push", "settle"), "prohibited": ("orbit", "crane")},
        "lens": "clean perspective, product captures pixel-exact",
        "lighting": "neutral, UI captures ungraded",
        "motion": "restrained; let the record timeline carry the motion",
        "transitions": "cuts",
        "asset_requirements": ("approved product captures", "problem footage"),
        "hunyuan_prompt_strategy": "problem-side atmosphere only; never generate product UI",
        "finishing_strategy": "product record timeline and CTA assembled deterministically",
        "cues": ("product", "dashboard", "record", "reveal", "launch", "ui", "upload"),
    },
    "kinetic-typography": {
        "purpose": "Short uppercase statements carry the film; footage is texture.",
        "best_for": ("manifestos", "awareness beats", "CTA-driven shorts"),
        "composition": "centered condensed type over darkened footage",
        "pacing": "one statement per 2-4 seconds",
        "beats": ("statement", "statement", "resolve into CTA"),
        "camera": {"preferred": ("static", "slow push"), "prohibited": ("tracking", "orbit")},
        "lens": "any; footage sits behind type",
        "lighting": "footage graded dark for legibility",
        "motion": "type fades/slides; camera nearly still",
        "transitions": "hard cuts on the beat",
        "asset_requirements": ("statement list", "texture footage"),
        "hunyuan_prompt_strategy": "abstract texture and atmosphere only; never render text",
        "finishing_strategy": "all type rendered deterministically for spelling control",
        "cues": ("manifesto", "statement", "headline", "typography", "caption", "cta"),
    },
    "glass-ui-launch": {
        "purpose": "Premium translucent product moments for launch films.",
        "best_for": ("product launches", "feature announcements"),
        "composition": "product capture floating over soft gradient environments",
        "pacing": "slow reveals, generous holds",
        "beats": ("tease", "reveal", "tour", "cta"),
        "camera": {"preferred": ("macro push", "parallax"), "prohibited": ("shaky cam", "whip pan")},
        "lens": "macro detail with soft falloff",
        "lighting": "clean studio-like key with brand-color rim",
        "motion": "slow dimensional drift",
        "transitions": "dissolves for time passage, cuts otherwise",
        "asset_requirements": ("approved product captures", "gradient environments"),
        "hunyuan_prompt_strategy": "environment backgrounds only; product comes from approved captures",
        "finishing_strategy": "product compositing and type done deterministically",
        "cues": ("launch", "premium", "glass", "feature", "sleek"),
    },
    "blueprint-to-building": {
        "purpose": "Diagrams become real: from plan to operational reality.",
        "best_for": ("infrastructure stories", "before/after narratives"),
        "composition": "schematic overlays resolving into photography",
        "pacing": "build-up then payoff hold",
        "beats": ("plan", "construction", "reality", "operation"),
        "camera": {"preferred": ("reveal", "crane"), "prohibited": ("macro",)},
        "lens": "wide establishing to medium detail",
        "lighting": "cool schematic tones warming into daylight",
        "motion": "drawing-on animations, then real movement",
        "transitions": "match cuts from line to reality",
        "asset_requirements": ("schematic artwork", "real facility footage"),
        "hunyuan_prompt_strategy": "facility and construction atmosphere; diagrams stay deterministic",
        "finishing_strategy": "diagram animation rendered as motion graphics",
        "cues": ("blueprint", "plan", "infrastructure", "construction", "before", "after"),
    },
    "exploded-product": {
        "purpose": "Show what a product/record is made of, layer by layer.",
        "best_for": ("record anatomy", "document workflows", "layered systems"),
        "composition": "centered subject with separating labeled layers",
        "pacing": "one layer per beat",
        "beats": ("whole", "explode", "tour layers", "reassemble"),
        "camera": {"preferred": ("orbit", "pull_out"), "prohibited": ("shaky cam",)},
        "lens": "controlled perspective, even focus across layers",
        "lighting": "even studio lighting",
        "motion": "slow separation and reassembly",
        "transitions": "continuous move, no cuts mid-explode",
        "asset_requirements": ("layer artwork or captures", "label copy"),
        "hunyuan_prompt_strategy": "physical exploded views only; labels stay deterministic",
        "finishing_strategy": "labels and callouts rendered as graphics",
        "cues": ("anatomy", "layers", "documents", "workflow", "exploded", " stack"),
    },
    "flat-vector-explainer": {
        "purpose": "Clear diagrammatic explanation with a consistent illustration system.",
        "best_for": ("process explainers", "data relationships", "timelines"),
        "composition": "flat vector scenes with one focal diagram",
        "pacing": "narration-paced builds",
        "beats": ("setup", "build", "build", "resolve"),
        "camera": {"preferred": ("static",), "prohibited": ("tracking", "orbit", "crane")},
        "lens": "orthographic feel; no lens effects",
        "lighting": "flat brand palette, no photometric lighting",
        "motion": "build-on animation, no camera motion",
        "transitions": "cuts",
        "asset_requirements": ("vector illustration system", "diagram copy"),
        "hunyuan_prompt_strategy": "not a Hunyuan recipe; use motion graphics end to end",
        "finishing_strategy": "fully deterministic vector/motion render",
        "cues": ("explainer", "diagram", "timeline", "process", "vector", "data"),
    },
    "hyper-motion": {
        "purpose": "High-energy sizzle for launches and events.",
        "best_for": ("event trailers", "launch sizzle", "recaps"),
        "composition": "rapid montage with graphic punches",
        "pacing": "1-3 second shots",
        "beats": ("punch", "punch", "punch", "title"),
        "camera": {"preferred": ("whip pan", "crash zoom"), "prohibited": ("static",)},
        "lens": "exaggerated perspective welcome",
        "lighting": "high contrast, saturated brand colors",
        "motion": "fast ramps with hard settles",
        "transitions": "cuts, flashes, graphic wipes",
        "asset_requirements": ("shot library", "title cards"),
        "hunyuan_prompt_strategy": "short energetic moments; keep each prompt to one action",
        "finishing_strategy": "speed ramps and punches timed in the edit",
        "cues": ("sizzle", "trailer", "event", "energy", "montage", "recap"),
    },
    "hybrid-2d-3d": {
        "purpose": "Dimensional product moments inside graphic storytelling.",
        "best_for": ("feature stories", "mixed product/graphic films"),
        "composition": "3D product moments bookended by 2D graphic passages",
        "pacing": "graphics move fast; 3D moments breathe",
        "beats": ("graphic setup", "dimensional moment", "graphic proof", "cta"),
        "camera": {"preferred": ("parallax", "push_in"), "prohibited": ("shaky cam",)},
        "lens": "dimensional shots use soft depth of field",
        "lighting": "graphics flat; 3D moments lit softly",
        "motion": "contrast graphic speed with dimensional calm",
        "transitions": "graphic wipes into 3D, cuts out",
        "asset_requirements": (" approved captures or 3D renders", "graphic system"),
        "hunyuan_prompt_strategy": "dimensional environments; product identity from approved assets",
        "finishing_strategy": "graphic passages deterministic; 3D via Hunyuan or approved renders",
        "cues": ("hybrid", "dimensional", "feature", "mixed", "3d"),
    },
    "editorial-collage": {
        "purpose": "Documentary texture from layered archival and graphic material.",
        "best_for": ("customer stories", "evidence-led narratives", "reports"),
        "composition": "layered frames, archival footage, source documents",
        "pacing": "measured, let sources breathe",
        "beats": ("context", "evidence", "evidence", "meaning"),
        "camera": {"preferred": ("static", "slow push"), "prohibited": ("orbit", "crane")},
        "lens": "documentary naturalism",
        "lighting": "available-light look",
        "motion": "subtle parallax on stills; sources never generated",
        "transitions": "cuts and soft dissolves",
        "asset_requirements": ("archival footage", "source documents with rights"),
        "hunyuan_prompt_strategy": "bridging atmosphere only; never fabricate sources or people",
        "finishing_strategy": "source captions and citations rendered deterministically",
        "cues": ("story", "customer", "evidence", "documentary", "archival", "report"),
    },
}


def list_recipes() -> list[str]:
    return sorted(RECIPES)


def select_recipe(text: str) -> tuple[str, dict[str, Any]]:
    """Deterministically score recipes by cue overlap; ties break by name."""
    haystack = str(text or "").lower()
    scored = [
        (sum(1 for cue in recipe["cues"] if cue in haystack), name)
        for name, recipe in RECIPES.items()
    ]
    best = max(scored)
    if best[0] == 0:
        return "footage-plus-graphics", RECIPES["footage-plus-graphics"]
    return best[1], RECIPES[best[1]]


def select_recipe_ai(brief: str, *, candidates: list[str] | None = None) -> dict[str, Any]:
    """Let the director pick (and justify) a recipe; falls back deterministically."""
    from services.creative_director import CreativeDirector, DirectorUnavailable

    options = candidates or list_recipes()
    try:
        director = CreativeDirector(
            "creative_direction",
            instructions=(
                "You are a creative director choosing a motion recipe. Pick exactly one "
                f"recipe from: {', '.join(options)}. Never invent a new recipe name."
            ),
        )
        from pydantic import BaseModel, Field

        class RecipeChoice(BaseModel):
            recipe: str = Field(min_length=1)
            reason: str = Field(min_length=3, max_length=240)

        choice = director.run(f"Brief: {brief[:1500]}", RecipeChoice)
        if choice.recipe in RECIPES:
            return {"source": "ai", "recipe": choice.recipe, "reason": choice.reason}
    except DirectorUnavailable:
        pass
    except Exception:
        # Any model failure falls back to deterministic selection.
        pass
    name, _ = select_recipe(brief)
    return {"source": "deterministic", "recipe": name, "reason": "cue overlap fallback"}
