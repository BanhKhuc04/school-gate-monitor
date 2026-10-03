// Shared UI fixtures. No test connects to a physical camera or live database.
//
// Tất cả request từ page đều xuất phát từ `baseURL` của Playwright
// (`http://127.0.0.1:5186` trong môi trường QA). Vite proxy chỉ chuyển tiếp
// sang backend ở mức HTTP server-to-server, không hiện lên URL mà browser
// nhìn thấy. Vì vậy mock phải khớp URL cùng-origin với frontend, KHÔNG
// được trỏ thẳng vào `http://localhost:8001` — pattern đó không bao giờ
// khớp và request sẽ chạy thẳng về proxy/backend thật (gây timeout khi
// backend không chạy, hoặc message khác kỳ vọng khi backend chạy).
//
// Bài học đau (2 lần):
// 1. `await page.route('http://localhost:8001/**', ...)` không khớp URL mà
//    browser nhìn thấy (đã qua proxy) → request chạy thẳng tới backend.
// 2. `await page.route('**/api/**', ...)` glob của Playwright khớp theo
//    substring, vô tình khớp cả `/src/api/client.js` (file JS module của
//    frontend) → browser nhận JSON thay vì JS → "Failed to load module
//    script ... MIME type of 'application/json'" → React crash, trang trắng.
//
// Cách đúng — dùng regex check PATHNAME, không phải URL. Pathname phải
// bắt đầu bằng `/api/`, `/guard/`, hoặc `/media/` (sau khi strip origin).
export async function installApiFixture(page) {
  await page.addInitScript(()=>{
    window.fixtureSockets=[];
    window.WebSocket=class {
      constructor(url){this.url=url;window.fixtureSockets.push(this);setTimeout(()=>this.onopen?.(),0);}
      close(){}
    };
  });
  const gif=Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7','base64');

  // Mock the video feed stream (cùng-origin) trước để video_feed được ưu tiên.
  await page.route('**/guard/video_feed*',r=>r.fulfill({contentType:'image/gif',body:gif}));

  // Catch-all handler: kiểm tra pathname thay vì URL để tránh khớp nhầm vào
  // file JS module có path chứa chuỗi `/api/` (vd. `/src/api/client.js`).
  // Dùng regex với negative lookbehind: chỉ match nếu KHÔNG có `/src/` ngay
  // trước prefix `/api|/guard|/media`.
  const apiHandler = async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (path === '/guard/video_feed') return route.fulfill({contentType:'image/gif',body:gif});
    if (path === '/api/auth/login') {
      const data = req.postDataJSON?.() ?? {};
      // Test cố tình truyền password sai để kiểm tra UI lỗi — vẫn dùng
      // message tiếng Việt để khớp assertion (`Sai tên đăng nhập hoặc mật khẩu`).
      if (data.password !== 'fixture-password') {
        return route.fulfill({status:401, json:{detail:'Sai tên đăng nhập hoặc mật khẩu'}});
      }
      return route.fulfill({json:{
        access_token:'isolated-test-token-over-twenty-characters',
        token_type:'bearer',
        username: data.username,
        role: data.username,
      }});
    }
    if (path === '/api/auth/me') {
      // Trả về user mặc định — FE AuthContext không gọi endpoint này nhưng
      // RequireRole có thể.
      return route.fulfill({json:{username:'admin', role:'admin'}});
    }
    if (path === '/api/system/health') return route.fulfill({json:{
      pipeline:{running:true, camera_open:true, last_frame_age_sec:.1, last_detection_age_sec:.2, uptime_sec:120},
      gates:[{id:'main', name:'Cổng Chính', pipeline:{running:true, camera_open:true, last_frame_age_sec:.1}}],
      db_size_mb:1, snapshot_count:1, snapshot_size_mb:.1, violations_today:1}});
    if (path === '/api/vehicles') return route.fulfill({json:[{id:1, plate_number:'89F123792', student_name:'Học sinh thử', student_class:'10A1'}]});
    if (path === '/api/violations/encounters') return route.fulfill({json:{total:1, items:[{
      id:1, encounter_id:'fixture', timestamp:'2026-10-01T00:00:00Z', gate_id:'main', status:'pending',
      violation_type:'NO_HELMET', issues:[{code:'NO_HELMET', status:'confirmed'}]}]}});
    if (path.startsWith('/api/media/')) return route.fulfill({contentType:'image/gif', body:gif});
    if (path === '/guard/recognition_cards') return route.fulfill({json:{status:'running', cards:[], models:{}}});
    if (path === '/guard/audio/config') return route.fulfill({json:{rate:1.3, volume:1}});
    if (path.startsWith('/api/stats/')) return route.fulfill({json:{total_vehicles:1, total_violations:1, by_type:[], by_day:[], by_class:[]}});
    return route.fulfill({json:[]});
  };

  // Dùng regex match pathname thuần (sau khi strip `http://host:port`).
  // Negative lookbehind `(?<!src/)` để không khớp `/src/api/client.js`,
  // `/src/guard/...` hay `/src/media/...`. Phải là path API/guard/media
  // bình thường từ Vite proxy hoặc từ axios call.
  await page.route(
    /^(?!https?:\/\/[^/]+\/src\/)(https?:\/\/[^/]+)?\/(api|guard|media)\//,
    apiHandler,
  );
}

export async function loginFixture(page,role='admin') {
  await page.goto('/login');
  await page.locator('#username').fill(role);
  await page.locator('#password').fill('fixture-password');
  await page.locator('button[type="submit"]').click();
  // Đợi token + user đã được ghi vào localStorage (AuthContext đã commit
  // state). Nếu không đợi, RequireRole ở route đích có thể re-render với
  // `user=null` và Navigate về /login trước khi setUser propagate.
  await page.waitForFunction(
    () => !!localStorage.getItem('token') && !!localStorage.getItem('user'),
    { timeout: 10000 },
  );
  await page.waitForURL(role==='security'?'**/guard':role==='management'?'**/dashboard':'**/admin/vehicles');
}
