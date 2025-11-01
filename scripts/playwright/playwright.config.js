import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for Open Notebook automation
 * @see https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: 'html',

  use: {
    baseURL: 'http://localhost:3006',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Run dev server if not already running
  webServer: {
    command: 'cd ../../ && make start-sqlite',
    url: 'http://localhost:5055/health',
    reuseExistingServer: true,
    timeout: 120000,
  },
});
