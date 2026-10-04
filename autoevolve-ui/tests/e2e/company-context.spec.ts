import { expect, test } from '@playwright/test'

const auth = `Basic ${btoa('founder:browser-secret')}`

// Walks the founder through the answers AutoEvolve needs, then checks the
// canonical company context through the same API the page reads.
test('a new user describes the business and the canonical context is stored', async ({ page, request }) => {
  await page.goto('/onboarding')
  await page.getByLabel('Username').fill('founder')
  await page.getByLabel('Password').fill('browser-secret')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByLabel('Founder action token').fill('browser-action')

  await page.getByLabel('Company name').fill('Example Studio')
  await page.getByLabel('Website').fill('https://studio.test')
  await page.getByLabel('Objective').fill('Get the first ten paying customers')
  await page.getByLabel('Primary market').fill('United States')
  await page.getByRole('button', { name: 'Save and continue' }).click()

  await expect(page.getByRole('heading', { name: /Research and confirm/ })).toBeVisible()
  await page.getByRole('button', { name: 'Research website' }).click()
  await expect(page.getByText('Source: website + companyenrich')).toBeVisible()

  // Optional answers the founder actually knows, asked in plain language.
  await page.getByText('More about your business').click()
  await page.getByLabel('Product or service').fill('Managed Operations Desk')
  await page.getByLabel('What it does').fill('A guided setup of the customer operations handoffs.')
  await page.getByLabel('Ideal customer').fill('Logistics teams running dispatch on spreadsheets')
  await page.getByLabel('Problem').fill('Missed loads are found a week late')
  await page.getByLabel('Testimonials · one per line').fill('Operations Director: handoffs stopped falling through')
  await page.getByLabel('Pricing').fill('$4,000 setup plus $1,500 per month')
  await page.getByRole('radio', { name: 'Starting from zero' }).check()
  await page.getByRole('button', { name: 'Confirm company context' }).click()

  await expect(page.getByText('context complete')).toBeVisible()
  const body = await (await request.get('/company/context', { headers: { Authorization: auth } })).json()
  expect(body.status).toBe('context_complete')
  expect(body.marketing_stage).toBe('starting_from_zero')
  expect(body.next_stage).toBe('market_validation')
  const context = body.context
  expect(context.company.name).toBe('Example Studio')
  expect(context.company.website).toBe('https://studio.test')
  expect(context.product.name).toBe('Managed Operations Desk')
  expect(context.customer.ideal_customer).toBe('Logistics teams running dispatch on spreadsheets')
  expect(context.market.problem).toBe('Missed loads are found a week late')
  expect(context.market.market).toBe('United States')
  expect(context.evidence.testimonials).toEqual(['Operations Director: handoffs stopped falling through'])
  expect(context.offer.pricing).toBe('$4,000 setup plus $1,500 per month')
  expect(context.objective.primary_goal).toBe('Get the first ten paying customers')
  expect(context.state.marketing_stage).toBe('starting_from_zero')
  expect(context.resources.channels).toEqual([]) // never answered, never invented
  expect(context.constraints.operational).toEqual([])

  // The context survives a reload, and a founder can correct it afterwards.
  await page.reload()
  await page.getByLabel('Username').fill('founder')
  await page.getByLabel('Password').fill('browser-secret')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByText('context complete')).toBeVisible()

  const replaced = await request.put('/company/context', {
    headers: { Authorization: auth, 'X-Founder-Action-Token': 'browser-action', 'Content-Type': 'application/json' },
    data: { product: { name: 'Managed Operations Desk' }, state: { marketing_stage: 'Starting from zero' } },
  })
  expect(replaced.status()).toBe(200)
  const partial = await replaced.json()
  expect(partial.status).toBe('context_incomplete')
  expect(partial.context.missing).toContain('company')
  expect(partial.next_stage).toBe('market_validation') // state, not a claim about completeness

  // The dashboard shows the state AutoEvolve resolved, and starts nothing.
  await page.getByRole('main').getByRole('link', { name: 'Home' }).click()
  await expect(page.getByRole('heading', { name: 'Home' })).toBeVisible()
  await expect(page.locator('.home-stage').getByText('Market Validation')).toBeVisible()
  await expect(page.locator('.home-stage')).toContainText('market-validation experiment')
  const workflows = await request.get('/company/workflows', { headers: { Authorization: auth } })
  expect((await workflows.json()).length).toBe(0)
})