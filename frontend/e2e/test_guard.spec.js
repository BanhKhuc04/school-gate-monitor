import { test, expect } from '@playwright/test';

const SECURITY_USER = 'security';
const SECURITY_PASS = 'security123';

async function login(page, username, password) {
  // Fetch token from Node side (bypassing Playwright browser network issues
  // on Windows with localhost), then inject into browser storage.
  const resp = await fetch('http://localhost:8000/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!resp.ok) throw new Error('Login failed: ' + resp.status);
  const body = await resp.json();
  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await page.evaluate(({ token, user }) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));
  }, { token: body.access_token, user: { username: body.username, role: body.role } });
  await page.goto('/guard', { waitUntil: 'domcontentloaded' });
}

test.describe('Guard Page', () => {

  test.beforeEach(async ({ page }) => {
    await login(page, SECURITY_USER, SECURITY_PASS);
  });

  test('Security login -> /guard', async ({ page }) => {
    await expect(page).toHaveURL(/\/guard/, { timeout: 5000 });
  });

  test('Video feed img exists', async ({ page }) => {
    await expect(page.locator('img[alt="Live camera feed"]')).toBeVisible({ timeout: 5000 });
  });

  test('Video img naturalWidth is defined', async ({ page }) => {
    await page.waitForTimeout(2000);
    const width = await page.evaluate(() => {
      return document.querySelector('img[alt="Live camera feed"]')?.naturalWidth;
    });
    expect(width).toBeDefined();
  });

  test('Alert banner appears after trigger', async ({ page }) => {
    await page.waitForTimeout(1000);
    const result = await page.evaluate(async () => {
      const token = localStorage.getItem('token');
      const resp = await fetch('http://localhost:8000/api/dev/trigger-test-alert', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({ violation_type: 'NO_HELMET', plate_read: 'TESTALERT001' }),
      });
      return { status: resp.status, ok: resp.ok };
    });
    expect(result.ok).toBe(true);
    // Poll for alert banner — it auto-hides after 3s, increase window
    let found = false;
    for (let i = 0; i < 24; i++) {  // 24 * 500ms = 12s window
      await page.waitForTimeout(500);
      const body = await page.textContent('body');
      if (body.includes('CẢNH BÁO') || body.includes('TESTALERT001') || body.includes('NO_HELMET')) {
        found = true;
        break;
      }
    }
    expect(found).toBe(true);
  });

  test('Alert banner shows snapshot thumbnail when snapshot_url is present', async ({ page }) => {
    await page.waitForTimeout(1000);
    const result = await page.evaluate(async () => {
      const token = localStorage.getItem('token');
      const params = new URLSearchParams({
        violation_type: 'NO_HELMET',
        plate_read: 'TESTTHUMB001',
        snapshot_url: '/media/fake_test_snapshot.jpg',
      });
      const resp = await fetch(`http://localhost:8000/api/dev/trigger-test-alert?${params}`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
      });
      return { status: resp.status, ok: resp.ok };
    });
    expect(result.ok).toBe(true);

    await expect(page.locator('img[alt="Ảnh chụp bằng chứng"]').first()).toBeVisible({ timeout: 12000 });
  });

});
