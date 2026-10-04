# AutoEvolve — Implement the First Automated Workflow Layer

## Mission

Upgrade the existing AutoEvolve-Shorty system with the **smallest clean workflow/orchestration layer** required to execute the first real automated marketing workflow.

The goal is NOT to redesign AutoEvolve.

The goal is:

> Allow AutoEvolve to define, persist, execute, observe, and track a multi-step business workflow using the existing G1, G2, G3, and Company Core capabilities.

The existing systems are the execution engines.

The new workflow layer is the coordinator.

---

# 1. NON-NEGOTIABLE RULES

Before modifying anything:

- Inspect the actual repository.
- Understand the existing architecture and conventions.
- Locate the existing:
  - G1 strategy/content intelligence
  - G2 media generation
  - G3 publishing/distribution
  - Company Core / sales / lead systems
  - campaign models and storage
  - dashboard/API conventions
  - database/storage conventions
  - authentication/authorization conventions
- Reuse existing interfaces wherever possible.
- Do NOT create duplicate versions of existing capabilities.
- Do NOT redesign G1, G2, G3, Company Core, the dashboard, or the video pipeline.
- Do NOT modify the coding-engine/worktree/agent system.
- Do NOT introduce a new agent framework.
- Do NOT introduce unnecessary dependencies.
- Do NOT create speculative abstractions.
- Keep the implementation small and production-oriented.

If an existing capability already performs a required operation, call it.

---

# 2. TARGET ARCHITECTURE

Add a lightweight workflow layer above the existing systems:

```text
                     WORKFLOW
                         │
        ┌────────────────┼────────────────┐
        │                │                │
     Objective         Trigger          Steps
                                          │
                         ┌────────────────┼───────────────┐
                         ↓                ↓               ↓
                        G1               G2              G3
                         │                │               │
                         └────────────────┼───────────────┘
                                          ↓
                                    Company Core
                                          ↓
                                      Results
                                          ↓
                                     Evaluator
```

The workflow layer should orchestrate existing capabilities.

---

# 3. MINIMAL WORKFLOW MODEL

Implement a workflow representation compatible with the project's existing data/storage patterns.

Conceptually:

```yaml
workflow:
  id:
  name:
  objective:

  trigger:
    type:
    config:

  steps:
    - id:
      action:
      config:

  success_metric:
    type:
    target:

  state:
    status:
    current_step:
    results:

  created_at:
  updated_at:
```

Do not blindly copy this structure if the repository has an established modeling convention.

Adapt it to the existing architecture.

---

# 4. WORKFLOW STATE

The workflow must have explicit state.

At minimum support:

```text
draft
ready
running
paused
completed
failed
```

Each execution step should produce a structured result conceptually equivalent to:

```json
{
  "status": "completed",
  "output": {},
  "metrics": {},
  "artifacts": [],
  "error": null,
  "next_step": "..."
}
```

Again, use the repository's existing response/model conventions where appropriate.

The workflow must be resumable from its current state.

Do not implement a distributed workflow engine.

A simple persisted state machine is sufficient.

---

# 5. WORKFLOW RUNNER

Implement a small workflow runner/orchestrator.

Conceptually:

```text
WorkflowRunner
    ↓
load workflow
    ↓
load current state
    ↓
execute current step
    ↓
persist result
    ↓
advance state
    ↓
execute next step
```

The runner must:

- validate the workflow before execution
- execute steps in order
- persist state after each step
- record outputs
- record failures
- stop safely on failure
- support resuming
- avoid duplicating completed work

Do not over-engineer retries, queues, distributed locks, scheduling, or agent planning unless the existing repository already has these capabilities.

---

# 6. STEP ACTIONS

Create only the minimum adapters required to invoke existing capabilities.

The first workflow should support actions conceptually equivalent to:

```text
g1_strategy
generate_assets
publish
collect_results
evaluate
```

Map these actions onto the REAL existing AutoEvolve APIs/services/functions.

Do not create fake implementations.

If one of these capabilities does not yet exist as a clean callable interface, create the smallest adapter around the existing implementation.

---

# 7. FIRST REAL WORKFLOW

Implement one complete workflow:

```text
Campaign Objective
        ↓
G1 generates marketing strategy / hypotheses
        ↓
Generate assets using existing G2 pipeline
        ↓
Publish using existing G3 pipeline
        ↓
Collect available results
        ↓
Evaluate results
```

The initial objective can be represented as:

```yaml
name: InDataFlow Launch Experiment

objective: Generate qualified demo conversations

steps:
  - g1_strategy
  - generate_assets
  - publish
  - collect_results
  - evaluate
```

Do not hard-code InDataFlow into the workflow engine.

Use it only as the initial example/test workflow.

---

# 8. HYPOTHESES

G1 should be able to produce multiple experiment hypotheses.

For the first workflow, target:

```text
Hypothesis A
Hypothesis B
Hypothesis C
```

Each should contain structured information such as:

```text
message
audience
angle
offer
creative_direction
success_metric
```

Use existing G1 output structures if they already exist.

The workflow engine should treat these as data and pass them downstream.

---

# 9. G2 INTEGRATION

Do not create a new renderer.

Use the existing G2/media-generation pipeline.

The workflow should pass the approved strategy/hypothesis/creative brief into the existing asset-generation capability.

The result should record references to the generated assets.

Conceptually:

```text
G1 hypothesis
      ↓
existing G2
      ↓
asset IDs / paths / metadata
```

---

# 10. G3 INTEGRATION

