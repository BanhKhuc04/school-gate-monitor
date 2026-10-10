// Task 3 E2E tests — full feedback + training loop.
//
// Pattern: isolated frontend, mock backend qua Playwright route. Tests cover
// client-side rendering cho DatasetManager, TrainingJobs, CandidateCompare
// pages, và BBoxEditor component. KHÔNG đụng backend thật, camera, hay
// training GPU.
//
// Routes cần có trong fixture:
//   /api/training/datasets          GET  list datasets
//   /api/training/datasets          POST create
//   /api/training/datasets/{id}     GET  detail
//   /api/training/datasets/{id}/samples POST add samples
//   /api/training/datasets/{id}/freeze  POST freeze
//   /api/training/datasets/{id}/splits/check POST check leakage
//   /api/training/jobs              GET  list jobs
//   /api/training/jobs              POST create job
//   /api/training/jobs/{id}         GET  detail
//   /api/training/jobs/{id}/cancel  POST cancel
//   /api/training/candidates        GET  list candidates
//   /api/training/candidates/{id}   GET  detail
//   /api/training/candidates/{id}/promote POST promote
//   /api/training/candidates/{id}/rollback POST rollback
//   /api/training/export/{id}       GET  ZIP
//   /api/training/import/preview    POST preview ZIP
//   /api/training/import/apply      POST apply ZIP

import {test, expect} from '@playwright/test';
import {installApiFixture, loginFixture} from './isolatedFixture.js';

test.use({baseURL: 'http://127.0.0.1:5186'});

const ADMIN_USER = 'admin';
const SECURITY_USER = 'security';
const ADMIN_PASS = 'fixture-password';

const DATASETS = [
  {
    dataset_id: 'dsv_test_plate_v1',
    name: 'plate_v1',
    engine: 'plate_ocr',
    state: 'frozen',
    sample_count: 120,
    source_hash: 'a'.repeat(64),
    created_at: '2026-10-01T08:00:00Z',
    created_by: 'admin',
    frozen_at: '2026-10-01T09:00:00Z',
  },
  {
    dataset_id: 'dsv_test_helmet_v1',
    name: 'helmet_v1',
    engine: 'helmet',
    state: 'draft',
    sample_count: 30,
    source_hash: null,
    created_at: '2026-10-02T08:00:00Z',
    created_by: 'admin',
    frozen_at: null,
  },
];

const JOBS = [
  {
    job_id: 'job_test_001',
    dataset_id: 'dsv_test_plate_v1',
    target: 'plate_ocr',
    engine: 'plate_ocr',
    state: 'completed',
    progress: 1,
    candidate_id: 'cnd_test_001',
    created_at: '2026-10-01T10:00:00Z',
    started_at: '2026-10-01T10:01:00Z',
    finished_at: '2026-10-01T10:30:00Z',
    error: null,
  },
  {
    job_id: 'job_test_002',
    dataset_id: 'dsv_test_helmet_v1',
    target: 'helmet',
    engine: 'helmet',
    state: 'training',
    progress: 0.5,
    candidate_id: null,
    created_at: '2026-10-02T11:00:00Z',
    started_at: '2026-10-02T11:01:00Z',
    finished_at: null,
    error: null,
  },
];

const CANDIDATES = [
  {
    candidate_id: 'cnd_test_001',
    job_id: 'job_test_001',
    dataset_id: 'dsv_test_plate_v1',
    target: 'plate_ocr',
    state: 'completed',
    metrics: {exact_match: 80, exact_match_pct: 80.0, total: 100, cer_avg: 0.05},
    baseline_metrics: {exact_match_pct: 70.0, cer_avg: 0.1},
    promoted: false,
    active: false,
    created_at: '2026-10-01T10:30:00Z',
  },
  {
    candidate_id: 'cnd_baseline_plate',
    job_id: null,
    dataset_id: null,
    target: 'plate_ocr',
    state: 'completed',
    metrics: {exact_match_pct: 70.0, cer_avg: 0.1},
    baseline_metrics: null,
    promoted: false,
    active: true,
    created_at: '2026-09-15T08:00:00Z',
  },
];

