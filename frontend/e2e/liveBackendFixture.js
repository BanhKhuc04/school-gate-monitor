// Live browser-integration fixture: connect browser to the QA backend through
// Vite proxy on http://127.0.0.1:5187 (default). NO Playwright route mock for
// /api/auth/login, /api/auth/me, /api/vehicles, /api/violations/*, etc. —
// browser receives whatever the real backend serves.
//
// ONLY endpoints that NEED heavy CV backend or that don't exist on the QA
// backend are stubbed:
//   - /guard/recognition_cards   (returns static fake card so GuardPage can render)
//   - /guard/video_feed          (returns 1×1 gif so video element doesn't crash)
//   - /guard/recognition_image/* (returns 1×1 gif for plate/person/head images)
//
// Anything else goes to the QA backend. This is the integration suite.

const GUARD_STUB_PATHS = new Set([
  /^\/guard\/recognition_cards(\?|$)/,
  /^\/guard\/video_feed(\?|$)/,
  /^\/guard\/recognition_image\//,
  /^\/guard\/ws(\?|$)/,
  /^\/guard\/audio\/config(\?|$)/,
]);

const TINY_GIF = Buffer.from(
  'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7',
  'base64'
);

export async function installLiveBackendFixture(page, baseURL = 'http://127.0.0.1:5187') {
  // Stub WebSocket (the QA backend has no running CV pipeline — ws would
  // fail to connect). Tests don't actually need WS events to verify scope/route
  // for non-guard pages; for guard-page tests we keep it open but inert.
  await page.addInitScript(() => {
    window.fixtureSockets = [];
    const RealWS = window.WebSocket;
    window.WebSocket = class {
      constructor(url) {
        this.url = url;
        window.fixtureSockets.push(this);
        // Pretend it connected so client code doesn't see connection errors.
        setTimeout(() => {
          if (this.onopen) this.onopen({});
        }, 0);
      }
      close() { /* no-op */ }
      send() { /* no-op */ }
    };
  });

  // Only stub guard/ paths — everything else goes to QA backend.
  await page.route(/^http:\/\/127\.0\.0\.1:5187\/guard\/recognition_cards/, async (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'running',
        run_id: 'qa-live',
        source_epoch: 0,
        models: { tracker: { engine: 'ByteTrack' } },
        cards: [],     // Empty list — guard page should render empty state, not crash.
      }),
    });
  });

  await page.route(/^http:\/\/127\.0\.0\.1:5187\/guard\/video_feed/, async (route) => {
    return route.fulfill({ status: 200, contentType: 'image/gif', body: TINY_GIF });
  });

  await page.route(/^http:\/\/127\.0\.0\.1:5187\/guard\/recognition_image\//, async (route) => {
    return route.fulfill({ status: 200, contentType: 'image/gif', body: TINY_GIF });
  });

  await page.route(/^http:\/\/127\.0\.0\.1:5187\/guard\/audio\/config/, async (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ rate: 1.45, volume: 1.0 }),
    });
  });

  // /guard/ws is intercepted to a no-op close handler (above init script
  // replaces WebSocket globally, so page.route is not strictly needed).
}

export async function liveLogin(page, username, password) {
  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await page.fill('#username', username);
  await page.fill('#password', password);
  await page.locator('button[type="submit"]').click();
  // Wait for AuthContext to commit (token + user in localStorage). Without
  // this, RequireRole re-renders with user=null and Navigate forces /login.
  await page.waitForFunction(
    () => !!localStorage.getItem('token') && !!localStorage.getItem('user'),
    { timeout: 15000 },
  );
  // Confirm NOT in /login.
  await page.waitForFunction(
    () => !window.location.pathname.startsWith('/login'),
    { timeout: 15000 },
  );
}