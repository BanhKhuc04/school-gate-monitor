import {test,expect} from '@playwright/test';
import {installApiFixture,loginFixture} from './isolatedFixture';
test.use({baseURL:'http://127.0.0.1:5186'});

test('gate line editor saves two points separately from ROI and reloads them',async({page})=>{
  await installApiFixture(page);
  let line=null,roiWrites=0,lineWrites=0,lineDeletes=0;
  const roi=[[.1,.1],[.9,.1],[.9,.9],[.1,.9]];
  await page.route('**/api/roi/main',route=>{
    if(route.request().method()!=='GET')roiWrites++;
    return route.fulfill({json:{gate_id:'main',points:roi}});
  });
  await page.route('**/api/roi/main/line',route=>{
    if(route.request().method()==='POST'){
      line=route.request().postDataJSON().line;lineWrites++;
    }
    if(route.request().method()==='DELETE'){
      line=null;lineDeletes++;
    }
    return route.fulfill({json:{gate_id:'main',line}});
  });
  await loginFixture(page);
  await page.goto('/admin/roi');
  await page.getByRole('button',{name:'Vạch mốc (cảnh báo sớm)',exact:true}).click();
  const canvas=page.locator('canvas');
  const box=await canvas.boundingBox();
  await canvas.click({position:{x:box.width*.2,y:box.height*.6}});
  await page.getByRole('button',{name:'Lưu vạch mốc',exact:true}).click();
  await expect(page.getByText('Lỗi: cần đúng 2 điểm để tạo vạch mốc.')).toBeVisible();
  expect(lineWrites).toBe(0);
  await canvas.click({position:{x:box.width*.8,y:box.height*.6}});
  await page.getByRole('button',{name:'Lưu vạch mốc',exact:true}).click();
  await expect(page.getByText('Đã lưu vạch mốc.',{exact:true})).toBeVisible();
  expect(lineWrites).toBe(1);expect(roiWrites).toBe(0);
  line.forEach((value,index)=>expect(value).toBeCloseTo([.2,.6,.8,.6][index],2));
  await page.reload();
  await page.getByRole('button',{name:'Vạch mốc (cảnh báo sớm)',exact:true}).click();
  await expect(page.getByRole('button',{name:'Hoàn tác điểm cuối'})).toBeEnabled();
  await page.getByRole('button',{name:'Lưu vạch mốc',exact:true}).click();
  await expect(page.getByText('Đã lưu vạch mốc.',{exact:true})).toBeVisible();
  expect(lineWrites).toBe(2);expect(roiWrites).toBe(0);
  await page.getByRole('button',{name:'Xoá vạch mốc',exact:true}).click();
  await expect(page.getByText('Đã xoá vạch mốc.',{exact:true})).toBeVisible();
  expect(lineDeletes).toBe(1);expect(roiWrites).toBe(0);
  await page.reload();
  await page.getByRole('button',{name:'Vạch mốc (cảnh báo sớm)',exact:true}).click();
  await expect(page.getByRole('button',{name:'Hoàn tác điểm cuối'})).toBeDisabled();
});
