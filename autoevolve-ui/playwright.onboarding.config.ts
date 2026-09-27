import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'onboarding.spec.ts',
  timeout: 90_000,
  expect: { timeout: 15_000, toHaveScreenshot: { animations: 'disabled', maxDiffPixels: 200 } },
  workers: 1,
  use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:8791', viewport: { width: 1536, height: 864 }, trace: 'retain-on-failure' },
  webServer: {
    command: '../.venv/bin/python ../tests/onboarding_fixture_server.py',
    url: 'http://127.0.0.1:8791/health',
    reuseExistingServer: false,
    timeout: 180_000,
  },
})
