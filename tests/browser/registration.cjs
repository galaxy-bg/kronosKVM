const {chromium}=require('../../dashboard/frontend/node_modules/playwright-core');
const fs=require('fs');const path=require('path');const assert=require('assert');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:1000}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  let html=fs.readFileSync('frontend/src/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,'');
  await page.setContent(html);await page.addStyleTag({path:path.resolve('frontend/src/styles.css')});
  await page.evaluate(()=>{
   document.querySelector('#auth-panel').hidden=true;document.querySelector('.app-shell').hidden=false;
   document.querySelectorAll('[data-view-section]').forEach(el=>el.hidden=el.id!=='settings-panel');
   window.state={installed:true,status:'ACTIVE',authorized:true,mode:'online',transport:'https',serial:'10000000000865DD',installation_id:'c96d6174-2e02-4fc7-b065-6d27809d22f2',device_id:'6998bfa8-3a28-4822-b290-ec1927cfa4b4',license_id:'36833f3a-fe4e-44d8-a956-681063c1bafe',checked_at:Date.now()/1000,authorization_expires_at:Date.now()/1000+86400};
   window.fetch=async url=>{if(url!=='/api/v1/system/registration')throw Error('Unexpected endpoint');return{ok:true,json:async()=>structuredClone(state)}};
  });
  await page.addScriptTag({path:path.resolve('frontend/src/registration.js')});
  await page.waitForFunction(()=>document.querySelector('#registration-state').textContent==='Active');
  assert.equal(await page.locator('#registration-mode').textContent(),'Online · HTTPS');
  fs.mkdirSync('artifacts/registration-wan',{recursive:true});
  await page.locator('#registration-card').screenshot({path:'artifacts/registration-wan/local-status-active.png'});
  await page.evaluate(()=>{state.mode='offline-grace';state.error='SERVER_UNREACHABLE';document.dispatchEvent(new Event('visibilitychange'))});
  await page.waitForFunction(()=>document.querySelector('#registration-mode').textContent==='Offline grace · HTTPS');
  assert((await page.locator('#registration-message').textContent()).includes('time-limited offline'));
  await page.evaluate(()=>{state.status='HARDWARE_MISMATCH';state.authorized=false;state.error='HARDWARE_MISMATCH';document.dispatchEvent(new Event('visibilitychange'))});
  await page.waitForFunction(()=>document.querySelector('#registration-state').textContent==='Hardware mismatch');
  await page.setViewportSize({width:390,height:844});
  await page.locator('#registration-card').screenshot({path:'artifacts/registration-wan/local-status-mobile.png'});
  await page.evaluate(()=>{state.status='PENDING';state.error=null;state.device_id='<img src=x onerror=alert(1)>';document.dispatchEvent(new Event('visibilitychange'))});
  await page.waitForFunction(()=>document.querySelector('#registration-state').textContent==='Pending approval');
  assert.equal(await page.locator('#registration-device img').count(),0);
  assert.equal(errors.length,0,JSON.stringify(errors));
  console.log('Local status UI: ACTIVE/HTTPS, offline grace, mismatch, pending, mobile and safe text rendering passed.');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exit(1)});
