import { test, expect } from '@playwright/test';

test('login, review data and training CRUD use the real backend through Vite', async ({ page }) => {
  const failures = [];
  page.on('pageerror', error => failures.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') failures.push(message.text());
  });
  await page.goto('/login');
  await page.locator('#username').fill('ocr_admin');
  await page.locator('#password').fill('ocr-test-password');
  const login = page.waitForResponse(response => response.url().endsWith('/api/auth/login'));
  await page.locator('button[type="submit"]').click();
  expect((await login).status()).toBe(200);
  await expect(page).toHaveURL(/\/admin\/vehicles$/);
  await page.reload();
  await expect(page).toHaveURL(/\/admin\/vehicles$/);
  const reviews = await page.request.get('/api/training/recognition-reviews');
  expect(reviews.status()).toBe(200);
  expect((await reviews.json()).items[0].review_id).toBe('ocr-browser-review');
  await page.goto('/admin/training/datasets');
  await expect(page.getByRole('cell', { name: 'ocr_live_seed', exact: true })).toBeVisible();
  const datasetName = 'ocr_live_' + Date.now();
  page.once('dialog', dialog => dialog.accept(datasetName));
  const create = page.waitForResponse(response => response.url().endsWith('/api/training/datasets') && response.request().method() === 'POST');
  await page.getByTestId('create-dataset').click();
  const created = await create;
  expect(created.status()).toBe(200);
  const { dataset_id: draftId } = await created.json();
  const add = await page.request.post(`/api/training/datasets/${draftId}/samples`, {
    data: { samples: [{
      target_id: 'bbox-browser-target', review_id: 'ocr-browser-review', gate_id: 'main',
      label: { verdict: 'correct', target_text: '89F123792' },
      source: { gate_id: 'main', camera_id: 'front', crop_url: '/media/plate.jpg' },
      bbox: [0.1, 0.1, 0.9, 0.9], version: 0,
    }] },
  });
  expect(add.status()).toBe(200);
  await expect(page.getByRole('cell', { name: datasetName, exact: true })).toBeVisible();
  const seed = page.getByRole('row').filter({ has: page.getByRole('cell', { name: 'ocr_live_seed', exact: true }) });
  await seed.getByRole('button', { name: /samples|xem/i }).click();
  await page.getByRole('tab', { name: 'Split 70/15/15', exact: true }).click();
  await expect(page.getByText('89F123792', { exact: true })).toBeVisible();
  await page.goto('/admin/training/jobs');
  await page.getByTestId('dataset-select').selectOption({ label: 'ocr_live_seed (plate_ocr)' });
  const createJob = page.waitForResponse(response => response.url().endsWith('/api/training/jobs') && response.request().method() === 'POST');
  await page.getByTestId('submit-job').click();
  expect((await createJob).status()).toBe(200);
  await expect(page.getByTestId('jobs-table').getByText('queued', { exact: true })).toBeVisible();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await expect(page.getByTestId('jobs-table').getByText('cancelled', { exact: true })).toBeVisible();
  await page.goto('/admin/training/candidates');
  await expect(page.getByRole('heading', { name: /candidate/i })).toBeVisible();
  await expect(page.getByTestId('candidates-table').getByRole('cell', { name: 'QA baseline', exact: true })).toBeVisible();
  await page.screenshot({ path: '../qa_logs/ocr_browser/candidates-ui.png', fullPage: true });
  await page.goto('/admin/training/bbox');
  await expect(page.getByRole('heading', { name: /bbox|biên tập/i }).first()).toBeVisible();
  await page.getByTestId('dataset-id-input').fill(draftId);
  await page.getByTestId('reload-samples').click();
  await expect(page.getByTestId('bbox-editor-row')).toHaveCount(1);
  await expect(page.getByTestId('bbox-overlay')).toBeVisible();
  await page.getByRole('img', { name: 'BBox editor canvas', exact: true }).press('ArrowRight');
  await expect(page.getByTestId('bbox-coords')).toHaveText('[0.105, 0.100, 0.905, 0.900]');
  const save = page.waitForResponse(response => response.request().method() === 'PATCH' && response.url().endsWith('/samples/bbox-browser-target/bbox'));
  await page.getByRole('button', { name: 'Lưu bbox', exact: true }).click();
  const saved = await save;
  expect(saved.status()).toBe(200);
  expect((await saved.json()).version).toBe(1);
  await page.getByTestId('reload-samples').click();
  await expect(page.getByTestId('bbox-coords')).toHaveText('[0.105, 0.100, 0.905, 0.900]');
  await page.screenshot({ path: '../qa_logs/ocr_browser/training-ui.png', fullPage: true });
  expect(failures).toEqual([]);
});
