import { test, expect } from '@playwright/test';

const SECURITY_USER = 'security';
const SECURITY_PASS = 'security123';

async function login(page, username, password) {
  await page.goto('/login', { waitUntil: 'networkidle' });
  await page.fill('#username', username);
  await page.fill('#password', password);
  await page.click('button[type="submit"]');
  await page.waitForResponse(resp => resp.url().includes('/api/auth/login') && resp.status() < 500, { timeout: 10000 });
  await page.waitForTimeout(500);
}

test.describe('Guard Page', () => {

  test.beforeEach(async ({ page }) => {
    await login(page, SECURITY_USER, SECURITY_PASS);
    await page.goto('/guard', { waitUntil: 'networkidle' });
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

    await expect(page.locator('img[alt="Ảnh chụp bằng chứng"]')).toBeVisible({ timeout: 12000 });
  });

});
