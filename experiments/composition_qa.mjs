import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base=process.env.QA_URL||'http://127.0.0.1:8767',browser=await chromium.launch({executablePath:'/home/ubuntu/.cache/ms-playwright/chromium-1243/chrome-linux-arm64/chrome',headless:true}),page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],failures=[],calls=[];
page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=400)failures.push(r.url());});page.on('request',r=>{if(r.url().includes('/api/plan')||r.url().includes('/api/translate'))calls.push(r.url());});
try{
 await page.goto(base+'/composition-study.html');await page.waitForFunction(()=>document.querySelector('#study-status').textContent==='86 条标题');assert.equal(await page.locator('.reference-case').count(),8);
 const data=await (await page.request.get(base+'/composition-study/index.json')).json();assert.equal(data.cases.length,86);
 for(const c of data.cases){assert.equal(c.arms.previous.candidates.length,6);assert.equal(c.arms.composition.candidates.length,6);}
 await page.locator('#study-search').fill('s048');await page.waitForFunction(()=>document.querySelectorAll('.reference-case').length===1);assert.equal(await page.locator('.composition-triplet>div').count(),3);
 await page.locator('button[aria-label="s048 构图实验 候选 6"]').click();assert.equal(await page.locator('button[aria-label="s048 构图实验 候选 6"]').getAttribute('aria-pressed'),'true');assert.match(await page.locator('[data-arm=composition]>img').getAttribute('src'),/composition-6.png/);
 assert.match(await page.locator('[data-arm=previous]>img').getAttribute('src'),/previous-1.png/);
 const svg=await page.request.get(base+await page.locator('[data-arm=composition] .reference-downloads a').last().getAttribute('href'));assert.equal(svg.status(),200);assert.match(await svg.text(),/<path/);
 await page.locator('[data-arm=composition]>img').click();assert.equal(await page.locator('#study-zoom').evaluate(d=>d.open),true);await page.keyboard.press('Escape');
 await page.screenshot({path:'analysis/ui-composition-study.png',fullPage:true});
 await page.locator('#study-search').fill('');await page.locator('#study-filter').selectOption('unseen');await page.waitForFunction(()=>document.querySelectorAll('.reference-case').length===4);assert.equal(await page.locator('.reference-original').count(),0);
 await page.setViewportSize({width:390,height:844});await page.locator('[data-ui-theme=night]').click();await page.evaluate(async()=>{const images=[...document.querySelectorAll('#study-list img')];images.forEach(img=>img.loading='eager');await Promise.all(images.map(img=>img.decode()));});await page.screenshot({path:'analysis/ui-composition-study-mobile.png',fullPage:true});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.goto(base+'/composition-study.html?reference=s014');await page.waitForFunction(()=>document.querySelector('#study-status').textContent==='1 条标题');assert.equal(await page.locator('.reference-case').getAttribute('data-case'),'s014');
 assert.deepEqual(errors,[]);assert.deepEqual(failures,[]);assert.deepEqual(calls,[]);
 const result={samples:86,candidates:1032,candidate_switch:'pass',independent_arm_selection:'pass',svg_download:'pass',zoom:'pass',unseen_filter:'pass',deep_link:'pass',mobile_overflow:false,page_errors:errors,failed_requests:failures,model_calls:calls.length};await fs.writeFile('analysis/composition_qa.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
