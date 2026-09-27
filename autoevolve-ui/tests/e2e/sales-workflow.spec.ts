import { expect, test, type Page } from '@playwright/test'

const auth = `Basic ${btoa('founder:browser-secret')}`

async function signIn(page: Page, path: string, heading: string) {
  await page.goto(path)
  await page.getByLabel('Username').fill('founder')
  await page.getByLabel('Password').fill('browser-secret')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
}

test('Replies and Meetings show persisted records in the shared visual system', async ({ page, request }) => {
  await page.clock.setFixedTime(new Date('2026-09-25T12:00:00Z'))
  await signIn(page, '/replies', 'Replies')
  await expect(page.getByRole('row', { name: /Rift Dynamics/ })).toBeVisible()
  await page.getByRole('row', { name: /Rift Dynamics/ }).click()
  await expect(page.getByRole('complementary', { name: 'Reply details' })).toContainText('Could you share the next step')
  await page.screenshot({ path: '/tmp/autoevolve-replies.png', fullPage: true })
  await expect(page).toHaveScreenshot('replies-workflow.png', { fullPage: true })
  await page.getByLabel('Main navigation').getByRole('link', { name: 'Meetings' }).click()
  await expect(page.getByRole('row', { name: /Rift Dynamics/ })).toBeVisible()
  await page.getByRole('row', { name: /Rift Dynamics/ }).click()
  await expect(page.getByRole('complementary', { name: 'Meeting details' })).toContainText('Manual meeting marker')
  await page.screenshot({ path: '/tmp/autoevolve-meetings.png', fullPage: true })
  await expect(page).toHaveScreenshot('meetings-workflow.png', { fullPage: true })
  for (const path of ['/company/ui/replies', '/company/ui/meetings']) {
    const response = await request.get(path, { headers: { Authorization: auth } })
    expect(response.status(), path).toBe(200)
    expect((await response.json()).items.length).toBeGreaterThan(0)
  }
})

test('reply draft respects the founder token and refreshes from the backend', async ({ page, request }) => {
  await signIn(page, '/replies', 'Replies')
  await page.getByRole('row', { name: /Rift Dynamics/ }).click()
  const drawer = page.getByRole('complementary', { name: 'Reply details' })
  await drawer.getByLabel('Founder action token').fill('wrong')
  await drawer.getByRole('button', { name: 'Draft reply' }).click()
  await expect(drawer.getByRole('alert')).toContainText('not authorized')
  await drawer.getByLabel('Founder action token').fill('browser-action')
  await drawer.getByRole('button', { name: 'Draft reply' }).click()
  await expect(drawer.getByRole('status')).toContainText('Reply draft saved by the backend')
  const href = await drawer.getByRole('link', { name: /Review it in Outreach/ }).getAttribute('href')
  const id = new URL(href!, 'http://localhost').searchParams.get('draft')
  const response = await request.get(`/company/ui/outreach/${id}`, { headers: { Authorization: auth } })
  expect(response.status()).toBe(200)
  expect((await response.json()).kind).toBe('reply')
})

test('record meeting saves a marker only after backend confirmation', async ({ page, request }) => {
  await signIn(page, '/meetings', 'Meetings')
  await page.getByRole('button', { name: 'Record meeting' }).click()
  const dialog = page.getByRole('dialog', { name: 'Record meeting' })
  await dialog.getByLabel('Find contact').fill('Sophia')
  await dialog.getByRole('combobox').selectOption({ label: 'Sophia Martinez · TerraBuild' })
  await dialog.getByLabel('Recorded date and time').fill('2026-10-03T10:00')
  await dialog.getByLabel('Note (optional)').fill('Review the saved reply.')
  await dialog.getByLabel('Founder action token').fill('wrong')
  await dialog.getByRole('button', { name: 'Save meeting marker' }).click()
  await expect(dialog.getByRole('alert')).toContainText('not authorized')
  await dialog.getByLabel('Founder action token').fill('browser-action')
  await dialog.getByRole('button', { name: 'Save meeting marker' }).click()
  await expect(page.getByRole('status')).toContainText('Manual meeting marker saved by the backend')
  const drawer = page.getByRole('complementary', { name: 'Meeting details' })
  await expect(drawer).toContainText('TerraBuild')
  await expect(drawer).toContainText('Review the saved reply.')
  const id = new URL(page.url()).searchParams.get('meeting')
  const response = await request.get(`/company/ui/meetings/${id}`, { headers: { Authorization: auth } })
  expect(response.status()).toBe(200)
  expect((await response.json()).status).toBe('scheduled')
})

test('read failures remain distinct from empty data and 401 returns to sign-in', async ({ page }) => {
  await signIn(page, '/replies', 'Replies')
  await page.route('**/company/ui/replies?*', route => route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'fixture failure' }) }))
  await page.getByPlaceholder('Search replies…').fill('failure')
  await expect(page.getByRole('heading', { name: 'Replies could not be loaded' })).toBeVisible()
  await expect(page.getByText('No replies found')).not.toBeVisible()
  await page.unroute('**/company/ui/replies?*')
  await page.route('**/company/ui/replies?*', route => route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Unauthorized' }) }))
  await page.getByPlaceholder('Search replies…').fill('session')
  await expect(page.getByLabel('Username')).toBeVisible()
})