function installTask3Fixture(page) {
  const gif = Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7', 'base64');

  return page.route(
    /^(?!https?:\/\/[^/]+\/src\/)(https?:\/\/[^/]+)?\/(api|guard|media)\//,
    async route => {
      const req = route.request();
      const url = new URL(req.url());
      const path = url.pathname;
      const method = req.method();

      if (path === '/api/auth/login') {
        const data = req.postDataJSON?.() ?? {};
        if (data.password !== ADMIN_PASS) {
          return route.fulfill({status: 401, json: {detail: 'Sai tên đăng nhập hoặc mật khẩu'}});
        }
        return route.fulfill({
          json: {
            access_token: 'isolated-test-token-over-twenty-characters',
            token_type: 'bearer',
            username: data.username,
            role: data.username,
          },
        });
      }
      if (path === '/api/auth/me') return route.fulfill({json: {username: 'admin', role: 'admin'}});
      if (path === '/api/system/health') return route.fulfill({json: {pipeline: {running: true}, gates: []}});
      if (path === '/api/training/datasets' && method === 'GET') {
        return route.fulfill({json: {items: DATASETS, total: DATASETS.length}});
      }
      if (path === '/api/training/datasets' && method === 'POST') {
        const data = req.postDataJSON?.() ?? {};
        return route.fulfill({
          status: 201,
          json: {
            dataset_id: 'dsv_test_new',
            name: data.name || 'new_dataset',
            engine: data.engine,
            state: 'draft',
            sample_count: 0,
            source_hash: null,
            created_at: new Date().toISOString(),
            created_by: 'admin',
            frozen_at: null,
          },
        });
      }
      const dsMatch = path.match(/^\/api\/training\/datasets\/([^/]+)$/);
      if (dsMatch && method === 'GET') {
        const id = dsMatch[1];
        const found = DATASETS.find(d => d.dataset_id === id);
        if (!found) return route.fulfill({status: 404, json: {detail: 'not found'}});
        return route.fulfill({
          json: {
            ...found,
            samples: Array.from({length: found.sample_count}, (_, i) => ({
              sample_id: `smp_${id}_${i}`,
              source_image: 'fixtures/crop.png',
              bbox: [0.1, 0.1, 0.9, 0.9],
              target_text: i % 3 === 0 ? '89F123456' : i % 3 === 1 ? '59C200000' : '',
              verdict: i % 3 === 2 ? 'unreadable' : 'correct',
              review_id: `r${i}`,
              frame_seq: i,
              gate_id: 'main',
              encounter_id: `e${i}`,
            })),
          },
        });
      }
      if (dsMatch && method === 'DELETE') {
        return route.fulfill({status: 204, body: ''});
      }
      if (/^\/api\/training\/datasets\/[^/]+\/freeze$/.test(path) && method === 'POST') {
        return route.fulfill({
          json: {
            ok: true,
            source_hash: 'b'.repeat(64),
            manifest_path: `data/training/datasets/dsv_test_new/manifest.json`,
            sample_count: 0,
          },
        });
      }
      if (/^\/api\/training\/datasets\/[^/]+\/splits\/check$/.test(path) && method === 'POST') {
        return route.fulfill({
          json: {
            ok: true,
            leakage: {duplicate_target_text: [], duplicate_crop_hash: []},
            splits: {train: 84, val: 18, test: 18},
            group_distribution: {train_groups: 50, val_groups: 12, test_groups: 12},
          },
        });
      }
      if (/^\/api\/training\/datasets\/[^/]+\/samples$/.test(path) && method === 'POST') {
        return route.fulfill({status: 201, json: {added: 5, rejected: []}});
      }
      if (path === '/api/training/jobs' && method === 'GET') {
        return route.fulfill({json: {items: JOBS, total: JOBS.length}});
      }
      if (path === '/api/training/jobs' && method === 'POST') {
        const data = req.postDataJSON?.() ?? {};
        return route.fulfill({
          status: 201,
          json: {
            job_id: 'job_test_new',
            dataset_id: data.dataset_id,
            target: data.target,
            engine: data.engine,
            state: 'queued',
            progress: 0,
            candidate_id: null,
            created_at: new Date().toISOString(),
            started_at: null,
            finished_at: null,
            error: null,
          },
        });
      }
      const jobMatch = path.match(/^\/api\/training\/jobs\/([^/]+)$/);
      if (jobMatch && method === 'GET') {
        const id = jobMatch[1];
        const found = JOBS.find(j => j.job_id === id);
        if (!found) return route.fulfill({status: 404, json: {detail: 'not found'}});
        return route.fulfill({json: found});
      }
      if (/^\/api\/training\/jobs\/[^/]+\/cancel$/.test(path) && method === 'POST') {
        return route.fulfill({json: {ok: true, state: 'cancelled'}});
      }
      if (path === '/api/training/candidates' && method === 'GET') {
        return route.fulfill({json: {items: CANDIDATES, total: CANDIDATES.length}});
      }
      const cndMatch = path.match(/^\/api\/training\/candidates\/([^/]+)$/);
      if (cndMatch && method === 'GET') {
        const id = cndMatch[1];
        const found = CANDIDATES.find(c => c.candidate_id === id);
        if (!found) return route.fulfill({status: 404, json: {detail: 'not found'}});
        return route.fulfill({json: found});
      }
      if (/^\/api\/training\/candidates\/[^/]+\/promote$/.test(path) && method === 'POST') {
        return route.fulfill({json: {ok: true, promoted: true, active: true}});
      }
      if (/^\/api\/training\/candidates\/[^/]+\/rollback$/.test(path) && method === 'POST') {
        return route.fulfill({json: {ok: true, active_candidate: 'cnd_baseline_plate'}});
      }
      if (/^\/api\/training\/export\/[^/]+$/.test(path) && method === 'GET') {
        return route.fulfill({
          status: 200,
          headers: {'content-type': 'application/zip'},
          body: gif, // tiny payload; UI just needs to know download fired
        });
      }
      if (path === '/api/training/import/preview' && method === 'POST') {
        return route.fulfill({
          json: {
            ok: true,
            dataset_name: 'imported_plate',
            engine: 'plate_ocr',
            sample_count: 50,
            target_text_distribution: {distinct: 30, unreadable: 5},
            conflicts: [],
          },
        });
      }
      if (path === '/api/training/import/apply' && method === 'POST') {
        return route.fulfill({
          json: {ok: true, dataset_id: 'dsv_imported', added: 50, skipped: 0},
        });
      }
      if (path.startsWith('/api/media/')) return route.fulfill({contentType: 'image/gif', body: gif});
      if (path === '/guard/recognition_cards') return route.fulfill({json: {status: 'running', cards: [], models: {}}});
      if (path === '/guard/audio/config') return route.fulfill({json: {rate: 1.3, volume: 1}});
      return route.fulfill({json: []});
    },
  );
}

