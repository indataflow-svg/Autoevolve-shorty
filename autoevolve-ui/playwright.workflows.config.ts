import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'workflows.spec.ts',
  timeout: 45_000,
  expect: { timeout: 10_000, toHaveScreenshot: { animations: 'disabled', maxDiffPixelRatio: 0.01 } },
  workers: 1,
  use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:8789', viewport: { width: 1536, height: 864 }, trace: 'retain-on-failure' },
  webServer: {
    command: '../.venv/bin/python ../tests/workflow_fixture_server.py',
    url: 'http://127.0.0.1:8789/home',
    reuseExistingServer: false,
    timeout: 180_000,
  },
})
