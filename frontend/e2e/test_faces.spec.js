import { test, expect } from '@playwright/test';

const ADMIN_USER = 'admin';
const ADMIN_PASS = 'admin123';

async function login(page, username, password) {
  await page.goto('/login', { waitUntil: 'networkidle' });
  await page.fill('#username', username);
  await page.fill('#password', password);
  await page.click('button[type="submit"]');
  await page.waitForResponse(
    resp => resp.url().includes('/api/auth/login') && resp.status() < 500,
    { timeout: 10000 }
  );
  await page.waitForTimeout(500);
}

test.describe('Admin Faces Page', () => {

  test.beforeEach(async ({ page }) => {
    await login(page, ADMIN_USER, ADMIN_PASS);
    await page.goto('/admin/faces', { waitUntil: 'networkidle' });
  });

  test('Navigates to /admin/faces', async ({ page }) => {
    await expect(page).toHaveURL(/\/admin\/faces/, { timeout: 5000 });
  });

  test('Page heading renders', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /Quản lý khuôn mặt/i })).toBeVisible({ timeout: 5000 });
  });

  test('Tab switcher exists (faces + events)', async ({ page }) => {
    await expect(page.getByRole('button', { name: 'Danh sách đã đăng ký' })).toBeVisible({ timeout: 3000 });
    await expect(page.getByRole('button', { name: 'Sự kiện nhận diện' })).toBeVisible({ timeout: 3000 });
  });

  test('Enroll form exists (name, vehicle_id, photo, submit)', async ({ page }) => {
    await expect(page.getByText('Tên người')).toBeVisible({ timeout: 3000 });
    await expect(page.getByText('ID xe')).toBeVisible({ timeout: 3000 });
    await expect(page.getByText('Ảnh khuôn mặt')).toBeVisible({ timeout: 3000 });
    await expect(page.getByRole('button', { name: 'Đăng ký', exact: true })).toBeVisible({ timeout: 3000 });
  });

  test('Switching to Events tab shows events section', async ({ page }) => {
    await page.getByRole('button', { name: 'Sự kiện nhận diện' }).click();
    await page.waitForTimeout(500);
    // Events table (or empty state) should appear
    const hasTable = await page.locator('table').isVisible({ timeout: 3000 }).catch(() => false);
    const hasEmpty = await page.getByText(/chưa có sự kiện/i).isVisible({ timeout: 3000 }).catch(() => false);
    expect(hasTable || hasEmpty).toBe(true);
  });

  test('NavBar shows Khuôn mặt link', async ({ page }) => {
    await login(page, ADMIN_USER, ADMIN_PASS);
    await expect(page.locator('nav')).toBeVisible();
    await expect(page.getByText('Khuôn mặt')).toBeVisible({ timeout: 3000 });
  });

  test('Security role blocked from /admin/faces', async ({ page }) => {
    // Switch to security user
    await page.evaluate(() => localStorage.clear());
    await login(page, 'security', 'security123');
    await page.goto('/admin/faces', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    const atFaces = page.url().includes('/admin/faces');
    expect(atFaces).toBe(false);
  });

});
