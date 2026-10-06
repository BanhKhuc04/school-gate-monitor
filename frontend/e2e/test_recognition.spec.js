import {test, expect} from '@playwright/test';
test.use({baseURL:'http://127.0.0.1:5186'});
const gif=Buffer.from('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7','base64');

async function setup(page, {modelError=false, failure=false, accumulate=false, best=false, plateOnly=false}={}) {
  let polls=0;
  await page.addInitScript(()=>{
    window.testSpeech=0;
    window.WebSocket=class {close(){}};
    Object.defineProperty(window,'speechSynthesis',{value:{getVoices:()=>[],cancel(){},speak(){window.testSpeech++;}}});
  });
  await page.route('**/guard/recognition_image/**',route=>route.fulfill({contentType:'image/gif',body:gif}));
  await page.route(
    /^(?!https?:\/\/[^/]+\/src\/)(?:https?:\/\/[^/]+)?\/(api|guard|media)\//,
    async route=>{
    const url=new URL(route.request().url());
    if(url.pathname==='/api/auth/login')return route.fulfill({json:{access_token:'fixture',username:'admin',role:'admin'}});
    if(url.pathname.startsWith('/guard/recognition_image/'))return route.fulfill({contentType:'image/gif',body:gif});
    if(url.pathname==='/api/system/health')return route.fulfill({json:{gates:[{id:'main',name:'Cổng Chính'}]}});
    if(url.pathname==='/guard/recognition_cards'){
      polls++;
      if(failure)return route.fulfill({status:503,json:{detail:'Thẻ tạm thời không tải được'}});
      const samples=accumulate?Math.min(4,polls):4;
      const card={card_id:'fixture-run:0:person:12',last_seen:'2026-10-01T06:00:00Z',camera_id:'main',
        source_epoch:0,frame_seq:accumulate?polls:42,track_id:12,vehicle_track_id:7,
        person:{state:samples===4?'confirmed':'checking',samples,required_samples:4},
        helmet:{state:samples===4?'confirmed':'checking',value:'helmet',samples,required_samples:4},
        plate:{state:'candidate',association:'unverified',text:'89F165123',samples:2,required_samples:2},
        images:Object.fromEntries(['person','head','plate'].map(kind=>[kind,{url:'/guard/recognition_image/'+kind+'?gate=main',frame_seq:42}])),
        reasons:['vehicle_not_associated']};
      if(best)Object.assign(card,{
        plate:{state:'confirmed',association:'verified',text:'89F123792',samples:1,required_samples:1},
        reasons:[],plate_debug:{best_frame_id:40,size:[180,120],quality:.86,blur:480,
          contrast:45,detector_confidence:.96,attempts:1,max_attempts:1,status:'CONFIRMED',
          raw_top:'89-F1',raw_bottom:'237.92',normalized:'89F123792'},
        riding:{state:'RIDING',leg_status:'UNAVAILABLE',hip_score:.95,torso_score:.9,
          overlap:.85,temporal:1,motion:.8,score:.92}});
      if(plateOnly)Object.assign(card,{kind:'plate',track_id:null,vehicle_track_id:null,ocr_track_id:-20003,
        person:undefined,helmet:undefined,riding:undefined,images:{plate:card.images.plate},
        plate:{...card.plate,state:'candidate',association:'unverified'}});
      return route.fulfill({json:{status:'running',run_id:'fixture-run',source_epoch:0,
        models:{tracker:{engine:'ByteTrack'},person:{family:'YOLOv8n',weights:'yolov8n.pt',device:'cuda:0'},
          ocr:{engine:'EasyOCR'},helmet:modelError?{status:'error'}:{status:'ready'}},cards:[card]}});
    }
    if(url.pathname==='/guard/video_feed')return route.fulfill({contentType:'image/gif',body:gif});
    return route.fulfill({json:[]});
  });
  await page.goto('/login');
  await page.getByLabel('Tên đăng nhập').fill('admin');await page.getByLabel('Mật khẩu',{exact:true}).fill('fixture');
  await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
  // Đợi token + user đã commit vào AuthContext.
  await page.waitForFunction(
    () => !!localStorage.getItem('token') && !!localStorage.getItem('user'),
    { timeout: 10000 },
  );
  await expect(page).not.toHaveURL(/\/login/);
  await page.goto('/guard');
  return ()=>polls;
}

