// Optional end-to-end QA. npm ci; npx playwright install chromium.
import {chromium} from 'playwright';import fs from 'node:fs/promises';
const base=process.env.QA_URL||'http://127.0.0.1:8765',exe=process.env.CHROMIUM_PATH;
const browser=await chromium.launch({headless:true,...(exe?{executablePath:exe}:{}),args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1080}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto(base);await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('就绪'),{timeout:30000});
await page.setInputFiles('#kanji','.research-fonts/noto-sans-jp-black.ttf');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('字体已加载'));
await page.setInputFiles('#kana','.research-fonts/ShipporiMincho-SemiBold.ttf');await page.waitForFunction(()=>!document.querySelector('#generate').disabled);
await page.click('#generate');await page.waitForFunction(()=>document.querySelectorAll('.candidate').length===6,{timeout:60000});
for(const format of ['PNG','SVG']){const event=page.waitForEvent('download');await page.locator('.candidate').first().getByRole('button',{name:format,exact:true}).click();const download=await event;await download.saveAs('analysis/browser-output.'+format.toLowerCase());}
await page.screenshot({path:'analysis/ui-generated.png',fullPage:true});
await page.setViewportSize({width:390,height:844});await page.screenshot({path:'analysis/ui-mobile.png',fullPage:true});
if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Mobile horizontal overflow');
if(errors.length)throw Error('Page errors: '+errors.join('; '));
await page.click('#clear');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('已清理'));
await fs.writeFile('analysis/browser_qa.json',JSON.stringify({base,checks:['font_upload','six_candidates','png_download','svg_download','mobile_no_overflow','clear_fonts','no_page_errors'],status:'passed'},null,2));
console.log('Browser QA passed');await browser.close();
