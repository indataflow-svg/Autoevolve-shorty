"""Five product-launch briefs for InDataFlow, one per researched video type.

Structure per type comes from 2026 SaaS launch research:
problem-first hook beats product-first intros; Problem -> Solution -> CTA is the
dominant pattern; top-of-funnel teasers run 15-30s; scene pacing of 3-5s is the
most common cadence. The protagonist is the viewer discovering InDataFlow.

Every brief is written for a renderer that cannot draw letters: no logo, no UI,
no dashboard, no chart. The idea is carried by light, machinery, landscape and
the protagonist's attention. All text lands in the deterministic finishing layer,
never in a generated frame.
"""

# Every brief renders at 15s / 360 frames. The MI300X worker's proven ceiling is
# 240 frames (10s); 360 frames is 1.5x that, whereas 480 frames (20s) is 2x and
# 720 frames (30s) already failed after 31 minutes of GPU work.
RUNTIME_SECONDS = 15

BRIEFS: dict[str, dict[str, object]] = {
    "teaser": {
        "type": "teaser (pre-launch, curiosity)",
        "runtime": RUNTIME_SECONDS,
        "brief": (
            "A person stands alone in a vast, empty industrial hall before dawn, "
            "watching a single line of light travel across the floor and stop at "
            "a door they have never opened. They walk toward it. As their hand "
            "rises to push, the hall fills with quiet movement: machinery "
            "waking, panels sliding, warm light spreading where nothing was lit "
            "before. They step through and keep walking, and the light keeps "
            "pace ahead of them. InDataFlow is the thing that was already "
            "running while they were not looking. Curiosity, restraint, no "
            "explanation yet. Welcome to InDataFlow."
        ),
    },
    "problem-solution": {
        "type": "problem -> solution (top of funnel)",
        "runtime": RUNTIME_SECONDS,
        "brief": (
            "Open on the problem: one person at a cluttered desk in a cramped "
            "room, surrounded by stacked paper, unopened boxes, a cold cup and "
            "a clock, working alone and behind. Nothing in the room moves but "
            "them. Then the shift: the clutter lifts and settles into neat "
            "stacks, the harsh overhead light warms, the room opens into a wide "
            "clean space, and a second pair of hands joins theirs instead of "
            "replacing them. The work that was one person fighting is now two "
            "people building. InDataFlow removes the work you were doing by "
            "hand so you can do the work only you can do. Try InDataFlow free."
        ),
    },
    "founder-story": {
        "type": "founder-led 'why we built this'",
        "runtime": RUNTIME_SECONDS,
        "brief": (
            "A founder at their desk late at after hours, alone, not working on "
            "the product but on the same problem the product was built to "
            "solve: a growing pile of work that no one has time for. They stop, "
            "look at it, and something resolves behind their eyes. Time moves. "
            "The pile is gone; the founder is not exhausted; the same desk now "
            "holds one open thing instead of forty. Calm, honest, human, "
            "unpolished. We built InDataFlow because the hardest part of the "
            "job was never the work itself. It was having no one to hand it to."
        ),
    },
    "workflow-reveal": {
        "type": "product reveal (the loop as a place)",
        "runtime": RUNTIME_SECONDS,
        "brief": (
            "Reveal the product as a physical place rather than an interface: a "
            "vast circular machine hall where a single warm ember of intent sits "
            "at the centre. Around it, an orderly ring of stations. The ember "
            "passes to the first station, where a researcher opens wide volumes "
            "and lays out what was found. It passes to a forge, where plans take "
            "shape as glowing metal. To a construction bay, where the plan "
            "becomes something that stands. To a workshop bench, where a part is "
            "fitted and tested. Back to the centre, changed. The ring never "
            "stops. One idea, going all the way round, getting better each lap. "
            "That loop is InDataFlow. Goal, research, strategy, build, execute, "
            "measure, review, improve, repeat."
        ),
    },
    "social-clip": {
        "type": "vertical social clip (single insight, 15s)",
        "runtime": RUNTIME_SECONDS,
        "brief": (
            "One tight idea, told in three beats. A person walks into a room "
            "where a hundred tasks are happening at once: machines running, "
            "paper moving, tools in hands, lights switching. They stop in the "
            "doorway, overwhelmed, and almost turn away. Then the room exhales: "
            "everything slows, syncs, and falls into one calm rhythm that a "
            "single person can direct. They walk in and start working. The "
            "point of the film is that the chaos did not need to be worked "
            "through harder. It needed something that could carry it. This is "
            "InDataFlow."
        ),
    },
}

# Every type is a full-video (whole-video) job, per the product default.
RENDER_MODE = "full"
