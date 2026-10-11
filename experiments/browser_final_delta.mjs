import {chromium} from 'playwright';
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';

const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'/home/ubuntu/.cache/ms-playwright/chromium-1243/chrome-linux-arm64/chrome',args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1100}}), errors=[];
const report={};let plans=0;
page.on('pageerror',e=>errors.push(e.message));
page.on('request',r=>{if(new URL(r.url()).pathname==='/api/plan')plans++;});
async function idle(){await page.waitForFunction(()=>!document.querySelector('#generate').disabled,{timeout:60000});}
try{
 await page.goto(process.env.TEST_URL||'http://127.0.0.1:8767');
 await page.locator('.candidate:not(.skeleton)').first().waitFor({timeout:60000});await idle();
 assert.equal(await page.locator('#kanji-select option').count(),8);
 await page.locator('#kanji-select').selectOption('source-han-sans-jp-heavy');await idle();
 assert.equal(await page.locator('#status').textContent(),'');report.cff_font='Source Han Sans JP Heavy';
 await page.locator('#count').selectOption('8');await idle();
 assert.equal(await page.locator('.candidate').count(),8);report.candidates=8;
 await page.locator('summary').click();await page.locator('#transparent').check();await idle();
 const event=page.waitForEvent('download');await page.locator('#download-png').click();const download=await event;
 const bytes=await fs.readFile(await download.path());
 const cornerAlpha=await page.evaluate(async src=>{const img=new Image();img.src=src;await img.decode();const c=document.createElement('canvas');c.width=img.width;c.height=img.height;const ctx=c.getContext('2d');ctx.drawImage(img,0,0);return ctx.getImageData(0,0,1,1).data[3];},'data:image/png;base64,'+bytes.toString('base64'));
 assert.equal(cornerAlpha,0);report.transparent_png=true;
 await page.locator('#transparent').uncheck();await idle();
 await page.locator('#text').fill('星の記憶を拾う夜明け');await page.locator('[data-mode="llm"]').click();await idle();
 assert.match(await page.locator('#provenance').textContent(),/实时/);assert.equal(plans,1);
 await page.locator('[data-palette="violet"]').click();await idle();
 await page.locator('#kanji-select').selectOption('mplus2-black');await idle();
 assert.equal(plans,1);report.font_and_palette_reuse_plan=true;
 await page.locator('#semantic-toggle').click();
 await page.locator('#semantic-replan').click();await idle();assert.equal(plans,2);report.explicit_replan=true;
 await page.locator('[data-mode="classic"]').click();await idle();
 await page.locator('#kanji-select').selectOption('noto-sans-jp-black');await idle();
 await page.locator('[data-palette="night"]').click();await idle();
 await page.locator('#count').selectOption('6');await idle();
 await page.locator('#text').fill('聖域の終わりと、崩壊の始まり');await page.locator('#generate').click();await idle();
 assert.equal(plans,2);report.A_has_no_model_requests=true;
 await page.screenshot({path:'analysis/ui-revision-desktop.png',fullPage:true});
 assert.deepEqual(errors,[]);report.page_errors=errors;
 await fs.writeFile('analysis/browser_final_delta.json',JSON.stringify(report,null,2));
 console.log(JSON.stringify(report));
}finally{await browser.close();}
