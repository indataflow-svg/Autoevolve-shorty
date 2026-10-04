import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: 'market-validation.spec.ts',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  workers: 1,
  use: { ...devices['Desktop Chrome'], baseURL: 'http://127.0.0.1:8792', viewport: { width: 1536, height: 900 }, trace: 'retain-on-failure' },
  webServer: {
    command: '../.venv/bin/python ../tests/validation_fixture_server.py',
    url: 'http://127.0.0.1:8792/health',
    reuseExistingServer: false,
    timeout: 180_000,
  },
})