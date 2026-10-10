import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e', testMatch: 'test_task05_navigation.spec.js', workers: 1,
  retries: 0, timeout: 45000,
  outputDir: '../qa_logs/task05_ui/browser_results',
  reporter: [['list'], ['json', { outputFile: '../qa_logs/task05_ui/results.json' }]],
  use: { baseURL: 'http://127.0.0.1:5198', trace: 'off', screenshot: 'only-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    { command: '"../venv/Scripts/python.exe" -B e2e/task05LiveBackend.py', url: 'http://127.0.0.1:8028/openapi.json', reuseExistingServer: false, timeout: 60000 },
    { command: 'node e2e/task05Vite.mjs', url: 'http://127.0.0.1:5198', reuseExistingServer: false, timeout: 30000 },
  ],
});
