# Documentation index

AutoEvolve's React UI uses the Company Core FastAPI backend. Existing
`COMPANY_CORE_*` configuration names and engine binaries retain their names.

## Start here

- [Functionality Reference](FUNCTIONALITY.md): **every capability in the product** — onboarding, sales, marketing, video, engineering, research, platform — with routes, tables, and honest limits.
- [API Reference](API-REFERENCE.md): every public function, class, route, and table, generated from source.

## Start and operate

- [README](../README.md): requirements, installation, frontend build, first boot.
- [Frontend Guide](../autoevolve-ui/README.md): development, sign-in, generated API contract, browser tests.
- [Product Tour](product-tour.md): current React pages and supported actions.
- [V2 Closure](v2-closure.md): resumable onboarding, real-record orchestration, legacy route disposition.
- [API Keys](keys.md), [Configuration](configuration.md), and [Provider Setup](providers.md): required versus optional integrations.
- [Deployment](deployment.md): native hosting, optional Docker, HTTPS, and public links.
- [Testing and Errors](v2-testing-and-errors.md): regression gates and HTTP failure handling.
- [Repository Readiness](repository-readiness.md): source packaging, exclusions, and unverified startup limits.
- [Production Checklist](production-checklist.md) and [Upgrading and Backups](upgrading.md).

## Current implementation references

- [System Architecture](system-architecture.md) and its [editable Excalidraw map](system-architecture.excalidraw): runtime, auth, persistence, frontend/backend relationships.
- [Workflow UI Contract](workflow-ui-contract.md): page reads, mutations, exact backend semantics, unsupported fields.
- [UI Reference Coverage](ui-reference-coverage.md): approved images mapped to implementation baselines; visual limitations.
- [Visual Specification](../autoevolve-ui-agent-pack/docs/SCREENSHOT_REFERENCES.md) and [UI Implementation Rules](../autoevolve-ui-agent-pack/docs/UI_IMPLEMENTATION.md).
- [Lifecycle Architecture](architecture.md): sales and publishing state transitions.
- [V2 Final Report](v2-final-report.md): closure functionality, validation, and remaining limitations.

## Tutorials and troubleshooting

- [First Sales Outreach](first-outreach.md) and [First Marketing Campaign](first-campaign.md).
- [Motion Designer Workflow](motion-design-workflow.md): source-grounded story, GPT skill, Higgsfield shots, and G2 review handoff.
- [Model Routing](model-routing.md), [Lead Intake](lead-intake.md), and [Troubleshooting](troubleshooting.md).

## Historical and planning material

Use these to understand decisions, not as current API or startup contracts:

- [Planning Sources](plans/README.md): original operating plan, extraction, and target-state drawings.
- [V2 Implementation Plan](v2-implementation-plan.md): product direction and proposed infrastructure.
- [Original Backend/UI Audit](backend-ui-audit.md): findings before later projections and pages were added.
- [Historical Backend Map](backend-system-map.md), [diagram](backend-system-map.excalidraw), and [preview](backend-system-map-preview.png).

Where a historical artifact differs from code, use the generated OpenAPI contract,
current runtime documentation, and regression tests.
