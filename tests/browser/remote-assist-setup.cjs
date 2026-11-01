const {chromium}=require('../../dashboard/frontend/node_modules/playwright-core');
const fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
 const page=await browser.newPage({viewport:{width:1280,height:1000}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 let html=fs.readFileSync('frontend/src/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,'');
 await page.setContent(html);await page.addStyleTag({path:path.resolve('frontend/src/styles.css')});
 await page.evaluate(()=>{
  document.querySelector('#auth-panel').hidden=true;document.querySelector('.app-shell').hidden=false;
  document.querySelectorAll('[data-view-section]').forEach(p=>p.hidden=p.id!=='remote-assist-panel');
  window.formatBytes=n=>String(n)+' B';
  window.fixture={calls:[],setup:0,state:{installed:true,stale:false,pending:false,enabled:false,profile:null,wan:[],state:'setup_required',central_vpn:{status:'PENDING'},last_result:{request_id:'old-failure',ok:false,message:'VPN profile is required'}}};
  window.getJson=async url=>url.includes('auth/session')?{authenticated:true,username:'admin',role:'admin'}:structuredClone(fixture.state);
  window.fetch=async(url,options)=>{fixture.calls.push({url,options});return{ok:true,json:async()=>({request_id:'new-action'})}};
  document.querySelector('[data-view="settings"]').addEventListener('click',()=>fixture.setup++);
 });
 await page.addScriptTag({path:path.resolve('frontend/src/remote-assist.js')});
 await page.waitForFunction(()=>document.querySelector('#ra-toggle').textContent==='Set up VPN');
 assert(await page.locator('#ra-boot').isDisabled());
 assert((await page.locator('#ra-message').textContent()).includes('Waiting for approval'));
 await page.locator('#ra-toggle').click();
 assert.equal(await page.evaluate(()=>fixture.calls.length),0);
 assert.equal(await page.evaluate(()=>fixture.setup),1);
 // Recovery keeps the same last-result ID, as in the real host bridge.
 await page.evaluate(()=>Object.assign(fixture.state,{enabled:true,profile:{name:'InfraBox VPN'},state:'connected',central_vpn:{status:'ACTIVE'}}));
 await page.locator('[data-view="remote-assist"]').click();
 await page.waitForFunction(()=>document.querySelector('#ra-toggle').textContent==='Turn off');
 assert(!(await page.locator('#ra-message').textContent()).includes('VPN profile is required'));
 assert(!(await page.locator('#ra-message').getAttribute('class')||'').includes('ra-error'));
 await page.locator('#ra-toggle').click();
 assert.equal(await page.evaluate(()=>fixture.calls[0].url),'/api/v1/remote-assist/disable');
 assert.deepEqual(errors,[]);
 console.log('Missing profile routes to setup; pending approval is explained; stale profile error clears after recovery; existing connection controls preserved.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
