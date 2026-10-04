# AutoEvolve — Phase 1: Company Context Layer

## Mission

Upgrade the existing AutoEvolve onboarding flow so that it produces a structured, persistent **CompanyContext** that future autonomous sales and marketing workflows can use.

This is **Phase 1 only**.

The only completed intelligence component currently available is **OmniRoute**.

Do not implement Hermes, autonomous execution, market validation, workflow generation, or evolution in this phase.

The objective is simply:

> Turn onboarding information into a reliable canonical representation of the company, product, market, customer, problem, evidence, resources, constraints, and business goal.

---

# 1. FIRST INSPECT THE EXISTING SYSTEM

Before changing anything, inspect the actual repository.

Locate:

- current onboarding flow
- onboarding API/routes
- onboarding UI
- company model
- company settings/configuration
- existing database/storage layer
- existing company state/context
- existing marketing configuration
- existing dashboard/company profile components
- existing validation conventions
- existing authentication/authorization

Determine whether an equivalent company-context structure already exists.

If it does, extend/reuse it instead of creating a duplicate.

Do not assume the architecture from documentation. Inspect the actual code.

---

# 2. SCOPE

Only implement:

```text
Existing Onboarding
        ↓
Structured CompanyContext
        ↓
Persistent Storage
        ↓
API access
```

Do not implement:

- Hermes
- OmniRoute changes
- workflow execution
- autonomous agents
- market research
- campaign generation
- G1 changes
- G2 changes
- G3 changes
- sales automation
- outbound automation
- autonomous publishing
- evolution
- new AI providers
- new agent frameworks

If another component must be touched to expose the context cleanly, make the smallest possible change.

---

# 3. COMPANY CONTEXT

Create or extend the canonical company context.

Conceptually:

```yaml
company_context:

  company:
    name:
    description:
    website:
    geography:

  product:
    name:
    description:
    category:
    value_proposition:

  customer:
    ideal_customer:
    industry:
    company_size:
    geography:
    buyer_role:

  market:
    market:
    segment:
    problem:
    urgency:
    alternatives:

  evidence:
    existing_customers:
    existing_demand:
    previous_marketing:
    testimonials:
    traction:
    other:

  offer:
    description:
    pricing:
    business_model:

  resources:
    channels:
    assets:
    team:
    budget:

  constraints:
    geographic:
    brand:
    budget:
    regulatory:
    operational:

  objective:
    primary_goal:
    desired_outcome:

  state:
    marketing_stage:
```

Do NOT blindly implement this exact schema.

Adapt it to the repository's existing models and conventions.

Keep fields practical and minimal.

---

# 4. MARKETING STAGE

Add a simple marketing-stage field.

For this phase support at least:

```text
starting_from_zero
```

If the existing system already has a compatible state model, reuse it.

Do not implement the second branch yet.

Do not build campaign-running logic.

The field simply establishes the user's starting state for future phases.

---

# 5. ONBOARDING UX

Keep the existing onboarding experience.

Do not redesign it unnecessarily.

Modify only what is required to collect the information needed for CompanyContext.

The onboarding should understand:

### Business

- company name
- what the company does
- website if available
- geography

### Product

- product/service
- what it does
- main value proposition

### Customer

- who the product is for
- industry/segment
- geography
- likely buyer

### Problem

- problem being solved
- why it matters
- urgency if known

### Market

- target market
- known alternatives/competitors if available

### Evidence

- customers
- demand
- previous sales
- previous campaigns
- testimonials
- traction

Do not force users to provide information they do not know.

Unknown values should remain explicitly unknown/null rather than being invented.

### Offer

- what is being sold
- pricing if known
- business model

### Resources

- existing channels
- existing marketing assets
- available team/resources
- budget if relevant

### Constraints

- geographic limitations
- budget limitations
- brand restrictions
- operational restrictions
- other relevant constraints

### Objective

Ask for the primary business outcome.

Examples:

```text
Get first customers
Generate qualified leads
Book sales meetings
Increase sales
Validate demand
Launch a product
```

