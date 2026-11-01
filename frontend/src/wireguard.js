(() => {
  const panel = document.querySelector('#wireguard-settings');
  if (!panel) return;
  panel.innerHTML = `
    <div class="settings-group-heading"><div><strong>WireGuard VPN</strong><p>Request access with this InfraBox's own key, then approve it in the central dashboard.</p></div><span id="wg-state" class="badge pending">Checking…</span></div>
    <p id="wg-message" role="status"></p>
    <form id="wg-quick"><p>No VPN server username or password is needed. A new setup generates a new VPN identity after deletion.</p><button type="submit" disabled>Request VPN access</button></form>
    <p id="wg-quick-status" role="status"></p>
    <div><button id="wg-quick-connect" type="button" disabled>Connect</button> <button id="wg-quick-disconnect" type="button" disabled>Disconnect</button> <button id="wg-restart" type="button" disabled>Restart VPN</button> <button id="wg-delete" type="button" disabled>Delete VPN</button></div>
    <label><input id="wg-autostart" type="checkbox" disabled> Automatically connect after startup</label>
    <details><summary>Connection details</summary><label>Device public key<textarea id="wg-public-key" readonly rows="2" spellcheck="false"></textarea></label><button id="wg-copy" type="button" disabled>Copy public key</button><dl id="wg-summary"></dl></details>
    <p class="muted">Deleting VPN removes this connection on both sides. An offline device finishes cleanup when it reconnects. Setup then requires a new key and approval; there is no restore.</p>`;
  const node = id => panel.querySelector(`#wg-${id}`);
  let state, admin = false, busy = false, pending = null, submitted = 0;
  let requestedAutostart = null;
  const message = text => { node('message').textContent = text; };
  function render() {
    if (!state) return;
    const disabled = !admin || busy || pending || state.pending || !state.installed || !state.wireguard_installed || state.stale;
    const central = state.central_vpn || {};
    const deleting = central.status === 'DELETE_PENDING';
    const registered = Boolean(state.endpoint);
    node('quick').querySelector('button').disabled = Boolean(disabled || deleting);
    node('quick-connect').disabled = Boolean(disabled || deleting || !registered || state.enabled);
    node('quick-disconnect').disabled = Boolean(disabled || !state.enabled);
    node('restart').disabled = Boolean(disabled || deleting || !registered);
    node('delete').disabled = Boolean(disabled || deleting || !(registered || state.enrollment));
    node('autostart').disabled = Boolean(disabled || deleting || !registered);
    node('autostart').checked = requestedAutostart ?? Boolean(state.autostart);
    node('public-key').value = state.enrollment?.public_key || '';
    node('copy').disabled = !state.enrollment;
    const labels = {connected:'Connected',waiting_handshake:'Waiting for handshake',off:'Disconnected',setup_required:'Registration required',unavailable:'Unavailable',stop_failed:'Disconnect failed'};
    node('state').textContent = state.stale ? 'Status unavailable' : labels[state.state] || state.state || 'Unknown';
    const messages = {REQUESTED:'Preparing your device-key request…',PENDING:'VPN request sent. Waiting for dashboard approval.',ACTIVE:'VPN access approved.',SUSPENDED:'VPN access disabled by the administrator.',ARCHIVED:'VPN removal is awaiting server confirmation.',DELETE_PENDING:'VPN removed locally. Server deletion is pending; it will retry when connectivity returns.',DELETED:'VPN deleted on both sides. Request access to create a fresh setup.',UNAVAILABLE:'Central VPN status is unavailable. Existing connection settings are preserved.'};
    const fresh = Number.isFinite(central.updated_at) && Math.abs(Date.now()/1000-central.updated_at) < 120;
    node('quick-status').textContent = !admin ? 'Administrator access is required to set up VPN.'
      : state.stale || !state.installed ? 'VPN host status is unavailable.'
      : busy || pending || state.pending ? 'Applying your request…'
      : central.status === 'DELETED' || deleting ? messages[central.status]
      : central.status && central.status !== 'NOT_REQUESTED' ? (fresh ? messages[central.status] || 'VPN request status unknown.' : 'Central VPN status is not current.')
      : state.state === 'connected' ? 'Connected. VPN server handshake verified.'
      : registered ? 'VPN is configured. Select Connect.' : 'Select Request VPN access, then approve this device in Dashboard → VPN.';
    if (central.status === 'ACTIVE' && state.state === 'connected' && fresh) node('quick-status').textContent += ' Connected; server handshake verified.';
    const fields = [['Device', state.device_name], ['VPN IP',state.vpn_ip],['Server endpoint',state.endpoint],['Routes',state.allowed_ips],['Latest handshake',state.last_handshake?new Date(state.last_handshake*1000).toLocaleString():'None'],['RX / TX bytes',`${state.rx_bytes||0} / ${state.tx_bytes||0}`],['Automatic startup',state.autostart?'Enabled':'Disabled']];
    node('summary').replaceChildren();
    for (const [label,value] of fields) { const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value||'—';node('summary').append(dt,dd); }
  }
  async function refresh() {
    try {
      state = await getJson('/api/v1/wireguard');
      if (pending && state.last_result?.request_id === pending) { pending=null;requestedAutostart=null;message(state.last_result.message); }
      else if (pending && Date.now()-submitted>100000) {pending=null;requestedAutostart=null;message('Result not confirmed. Check the current status before retrying.');}
      render();
    } catch (error) {if(state){state.stale=true;render();}message(error.message);}
  }
  async function send(path,method='POST') {
    if (!admin || busy || pending) return;
    busy=true;render();
    try {
      const response=await fetch(`/api/v1/wireguard${path}`,{method,headers:{'Content-Type':'application/json'}});
      const value=await response.json();
      if(!response.ok) throw new Error(typeof value.detail==='string'?value.detail:'VPN request failed');
      pending=value.request_id;submitted=Date.now();message('Applying…');
    } catch(error){requestedAutostart=null;message(error.message);}
    finally{busy=false;render();}
  }
  node('quick').addEventListener('submit',event=>{event.preventDefault();send('/central-register');});
  node('quick-connect').addEventListener('click',()=>send('/connect'));
  node('quick-disconnect').addEventListener('click',()=>send('/disconnect'));
  node('restart').addEventListener('click',()=>send('/restart'));
  node('delete').addEventListener('click',()=>{if(window.confirm('Delete VPN from both the InfraBox and server? The tunnel will stop and its VPN key will be removed. Offline cleanup retries automatically. A new setup requires a new key and approval.'))send('','DELETE');});
  node('autostart').addEventListener('change',event=>{requestedAutostart=event.target.checked;send(requestedAutostart?'/enable-autostart':'/disable-autostart');});
  node('copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(state.enrollment.public_key);message('Public key copied.');}catch{message('Select and copy the public key above.');}});
  document.querySelector('[data-view="settings"]').addEventListener('click',refresh);
  window.setInterval(()=>{if(!document.querySelector('#settings-panel').hidden||pending)refresh();},3000);
  getJson('/api/v1/auth/session').then(session=>{admin=session.authenticated&&session.username==='admin'&&(!session.role||session.role==='admin');refresh();}).catch(error=>message(error.message));
})();
