import { test, expect } from '@playwright/test';

// All API/camera traffic is mocked; these tests never change the live gate.
test.use({ baseURL: 'http://localhost:5186' });

const gates = [{ id: 'main', name: 'Cổng Chính' }, { id: 'secondary', name: 'Cổng Phụ' }];
const initial = (gate = 'main') => ({
  gate_id: gate, name: gates.find(g => g.id === gate).name,
  current: gate === 'main' ? '0' : '2', current_preset_id: gate === 'main' ? 'preset-0' : null,
  pending: '', state: 'idle', error: null,
  presets: [{ id: 'preset-0', label: 'Webcam laptop', source: '0' }, { id: 'preset-1', label: 'OBS Virtual Camera', source: '1' }],
  health: { camera_open: true, running: true, thread_alive: true, last_frame_age_sec: 0.2 },
});

async function setup(page, { fail = false, loadFail = false } = {}) {
  let camera = initial();
  let submitted = false;
  let polls = 0;
  const posts = [];
  await page.route(
    /^(?!https?:\/\/[^/]+\/src\/)(?:https?:\/\/[^/]+)?\/(api|guard|media)\//,
    async route => {
    const path = new URL(route.request().url()).pathname;
    let body = [];
    if (path === '/api/auth/login') body = { access_token: 'camera-test-token', username: 'admin', role: 'admin' };
    if (path === '/api/system/health') body = { gates };
    if (path === '/api/stats/summary') body = {};
    if (path === '/api/camera') body = { gates };
    if (path.startsWith('/guard/')) return route.fulfill({ status: 200, contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#123b6d"/></svg>' });
    if (path.startsWith('/api/camera/')) {
      if (loadFail) return route.fulfill({ status: 503, json: { detail: 'Không tải được nguồn camera' } });
      if (route.request().method() === 'POST') {
        posts.push(route.request().postDataJSON());
        submitted = true;
        camera = { ...camera, state: 'checking', pending: '1' };
        return route.fulfill({ status: 202, json: camera });
      }
      if (submitted && ++polls >= 2) camera = fail
        ? { ...camera, state: 'error', pending: '', error: 'Không đọc được camera mới. Nguồn cũ được giữ nguyên.' }
        : { ...camera, state: 'applied', pending: '', current: '1', current_preset_id: 'preset-1' };
      body = path.endsWith('/secondary') ? initial('secondary') : camera;
    }
    return route.fulfill({ json: body });
  });
  await page.goto('/login');
  await page.locator('#username').fill('admin');
  await page.locator('#password').fill('test-only-password');
  await page.locator('button[type="submit"]').click();
  // Đợi token + user đã commit vào AuthContext (RequireRole ở route đích
  // có thể re-render với user=null nếu setUser chưa propagate).
  await page.waitForFunction(
    () => !!localStorage.getItem('token') && !!localStorage.getItem('user'),
    { timeout: 10000 },
  );
  await expect(page).not.toHaveURL(/\/login/);
  await page.goto('/admin/camera');
  return posts;
}

test('waits for verified frames before showing success', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const posts = await setup(page);
  await page.getByLabel('Nguồn camera').selectOption('preset-1');
  await page.getByRole('button', { name: 'Kiểm tra và áp dụng' }).click();
  await expect(page.getByRole('status')).toContainText('Đang kiểm tra');
  await expect(page.getByLabel('Cổng camera')).toBeDisabled();
  await expect(page.getByRole('status')).toContainText('Đã áp dụng', { timeout: 10000 });
  expect(posts).toEqual([{ preset_id: 'preset-1' }]);
  await expect(page.getByTestId('current-source')).toHaveText('1');
  expect(errors).toEqual([]);
  await page.screenshot({ path: test.info().outputPath('camera-preview.png'), fullPage: true });
});

test('failed source keeps current source and permits retry', async ({ page }) => {
  await setup(page, { fail: true });
  await page.getByLabel('Nguồn camera').selectOption('preset-1');
  await page.getByRole('button', { name: 'Kiểm tra và áp dụng' }).click();
  await expect(page.getByRole('alert')).toContainText('Nguồn cũ được giữ nguyên', { timeout: 10000 });
  await expect(page.getByTestId('current-source')).toHaveText('0');
  await expect(page.getByRole('button', { name: 'Kiểm tra và áp dụng' })).toBeEnabled();
});

test('gate selection reloads its own source, including webcam zero', async ({ page }) => {
  await setup(page);
  await expect(page.getByTestId('current-source')).toHaveText('0');
  await page.getByLabel('Cổng camera').selectOption('secondary');
  await expect(page.getByTestId('current-source')).toHaveText('2');
  await page.getByLabel('Cổng camera').selectOption('main');
  await expect(page.getByTestId('current-source')).toHaveText('0');
});

test('camera load failure is visible and cannot be submitted', async ({ page }) => {
  await setup(page, { loadFail: true });
  await expect(page.getByRole('alert')).toContainText('Không tải được nguồn camera');
  await expect(page.getByRole('button', { name: 'Kiểm tra và áp dụng' })).toHaveCount(0);
});
