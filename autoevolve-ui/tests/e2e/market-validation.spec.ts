import { expect, test } from '@playwright/test'

const auth = `Basic ${btoa('founder:browser-secret')}`

// Onboarding -> CompanyContext -> market_validation -> a stored plan the founder
// can review. Nothing is sent, published, launched, or spent.
test('a founder reaches market validation and reviews a generated plan', async ({ page, request }) => {
  await page.goto('/onboarding')
  await page.getByLabel('Username').fill('founder')
  await page.getByLabel('Password').fill('browser-secret')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByLabel('Founder action token').fill('browser-action')

  await page.getByLabel('Company name').fill('Northlight Ops')
  await page.getByLabel('Website').fill('https://northlight.example')
  await page.getByLabel('Objective').fill('Get the first ten paying customers')
  await page.getByLabel('Primary market').fill('United States')
  await page.getByRole('button', { name: 'Save and continue' }).click()
  await expect(page.getByRole('heading', { name: /Research and confirm/ })).toBeVisible()

  // The confirm step keeps its required founder-confirmed facts.
  await page.getByLabel('Description').fill('Northlight Ops runs a managed operations desk for small logistics teams.')
  await page.getByLabel('Industry').fill('Logistics')
  await page.getByLabel('Positioning').fill('Operations teams get a clean handoff record in one week.')
  await page.getByLabel('Offer summary').fill('A two-week managed operations setup plus monthly review.')

  await page.getByText('More about your business').click()
  await page.getByLabel('Product or service').fill('Managed Operations Desk')
  await page.getByLabel('Ideal customer').fill('Logistics companies with 20-200 people running dispatch on spreadsheets')
  await page.getByLabel('Problem').fill('Dispatch handoffs live in spreadsheets, so missed loads are found late')
  await page.getByLabel('Customers · one per line').fill('Two design partners running the desk since March')
  await page.getByLabel('Traction · one per line').fill('Two paid setups')
  await page.getByLabel('Pricing').fill('$4,000 setup plus $1,500 per month')
  await page.getByRole('radio', { name: 'Starting from zero' }).check()
  await page.getByRole('button', { name: 'Confirm company context' }).click()
  await expect(page.getByText('context complete')).toBeVisible()

  // The dashboard routes the company into market validation.
  await page.getByRole('main').getByRole('link', { name: 'Home' }).click()
  await expect(page.getByRole('heading', { name: 'Home' })).toBeVisible()
  await expect(page.locator('.home-stage').getByText('Market Validation')).toBeVisible()
  await expect(page.locator('.home-stage')).toContainText('market-validation experiment')

  // The market-validation screen plans only.
  await page.getByRole('link', { name: 'Market Validation' }).click()
  await expect(page.getByRole('heading', { name: 'Market Validation', exact: true })).toBeVisible()
  await expect(page.getByText('no plan yet')).toBeVisible()
  for (const forbidden of ['Send', 'Publish', 'Launch', 'Execute', 'Run campaign']) {
    await expect(page.getByRole('button', { name: forbidden })).toHaveCount(0)
  }
  await page.getByLabel('Founder action token').fill('browser-action')
  await page.getByRole('button', { name: 'Generate Validation Plan' }).click()

  await expect(page.getByText('Validation Plan Ready')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Hypothesis' })).toBeVisible()
  await expect(page.getByText('Booked discovery call').first()).toBeVisible()
  await expect(page.getByText('At least 5 booked discovery calls from the first 50 targeted prospects')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Evidence' })).toBeVisible()
  await expect(page.getByText('Two paid setups')).toBeVisible()
  await expect(page.getByText('How many comparable operators run dispatch on spreadsheets')).toBeVisible()
  await page.screenshot({ path: '/tmp/autoevolve-market-validation-plan.png', fullPage: true })

  // The plan is persisted, reviewable after a reload, and nothing ran.
  await page.reload()
  await page.getByLabel('Username').fill('founder')
  await page.getByLabel('Password').fill('browser-secret')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.locator('.onboarding-progress').getByText('plan ready')).toBeVisible()
  await page.getByRole('button', { name: 'View Plan' }).click()
  await expect(page.getByRole('heading', { name: 'Hypothesis' })).toBeVisible()

  const stored = await (await request.get('/company/marketing/validation/plan', { headers: { Authorization: auth } })).json()
  expect(stored.status).toBe('planned')
  expect(stored.plan.workflow_template).toBe('market_validation_v1')
  expect(stored.plan.validation.method).toBe('targeted_outbound')
  expect(stored.plan.evidence.known_facts).toContain('Two paid setups')
  expect(stored.plan.limits.requires_approval).toBe(true)
  expect(stored.provenance.prompt_version).toBe('market_validation_v1')

  const workflows = await (await request.get('/company/workflows', { headers: { Authorization: auth } })).json()
  expect(workflows.length).toBe(0)
})

// Governance turns the same plan into a runnable workflow, and the existing
// runner executes one simulated action. Nothing is sent or published.
test('governance validates, creates a workflow, and runs a simulation', async ({ page, request }) => {
  // Setup goes through the API so this test owns only the governance lifecycle.
  const write = { Authorization: auth, 'X-Founder-Action-Token': 'browser-action', 'Content-Type': 'application/json' }
  await request.post('/company/setup/onboarding/company', { headers: write, data: {
    name: 'Northlight Ops', website: 'https://northlight.example',
    objective: 'Get the first ten paying customers', market: 'United States',
  } })
  await request.post('/company/setup/onboarding/company/confirm', { headers: write, data: {
    name: 'Northlight Ops', website: 'https://northlight.example',
    description: 'Northlight Ops runs a managed operations desk for small logistics teams.',
    industry: 'Logistics', positioning: 'Operations teams get a clean handoff record in one week.',
    offer_summary: 'A two-week managed operations setup plus monthly review.',
    product_name: 'Managed Operations Desk',
    ideal_customer: 'Logistics companies with 20-200 people running dispatch on spreadsheets',
    problem: 'Dispatch handoffs live in spreadsheets, so missed loads are found late',
    existing_customers: ['Two design partners running the desk since March'],
    traction: ['Two paid setups'], channels: ['Email'],
    marketing_stage: 'starting_from_zero',
  } })

  await page.goto('/validation')
  await page.getByLabel('Username').fill('founder')
  await page.getByLabel('Password').fill('browser-secret')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByLabel('Founder action token').fill('browser-action')
  await page.getByRole('button', { name: 'Generate Validation Plan' }).click()
  await expect(page.getByText('Validation Plan Ready')).toBeVisible()

  await page.getByRole('button', { name: 'Validate Plan' }).first().click()
  await expect(page.locator('.validation-lifecycle').getByText('Workflow Created')).toBeVisible()
  // A fully specified, in-limit plan passes with nothing to report.
  await expect(page.locator('.validation-lifecycle').getByText('Validated')).toBeVisible()
  await expect(page.locator('.validation-reasons')).toHaveCount(0)

  // Execution stays locked until the founder approves.
  await expect(page.getByRole('button', { name: 'Run Simulation' })).toBeDisabled()
  await page.getByRole('button', { name: 'Approve' }).click()
  await expect(page.locator('.validation-lifecycle').getByText('Approved')).toBeVisible()
  await page.getByRole('button', { name: 'Run Simulation' }).click()
  await expect(page.locator('.validation-lifecycle').getByText('Executed')).toBeVisible()
  await expect(page.getByText('simulated · outreach')).toBeVisible()
  await expect(page.getByText('External side effects')).toBeVisible()
  await page.screenshot({ path: '/tmp/autoevolve-market-validation-executed.png', fullPage: true })

  const governance = await (await request.get('/company/marketing/validation/workflow', { headers: { Authorization: auth } })).json()
  expect(governance.status).toBe('valid')
  expect(governance.lifecycle).toBe('executed')
  expect(governance.required_approval).toBe(true)
  expect(governance.resolved_actions[0].action).toBe('simulate_outreach')
  expect(governance.execution.status).toBe('completed')
  expect(governance.execution.steps[0].output.external_side_effects).toBe(false)
  expect(governance.execution.steps[0].output.targets).toBe(50)

  // The workflow is an ordinary, already-completed workflow document.
  const workflows = await (await request.get('/company/workflows', { headers: { Authorization: auth } })).json()
  expect(workflows).toHaveLength(1)
  expect(workflows[0].state.status).toBe('completed')
  expect(workflows[0].steps[0].action).toBe('simulate_outreach')
  expect(workflows[0].trigger.config.simulation).toBe(true)
})