import { test, expect } from '@playwright/test';

const ADMIN_USER = 'admin';
const ADMIN_PASS = 'admin123';
const SECURITY_USER = 'security';
const SECURITY_PASS = 'security123';

async function login(page, username, password) {
  const resp = await page.request.post('http://localhost:8000/api/auth/login', {
    data: { username, password },
    headers: { 'Content-Type': 'application/json' },
  });
  if (resp.status() !== 200) throw new Error('Login failed');
  const body = await resp.json();
  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await page.evaluate(({ token, user }) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));
  }, { token: body.access_token, user: { username: body.username, role: body.role } });
}

test.describe('Admin Vehicles Page', () => {

  test.beforeEach(async ({ page }) => {
    await login(page, ADMIN_USER, ADMIN_PASS);
    await page.goto('/admin/vehicles', { waitUntil: 'domcontentloaded' });
  });

  test('Navigates to /admin/vehicles', async ({ page }) => {
    await expect(page).toHaveURL(/\/admin\/vehicles/, { timeout: 5000 });
  });

  test('Vehicles table exists', async ({ page }) => {
    await expect(page.locator('table')).toBeVisible({ timeout: 5000 });
  });

  test('Add vehicle form exists', async ({ page }) => {
    await expect(page.locator('form')).toBeVisible({ timeout: 3000 });
  });

  test('CSV import section exists', async ({ page }) => {
    await expect(page.getByText('Nhập danh sách từ CSV')).toBeVisible({ timeout: 3000 });
  });

  test('Security role blocked from /admin/vehicles', async ({ page }) => {
    // Switch to security user
    await page.evaluate(() => localStorage.clear());
    await login(page, SECURITY_USER, SECURITY_PASS);
    await page.goto('/admin/vehicles', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(500);
    // Should redirect away
    const atVehicles = page.url().includes('/admin/vehicles');
    expect(atVehicles).toBe(false);
  });

});

test.describe('Admin Violations Page', () => {

  test.beforeEach(async ({ page }) => {
    await login(page, ADMIN_USER, ADMIN_PASS);
    await page.goto('/admin/violations', { waitUntil: 'domcontentloaded' });
  });

  test('Navigates to /admin/violations', async ({ page }) => {
    await expect(page).toHaveURL(/\/admin\/violations/, { timeout: 5000 });
  });

  test('Violations table exists', async ({ page }) => {
    await expect(page.locator('table')).toBeVisible({ timeout: 5000 });
  });

  test('Filter form exists', async ({ page }) => {
    await expect(page.locator('input[placeholder*="biển số"]')).toBeVisible({ timeout: 3000 });
  });

});

test.describe('Admin Health Page', () => {

  test.beforeEach(async ({ page }) => {
    await login(page, ADMIN_USER, ADMIN_PASS);
    await page.goto('/admin/health', { waitUntil: 'domcontentloaded' });
  });

  test('Navigates to /admin/health', async ({ page }) => {
    await expect(page).toHaveURL(/\/admin\/health/, { timeout: 5000 });
  });

  test('Pipeline status section renders', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Pipeline' })).toBeVisible({ timeout: 5000 });
  });

  test('Storage section renders', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Lưu trữ', exact: true })).toBeVisible({ timeout: 3000 });
  });

  test('NavBar shows Hệ thống link', async ({ page }) => {
    await login(page, ADMIN_USER, ADMIN_PASS);
    await page.goto('/admin/health', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('nav')).toBeVisible();
    await expect(page.getByText('Hệ thống')).toBeVisible({ timeout: 3000 });
  });

});
