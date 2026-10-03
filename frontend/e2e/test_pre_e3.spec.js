import {test, expect} from '@playwright/test';

test.use({baseURL:'http://127.0.0.1:5186'});
// Isolated browser/API/media fixtures: never connect to the operating cameras.
async function setup(page, {loadFailure = false, staleFirstResponse = false, leaseConflict = false} = {}) {
  const queries = [];
  await page.addInitScript(() => {
    window.testAudio = {beeps:0, speech:[], options:[], sockets:[]};
    window.WebSocket = class {
      constructor() { window.testAudio.sockets.push(this); setTimeout(() => this.onopen?.(), 0); }
      close() { this.onclose?.(); }
    };
    window.AudioContext = class {
      currentTime=0; destination={};
      createOscillator() { return {frequency:{}, connect(){}, start(){window.testAudio.beeps++;}, stop(){}}; }
      createGain() { return {gain:{}, connect(){}}; }
      close() { return Promise.resolve(); }
    };
    Object.defineProperty(window, 'speechSynthesis', {value:{
      getVoices:() => [{name:'Test Vietnamese',lang:'vi-VN'}],
      cancel(){},
      speak(utterance) { window.testAudio.speech.push(utterance.text); window.testAudio.options.push({rate:utterance.rate,volume:utterance.volume}); setTimeout(() => utterance.onend?.(), 0); },
    }});
    window.SpeechSynthesisUtterance = class { constructor(text) {this.text=text;} };
  });
  await page.route(
    /^(?!https?:\/\/[^/]+\/src\/)(?:https?:\/\/[^/]+)?\/(api|guard|media)\//,
    async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let body = [];
    if (path === '/api/auth/login') body = {access_token:'isolated-test-token',username:'admin',role:'admin'};
    if (path === '/api/system/health') body = {gates:[{id:'main',name:'Cổng Chính'}]};
    if (path === '/api/stats/summary') body = {};
    if (path === '/guard/audio/config') body = {rate:1.32,volume:.95,engine:'Web Speech API'};
    if (path === '/guard/audio/lease') return leaseConflict
      ? route.fulfill({status:409,json:{detail:'Loa đang được sử dụng trên một máy khác'}})
      : route.fulfill({json:{granted:true,expires_in:15}});
    if (path === '/api/violations/encounters') {
      queries.push(Object.fromEntries(url.searchParams));
      const isStale = staleFirstResponse && !url.searchParams.has('violation_type');
      if (isStale) await new Promise(resolve => setTimeout(resolve, 1500));
      if (loadFailure) return route.fulfill({status:503,json:{detail:'Không tải được dữ liệu thử'}});
      const secondPage = url.searchParams.get('offset') === '20';
      body = {total:21,items:[{id:secondPage ? 21 : 1,encounter_id:secondPage ? 'second' : 'first',
        timestamp:'2026-10-01T08:00:00Z',gate_id:'main',status:'pending',violation_type:'MULTIPLE',
        student_name:isStale ? 'Phản hồi cũ cần bỏ' : secondPage ? 'Học sinh trang hai' : 'Học sinh trang một',
        issues:[{code:'NO_HELMET',status:'confirmed'},
                {code:'PLATE_LOW_CONFIDENCE',status:'needs_review',reason:'Biển mờ trong ảnh thử'}]}]};
    }
    if (path.startsWith('/guard/video_feed') || path.startsWith('/api/media/')) {
      return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"/>'});
    }
    return route.fulfill({json:body});
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
  return queries;
}

test('encounter table shows both issues and reloads pagination/filter', async ({page}) => {
  const errors=[];
  page.on('pageerror', error => errors.push(error.message));
  const queries=await setup(page);
  await page.goto('/admin/violations');
  await expect(page.getByText('Học sinh trang một')).toBeVisible();
  const row=page.locator('tbody tr').first();
  await expect(row.getByText('Biển mờ trong ảnh thử')).toBeVisible();
  await expect(row.locator('.bg-red-100')).toHaveCount(1);
  await expect(row.locator('.bg-amber-100')).toHaveCount(1);
  await expect(row.getByText('Chưa đọc rõ')).toBeVisible();
  await page.screenshot({path:'../docs/pre-e3-violations-preview.png',fullPage:true});
  await page.getByRole('button',{name:'Sau →'}).click();
  await expect(page.getByText('Học sinh trang hai')).toBeVisible();
  expect(queries.at(-1).offset).toBe('20');
  await page.getByRole('button',{name:'Lọc',exact:true}).click();
  await expect(page.getByText('Học sinh trang một')).toBeVisible();
  expect(queries.at(-1).offset).toBe('0');
  expect(errors).toEqual([]);
});

test('sealed crossing: one physical beep and one utterance uses configured rate/volume', async ({page}) => {
  await setup(page); await page.goto('/guard');
  await page.getByRole('button',{name:'Bật loa trên máy này'}).click();
  await expect(page.getByRole('button',{name:'Tắt loa trên máy này'})).toBeVisible();
  await page.waitForTimeout(150);
  const data={event_id:'cross-e',crossing_event_id:'cross-c',vehicle_track_id:7,source_epoch:0,gate_id:'main',
    alert_finalized:true,evidence_state:'persisted',plate_status:'CONFIRMED',plate_read:'89F123792',timestamp:new Date().toISOString(),
    issues:[{code:'NO_HELMET',status:'confirmed'},{code:'RIDING_THROUGH_GATE',status:'confirmed'}]};
  const send = data => page.evaluate(data=>window.testAudio.sockets.at(-1).onmessage({data:JSON.stringify(data)}),data);
  await send(data);
  await expect.poll(()=>page.evaluate(()=>window.testAudio.speech.length)).toBe(1);
  expect(await page.evaluate(()=>window.testAudio.speech[0])).toBe('89 F1 237 92. Không đội mũ, vui lòng dắt xe.');
  expect(await page.evaluate(()=>window.testAudio.beeps)).toBe(1);
  expect(await page.evaluate(()=>window.testAudio.options[0])).toEqual({rate:1.32,volume:.95});
  await send({...data,event_version:2,issues:[...data.issues,{code:'PLATE_UNREADABLE',status:'confirmed'}]});
  await page.waitForTimeout(500);
  expect(await page.evaluate(()=>window.testAudio.speech.length)).toBe(1);
  await send({...data,event_id:'cross-e2',crossing_event_id:'cross-c2',plate_read:'',plate_status:'UNREADABLE',
    issues:[{code:'PLATE_UNREADABLE',status:'confirmed'},...data.issues]});
  await expect.poll(()=>page.evaluate(()=>window.testAudio.speech.length)).toBe(2);
  expect(await page.evaluate(()=>window.testAudio.speech[1])).toBe('Không đọc được biển số. Không đội mũ, vui lòng dắt xe.');
  expect(await page.evaluate(()=>window.testAudio.beeps)).toBe(2);
});

test('viewers stay silent and cannot take another machine speaker lease', async ({page}) => {
  await setup(page,{leaseConflict:true});
  await page.goto('/guard');
  await expect.poll(() => page.evaluate(() => window.testAudio.sockets.length)).toBeGreaterThan(0);
  await page.evaluate(() => window.testAudio.sockets.at(-1).onmessage({data:JSON.stringify({
    event_id:'viewer-event',evidence_state:'persisted',timestamp:new Date().toISOString(),
    issues:[{code:'NO_HELMET',status:'confirmed'}],
  })}));
  await page.waitForTimeout(700);
  expect(await page.evaluate(() => window.testAudio.beeps)).toBe(0);
  await page.getByRole('button',{name:'Bật loa trên máy này'}).click();
  await expect(page.getByRole('alert')).toHaveText('Loa đang được sử dụng trên một máy khác');
  await expect(page.getByRole('button',{name:'Bật loa trên máy này'})).toBeVisible();
});

test('late response cannot overwrite results from a newer filter request', async ({page}) => {
  const queries=await setup(page,{staleFirstResponse:true});
  await page.goto('/admin/violations');
  await expect.poll(() => queries.length).toBeGreaterThan(0);
  await page.locator('select').selectOption('NO_HELMET');
  await page.getByRole('button',{name:'Lọc',exact:true}).click();
  await expect(page.getByText('Học sinh trang một')).toBeVisible();
  await page.waitForTimeout(1800);
  await expect(page.getByText('Phản hồi cũ cần bỏ')).toHaveCount(0);
});

test('load error displays retry rather than empty results', async ({page}) => {
  const errors=[];
  page.on('pageerror',error => errors.push(error.message));
  await setup(page,{loadFailure:true});
  await page.goto('/admin/violations');
  await expect(page.getByText('Không tải được dữ liệu thử')).toBeVisible();
  await expect(page.getByRole('button',{name:/Thử lại/})).toBeVisible();
  await expect(page.getByText('Không có vi phạm nào', {exact:true})).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('OCR is silent; mixed event speaks helmet once and cleanup cancels pending sound', async ({page}) => {
  const errors=[];
  page.on('pageerror',error => errors.push(error.message));
  await setup(page);
  await page.goto('/guard');
  await page.getByRole('button',{name:'Bật loa trên máy này'}).click();
  await expect(page.getByRole('button',{name:'Tắt loa trên máy này'})).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.testAudio.sockets.length)).toBeGreaterThan(0);
  const send = (data) => page.evaluate(data => window.testAudio.sockets.at(-1).onmessage({data:JSON.stringify(data)}),data);
  const event = {event_id:'fixture-event',timestamp:new Date().toISOString(),evidence_state:'persisted',
    gate_id:'main',violation_type:'NO_PLATE',issues:[{code:'NO_PLATE',status:'needs_review'}]};
  await send(event);
  await page.waitForTimeout(900);
  expect(await page.evaluate(() => window.testAudio.beeps)).toBe(0);
  event.issues.push({code:'NO_HELMET',status:'confirmed'});
  await send(event);
  await expect.poll(() => page.evaluate(() => window.testAudio.speech.length)).toBe(1);
  const speech=await page.evaluate(() => window.testAudio.speech[0]);
  expect(speech).toContain('Vui lòng đội mũ.');
  expect(speech).not.toContain('biển');
  await send(event);
  await page.waitForTimeout(900);
  expect(await page.evaluate(() => window.testAudio.speech.length)).toBe(1);
  await send({...event,event_id:'pending-unmount'});
  await page.getByRole('link',{name:'Nhật ký vi phạm'}).click();
  await page.waitForTimeout(900);
  expect(await page.evaluate(() => window.testAudio.speech.length)).toBe(1);
  expect(errors).toEqual([]);
});
