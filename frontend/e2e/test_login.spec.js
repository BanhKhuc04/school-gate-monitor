import { test, expect } from '@playwright/test';

const ADMIN_USER = 'admin';
const ADMIN_PASS = 'admin123';
const SECURITY_USER = 'security';
const SECURITY_PASS = 'security123';
const MANAGEMENT_USER = 'management';
const MANAGEMENT_PASS = 'management123';

async function login(page, username, password) {
  await page.goto('/login', { waitUntil: 'networkidle' });
  await page.fill('#username', username);
  await page.fill('#password', password);
  await page.click('button[type="submit"]');
  // Wait for the API response (login can succeed or fail)
  await page.waitForResponse(resp => resp.url().includes('/api/auth/login') && resp.status() < 500, { timeout: 10000 });
  // Small settle time for React to update
  await page.waitForTimeout(500);
}

test.describe('Login', () => {

  test('Login page renders with all elements', async ({ page }) => {
    await page.goto('/login', { waitUntil: 'networkidle' });
    await expect(page.locator('#username')).toBeVisible();
    await expect(page.locator('#password')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('Wrong password shows error message', async ({ page }) => {
    await page.goto('/login', { waitUntil: 'networkidle' });
    await page.fill('#username', ADMIN_USER);
    await page.fill('#password', 'wrongpassword');
    await page.click('button[type="submit"]');
    // Wait for error to appear (the API returns 401 and React sets error state)
    await page.waitForSelector('.bg-red-50, [class*="error"]', { timeout: 8000 }).catch(() => {});
    const errorVisible = await page.locator('.bg-red-50, [class*="error"]').first().isVisible().catch(() => false);
    expect(errorVisible).toBe(true);
    // Should still be on login page
    await expect(page).toHaveURL(/\/login/);
  });

  test('Admin login stores token in localStorage', async ({ page }) => {
    await login(page, ADMIN_USER, ADMIN_PASS);
    const token = await page.evaluate(() => localStorage.getItem('token'));
    expect(token).toBeTruthy();
    expect(token.length).toBeGreaterThan(20);
  });

  test('Admin login navigates away from /login', async ({ page }) => {
    await login(page, ADMIN_USER, ADMIN_PASS);
    // Admin redirects to /dashboard or /admin/... but not /login
    await expect(page).not.toHaveURL(/\/login/, { timeout: 5000 });
  });

  test('Security login redirects to /guard', async ({ page }) => {
    await login(page, SECURITY_USER, SECURITY_PASS);
    await expect(page).toHaveURL(/\/guard/, { timeout: 5000 });
  });

  test('Management blocked from /guard route', async ({ page }) => {
    await login(page, MANAGEMENT_USER, MANAGEMENT_PASS);
    // Management should NOT end up at /guard
    await page.waitForTimeout(500);
    const atGuard = page.url().includes('/guard');
    expect(atGuard).toBe(false);
  });

  test('NavBar renders after admin login', async ({ page }) => {
    await login(page, ADMIN_USER, ADMIN_PASS);
    await expect(page.locator('nav')).toBeVisible({ timeout: 5000 });
  });

});