Do not force the user to choose from these exact values if the current onboarding already uses a better mechanism.

---

# 6. USER EXPERIENCE PRINCIPLE

The user should feel like they are explaining their business, not filling out a database schema.

Prefer:

```text
"What are you selling?"
```

over:

```text
"Enter value_proposition"
```

Prefer progressive/contextual questions where the existing onboarding architecture supports them.

Do not turn onboarding into a long questionnaire unnecessarily.

The system should collect enough information to understand the business while allowing unknown fields.

---

# 7. NORMALIZATION

When onboarding is submitted:

```text
raw onboarding answers
        ↓
normalize
        ↓
CompanyContext
        ↓
validate
        ↓
persist
```

Normalization should:

- clean obvious formatting issues
- normalize known enum/state values
- preserve user meaning
- preserve unknown values
- avoid inventing information
- avoid silently changing business claims

If existing normalization utilities exist, reuse them.

---

# 8. VALIDATION

Validate the minimum required information.

At minimum, AutoEvolve should know:

```text
company
product/service
customer
problem
objective
marketing_stage
```

If one is genuinely unknown, allow the onboarding to continue where appropriate and mark it as unknown/incomplete.

Do not fabricate missing information.

The system should be able to determine:

```text
context_complete
context_incomplete
```

If the existing application has validation conventions, follow them.

---

# 9. PERSISTENCE

Persist the CompanyContext using the existing storage architecture.

Do not create a second company database.

The context should survive:

- page reload
- login
- API restart
- later workflow execution

Use existing migrations/model conventions.

---

# 10. API

Expose the canonical context through the existing API architecture.

Conceptually:

```text
GET  /company/context
PUT  /company/context
```

If equivalent company/profile endpoints already exist, extend those rather than creating duplicates.

The API response should return the normalized CompanyContext.

Do not expose secrets or internal credentials.

---

# 11. FUTURE COMPATIBILITY

The resulting CompanyContext must be easy for future components to consume.

Future architecture:

```text
CompanyContext
      ↓
Workflow Prompt
      ↓
OmniRoute
      ↓
Hermes
      ↓
Workflow
```

This phase only implements the first box.

Do not implement the rest.

Design the data structure so future prompts/agents can consume it without scraping UI fields.

---

# 12. TESTING

Add tests following existing project conventions.

Test:

### Onboarding

- valid onboarding
- partial onboarding
- missing required context
- unknown values
- existing user/company update

### Normalization

- raw input becomes correct CompanyContext
- marketing stage is correctly stored
- no information is invented

### Persistence

- context survives reload
- update replaces/merges correctly according to existing conventions

### API

- retrieve context
- update context
- validation errors
- authorization

### Regression

Run the existing test suite.

Make sure current onboarding functionality still works.

---

# 13. ACCEPTANCE TEST

The phase is complete when a new user can:

```text
Start onboarding
      ↓
Describe company
      ↓
Describe product
      ↓
Describe customer
      ↓
Describe problem
      ↓
Describe market
      ↓
Provide known evidence
      ↓
Define objective
      ↓
Select/confirm "Starting from zero"
      ↓
Complete onboarding
```

and AutoEvolve stores a canonical object equivalent to:

```json
{
  "company": {},
  "product": {},
  "customer": {},
  "market": {},
  "evidence": {},
  "offer": {},
  "resources": {},
  "constraints": {},
  "objective": {},
  "state": {
    "marketing_stage": "starting_from_zero"
  }
}
```

The exact implementation should follow the repository's existing architecture.

---

# 14. FINAL REPORT

After implementation, report only:

1. Existing onboarding architecture discovered
2. CompanyContext implementation
3. Files changed
4. Database/model changes
5. API changes
6. UI changes
7. Tests executed
8. Any issues/blockers
9. Example of the resulting CompanyContext

Do not implement Phase 2.

Do not start Hermes.

Do not modify OmniRoute.

Stop after CompanyContext is working and tested.
