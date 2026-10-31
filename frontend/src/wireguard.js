(() => {
  const panel = document.querySelector('#wireguard-settings');
  if (!panel) return;
  panel.innerHTML = `
    <div class="settings-group-heading"><div><strong>WireGuard VPN</strong><p>Register this InfraBox with an approved VPN server. Existing Remote Assist controls use the same connection.</p></div><span id="wg-state" class="badge pending">Checking…</span></div>
    <p id="wg-message" role="status"></p>
    <form id="wg-quick">
      <label>VPN server address<input name="host" required placeholder="vpn.example.com" autocomplete="off"></label>
      <label>Username<input name="username" required value="root" autocomplete="off"></label>
      <label>Password<input name="password" type="password" required autocomplete="new-password"></label>
      <details><summary>Advanced connection settings</summary>
        <label>SSH port<input name="port" type="number" min="1" max="65535" value="22" required></label>
        <label>Public VPN endpoint (optional)<input name="endpoint" placeholder="vpn.example.com:51820"></label>
        <p>Leave the VPN endpoint empty to use the server's saved settings.</p>
      </details>
      <button type="submit" disabled>Register &amp; connect</button>
      <p>Your password is used for this setup only and is not saved. Use the VPN server access provided by your administrator.</p>
    </form>
    <p id="wg-quick-status" role="status"></p>
    <div><button id="wg-quick-connect" type="button" disabled>Connect</button> <button id="wg-quick-disconnect" type="button" disabled>Disconnect</button> <button id="wg-quick-restore" type="button" hidden disabled>Restore &amp; connect</button></div>
    <details id="wg-advanced"><summary>Advanced / manual setup</summary>
    <p id="wg-next" role="status"></p>
    <ol class="wg-steps" aria-label="VPN setup steps">
      <li id="wg-step-1"><h3><span>1</span> Device identity <small id="wg-progress-1"></small></h3>
        <p>Create this InfraBox's identity. An existing identity can be reused after deleting a profile.</p>
        <button id="wg-identity" type="button" disabled>Create device identity</button>
        <details><summary>Public key and registration request</summary>
          <label>Device public key<textarea id="wg-public-key" readonly rows="2" spellcheck="false"></textarea></label>
          <div><button id="wg-copy" type="button" disabled>Copy public key</button> <button id="wg-request" type="button" disabled>Download registration request</button></div>
        </details>
      </li>
      <li id="wg-step-2"><h3><span>2</span> Server approval <small id="wg-progress-2"></small></h3>
        <p id="wg-enrollment-hint"></p>
        <p>For a new server approval, send the registration request from step 1 to your VPN administrator. They can authorize automatic registration or return an approved JSON file for step 3.</p>
      </li>
      <li id="wg-step-3"><h3><span>3</span> Install VPN profile <small id="wg-progress-3"></small></h3>
        <button id="wg-enroll" type="button" disabled>Generate &amp; Register</button>
        <p>Installing a profile does not connect the VPN. Restoring a previous approval keeps its assigned IP and server settings; it does not create a new server peer.</p>
        <details id="wg-manual-options"><summary>Use an approved file or enter approved settings</summary>
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
        </details>
      </li>
      <li id="wg-step-4"><h3><span>4</span> Connect and verify <small id="wg-progress-4"></small></h3>
        <p id="wg-connection-hint">Install a profile in step 3 before connecting.</p>
        <div><button id="wg-connect" type="button" disabled>Connect</button> <button id="wg-disconnect" type="button" disabled>Disconnect</button> <button id="wg-restart" type="button" disabled>Restart VPN</button></div>
        <label><input id="wg-autostart" type="checkbox" disabled> Automatically connect after startup</label>
      </li>
    </ol>
    <details><summary>Connection details</summary><dl id="wg-summary"></dl></details>
    </details>
    <p class="muted">VPN routes are limited to the approved private networks. Customer LAN access and default routing are unchanged.</p>`;
  const node = id => panel.querySelector(`#wg-${id}`);
  let state, admin = false, busy = false, pending = null, submitted = 0;
  let requestedAutostart = null;
  let quickBusy = false;
  const trustedServers = new Map();
  let pendingTimeout = 100000;
  const labels = {off:'Disconnected',connected:'Connected',waiting_handshake:'Waiting for handshake',
    disconnected:'Disconnected',setup_required:'Registration required',unavailable:'Unavailable',stop_failed:'Disconnect failed'};
  const message = text => { node('message').textContent = text; };
  function render() {
    if (!state) return;
    const disabled = !admin || quickBusy || busy || pending || state.pending || !state.installed || !state.wireguard_installed || state.stale;
    const registered = Boolean(state.endpoint);
    node('quick').querySelector('button[type=submit]').disabled = Boolean(disabled || state.enabled);
    node('quick-connect').disabled = Boolean(disabled || !registered || state.enabled);
    node('quick-disconnect').disabled = Boolean(disabled || !state.enabled);
    node('quick-restore').hidden = registered || state.auto_enrollment?.state !== 'reply_cached';
    node('quick-restore').disabled = Boolean(disabled || !state.auto_enrollment?.ready);
    node('quick-status').textContent = !admin ? 'Administrator access is required to set up VPN.'
      : state.stale || !state.installed ? 'VPN host status is unavailable.'
      : quickBusy || busy || pending || state.pending ? 'Setup in progress…'
      : state.state === 'connected' ? 'Connected. VPN server handshake verified.'
      : state.enabled ? 'Connecting… Waiting for the VPN server handshake.'
      : registered ? 'VPN is configured. Select Connect.'
      : state.auto_enrollment?.state === 'reply_cached' ? 'A previous setup is available. Select Restore & connect, or enter a different server above.'
      : 'Enter your server address and login, then select Register & connect.';

    node('state').textContent = state.stale ? 'Status unavailable' : labels[state.state] || state.state;
    node('public-key').value = state.enrollment?.public_key || '';
    node('identity').disabled = Boolean(disabled || state.enrollment);
    node('enroll').disabled = Boolean(disabled || registered || state.enabled || !state.auto_enrollment?.ready);
    const auto = state.auto_enrollment || {};
    const cached = auto.state === 'reply_cached';
    node('enroll').textContent = cached ? 'Restore previous registration' : 'Generate & Register';
    const explanations = {
      expired: 'Automatic registration approval expired. Ask your VPN administrator to renew it, or import their approved JSON file in step 3.',
      not_authorized: 'This device has no automatic registration approval. Request approval from your VPN administrator, or use their approved JSON file in step 3.',
      invalid_reply: 'The saved registration does not match this device. Request a new approval from your VPN administrator.',
      registered: 'A VPN profile is installed. Continue to step 4 to connect.',
      reply_cached: 'A previous approval is saved for this device. Select Restore previous registration in step 3. If your administrator removed or changed the server peer, request a new approval instead.',
      authorized: 'Automatic registration approval is available. Continue to step 3 before the approval expires.',
    };
    node('enrollment-hint').textContent = registered
      ? explanations.registered
      : explanations[auto.state] || explanations.not_authorized;
    const next = registered ? 4 : state.enrollment ? (auto.ready ? 3 : 2) : 1;
    node('next').textContent = !admin ? 'Read-only: an administrator must complete setup.'
      : state.stale || !state.installed ? 'Host status is unavailable. Setup will resume when the host responds.'
      : busy || pending || state.pending ? 'Applying your request. Wait for the result before continuing.'
      : state.state === 'connected' ? 'VPN connected: the server handshake is verified.'
      : `Next: step ${next} — ${['','create the device identity','request server approval','install the approved profile','connect and verify the VPN'][next]}.`;
    const progress = [Boolean(state.enrollment), registered || Boolean(auto.ready), registered, state.state === 'connected'];
    for (let i = 1; i <= 4; i++) {
      node(`progress-${i}`).textContent = progress[i-1] ? 'Ready' : i === next ? 'Next' : 'Pending';
      node(`step-${i}`).classList.toggle('wg-current', i === next && !progress[3]);
      if (i === next && !progress[3]) node(`step-${i}`).setAttribute('aria-current', 'step');
      else node(`step-${i}`).removeAttribute('aria-current');
    }
    node('connection-hint').textContent = state.state === 'connected'
      ? 'VPN connected. The server handshake is verified.'
      : state.enabled ? 'VPN is enabled. Waiting for a verified server handshake; enabling alone does not confirm connectivity.'
      : registered ? 'Select Connect, then wait for the server handshake.' : 'Install a profile in step 3 before connecting.';
    node('copy').disabled = !state.enrollment;
    node('request').disabled = !state.enrollment;
    node('connect').disabled = Boolean(disabled || !registered || state.enabled);
    node('disconnect').disabled = Boolean(disabled || !state.enabled);
    node('restart').disabled = Boolean(disabled || !registered);
    node('autostart').disabled = Boolean(disabled || !registered);
    node('autostart').checked = requestedAutostart ?? Boolean(state.autostart);
    panel.querySelectorAll('form:not(#wg-quick) button').forEach(button => {
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
  async function setupRequest(path, payload) {
    const response = await fetch(`/api/v1/wireguard${path}`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload),
    });
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'VPN setup failed');
    return value;
  }
  async function waitForHost() {
    const until = Date.now() + 90000;
    while (pending && Date.now() < until) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      await refresh();
    }
    if (pending || !state?.last_result?.ok) throw new Error(state?.last_result?.message || 'VPN setup result could not be confirmed');
  }
  node('quick').addEventListener('submit', async event => {
    event.preventDefault();
    if (!admin || quickBusy || busy || pending) return;
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    values.port = Number(values.port);
    values.host = values.host.trim(); values.username = values.username.trim();
    quickBusy = true; render();
    try {
      message('Checking server access…');
      const check = await setupRequest('/server-check', {host:values.host, port:values.port});
      const server = `${values.host}:${values.port}`;
      if (trustedServers.get(server) !== check.fingerprint) {
        if (!window.confirm(`Trust VPN server ${server}?\nSSH identity: ${check.fingerprint}\nVerify this identity with your administrator before continuing.`)) return;
        trustedServers.set(server, check.fingerprint);
      }
      values.fingerprint = check.fingerprint;
      if (!state.enrollment) {
        message('Preparing this InfraBox…');
        if (!await send('/identity')) throw new Error('Could not create device identity');
        await waitForHost();
      }
      message('Registering this InfraBox with the VPN server…');
      const accepted = await setupRequest('/quick-register', values);
      pending = accepted.request_id; submitted = Date.now(); pendingTimeout = 100000;
      message('Installing VPN settings and connecting…');
    } catch (error) { message(error.message); }
    finally { values.password = ''; form.elements.password.value = ''; quickBusy = false; render(); }
  });
  node('quick-connect').addEventListener('click', () => send('/connect'));
  node('quick-disconnect').addEventListener('click', () => send('/disconnect'));
  node('quick-restore').addEventListener('click', async () => {
    if (quickBusy || busy || pending) return;
    quickBusy = true; render();
    try {
      if (await send('/enroll')) { await waitForHost(); await send('/connect'); }
    } catch (error) { message(error.message); }
    finally { quickBusy = false; render(); }
  });
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
