import { expect, test } from '@playwright/test'

const auth = `Basic ${btoa('founder:browser-secret')}`

// Onboarding -> CompanyContext -> market_validation -> a stored plan the founder
// can review. Nothing is sent, published, launched, or spent.
test('a founder reaches market validation and reviews a generated plan', async ({ page, request }) => {
  await page.goto('/onboarding')
  await page.getByLabel('Username').fill('founder')
  await page.getByLabel('Password').fill('browser-secret')
  await page.getByRole('button', { name: 'Sign in' }).click()
  const write = { Authorization: auth, 'X-Founder-Action-Token': 'browser-action', 'Content-Type': 'application/json' }
  const seeded = await request.put('/company/context', { headers: write, data: {
    company: {
      name: 'Northlight Ops', website: 'https://northlight.example',
      description: 'Northlight Ops runs a managed operations desk for small logistics teams.',
    },
    product: { name: 'Managed Operations Desk', description: 'A two-week managed operations setup plus monthly review.' },
    customer: { ideal_customer: 'Logistics companies with 20-200 people running dispatch on spreadsheets' },
    market: { problem: 'Dispatch handoffs live in spreadsheets, so missed loads are found late', market: 'United States' },
    objective: { primary_goal: 'Get the first ten paying customers' },
    evidence: { existing_customers: ['Two design partners running the desk since March'], traction: ['Two paid setups'] },
    resources: { channels: ['Email'] },
    state: { marketing_stage: 'starting_from_zero' },
  } })
  expect(seeded.status()).toBe(200)

  await page.goto('/home')
  await page.getByLabel('Username').fill('founder')
  await page.getByLabel('Password').fill('browser-secret')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: 'Home' })).toBeVisible()
  await expect(page.locator('.home-stage').getByText('Market Validation')).toBeVisible()
  await expect(page.locator('.home-stage')).toContainText('market-validation experiment')

  // The market-validation screen plans only.
  await page.getByRole('link', { name: 'Workflows' }).click()
  await expect(page.getByRole('heading', { name: 'Workflows', exact: true })).toBeVisible()
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

  const stored = await (await request.get('/company/automation/plan', { headers: { Authorization: auth } })).json()
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
  const seeded = await request.put('/company/context', { headers: write, data: {
    company: {
      name: 'Northlight Ops', website: 'https://northlight.example',
      description: 'Northlight Ops runs a managed operations desk for small logistics teams.',
    },
    product: { name: 'Managed Operations Desk', description: 'A two-week managed operations setup plus monthly review.' },
    customer: { ideal_customer: 'Logistics companies with 20-200 people running dispatch on spreadsheets' },
    market: { problem: 'Dispatch handoffs live in spreadsheets, so missed loads are found late', market: 'United States' },
    objective: { primary_goal: 'Get the first ten paying customers' },
    evidence: { existing_customers: ['Two design partners running the desk since March'], traction: ['Two paid setups'] },
    resources: { channels: ['Email'] },
    state: { marketing_stage: 'starting_from_zero' },
  } })
  expect(seeded.status()).toBe(200)

  await page.goto('/workflows')
  await page.getByLabel('Username').fill('founder')
  await page.getByLabel('Password').fill('browser-secret')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByLabel('Founder action token').fill('browser-action')
  await page.getByRole('button', { name: 'Generate Validation Plan' }).click()
  await expect(page.getByText('Validation Plan Ready')).toBeVisible()

  await page.getByRole('button', { name: 'Governance' }).click()
  await page.getByRole('button', { name: 'Validate Plan' }).first().click()
  await expect(page.locator('.validation-lifecycle').getByText('Workflow Created')).toBeVisible()
  await expect(page.locator('.validation-reasons')).toHaveCount(0)

  // Execution stays locked until the founder approves.
  await expect(page.getByRole('button', { name: 'Run', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Approve' }).click()
  await expect(page.locator('.validation-lifecycle').getByText('Approved')).toBeVisible()
  await page.getByRole('button', { name: 'Run', exact: true }).click()
  await expect(page.locator('.validation-lifecycle').getByText('Executed')).toBeVisible()
  await expect(page.getByText('simulated · outreach')).toBeVisible()
  await expect(page.locator('.onboarding-panel', { has: page.getByRole('heading', { name: 'Governance' }) }).getByText('External side effects')).toBeVisible()
  await page.screenshot({ path: '/tmp/autoevolve-market-validation-executed.png', fullPage: true })

  const governance = await (await request.get('/company/automation/governance', { headers: { Authorization: auth } })).json()
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