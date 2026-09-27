import { test, expect } from '@playwright/test';

const ADMIN_USER = 'admin';
const ADMIN_PASS = 'admin123';
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

test.describe('Admin Vehicles Page', () => {

  test.beforeEach(async ({ page }) => {
    await login(page, ADMIN_USER, ADMIN_PASS);
    await page.goto('/admin/vehicles', { waitUntil: 'networkidle' });
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
    await page.goto('/admin/vehicles', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    // Should redirect away
    const atVehicles = page.url().includes('/admin/vehicles');
    expect(atVehicles).toBe(false);
  });

});

test.describe('Admin Violations Page', () => {

  test.beforeEach(async ({ page }) => {
    await login(page, ADMIN_USER, ADMIN_PASS);
    await page.goto('/admin/violations', { waitUntil: 'networkidle' });
  });

  test('Navigates to /admin/violations', async ({ page }) => {
    await expect(page).toHaveURL(/\/admin\/violations/, { timeout: 5000 });
  });

  test('Violations table exists', async ({ page }) => {
    await expect(page.locator('table')).toBeVisible({ timeout: 5000 });
  });

  test('Filter form exists', async ({ page }) => {
    await expect(page.locator('form').first()).toBeVisible({ timeout: 3000 });
  });

});

test.describe('Admin Health Page', () => {

  test.beforeEach(async ({ page }) => {
    await login(page, ADMIN_USER, ADMIN_PASS);
    await page.goto('/admin/health', { waitUntil: 'networkidle' });
  });

  test('Navigates to /admin/health', async ({ page }) => {
    await expect(page).toHaveURL(/\/admin\/health/, { timeout: 5000 });
  });

  test('Pipeline status section renders', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Pipeline' })).toBeVisible({ timeout: 5000 });
  });

  test('Storage section renders', async ({ page }) => {
    await expect(page.getByText('Lưu trữ')).toBeVisible({ timeout: 3000 });
  });

  test('NavBar shows Hệ thống link', async ({ page }) => {
    await login(page, ADMIN_USER, ADMIN_PASS);
    await expect(page.locator('nav')).toBeVisible();
    await expect(page.getByText('Hệ thống')).toBeVisible({ timeout: 3000 });
  });

});
