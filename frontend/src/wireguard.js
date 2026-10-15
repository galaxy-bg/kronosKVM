(() => {
  const panel = document.querySelector('#wireguard-settings');
  if (!panel) return;
  panel.innerHTML = `
    <div class="settings-group-heading"><div><strong>WireGuard VPN</strong><p>Register this InfraBox with an approved VPN server. Existing Remote Assist controls use the same connection.</p></div><span id="wg-state" class="badge pending">Checking…</span></div>
    <p id="wg-message" role="status"></p>
    <dl id="wg-summary"></dl>
    <div><button id="wg-enroll" type="button" disabled>Generate &amp; Register</button> <button id="wg-identity" type="button" disabled>Create identity manually</button></div>
    <p id="wg-enrollment-hint" class="muted"></p>
    <label>Device public key<textarea id="wg-public-key" readonly rows="2" spellcheck="false"></textarea></label>
    <div><button id="wg-copy" type="button" disabled>Copy public key</button> <button id="wg-request" type="button" disabled>Download registration request</button></div>
    <p class="muted">Send the public registration request to your VPN administrator for approval. The device private key stays on this InfraBox.</p>
    <form id="wg-registration"><label>Approved registration response<input name="registration" type="file" accept=".json,application/json" required></label><button type="submit" disabled>Import registration</button></form>
    <details><summary>Enter approved server settings manually</summary>
      <form id="wg-server">
        <label>Assigned device VPN IP<input name="address" required placeholder="10.77.0.11/32"></label>
        <label>Server endpoint<input name="endpoint" required placeholder="vpn.example.com:51820"></label>
        <label>Server public key<input name="server_public_key" required spellcheck="false"></label>
        <label>Permitted VPN routes<input name="allowed_ips" required value="10.77.0.0/24"></label>
        <button type="submit" disabled>Save approved registration</button>
      </form>
    </details>
    <div><button id="wg-connect" type="button" disabled>Connect</button> <button id="wg-disconnect" type="button" disabled>Disconnect</button> <button id="wg-restart" type="button" disabled>Restart VPN</button></div>
    <label><input id="wg-autostart" type="checkbox" disabled> Automatically connect after startup</label>
    <p class="muted">VPN routes are limited to the approved private networks. Customer LAN access and default routing are unchanged.</p>`;
  const node = id => panel.querySelector(`#wg-${id}`);
  let state, admin = false, busy = false, pending = null, submitted = 0;
  let requestedAutostart = null;
  let pendingTimeout = 100000;
  const labels = {off:'Disconnected',connected:'Connected',waiting_handshake:'Waiting for handshake',
    disconnected:'Disconnected',setup_required:'Registration required',unavailable:'Unavailable',stop_failed:'Disconnect failed'};
  const message = text => { node('message').textContent = text; };
  function render() {
    if (!state) return;
    const disabled = !admin || busy || pending || state.pending || !state.installed || !state.wireguard_installed || state.stale;
    const registered = Boolean(state.endpoint);
    node('state').textContent = state.stale ? 'Status unavailable' : labels[state.state] || state.state;
    node('public-key').value = state.enrollment?.public_key || '';
    node('identity').disabled = Boolean(disabled || state.enrollment);
    node('enroll').disabled = Boolean(disabled || state.enabled || !state.auto_enrollment?.ready);
    const auto = state.auto_enrollment || {};
    node('enrollment-hint').textContent = auto.state === 'registered'
      ? 'Automatic registration complete. Select Connect to start the VPN.'
      : auto.ready ? 'Automatic registration is authorized. Generate & Register creates the device identity, registers it with the server and imports the approved settings.'
      : 'For automatic registration, ask your administrator to authorize this device. Manual registration remains available below.';
    node('copy').disabled = !state.enrollment;
    node('request').disabled = !state.enrollment;
    node('connect').disabled = Boolean(disabled || !registered || state.enabled);
    node('disconnect').disabled = Boolean(disabled || !state.enabled);
    node('restart').disabled = Boolean(disabled || !registered);
    node('autostart').disabled = Boolean(disabled);
    node('autostart').checked = requestedAutostart ?? Boolean(state.autostart);
    panel.querySelectorAll('form button').forEach(button => {
      button.disabled = Boolean(disabled || state.enabled || !state.enrollment);
    });
    const fields = [['Device', state.device_name], ['VPN IP', state.vpn_ip],
      ['Server endpoint', state.endpoint], ['Routes', state.allowed_ips],
      ['Latest handshake', state.last_handshake ? new Date(state.last_handshake * 1000).toLocaleString() : 'None'],
      ['RX / TX bytes', `${state.rx_bytes || 0} / ${state.tx_bytes || 0}`],
      ['Automatic startup', state.autostart ? 'Enabled' : 'Disabled'],
      ['WireGuard tools', state.wireguard_installed ? 'Installed' : 'Unavailable']];
    node('summary').replaceChildren();
    for (const [label, value] of fields) {
      const dt = document.createElement('dt'), dd = document.createElement('dd');
      dt.textContent = label; dd.textContent = value || '—';
      node('summary').append(dt, dd);
    }
  }
  async function refresh() {
    try {
      state = await getJson('/api/v1/wireguard');
      if (pending && state.last_result?.request_id === pending) {
        pending = null; requestedAutostart = null;
        message(state.last_result.message);
      } else if (pending && Date.now() - submitted > pendingTimeout) {
        pending = null; requestedAutostart = null;
        message('Result not confirmed. Check the current connection status before retrying.');
      }
      render();
    } catch (error) {
      if (state) { state.stale = true; render(); }
      message(error.message);
    }
  }
  async function send(path, method = 'POST', payload) {
    if (!admin || busy || pending) return false;
    busy = true; render();
    try {
      const response = await fetch(`/api/v1/wireguard${path}`, {
        method, headers: {'Content-Type':'application/json'},
        ...(payload ? {body: JSON.stringify(payload)} : {}),
      });
      const value = await response.json();
      if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Request failed');
      pending = value.request_id; submitted = Date.now();
      pendingTimeout = path === '/enroll' ? 260000 : 100000;
      message(path === '/enroll' ? 'Generating identity and registering with VPN server…' : 'Applying…');
      return true;
    } catch (error) { message(error.message); return false; }
    finally { busy = false; if (!pending) requestedAutostart = null; render(); }
  }
  node('enroll').addEventListener('click', () => send('/enroll'));
  node('identity').addEventListener('click', () => send('/identity'));
  for (const action of ['connect','disconnect','restart']) {
    node(action).addEventListener('click', () => send(`/${action}`));
  }
  node('autostart').addEventListener('change', event => {
    requestedAutostart = event.target.checked;
    send(requestedAutostart ? '/enable-autostart' : '/disable-autostart');
  });
  node('copy').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(state.enrollment.public_key); message('Public key copied.'); }
    catch { message('Select and copy the public key above.'); }
  });
  node('request').addEventListener('click', () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(state.enrollment, null, 2)], {type:'application/json'}));
    const link = document.createElement('a'); link.href = url;
    link.download = `${state.enrollment.hostname}-registration.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  node('registration').addEventListener('submit', async event => {
    event.preventDefault();
    const file = event.currentTarget.elements.registration.files[0];
    if (!file || file.size > 4096) return message('Choose registration JSON smaller than 4 KiB.');
    try {
      if (await send('/registration', 'PUT', JSON.parse(await file.text()))) node('registration').reset();
    } catch { message('Invalid registration JSON.'); }
  });
  node('server').addEventListener('submit', async event => {
    event.preventDefault();
    if (!state.enrollment) return;
    const values = Object.fromEntries(new FormData(event.currentTarget));
    await send('/registration', 'PUT', {...state.enrollment, ...values, keepalive:25});
  });
  document.querySelector('[data-view="settings"]').addEventListener('click', refresh);
  window.setInterval(() => { if (!document.querySelector('#settings-panel').hidden || pending) refresh(); }, 3000);
  getJson('/api/v1/auth/session').then(session => {
    admin = session.authenticated && session.username === 'admin' && (!session.role || session.role === 'admin');
    if (!admin) message('Read-only VPN status. Administrator access is required to change settings.');
    refresh();
  }).catch(error => message(error.message));
})();