Do not create a new publishing system.

Use the existing G3 distribution/publishing layer.

The workflow should pass the generated assets to the existing publishing mechanism.

Record:

```text
campaign_id
workflow_id
workflow_step_id
asset_id
platform
post_id
publication status
```

Use existing attribution fields if they already exist.

Do not duplicate attribution systems.

---

# 11. RESULTS + EVALUATION

Use existing analytics/results infrastructure where available.

For the first implementation, evaluation can remain intentionally simple.

Support metrics such as:

```text
engagement
leads
qualified leads
meetings
conversion
```

The evaluator should return a structured result.

For example:

```json
{
  "winner": "hypothesis_b",
  "metrics": {},
  "reason": "...",
  "next_action": "create_variation"
}
```

Do not build a sophisticated optimization algorithm yet.

The purpose of this first version is to establish the feedback loop.

---

# 12. EVOLUTION HOOK

The first implementation must leave a clean place for:

```text
result
   ↓
evaluation
   ↓
next_action
   ↓
new workflow step / experiment
```

Do NOT implement a full autonomous evolution engine yet.

Simply ensure the workflow state can store:

```text
evaluation
winner
losers
metrics
next_action
```

This becomes the foundation for the next upgrade.

---

# 13. API

Follow the existing API architecture.

Expose the smallest useful interface, conceptually:

```text
POST   /workflows
GET    /workflows
GET    /workflows/{id}
POST   /workflows/{id}/run
GET    /workflows/{id}/state
```

If equivalent routes already exist, extend them rather than creating duplicates.

The API should allow the operator/dashboard to:

1. create a workflow
2. inspect it
3. start it
4. inspect execution state
5. inspect results

---

# 14. DASHBOARD

Only make dashboard changes if required to expose the new workflow capability.

Do not redesign the dashboard.

The minimum useful UI is:

```text
Workflows
 ├── Create
 ├── Status
 ├── Current step
 ├── Results
 └── Run
```

Reuse existing dashboard components and styling.

If the API can be fully tested without UI changes, do not unnecessarily expand the UI in this implementation.

---

# 15. DATABASE / STORAGE

Use the existing persistence layer.

Create only the minimum required models/tables/collections.

The workflow must persist:

```text
workflow definition
execution status
current step
step results
artifacts
evaluation
timestamps
errors
```

Use existing migration and database conventions.

---

# 16. TESTING

Testing is mandatory.

Add tests for:

### Workflow creation
- valid workflow
- invalid workflow

### Execution
- steps execute in order
- state persists
- completed steps are not duplicated
- failure stops execution
- workflow can resume

### Integration
- G1 adapter called correctly
- G2 adapter called correctly
- G3 adapter called correctly
- results are captured
- evaluator receives results

### API
- create
- list
- inspect
- run
- state

### End-to-end

Create one test workflow equivalent to:

```text
objective
→ G1
→ 3 hypotheses
→ G2 assets
→ G3 publish
→ results
→ evaluation
```

Where external services cannot safely run during tests, mock them at the existing service boundary.

Do not fake the architecture itself.

---

# 17. OBSERVABILITY

Use the project's existing logging/monitoring conventions.

Every workflow execution should make it possible to determine:

```text
workflow
step
status
duration
output
error
```

Avoid introducing a new logging system.

---

# 18. SECURITY

Follow the repository's existing authentication and authorization.

Do not expose workflow execution publicly without the existing security controls.

Do not expose internal GPU credentials, API keys, or service credentials through workflow state or API responses.

---

# 19. IMPLEMENTATION PROCESS

Work in this order:

```text
1. Inspect repository
2. Map existing G1/G2/G3/Company Core interfaces
3. Identify existing campaign/attribution/storage models
4. Design the smallest compatible workflow model
5. Implement persistence
6. Implement runner
7. Implement adapters
8. Implement API
9. Add minimal dashboard exposure if necessary
10. Add tests
11. Run existing test suite
12. Run lint/type checks
13. Run the real end-to-end workflow
14. Fix integration issues
15. Report final architecture
```

Do not start coding before understanding the existing interfaces.

---

# 20. ACCEPTANCE CRITERIA

The implementation is complete only when this is possible:

```text
Create workflow
      ↓
Start workflow
      ↓
G1 executes
      ↓
3 hypotheses exist
      ↓
G2 executes using existing pipeline
      ↓
Assets exist
      ↓
G3 executes using existing publishing system
      ↓
Results are captured
      ↓
Evaluator runs
      ↓
Winner / metrics / next action stored
      ↓
Workflow reaches completed state
```

And the operator can inspect the entire execution through the existing control plane/API.

---

# 21. IMPORTANT SCOPE LIMIT

Do NOT build yet:

- Meta Ads integration
- Instagram API replacement
- WhatsApp replacement
- LinkedIn replacement
- autonomous ad buying
- autonomous CRM replacement
- sophisticated reinforcement learning
- complex agent orchestration
- distributed workflow infrastructure
- new video-generation infrastructure
- new GPU infrastructure
- coding-agent infrastructure
- generalized AI planner

Those are future capabilities.

This implementation exists for one purpose:

> **Give AutoEvolve the ability to execute its first complete business workflow using the systems that already exist.**

At the end, provide:

1. Files changed
2. Architecture added
3. Existing systems reused
4. Tests run
5. End-to-end test result
6. Any blockers
7. The exact next upgrade required for autonomous evolution

Do not claim completion unless the end-to-end workflow has actually executed successfully.
