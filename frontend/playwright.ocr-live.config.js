import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  testMatch: 'test_ocr_backend_live.spec.js',
  workers: 1,
  timeout: 30000,
  outputDir: '../qa_logs/ocr_browser/results',
  reporter: [['list'], ['json', { outputFile: '../qa_logs/ocr_browser/results.json' }]],
  use: { baseURL: 'http://127.0.0.1:5196', browserName: 'chromium', screenshot: 'only-on-failure' },
  webServer: [
    { command: '..\\venv\\Scripts\\python.exe e2e\\ocrLiveBackend.py', url: 'http://127.0.0.1:8026/openapi.json', timeout: 90000, reuseExistingServer: false },
    { command: 'node node_modules/vite/bin/vite.js --config vite.qa.config.js', url: 'http://127.0.0.1:5196', timeout: 45000, reuseExistingServer: false,
      env: { QA_BACKEND_PORT: '8026', QA_FRONTEND_PORT: '5196' } },
  ],
});
