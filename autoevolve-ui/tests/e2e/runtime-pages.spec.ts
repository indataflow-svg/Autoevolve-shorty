import { expect, test } from '@playwright/test'

test('every operator route renders with successful API reads and no browser errors', async ({ page }) => {
  const errors: string[] = []
  const failedApi: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  page.on('response', response => {
    if (response.url().includes('/company/') && response.status() >= 400) failedApi.push(`${response.status()} ${response.request().method()} ${new URL(response.url()).pathname}`)
  })
  await page.goto('/onboarding')
  await page.getByLabel('Username').fill('founder')
  await page.getByLabel('Password').fill('browser-secret')
  await page.getByRole('button', { name: 'Sign in' }).click()
  const pages = [
    ['/onboarding', 'First-run setup'], ['/home', 'Home'], ['/contacts', 'Contacts'],
    ['/research', 'Research'], ['/companies', 'Companies'], ['/outreach', 'Outreach'],
    ['/replies', 'Replies'], ['/meetings', 'Meetings'], ['/campaigns', 'Campaigns'],
    ['/content', 'Content'], ['/integrations', 'Integrations'], ['/settings', 'Settings'],
  ] as const
  for (const [path, heading] of pages) {
    if (page.url().endsWith('/onboarding') && path === '/onboarding') {
      await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
      continue
    }
    await page.getByLabel('Main navigation').locator(`a[href="${path}"]`).click()
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
  }
  expect(failedApi).toEqual([])
  expect(errors).toEqual([])
})
