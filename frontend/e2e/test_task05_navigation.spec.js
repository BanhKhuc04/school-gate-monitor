import { test, expect } from '@playwright/test';

async function login(page, role = 'admin') {
  // This fixture starts no camera. Navigation tests stub only preview/WS; API and bbox media remain real.
  await page.routeWebSocket(/\/guard\/ws(?:\?|$)/, () => {});
  const gif = Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7', 'base64');
  await page.route('**/guard/video_feed*', route => route.fulfill({ contentType: 'image/gif', body: gif }));
  await page.goto('/login');
  await page.locator('#username').fill('ui_' + role);
  await page.locator('#password').fill('ui-fixture-password');
  await page.locator('button[type="submit"]').click();
  await expect(page).not.toHaveURL(/\/login$/);
}

async function getDataset(page, name) {
  const response = await page.request.get('/api/training/datasets');
  expect(response.ok()).toBeTruthy();
  return (await response.json()).items.find(d => d.name === name);
}

test('Admin has four main items; reports live under violations; old links redirect', async ({ page }) => {
  await login(page);
  const menu = page.getByRole('navigation', { name: 'Menu chính' });
  await expect(menu.getByRole('link')).toHaveText(['Giám sát', 'Vi phạm', 'Xe đăng ký', 'Cài đặt']);
  await page.goto('/dashboard');
  await expect(page).toHaveURL(/\/admin\/violations\/report$/);
  await expect(page.getByRole('navigation', { name: 'Vi phạm' })).toBeVisible();
  await expect(menu.getByRole('link', { name: 'Vi phạm', exact: true })).toHaveAttribute('aria-current', 'page');
  await page.goto('/admin/camera');
  await expect(page).toHaveURL(/\/settings\/camera$/);
  await expect(page.getByRole('navigation', { name: 'Cài đặt' })).toBeVisible();
});

test('AI is admin-only and baseline/registry status is honest', async ({ page }) => {
  await login(page);
  await page.goto('/settings/ai');
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('AI nâng cao');
  await expect(page.getByText('Nhập model: chưa khả dụng')).toBeVisible();
  await page.goto('/admin/training/jobs');
  await expect(page).toHaveURL(/\/settings\/ai\/jobs$/);
  await expect(page.getByRole('button', { name: 'Đánh giá baseline', exact: true })).toBeVisible();
  await page.goto('/admin/training/candidates');
  await expect(page.getByText('Registry active · chờ xác nhận runtime')).toBeVisible();
  await expect(page.getByText('đang chạy', { exact: true })).toHaveCount(0);
});

test('Selected sample opens bbox with real image and saves a new version', async ({ page }) => {
  await login(page);
  await page.goto('/settings/ai/datasets');
  const row = page.getByRole('row').filter({ hasText: 'UI_draft' });
  await row.getByRole('button', { name: 'Xem', exact: true }).click();
  await page.getByRole('link', { name: 'Xem / Sửa bbox' }).click();
  await expect(page).toHaveURL(/\/settings\/ai\/bbox\?dataset=.*&sample=ui_sample$/);
  await expect(page.getByTestId('dataset-id-input')).toHaveCount(0);
  await expect(page.getByTestId('bbox-editor-row')).toHaveCount(1);
  const image = page.getByRole('img', { name: 'bbox target', exact: true });
  await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate(el => el.naturalWidth)).toBe(200);
  const canvas = page.getByRole('img', { name: 'BBox editor canvas' });
  await canvas.focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByTestId('bbox-coords')).toContainText('0.105');
  await page.keyboard.press('Escape');
  await expect(page.getByTestId('bbox-coords')).toContainText('0.100');
  await page.keyboard.press('ArrowRight');
  await page.getByRole('button', { name: 'Lưu bbox' }).click();
  await expect(page.getByRole('status')).toHaveText('Đã lưu bbox.');
  await expect(page.getByText(/phiên bản 1/)).toBeVisible();
  const dataset = await getDataset(page, 'UI_draft');
  const samples = await (await page.request.get(`/api/training/datasets/${dataset.id}/samples`)).json();
  expect(samples.items[0].bbox[0]).toBe(.105);
});

test('Legacy bbox link keeps selection; frozen sample and missing image block saving', async ({ page }) => {
  await login(page);
  const frozen = await getDataset(page, 'UI_frozen');
  await page.goto('/admin/training/bbox?' + new URLSearchParams({ dataset: frozen.id, sample: 'ui_frozen_sample' }));
  await expect(page).toHaveURL(/\/settings\/ai\/bbox\?dataset=/);
  await expect(page.getByText('Bộ dữ liệu đã đóng băng. Tạo phiên bản mới để sửa nhãn.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Lưu bbox' })).toBeDisabled();
  const draft = await getDataset(page, 'UI_draft');
  // Only image failure is mocked; auth, sample metadata and permissions use the real API.
  await page.route('**/samples/ui_sample/image', route => route.fulfill({ status: 404, json: { detail: 'missing fixture image' } }));
  await page.goto('/settings/ai/bbox?' + new URLSearchParams({ dataset: draft.id, sample: 'ui_sample' }));
  await expect(page.getByText('Không tải được ảnh nguồn. Bổ sung ảnh trước khi sửa bbox.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Lưu bbox' })).toBeDisabled();
});

for (const role of ['management', 'teacher', 'security']) {
  test(`${role}: own routes still work; AI page and API are denied`, async ({ page }) => {
    await login(page, role);
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Cài đặt', exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: 'AI nâng cao', exact: true })).toHaveCount(0);
    await page.goto('/settings/ai');
    await expect(page).not.toHaveURL(/\/settings\/ai$/);
    const response = await page.request.get('/api/training/datasets');
    expect(response.status()).toBe(403);
    if (role !== 'management') expect((await page.request.post('/guard/debug_overlay?enabled=false&gate=main')).status()).toBe(403);
    if (role === 'teacher') {
      await page.goto('/teacher/vehicles');
      await expect(page).toHaveURL(/\/teacher\/vehicles$/);
    }
  });
}

test('Settings and AI work at mobile width without JS errors', async ({ page }, testInfo) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await login(page);
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto('/settings/ai');
  await expect(page.getByRole('heading', { name: 'AI nâng cao', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('ai-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: testInfo.outputPath('ai-desktop.png'), fullPage: true });
  expect(errors).toEqual([]);
});

test('Guard debug overlay reports camera scope and a stopped camera refuses mutation', async ({ page }) => {
  await login(page);
  await page.goto('/guard');
  const toggle = page.getByRole('checkbox', { name: 'Khung AI — Cổng Chính' });
  await expect(toggle).toBeChecked();
  await expect(page.getByText('Áp dụng cho mọi người xem camera này.')).toBeVisible();
  await toggle.click();
  await expect(page.getByRole('alert')).toContainText('camera chưa chạy');
  await expect(toggle).toBeChecked();
  const state = await (await page.request.get('/guard/debug_overlay?gate=main')).json();
  expect(state.scope).toBe('camera');
  expect(state.enabled).toBe(true);
});

