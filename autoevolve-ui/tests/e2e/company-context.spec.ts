import { expect, test } from '@playwright/test'

const auth = `Basic ${btoa('founder:browser-secret')}`

// The four cards write the same canonical context the rest of the app reads.
test('a new user completes Get Started and the canonical context is stored', async ({ page, request }) => {
  await page.goto('/onboarding')
  await page.getByLabel('Username').fill('founder')
  await page.getByLabel('Password').fill('browser-secret')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByLabel('Founder action token').fill('browser-action')

  await expect(page.getByRole('heading', { name: 'Set the company context.' })).toBeVisible()
  await page.getByLabel(/Company name/).fill('Example Studio')
  await page.getByLabel(/Website/).fill('https://studio.test')
  await page.getByLabel(/What does your company do/).fill('Example Studio builds operations tools for growing teams.')
  await page.getByRole('button', { name: 'Next' }).click()

  await page.getByLabel(/Product or offer name/).fill('Operations audit')
  await page.getByLabel(/What does the offer do/).fill('A guided audit that finds and fixes manual handoffs.')
  await page.getByRole('button', { name: 'Next' }).click()

  await page.getByLabel(/Who is your ideal customer/).fill('Operations managers at 20–200 person logistics firms.')
  await page.getByLabel(/What problem do they pay/).fill('Handoffs are manual and loads are found late.')
  await page.getByRole('button', { name: 'Next' }).click()

  await page.getByLabel(/What should this workspace prove first/).fill('Book five qualified discovery calls in two weeks.')
  await page.getByRole('button', { name: 'Finish setup' }).click()

  await expect(page.getByRole('heading', { name: /is ready\./ })).toBeVisible()
  const body = await (await request.get('/company/context', { headers: { Authorization: auth } })).json()
  expect(body.status).toBe('context_complete')
  expect(body.marketing_stage).toBe('starting_from_zero')
  expect(body.next_stage).toBe('market_validation')
  expect(body.context.completeness_percent).toBe(100)
  const context = body.context
  expect(context.company.name).toBe('Example Studio')
  expect(context.company.website).toBe('https://studio.test')
  expect(context.product.name).toBe('Operations audit')
  expect(context.customer.ideal_customer).toBe('Operations managers at 20–200 person logistics firms.')
  expect(context.market.problem).toBe('Handoffs are manual and loads are found late.')
  expect(context.objective.primary_goal).toBe('Book five qualified discovery calls in two weeks.')
  expect(context.state.marketing_stage).toBe('starting_from_zero')

  // Reload keeps the completed context and the handoff state.
  await page.reload()
  await page.getByLabel('Username').fill('founder')
  await page.getByLabel('Password').fill('browser-secret')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: /is ready\./ })).toBeVisible()

  // The API remains the source of truth; a partial replacement is explicit.
  const replaced = await request.put('/company/context', {
    headers: { Authorization: auth, 'X-Founder-Action-Token': 'browser-action', 'Content-Type': 'application/json' },
    data: { product: { name: 'Operations audit' }, state: { marketing_stage: 'Starting from zero' } },
  })
  expect(replaced.status()).toBe(200)
  const partial = await replaced.json()
  expect(partial.status).toBe('context_incomplete')
  expect(partial.context.missing).toContain('company')

  const workflows = await request.get('/company/workflows', { headers: { Authorization: auth } })
  expect((await workflows.json()).length).toBe(0)
})