test('visual cards show three crops and uncertain OCR without speech; filter, pause and hide work',async({page})=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await setup(page);
  await expect(page.getByRole('tab',{name:'Nhận diện trực tiếp'})).toHaveAttribute('aria-selected','true');
  const card=page.getByTestId('recognition-card');
  await expect(card).toHaveCount(1);
  for(const name of ['Ảnh người','Ảnh đầu / mũ','Ảnh biển số']){
    await expect(card.getByRole('img',{name,exact:true})).toBeVisible();
    expect(await card.getByRole('img',{name,exact:true}).evaluate(img=>img.complete && img.naturalWidth>0)).toBe(true);
  }
  await expect(card.getByText('89F165123',{exact:true})).toBeVisible();
  await expect(card.getByText('0/1 lượt OCR · chờ crop biển phù hợp')).toBeVisible();
  await expect(card.getByText(/mẫu OCR khác frame/)).toHaveCount(0);
  await expect(card.getByText('Chưa ghép xe — không gán học sinh')).toBeVisible();
  await page.getByLabel('Lọc track').fill('999');await expect(page.getByText('Không có thẻ phù hợp bộ lọc.')).toBeVisible();
  await page.getByLabel('Lọc track').fill('7');await expect(card).toHaveCount(1);
  await page.getByRole('button',{name:'Tạm dừng cập nhật'}).click();
  await expect(page.getByRole('button',{name:'Tiếp tục cập nhật'})).toBeVisible();
  await page.getByLabel('Lọc track').fill('');await page.getByRole('button',{name:'Ẩn thẻ hiện tại'}).click();
  await page.waitForTimeout(1300);await expect(card).toHaveCount(0);
  await page.getByRole('tab',{name:'Cảnh báo',exact:true}).click();await expect(page.getByText('Chưa có cảnh báo nào trong phiên này.')).toBeVisible();
  expect(await page.evaluate(()=>window.testSpeech)).toBe(0);expect(errors).toEqual([]);
});

test('best plate shows one attempt, original size, raw lines and unavailable legs',async({page})=>{
  await setup(page,{best:true});
  const card=page.getByTestId('recognition-card');
  await expect(card.getByText('1/1 lượt OCR · chọn một crop tốt nhất')).toBeVisible();
  await expect(card.getByText('Ảnh chọn: frame 40 · 180×120 px gốc')).toBeVisible();
  await expect(card.getByText('Hành vi: Đang đi xe · chân: không đủ quan sát')).toBeVisible();
  await expect(card.getByRole('link',{name:'Tải ảnh biển đã chọn'})).toHaveAttribute('href','/guard/plate_best/7?gate=main&epoch=0');
  await card.getByText('Chi tiết OCR',{exact:true}).click();
  await expect(card.getByText('Dòng trên: 89-F1')).toBeVisible();
  await expect(card.getByText('Dòng dưới: 237.92')).toBeVisible();
  await card.getByText('Chi tiết tư thế',{exact:true}).click();
  await expect(card.getByText('Score: 0.92 · chân: UNAVAILABLE')).toBeVisible();
  expect(await page.evaluate(()=>window.testSpeech)).toBe(0);
  await page.screenshot({path:'../docs/best-plate-fixture-preview.png',fullPage:true});
});

test('one track updates a single card and only confirms after enough observations',async({page})=>{
  await setup(page,{accumulate:true});
  const card=page.getByTestId('recognition-card');
  await expect(card.getByText('1/4 mẫu · Đang kiểm tra').first()).toBeVisible();
  await expect(card.getByText('4/4 mẫu · Đã đối chiếu').first()).toBeVisible({timeout:7000});
  await expect(card).toHaveCount(1);
  await expect(card.getByText('Biển đọc thử',{exact:true})).toBeVisible();
  await page.getByText('Model đang dùng · ByteTrack',{exact:true}).click();
  await expect(page.getByText('Người/xe: YOLOv8n · yolov8n.pt · cuda:0')).toBeVisible();
});

test('model contract failure is visible without disabling other recognition',async({page})=>{
  await setup(page,{modelError:true});
  await expect(page.getByRole('alert').filter({hasText:'Nhận diện mũ chưa khả dụng'})).toBeVisible();
  await expect(page.getByText('89F165123',{exact:true})).toBeVisible();
});

test('card failure has retry and polling stops when leaving guard',async({page})=>{
  const polls=await setup(page,{failure:true});
  await expect(page.getByText('Thẻ tạm thời không tải được')).toBeVisible();
  await page.getByRole('button',{name:'Thử lại',exact:true}).click();
  await page.getByRole('link',{name:'Nhật ký vi phạm'}).click();
  const before=polls();await page.waitForTimeout(1300);expect(polls()).toBe(before);
});

test('independent plate is visible with a crop and OCR but no invented person',async({page})=>{
  await setup(page,{best:true,plateOnly:true});
  const card=page.getByTestId('recognition-card');
  await expect(card.getByText('Biển số chưa ghép xe',{exact:true})).toBeVisible();
  await expect(card.getByRole('img',{name:'Ảnh biển số',exact:true})).toBeVisible();
  await expect(card.getByRole('img',{name:'Ảnh người',exact:true})).toHaveCount(0);
  await expect(card.getByText('89F123792',{exact:true})).toBeVisible();
  await expect(card.getByRole('link',{name:'Tải ảnh biển đã chọn'})).toHaveAttribute('href','/guard/plate_best/-20003?gate=main&epoch=0');
  expect(await page.evaluate(()=>window.testSpeech)).toBe(0);
});
