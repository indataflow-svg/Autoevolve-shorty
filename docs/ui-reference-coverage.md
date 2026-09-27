# Approved UI images and implementation coverage

Your nine original JPEGs remain unchanged in
`autoevolve-ui-agent-pack/references/ui/`. They specify layout, density, shell,
tables, drawers, color, and interaction style. Backend records and allowed
transitions determine displayed facts and actions. Reference sample data is
never production data.

## Page-to-image traceability

Baseline links below open the actual implementation screenshots used by
Playwright. These are distinct from the approved reference images.

| React page | Approved image | Implementation baseline | Backend constraint affecting parity |
| --- | --- | --- | --- |
| Integrations | [01-integrations](../autoevolve-ui-agent-pack/references/ui/01-integrations.jpeg) | [Integrations](../autoevolve-ui/tests/e2e/operational.spec.ts-snapshots/integrations-desktop-linux.png) | Configured keys do not establish health; unsupported quota/spend cards are omitted. |
| Research | [02-research](../autoevolve-ui-agent-pack/references/ui/02-research.jpeg) | [Research](../autoevolve-ui/tests/e2e/companies.spec.ts-snapshots/research-desktop-linux.png) | Optional enrichment facts remain optional; saved searches, owner, and inferred signals are not invented. |
| Content | [03-content](../autoevolve-ui-agent-pack/references/ui/03-content.jpeg) | [Content](../autoevolve-ui/tests/e2e/workflows.spec.ts-snapshots/content-workflow-linux.png) | Manual posts and asset packs have distinct states; Buffer scheduled is not published; metrics require provider confirmation. |
| Settings | [04-settings](../autoevolve-ui-agent-pack/references/ui/04-settings.jpeg) | [Settings](../autoevolve-ui/tests/e2e/operational.spec.ts-snapshots/settings-desktop-linux.png) | Real organization/capability settings; unsupported billing, team, and backup controls are omitted. |
| Campaigns | [05-campaigns](../autoevolve-ui-agent-pack/references/ui/05-campaigns.jpeg) | [Campaigns](../autoevolve-ui/tests/e2e/workflows.spec.ts-snapshots/campaigns-workflow-linux.png) | Actual campaign stages and saved scripts; no invented launch dates or campaign performance. |
| Meetings | [06-meetings](../autoevolve-ui-agent-pack/references/ui/06-meetings.jpeg) | [Meetings](../autoevolve-ui/tests/e2e/sales-workflow.spec.ts-snapshots/meetings-workflow-linux.png) | Manual meeting markers do not establish calendar bookings, attendance, duration, or opportunity value. |
| Replies | [07-replies](../autoevolve-ui-agent-pack/references/ui/07-replies.jpeg) | [Replies](../autoevolve-ui/tests/e2e/sales-workflow.spec.ts-snapshots/replies-workflow-linux.png) | Saved inbound interactions; no fabricated intent/confidence or positive-reply classification. |
| Contacts | [08-contacts](../autoevolve-ui-agent-pack/references/ui/08-contacts.jpeg) | [Contacts](../autoevolve-ui/tests/e2e/contacts.spec.ts-snapshots/contacts-desktop-linux.png) | Uses real leads/contacts; unavailable ownership/fit/engagement facts are not fabricated. |
| Outreach | [09-outreach](../autoevolve-ui-agent-pack/references/ui/09-outreach.jpeg) | [Outreach](../autoevolve-ui/tests/e2e/workflows.spec.ts-snapshots/outreach-workflow-linux.png) | Exact draft/approved/sending/sent/send_unknown states; unsupported due dates and personalization reasons are omitted. |

Companies reuses the Research composition. Home and Onboarding have no dedicated
approved images; they reuse the established shell and controls. Home has a
[visual baseline](../autoevolve-ui/tests/e2e/workflows.spec.ts-snapshots/home-workflow-linux.png).
The onboarding E2E also compares its
[visual baseline](../autoevolve-ui/tests/e2e/onboarding.spec.ts-snapshots/onboarding-first-run-linux.png).
It is not an additional approved reference image.

## What visual validation proves

Tests compare rendered fixture-backed pages against implementation baselines,
using Chromium at 1536 × 864. The default, workflow, and sales visual suites
allow a maximum differing-pixel ratio of 0.01. They detect regressions in the
approved implementation, not exact equality with your original JPEGs.
Mobile behavior has separate functional checks.

The original JPEGs are reviewed manually for layout and visual language. There
is no automated original-image similarity score and no claim of pixel-perfect
parity. Honest backend limitations intentionally change visible content and
some controls. [Workflow UI Contract](workflow-ui-contract.md) documents those
differences; [Visual Specification](../autoevolve-ui-agent-pack/docs/SCREENSHOT_REFERENCES.md)
describes the page anatomy to preserve.

CI runs functional and baseline comparisons without updating screenshots.
Changes to visual baselines require reviewing both the original image and the
rendered page, documenting intentional differences, and preserving backend
action gates. Test records and provider substitutes remain fixture-only.
