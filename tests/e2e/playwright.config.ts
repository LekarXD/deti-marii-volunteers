import {defineConfig, devices} from '@playwright/test';

const baseURL = process.env.OPORA_G1_WEB_URL || 'http://127.0.0.1:5174';
if (!['localhost', '127.0.0.1', '[::1]'].includes(new URL(baseURL).hostname)) {
  throw new Error('G1 browser acceptance only targets disposable localhost');
}

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 45_000,
  expect: {timeout: 10_000},
  reporter: [['list']],
  use: {baseURL, ...devices['Desktop Chrome'], trace: 'off', screenshot: 'off', video: 'off'},
  projects: [{name: 'chromium'}],
});
