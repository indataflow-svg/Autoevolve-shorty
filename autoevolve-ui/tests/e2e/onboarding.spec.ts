import { expect, test } from '@playwright/test'


test('first user completes the company context cards and reaches the handoff', async ({ page }) => {
  await page.goto('/onboarding')
  await page.getByLabel('Username').fill('founder')
  await page.getByLabel('Password').fill('browser-secret')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByRole('heading', { name: 'Set the company context.' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Company identity' })).toBeVisible()
  await page.screenshot({ path: '/tmp/autoevolve-get-started-company.png', fullPage: true })
  await expect(page).toHaveScreenshot('onboarding-first-run.png', { fullPage: true })

  await page.getByLabel('Founder action token').fill('browser-action')
  await page.getByLabel(/Company name/).fill('Example Studio')
  await page.getByLabel(/Website/).fill('https://studio.test')
  await page.getByLabel(/What does your company do/).fill('Example Studio builds operations tools for growing teams.')
  await page.getByRole('button', { name: 'Next' }).click()

  await expect(page.getByRole('heading', { name: 'What you sell' })).toBeVisible()
  await page.getByLabel(/Product or offer name/).fill('Operations audit')
  await page.getByLabel(/What does the offer do/).fill('A guided audit that finds and fixes manual handoffs.')
  await page.getByRole('button', { name: 'Back' }).click()
  await expect(page.getByRole('heading', { name: 'Company identity' })).toBeVisible()
  await expect(page.getByLabel(/Company name/)).toHaveValue('Example Studio')
  await page.getByRole('button', { name: 'Next' }).click()
  await page.getByRole('button', { name: 'Next' }).click()

  await expect(page.getByRole('heading', { name: 'Who buys and why' })).toBeVisible()
  await page.getByLabel(/Who is your ideal customer/).fill('Operations managers at 20–200 person logistics firms.')
  await page.getByLabel(/What problem do they pay/).fill('Handoffs are manual and loads are found late.')
  await page.getByRole('button', { name: 'Next' }).click()

  await expect(page.getByRole('heading', { name: 'Your first objective' })).toBeVisible()
  await page.getByLabel(/What should this workspace prove first/).fill('Book five qualified discovery calls in two weeks.')
  await page.getByRole('button', { name: 'Finish setup' }).click()

  await expect(page.getByRole('heading', { name: /is ready\./ })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Your daily loop' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Commercial outreach' })).toBeVisible()
  await expect(page.getByRole('link', { name: /Open Workflows/ })).toBeVisible()
  await expect(page.getByRole('link', { name: /Open Commercial/ })).toBeVisible()

  await page.getByRole('link', { name: /Open Workflows/ }).click()
  await expect(page).toHaveURL(/\/workflows$/)
  await expect(page.getByRole('heading', { name: 'Workflows' })).toBeVisible()
})
