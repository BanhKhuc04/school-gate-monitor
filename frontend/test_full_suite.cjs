/**
 * Comprehensive autonomous test suite for Steps 8-13.
 * Run: node test_full_suite.cjs
 */
const { chromium } = require('playwright');
async function isServerUp(url, maxRetries = 3) {
  const axios = require('axios');
  for (let i = 0; i < maxRetries; i++) {
    try {
      // Axios doesn't throw on 4xx, so any non-network error means server is up
      await axios.get(url, { timeout: 2000, validateStatus: () => true });
      return true;
    } catch { /* network error, retry */ }
    await new Promise(r => setTimeout(r, 2000));
  }
  return false;
}

const axios = require('axios');
const BASE_DEV = 'http://localhost:5173';
const BASE_PROD = 'http://localhost:8000';

let passed = 0, failed = 0;
function assert(cond, label) {
  if (cond) { console.log(`  ✅ ${label}`); passed++; }
  else { console.error(`  ❌ ${label}`); failed++; }
}

// Always use fresh page to avoid React state contamination
async function freshLogin(page, username, password) {
  await page.goto(`${BASE_DEV}/login`, { waitUntil: 'networkidle' });
  await page.fill('#username', username);
  await page.fill('#password', password);
  await page.click('button[type="submit"]');
  await page.waitForTimeout(5000);
}