test.describe('Task 3 — Dataset Manager Page', () => {
  test.beforeEach(async ({page}) => {
    await installApiFixture(page);
    await installTask3Fixture(page);
    await loginFixture(page, ADMIN_USER);
    await page.goto('/admin/datasets', {waitUntil: 'domcontentloaded'});
  });

  test('Navigates to /admin/datasets', async ({page}) => {
    await expect(page).toHaveURL(/\/admin\/datasets/);
  });

  test('Lists existing datasets', async ({page}) => {
    await expect(page.getByText('plate_v1')).toBeVisible({timeout: 5000});
    await expect(page.getByText('helmet_v1')).toBeVisible({timeout: 5000});
  });

  test('Shows engine column', async ({page}) => {
    await expect(page.getByText('plate_ocr').first()).toBeVisible();
    await expect(page.getByText('helmet').first()).toBeVisible();
  });

  test('Shows dataset state column', async ({page}) => {
    await expect(page.getByText('frozen').first()).toBeVisible();
    await expect(page.getByText('draft').first()).toBeVisible();
  });

  test('Has form to create new dataset', async ({page}) => {
    await expect(page.getByRole('button', {name: /Tạo dataset/i})).toBeVisible({timeout: 3000});
  });

  test('Has leakage check button', async ({page}) => {
    await expect(page.getByRole('button', {name: /Kiểm tra leakage/i}).first()).toBeVisible({timeout: 3000});
  });

  test('Click row opens detail panel', async ({page}) => {
    await page.getByText('plate_v1').click();
    await expect(page.getByTestId('dataset-detail-panel').or(page.getByText(/Sample/)).first()).toBeVisible({timeout: 3000});
  });

  test('Security user cannot access /admin/datasets', async ({page}) => {
    await page.evaluate(() => localStorage.clear());
    await loginFixture(page, SECURITY_USER);
    await page.goto('/admin/datasets', {waitUntil: 'domcontentloaded'});
    await page.waitForTimeout(500);
    const at = page.url().includes('/admin/datasets');
    expect(at).toBe(false);
  });
});

