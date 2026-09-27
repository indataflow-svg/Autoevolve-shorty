# SCREENSHOT_REFERENCES.md — AutoEvolve Visual Specification

## Purpose
These screenshots are approved visual references. They define visual language, information density, page anatomy, and interaction patterns. They do not override backend truth.

Location:
```text
references/ui/
```

## How to inspect
For any model/tool that supports image-detail control, inspect references at `original` or `auto` detail rather than a low-resolution thumbnail.

For each page identify:
1. global shell regions
2. page-specific regions
3. component families
4. alignment lines
5. repeated spacing units
6. typography hierarchy
7. semantic color use
8. row/drawer interaction
9. visible states/actions
10. screenshot data not supported by backend

Do not assume sample values are real requirements.

## Global visual grammar
- very dark navy shell, not pure black
- fixed left sidebar separated by subtle border
- topbar/global search aligned with main content
- white page title + muted supporting copy
- restrained blue primary action
- KPI strip below page header where relevant
- tabs/view filters immediately above main table
- subtle row separators
- compact rows and controls
- selected row highlighted blue
- selected record shown in right drawer
- semantic colors:
  - green = healthy/verified/approved/positive/sent
  - yellow = warning/review/due
  - red = invalid/destructive/suppressed/problem
  - purple = AI/content/special workflow
  - blue = selected/primary/in-progress/navigation
- compact iconography
- consistent control heights
- moderate radii
- no glassmorphism
- no neon
- no generic dashboard-template feel
- no excessive gradient decoration

## 01 — Integrations
File: `01-integrations.jpeg`

Structure:
- sidebar + global search
- title + API docs + add integration
- 4 KPI cards
- category tabs/search/sort
- integration table
- provider drawer
- overview/usage/settings/logs tabs

Key reusable components:
- IntegrationCell
- HealthBadge
- CapabilityTag
- ProviderDrawer
- UsageMeter

Never fake provider health, usage, webhook events, or credentials.

## 02 — Research
File: `02-research.jpeg`

Structure:
- title + saved searches + new research
- 4 KPI cards
- persistent left filter column
- view tabs
- company table
- company drawer

Behavior:
- company-centric workspace
- left filters separate from table toolbar
- next-step action visible in each row
- drawer includes company summary, tools, signals, notes, recommendation

Never invent detected tools/signals.

## 03 — Content
File: `03-content.jpeg`

Structure:
- title + generation/new-content actions
- 4 KPIs
- lifecycle tabs
- content table
- content drawer with asset previews

Behavior:
- format and lifecycle stage remain separate
- script/caption central in drawer
- review/regenerate/handoff actions grouped at bottom

Do not claim publication before provider confirmation.

## 04 — Settings
File: `04-settings.jpeg`

Structure:
- page title
- secondary settings navigation
- central forms
- right health/data/quick-links sidebar

Behavior:
- no KPI strip
- broad bordered form sections
- compact labels/help copy
- subordinate environment-health panel

Do not expose secrets or create fake billing/security controls.

## 05 — Campaigns
File: `05-campaigns.jpeg`

Structure:
- title/date range/new campaign
- 4 KPIs
- program/status tabs
- filters/sort
- campaign table
- campaign drawer

Behavior:
- compact channel icons
- status badge communicates workflow
- drawer combines goal, audience, channels, tracked URL, real performance, next step

Do not fabricate analytics.

## 06 — Meetings
File: `06-meetings.jpeg`

Structure:
- title + booking action
- 4 KPIs
- state tabs + filters/sort
- meeting table
- weekly schedule strip
- meeting drawer

Behavior:
- actionable list first, calendar second
- drawer: details, agenda, notes, source, opportunity, actions

Links/status must be real.

## 07 — Replies
File: `07-replies.jpeg`

Structure:
- title/date range
- 4 KPIs
- 2 priority summary cards
- state tabs
- reply table
- message drawer

Behavior:
- intent and confidence separate
- suggested action per row
- original message shown before extracted signals/generated response

Never replace original inbound content with generated text.

## 08 — Contacts
File: `08-contacts.jpeg`

Recommended first vertical slice.

Structure:
- title + import/enrich/add
- 4 KPIs
- program/status tabs
- contact table
- contact drawer

Behavior:
- canonical person/company relation
- concise fit score
- explicit email state
- source + last touch visible
- row-level next action
- drawer combines identity, company, research, notes, tags, primary action

Use this page to stabilize shared table + drawer patterns.

## 09 — Outreach
File: `09-outreach.jpeg`

Structure:
- title + new outreach
- 4 KPIs
- workflow-state tabs
- outreach table
- selected draft drawer

Behavior:
- state-aware actions: approve/edit/send/follow-up/view
- message preview central in drawer
- personalization reason visible
- strong primary action only when workflow state allows it

Never bypass backend approval gates.

## Approximate shared geometry
Starting points only:
- sidebar ~220px
- topbar ~60–64px
- right drawer ~340–400px
- content horizontal padding ~20–28px
- table rows compact, roughly mid-50px
- controls consistent in height
- 4 KPI cards across wide desktop

Refine through browser screenshots rather than hardcoding screenshot measurements.

## Match first
1. sidebar/main/drawer proportions
2. topbar/page-header alignment
3. table width/column rhythm
4. KPI height/spacing
5. selected-row treatment
6. drawer hierarchy
7. typography
8. color refinement
9. icon sizing
10. micro-spacing

## Do not copy literally
- sample names
- sample metrics
- fake provider data
- fake analytics
- fake signals
- unsupported actions
- exact text lengths
- screenshot artifacts

The screenshot is the visual target. The backend decides what the UI can truthfully say.
