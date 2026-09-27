import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  testIgnore: ['workflows.spec.ts', 'sales-workflow.spec.ts', 'onboarding.spec.ts'],
  timeout: 45_000,
  expect: { timeout: 10_000, toHaveScreenshot: { animations: 'disabled', maxDiffPixelRatio: 0.01 } },
  use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:8788', viewport: { width: 1536, height: 864 }, trace: 'retain-on-failure' },
  webServer: {
    command: '../.venv/bin/python ../tests/contacts_fixture_server.py',
    url: 'http://127.0.0.1:8788/contacts',
    reuseExistingServer: false,
    timeout: 180_000,
  },
})
