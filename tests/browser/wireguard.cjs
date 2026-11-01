const {chromium}=require('playwright-core');
const fs=require('fs'),path=require('path'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
 async function setup(role){
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const html=fs.readFileSync('frontend/src/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,'');
  await page.setContent(html);
  for(const file of ['styles.css','ap-access.css','remote-assist.css','wireguard.css','mobile.css'])await page.addStyleTag({path:path.resolve('frontend/src',file)});
  await page.evaluate(role=>{
   document.querySelector('#auth-panel').hidden=true;document.querySelector('.app-shell').hidden=false;
   document.querySelectorAll('[data-view-section]').forEach(p=>p.hidden=p.id!=='settings-panel');
   window.fixture={role,calls:[],state:{installed:true,wireguard_installed:true,stale:false,pending:false,enabled:false,autostart:false,state:'off',device_name:'infrabox-test'}};
   window.getJson=async url=>url.includes('auth/session')?{authenticated:true,username:role==='admin'?'admin':'operator',role}:structuredClone(fixture.state);
   window.fetch=async(url,options)=>{fixture.calls.push({url,options});return{ok:true,json:async()=>({request_id:'request-'+fixture.calls.length})}};
  },role);
  await page.addScriptTag({path:path.resolve('frontend/src/wireguard.js')});
  await page.waitForFunction(()=>document.querySelector('#wg-state').textContent==='Disconnected');
  return{page,errors};
 }
 const {page,errors}=await setup('admin');
 assert.equal(await page.locator('#wg-quick input').count(),0);
 assert.equal(await page.locator('#wg-quick-restore,#wg-enroll').count(),0);
 await page.locator('#wg-quick button').click();
 assert.equal(await page.evaluate(()=>fixture.calls[0].url),'/api/v1/wireguard/central-register');
 await page.evaluate(()=>Object.assign(fixture.state,{enrollment:{public_key:'NEW-DEVICE-PUBLIC'},central_vpn:{status:'PENDING',updated_at:Date.now()/1000},last_result:{request_id:'request-1',ok:true,message:'Request queued'}}));
 await page.locator('[data-view="settings"]').click();
 await page.waitForFunction(()=>document.querySelector('#wg-quick-status').textContent.includes('Waiting for dashboard approval'));
 assert(await page.locator('#wg-delete').isEnabled());
 page.once('dialog',d=>d.dismiss());await page.locator('#wg-delete').click();
 assert.equal(await page.evaluate(()=>fixture.calls.length),1);
 page.once('dialog',d=>d.accept());await page.locator('#wg-delete').click();
 const deletion=await page.evaluate(()=>fixture.calls[1]);
 assert.equal(deletion.url,'/api/v1/wireguard');assert.equal(deletion.options.method,'DELETE');
 await page.evaluate(()=>Object.assign(fixture.state,{enrollment:null,central_vpn:{status:'DELETE_PENDING',updated_at:Date.now()/1000},last_result:{request_id:'request-2',ok:true,message:'Local profile removed'}}));
 await page.locator('[data-view="settings"]').click();
 await page.waitForFunction(()=>document.querySelector('#wg-quick-status').textContent.includes('Server deletion is pending'));
 assert(await page.locator('#wg-quick button').isDisabled());
 await page.evaluate(()=>Object.assign(fixture.state,{central_vpn:{status:'DELETED',updated_at:Date.now()/1000-300}}));
 await page.locator('[data-view="settings"]').click();
 await page.waitForFunction(()=>document.querySelector('#wg-quick-status').textContent.includes('deleted on both sides'));
 assert(await page.locator('#wg-quick button').isEnabled());
 await page.locator('#wg-quick button').click();
 assert.equal(await page.evaluate(()=>fixture.calls[2].url),'/api/v1/wireguard/central-register');
 await page.setViewportSize({width:390,height:844});
 assert(await page.locator('#wireguard-settings').evaluate(e=>e.scrollWidth<=e.clientWidth));
 await page.locator('#wireguard-settings').screenshot({path:'/tmp/kdx-vpn-delete-mobile.png'});
 assert.deepEqual(errors,[]);
 const viewer=await setup('operator');
 for(const selector of ['#wg-quick button','#wg-delete','#wg-autostart'])assert(await viewer.page.locator(selector).isDisabled());
 assert.equal(await viewer.page.evaluate(()=>fixture.calls.length),0);assert.deepEqual(viewer.errors,[]);
 console.log('Device-key request, confirmed two-sided deletion, offline retry, fresh setup, no restore, mobile and viewer checks passed.');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
