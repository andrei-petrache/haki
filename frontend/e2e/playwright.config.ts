import { defineConfig, devices } from '@playwright/test'

// Run through scripts/e2e.sh, inside the Playwright container on a throwaway
// Compose stack; it sets E2E_BASE_URL and E2E_OUT.
const out = process.env.E2E_OUT ?? '/tmp/haki-e2e'

export default defineConfig({
  testDir: '.',
  // Not *.test.ts or *.spec.ts: Vitest would pick those up too
  testMatch: '*.e2e.ts',
  outputDir: `${out}/test-results`,
  // One account, one browser, in order: login and signup are rate limited
  workers: 1,
  fullyParallel: false,
  retries: 0,
  forbidOnly: true,
  reporter: 'list',
  timeout: 60_000,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://frontend:8080',
    // Fixed, so the app picks English; one file checks Romanian on its own
    locale: 'en-US',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
