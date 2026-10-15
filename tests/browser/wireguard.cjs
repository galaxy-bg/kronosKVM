const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');
const assert = require('assert');
const root = process.cwd();
(async () => {
 const browser = await chromium.launch({channel:'chrome',headless:true});
 async function setup(role) {
  const page = await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  let html=fs.readFileSync(path.join(root,'frontend/src/index.html'),'utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,'');
  await page.setContent(html);
  for(const file of ['styles.css','ap-access.css','remote-assist.css','wireguard.css','mobile.css']) {
   await page.addStyleTag({path:path.join(root,'frontend/src',file)});
  }
  await page.evaluate((role)=>{
   document.querySelector('#auth-panel').hidden=true;
   document.querySelector('.app-shell').hidden=false;
   document.querySelectorAll('[data-view-section]').forEach(p=>p.hidden=p.id!=='settings-panel');
   window.fixture={role, calls:[], state:{installed:true,stale:false,pending:false,enabled:false,
     autostart:false,state:'off',device_name:'infrabox-000865dd',wireguard_installed:true}};
   window.getJson=async path=>path.includes('auth/session')?{authenticated:true,username:role==='admin'?'admin':'operator',role}:structuredClone(window.fixture.state);
   window.fetch=async (url,options)=>{
    window.fixture.calls.push({url,options});
    return {ok:true,json:async()=>({request_id:'request-'+window.fixture.calls.length})};
   };
  },role);
  await page.addScriptTag({path:path.join(root,'frontend/src/wireguard.js')});
  await page.waitForFunction(()=>document.querySelector('#wg-state').textContent==='Disconnected');
  return {page,errors};
 }
 const {page,errors}=await setup('admin');
 await page.locator('#wg-identity').click();
 assert.equal(await page.locator('#wg-identity').isDisabled(),true);
 assert.equal(await page.evaluate(()=>fixture.calls[0].url),'/api/v1/wireguard/identity');
 await page.evaluate(()=>{fixture.state.enrollment={version:1,device_id:'10000000000865dd',hostname:'infrabox-000865dd',public_key:'PUBLIC-ONLY',request_id:'device-request'};fixture.state.last_result={request_id:'request-1',ok:true,message:'Identity ready'};});
 await page.locator('[data-view="settings"]').click();
 await page.waitForFunction(()=>document.querySelector('#wg-public-key').value==='PUBLIC-ONLY');
 assert.equal(await page.locator('#wg-request').isEnabled(),true);
 await page.locator('#wg-server').evaluate(el=>el.closest('details').open=true);
 await page.locator('#wg-server [name=address]').fill('10.77.0.11/32');
 await page.locator('#wg-server [name=endpoint]').fill('vpn.example.com:51820');
 await page.locator('#wg-server [name=server_public_key]').fill('SERVER-PUBLIC');
 await page.locator('#wg-server button').click();
 const registration=await page.evaluate(()=>JSON.parse(fixture.calls[1].options.body));
 assert.equal(registration.allowed_ips,'10.77.0.0/24');
 assert.equal(registration.public_key,'PUBLIC-ONLY');
 assert.equal('private_key' in registration,false);
 await page.evaluate(()=>{Object.assign(fixture.state,{endpoint:'vpn.example.com:51820',vpn_ip:'10.77.0.11',allowed_ips:'10.77.0.0/24',last_result:{request_id:'request-2',ok:true,message:'Registered'}});});
 await page.locator('[data-view="settings"]').click();
 await page.waitForFunction(()=>!document.querySelector('#wg-connect').disabled);
 await page.locator('#wg-connect').click();
 assert.equal(await page.evaluate(()=>fixture.calls[2].url),'/api/v1/wireguard/connect');
 await page.evaluate(()=>{Object.assign(fixture.state,{enabled:true,state:'waiting_handshake',last_result:{request_id:'request-3',ok:true,message:'Applied'}});});
 await page.locator('[data-view="settings"]').click();
 await page.waitForFunction(()=>!document.querySelector('#wg-disconnect').disabled);
 assert.equal(await page.locator('#wg-state').textContent(),'Waiting for handshake');
 await page.locator('#wg-disconnect').click();
 assert.equal(await page.evaluate(()=>fixture.calls[3].url),'/api/v1/wireguard/disconnect');
 await page.evaluate(()=>{Object.assign(fixture.state,{enabled:false,state:'off',last_result:{request_id:'request-4',ok:true,message:'Disconnected'}});});
 await page.locator('[data-view="settings"]').click();
 await page.waitForFunction(()=>!document.querySelector('#wg-autostart').disabled);
 await page.locator('#wg-autostart').check();
 assert.equal(await page.evaluate(()=>fixture.calls[4].url),'/api/v1/wireguard/enable-autostart');
 await page.evaluate(()=>{fixture.state.autostart=true;fixture.state.last_result={request_id:'request-5',ok:true,message:'Automatic startup enabled'};});
 await page.locator('[data-view="settings"]').click();
 await page.waitForFunction(()=>!document.querySelector('#wg-autostart').disabled);
 assert.equal(await page.locator('#wg-autostart').isChecked(),true);
 await page.locator('#wireguard-settings').screenshot({path:process.env.KDX_WG_SCREENSHOT || '/tmp/kdx-wireguard-settings.png'});
 assert.deepEqual(errors,[]);
 const automatic=await setup('admin');
 assert.equal(await automatic.page.locator('#wg-enroll').isDisabled(),true);
 await automatic.page.evaluate(()=>{fixture.state.auto_enrollment={ready:true,state:'authorized'};});
 await automatic.page.locator('[data-view="settings"]').click();
 await automatic.page.waitForFunction(()=>!document.querySelector('#wg-enroll').disabled);
 await automatic.page.locator('#wg-enroll').click();
 assert.equal(await automatic.page.evaluate(()=>fixture.calls[0].url),'/api/v1/wireguard/enroll');
 await automatic.page.evaluate(()=>{Object.assign(fixture.state,{
   enrollment:{public_key:'AUTOMATIC-PUBLIC-KEY',hostname:'infrabox-000865dd'},
   endpoint:'vpn.example.com:51820',vpn_ip:'10.77.0.11',allowed_ips:'10.77.0.0/24',
   auto_enrollment:{ready:false,state:'registered'},
   last_result:{request_id:'request-1',ok:true,message:'Registered'},
 });});
 await automatic.page.locator('[data-view="settings"]').click();
 await automatic.page.waitForFunction(()=>!document.querySelector('#wg-connect').disabled);
 assert.equal(await automatic.page.locator('#wg-enroll').isDisabled(),true);
 assert.equal(await automatic.page.locator('#wg-public-key').inputValue(),'AUTOMATIC-PUBLIC-KEY');
 assert.deepEqual(automatic.errors,[]);
 const readOnly=await setup('operator');
 assert.equal(await readOnly.page.locator('#wg-identity').isDisabled(),true);
 assert.equal(await readOnly.page.locator('#wg-autostart').isDisabled(),true);
 assert.equal(await readOnly.page.evaluate(()=>fixture.calls.length),0);
 assert.deepEqual(readOnly.errors,[]);
 console.log('Browser checks passed: manual/automatic registration, public identity, connect/disconnect, autostart, read-only role; no page errors.');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
