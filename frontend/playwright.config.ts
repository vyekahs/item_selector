import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for the itemSelector frontend.
 *
 * Strategy
 * --------
 * - We don't depend on the real FastAPI backend at E2E time. Every
 *   test intercepts outgoing API calls via `page.route()` and returns
 *   fixed JSON, so the runner stays deterministic and can execute in
 *   CI without Postgres/Redis.
 * - The frontend is served by Next.js (`pnpm dev` or the production
 *   build via `pnpm start`). The `webServer` block below boots it
 *   automatically and reuses an already-running server in local dev.
 * - `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` ensures the
 *   frontend issues requests to an absolute URL we can match inside
 *   `page.route()` (the default `/api` works through nginx only).
 */
export default defineConfig({
  testDir: './e2e/tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [['github'], ['list']] : [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3100',
    trace: 'on-first-retry',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    // `pnpm dev` is reliable even without a production build; port 3100
    // keeps E2E runs from colliding with a local `pnpm dev` on 3000.
    command: 'pnpm exec next dev -p 3100',
    url: process.env.E2E_BASE_URL ?? 'http://localhost:3100',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_API_BASE_URL: 'http://localhost:8000',
      NEXT_TELEMETRY_DISABLED: '1',
    },
  },
});