test.describe('Task 3 — Training Jobs Page', () => {
  test.beforeEach(async ({page}) => {
    await installApiFixture(page);
    await installTask3Fixture(page);
    await loginFixture(page, ADMIN_USER);
    await page.goto('/admin/training/jobs', {waitUntil: 'domcontentloaded'});
  });

  test('Navigates to /admin/training/jobs', async ({page}) => {
    await expect(page).toHaveURL(/\/admin\/training\/jobs/);
  });

  test('Lists existing jobs', async ({page}) => {
    await expect(page.getByText('job_test_001').first()).toBeVisible({timeout: 5000});
    await expect(page.getByText('job_test_002').first()).toBeVisible({timeout: 5000});
  });

  test('Shows job state badges', async ({page}) => {
    await expect(page.getByText('completed').first()).toBeVisible();
    await expect(page.getByText('training').first()).toBeVisible();
  });

  test('Has create-job form', async ({page}) => {
    await expect(page.getByRole('button', {name: /Tạo job|Tạo Job/i}).first()).toBeVisible({timeout: 3000});
  });

  test('Cancel button visible for running job', async ({page}) => {
    await expect(page.getByRole('button', {name: /Huỷ/i}).first()).toBeVisible({timeout: 3000});
  });

  test('Security user cannot access jobs page', async ({page}) => {
    await page.evaluate(() => localStorage.clear());
    await loginFixture(page, SECURITY_USER);
    await page.goto('/admin/training/jobs', {waitUntil: 'domcontentloaded'});
    await page.waitForTimeout(500);
    expect(page.url().includes('/admin/training/jobs')).toBe(false);
  });
});

test.describe('Task 3 — Candidate Compare Page', () => {
  test.beforeEach(async ({page}) => {
    await installApiFixture(page);
    await installTask3Fixture(page);
    await loginFixture(page, ADMIN_USER);
    await page.goto('/admin/training/candidates', {waitUntil: 'domcontentloaded'});
  });

  test('Navigates to /admin/training/candidates', async ({page}) => {
    await expect(page).toHaveURL(/\/admin\/training\/candidates/);
  });

  test('Lists candidates', async ({page}) => {
    await expect(page.getByText('cnd_test_001').first()).toBeVisible({timeout: 5000});
  });

  test('Shows baseline vs candidate metrics', async ({page}) => {
    await expect(page.getByText(/baseline/i).first()).toBeVisible({timeout: 3000});
  });

  test('Has promote button on non-promoted candidate', async ({page}) => {
    await expect(page.getByRole('button', {name: /Promote/i}).first()).toBeVisible({timeout: 3000});
  });

  test('Has rollback button on active candidate', async ({page}) => {
    await expect(page.getByRole('button', {name: /Rollback/i}).first()).toBeVisible({timeout: 3000});
  });

  test('Security user cannot access candidates page', async ({page}) => {
    await page.evaluate(() => localStorage.clear());
    await loginFixture(page, SECURITY_USER);
    await page.goto('/admin/training/candidates', {waitUntil: 'domcontentloaded'});
    await page.waitForTimeout(500);
    expect(page.url().includes('/admin/training/candidates')).toBe(false);
  });
});

test.describe('Task 3 — BBoxEditor component (smoke)', () => {
  test('Module exports a default React component', async ({page}) => {
    // Static check via module import — no esm.sh CDN needed
    await page.goto('/', {waitUntil: 'domcontentloaded'});
    const moduleOk = await page.evaluate(async () => {
      try {
        // The Vite dev server serves the source under /src/* (no CDN).
        const mod = await import('/src/components/training/BBoxEditor.jsx');
        return typeof mod.default === 'function';
      } catch (e) {
        return false;
      }
    });
    expect(moduleOk).toBe(true);
  });
});
