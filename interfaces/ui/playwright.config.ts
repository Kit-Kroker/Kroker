import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testMatch: '**/*.pw.ts',
  use: {
    baseURL: 'http://localhost:4173',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run preview --workspace @kroker/ui',
    url: 'http://localhost:4173',
    reuseExistingServer: !process.env.CI,
  },
})