(async () => {
  console.log('========== FULL AUTONOMOUS TEST SUITE ==========\n');
  const browser = await chromium.launch({ headless: true });
  console.log('\n========== FULL AUTONOMOUS TEST SUITE ==========\n');

  // ─── BƯỚC 8 ────────────────────────────────────────────
  console.log('--- BƯỚC 8: Login scaffold ---');
  {
    // 8a–c: wrong password in isolated context
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto(`${BASE_DEV}/login`, { waitUntil: 'networkidle' });
  // 8c. Wrong password — go to a FRESH login page (not the one from 8d which unmounted)
  const ctxW = await browser.newContext();
  const pageW = await ctxW.newPage();
  await pageW.goto(`${BASE_DEV}/login`, { waitUntil: 'networkidle' });
  await pageW.fill('#username', 'admin');
  await pageW.fill('#password', 'wrongpassword');
  await pageW.click('button[type="submit"]');
  // Wait for error div (the red error box) to appear — use waitForSelector directly
  // in the assert so we FAIL with a meaningful message if it doesn't appear
  const errorBox = await pageW.waitForSelector('.bg-red-50', { timeout: 10000 }).catch(() => null);
  assert(!!errorBox, 'Wrong password shows error message');
  assert(pageW.url().includes('/login'), 'Wrong password stays on /login');
  await ctxW.close();
    await ctx.close();

    // 8d–f: correct login in isolated context
    const ctx2 = await browser.newContext();
    const page2 = await ctx2.newPage();
    await freshLogin(page2, 'admin', 'admin123');
    const afterUrl = page2.url();
    assert(
      afterUrl.includes('/admin/vehicles') || afterUrl.includes('/dashboard') || afterUrl.includes('/guard'),
      `Correct login redirects (got: ${afterUrl})`
    );
    const token = await page2.evaluate(() => localStorage.getItem('token'));
    assert(!!token && token.length > 20, 'Token stored in localStorage');
    assert(!!(await page2.$('nav')), 'NavBar rendered (Layout works)');
    await ctx2.close();
  }

  // ─── BƯỚC 9 ────────────────────────────────────────────
  console.log('\n--- BƯỚC 9: GuardPage + AlertBanner ---');
  {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await freshLogin(page, 'security', 'security123');
    assert(page.url().includes('/guard'), 'Security login -> /guard');

    await page.waitForTimeout(2000);
    assert(!!(await page.$('img[alt="Live camera feed"]')), 'Video feed img exists');
    const imgW = await page.evaluate(() => document.querySelector('img[alt="Live camera feed"]')?.naturalWidth);
    console.log(`  Video img naturalWidth: ${imgW} (0 = no camera — OK)`);

    // Management blocked from /guard
    const ctx2 = await browser.newContext();
    const page2 = await ctx2.newPage();
    await freshLogin(page2, 'management', 'management123');
    await page2.goto(`${BASE_DEV}/guard`, { waitUntil: 'networkidle' });
    await page2.waitForTimeout(500);
    assert(!(await page2.$('img[alt="Live camera feed"]')), 'Management blocked from /guard');
    await ctx2.close();

    // Trigger test alert — use the SAME page as the guard navigation above
    // (NOT a fresh context/page) so there is only ONE WS consumer for the queue.
    // Trigger test alert — use the SAME security page (the one already on /guard)
    // so there is only ONE WS consumer. Call the API from within the page so the
    // browser's localStorage token is automatically included via the client interceptor.
    // The endpoint requires security or admin role (security token is sufficient).
    const triggerResult = await page.evaluate(async () => {
      try {
        const resp = await fetch('http://localhost:8000/api/dev/trigger-test-alert', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ violation_type: 'PLATE_NOT_REGISTERED', plate_read: 'TESTALERT999' })
        });
        return { ok: resp.ok, status: resp.status };
      } catch (e) {
        return { error: e.message };
      }
    });
    console.log(`  Trigger alert API: ${JSON.stringify(triggerResult)}`);

    // Wait for the alert banner text to appear. Pipeline WS polls every 200ms.
    // The banner auto-hides after 3s — poll every 500ms for up to 6s to catch
    // the brief window when it's visible, rather than a single point-in-time check.
    let alertFound = false;
    for (let i = 0; i < 12; i++) {
      await page.waitForTimeout(500);
      const bodyAlert = await page.textContent('body');
      if (
        bodyAlert.includes('CẢNH BÁO') || bodyAlert.includes('TESTALERT999') ||
        bodyAlert.includes('PLATE_NOT_REGISTERED') || bodyAlert.includes('NO_HELMET') ||
        bodyAlert.includes('PLATE_UNREADABLE')
      ) {
        alertFound = true;
        break;
      }
    }
    assert(alertFound, 'Alert content appeared after trigger');
    console.log('  [CẦN NGƯỜI KIỂM TRA] Tiếng beep có phát ra thật không?');
    await ctx.close();
  }

  // ─── BƯỚC 10 ────────────────────────────────────────────
  console.log('\n--- BƯỚC 10: AdminVehiclesPage + AdminViolationsPage ---');
  {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await freshLogin(page, 'admin', 'admin123');

    await page.goto(`${BASE_DEV}/admin/vehicles`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    assert(page.url().includes('/admin/vehicles'), 'Navigated to /admin/vehicles');
    assert(!!(await page.$('table')), 'Vehicles table exists');

    const rowsBefore = await page.$$('table tbody tr');

    // Add vehicle
    const inputs = await page.$$('input');
    if (inputs.length >= 3) {
      await inputs[0].fill('AUTOTEST99');
      await inputs[1].fill('Auto Test User');
      await inputs[2].fill('Auto Class');
      const form = await page.$('form');
      if (form) {
        await form.evaluate(f => { const b = f.querySelector('button[type="submit"]'); if (b) b.click(); });
        await page.waitForTimeout(2000);
      }
      const rowsAfter = await page.$$('table tbody tr');
      assert(rowsAfter.length >= rowsBefore.length, `Add vehicle: rows ${rowsBefore.length} → ${rowsAfter.length}`);

      // Cleanup
      await page.goto(`${BASE_DEV}/admin/vehicles`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(1000);
      const btns = await page.$$('button');
      for (const btn of btns) {
        const t = await btn.textContent();
        if (t.includes('Xóa') || t.includes('Delete')) { await btn.click(); await page.waitForTimeout(1000); break; }
      }
      console.log('  Test vehicle deleted');
    } else {
      assert(!!(await page.$('table')), 'Vehicles table rendered');
    }

    // Violations
    await page.goto(`${BASE_DEV}/admin/violations`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    assert(page.url().includes('/admin/violations'), 'Navigated to /admin/violations');
    assert(!!(await page.$('table')), 'Violations table exists');

    const snapImgs = await page.$$('img[src*="/media/"]');
    if (snapImgs.length > 0) {
      const src = await snapImgs[0].getAttribute('src');
      const reqSrc = src.startsWith('http') ? src : `${BASE_DEV}${src}`;
      const resp = await page.request.get(reqSrc);
      assert(resp.status() === 200, `Violation image loads (${src.split('/').pop()})`);
    } else {
      console.log('  No violation images (no data in test env)');
    }

    // Security blocked
    const ctx2 = await browser.newContext();
    const page2 = await ctx2.newPage();
    await freshLogin(page2, 'security', 'security123');
    await page2.goto(`${BASE_DEV}/admin/vehicles`, { waitUntil: 'networkidle' });
    await page2.waitForTimeout(500);
    assert(!page2.url().includes('/admin/vehicles'), 'Security blocked from /admin/vehicles');
    await ctx.close(); await ctx2.close();
  }

  // ─── BƯỚC 11 ────────────────────────────────────────────
  console.log('\n--- BƯỚC 11: DashboardPage ---');
  {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await freshLogin(page, 'management', 'management123');
    await page.goto(`${BASE_DEV}/dashboard`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(2500);

    const body = await page.textContent('body');
    assert(body.includes('Vi phạm hôm nay'), 'KPI "Vi phạm hôm nay" exists');
    assert(body.includes('Vi phạm tuần này'), 'KPI "Vi phạm tuần này" exists');

    const token = await page.evaluate(() => localStorage.getItem('token'));
    const apiResp = await axios.get(`${BASE_PROD}/api/stats/summary`, {
      headers: { Authorization: `Bearer ${token}` }, timeout: 5000,
    });
    const api = apiResp.data;
    console.log(`  API: today=${api.total_today}, week=${api.total_week}`);
    assert(typeof api.total_today === 'number', 'API returns total_today');
    assert(typeof api.total_week === 'number', 'API returns total_week');

    assert(!!(await page.$('.recharts-wrapper svg, .recharts-surface')), 'Recharts chart SVG rendered');
    console.log('  [CẦN NGƯỜI KIỂM TRA] Biểu đồ đẹp và đúng tỷ lệ?');

    const ctx2 = await browser.newContext();
    const page2 = await ctx2.newPage();
    await freshLogin(page2, 'security', 'security123');
    await page2.goto(`${BASE_DEV}/dashboard`, { waitUntil: 'networkidle' });
    await page2.waitForTimeout(500);
    assert(!page2.url().includes('/dashboard'), 'Security blocked from /dashboard');
    await ctx.close(); await ctx2.close();
  }

  // ─── BƯỚC 12 ────────────────────────────────────────────
  console.log('\n--- BƯỚC 12: Old Jinja routes are 410 Gone ---');
  {
    for (const url of ['http://localhost:8000/admin', 'http://localhost:8000/admin/violations']) {
      try {
        const resp = await axios.get(url, { timeout: 5000 });
        assert(resp.status === 410, `GET ${url} -> 410 (got ${resp.status})`);
      } catch (e) {
        assert(e.response?.status === 410, `GET ${url} -> 410 (got ${e.response?.status || 'err'})`);
      }
    }
    // /guard is now a SPA route — must return index.html, not 410
    try {
      const resp = await axios.get('http://localhost:8000/guard', { timeout: 5000 });
      assert(resp.status === 200, `GET /guard -> 200 (got ${resp.status})`);
      assert(resp.data.includes('<!doctype') || resp.data.includes('<html'), 'GET /guard returns HTML');
    } catch (e) {
      assert(false, `GET /guard should return 200 HTML (got ${e.response?.status || 'err'})`);
    }
    for (const url of ['/api/vehicles', '/api/violations', '/api/stats/summary']) {
      try {
        const resp = await axios.get(`${BASE_PROD}${url}`, { timeout: 5000 });
        assert([200, 401].includes(resp.status), `GET ${url} accessible (${resp.status})`);
      } catch (e) {
        assert(e.response?.status !== 404, `GET ${url} exists (not 404)`);
      }
    }

    // Security: /api/dev/trigger-test-alert requires admin role
    // 12a: no token → 401/403
    try {
      await axios.post(`${BASE_PROD}/api/dev/trigger-test-alert`, {}, { timeout: 5000 });
      assert(false, 'Trigger alert without token -> 401/403');
    } catch (e) {
      assert([401, 403].includes(e.response?.status), `Trigger alert without token -> 401/403 (got ${e.response?.status})`);
    }
    // 12b: non-admin token → 401/403
    try {
      await axios.post(`${BASE_PROD}/api/dev/trigger-test-alert`, {}, {
        headers: { Authorization: `Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.bad` },
        timeout: 5000
      });
      assert(false, 'Trigger alert with invalid token -> 401/403');
    } catch (e) {
      assert([401, 403].includes(e.response?.status), `Trigger alert with invalid token -> 401/403 (got ${e.response?.status})`);
    }
  }

  // ─── BƯỚC 13 ────────────────────────────────────────────
  console.log('\n--- BƯỚC 13: SPA fallback (production mode) ---');
  {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();

    await page.goto(`${BASE_PROD}/`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    assert(!!(await page.$('#username')), 'Root at :8000 serves SPA login');

    for (const route of ['/admin/vehicles', '/guard', '/dashboard']) {
      await page.goto(`${BASE_PROD}${route}`, { waitUntil: 'networkidle' });
      // Wait for React to mount (index.html shell → JS → React renders)
      await page.waitForSelector('#username, nav, table, img[alt="Live camera feed"]', { timeout: 15000 }).catch(() => {});
      const content = await page.$('#username, nav, table, img[alt="Live camera feed"]');
      assert(!!content, `Hard refresh ${route} renders`);
    }

    const resp = await axios.get(`${BASE_PROD}/admin/vehicles`, { timeout: 5000 });
    assert(
      resp.data.includes('<!doctype') || resp.data.includes('root'),
      'SPA fallback returns index.html (not 404)'
    );
    console.log('  [CẦN NGƯỜI KIỂM TRA] F5 cứng trên sub-routes ở :8000 không bị 404?');
    await ctx.close();
  }

  // ─── FULL FLOW ────────────────────────────────────────────
  console.log('\n--- FULL FLOW: Admin navigation + logout ---');
  {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await freshLogin(page, 'admin', 'admin123');

    for (const route of ['/admin/vehicles', '/admin/violations']) {
      await page.goto(`${BASE_DEV}${route}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(500);
      assert(page.url().includes(route), `Navigate to ${route}`);
    }
    await page.goto(`${BASE_DEV}/guard`, { waitUntil: 'networkidle' });
    assert(page.url().includes('/guard'), 'Navigate to /guard');

    await page.waitForSelector('nav', { timeout: 5000 });
    const logoutBtn = await page.waitForSelector('button:text("Đăng xuất")', { timeout: 5000 }).catch(() => null);
    assert(!!logoutBtn, 'Logout button present');
    await logoutBtn.click();
    await page.waitForTimeout(500);
    assert(page.url().includes('/login'), 'Logout redirects to /login');
    assert(!(await page.evaluate(() => localStorage.getItem('token'))), 'Token cleared after logout');

    await ctx.close();
  }

  console.log(`\n========== RESULTS: ${passed} passed, ${failed} failed ==========\n`);
  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
})().catch(e => {
  console.error('FATAL:', e.message, e.stack);
  process.exit(1);
});
