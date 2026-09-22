(() => {
  const panel = document.querySelector('#remote-assist-panel');
  panel.innerHTML = `
    <div class="panel-heading"><div><h2>Remote Assist</h2><p>Connect this InfraBox to your office or customer VPN.</p></div>
      <button id="ra-toggle" type="button" role="switch" aria-checked="false" disabled>Turn on</button></div>
    <div class="ra-body">
      <p id="ra-message" role="status">Loading Remote Assist…</p>
      <div class="ra-cards">
        <article><h3>USB WAN</h3><strong id="ra-wan">Checking…</strong><p id="ra-wan-detail"></p><small id="ra-uplink"></small></article>
        <article><h3>WireGuard</h3><strong id="ra-state">Off</strong><p id="ra-profile-name">No profile configured</p><small id="ra-handshake"></small><p id="ra-transfer"></p></article>
        <article><h3>Remote access</h3><a id="ra-url" hidden target="_blank" rel="noopener"></a><p id="ra-access-hint">Configure a VPN profile to get the access address.</p><button id="ra-copy" type="button" disabled>Copy address</button><small>Available to authorized peers on your VPN. This is not a public URL.</small></article>
      </div>
      <label class="ra-boot"><input id="ra-boot" type="checkbox" disabled> Automatically connect after appliance startup</label>
      <details id="ra-settings" open><summary>VPN settings</summary>
        <p>One office/customer profile. Turn Remote Assist off before replacing it. Keys are saved privately and are never shown again.</p>
        <form id="ra-import"><h3>Import WireGuard configuration</h3>
          <label>Profile name<input name="name" required maxlength="80" placeholder="Office / Customer name"></label>
          <label>WireGuard .conf file<input name="config" type="file" accept=".conf,text/plain" required></label>
          <p>Use one IPv4 peer and specific private VPN networks in AllowedIPs. Full-tunnel routes, DNS overrides and scripts are not supported.</p>
          <button type="submit">Save imported profile</button>
        </form>
        <details><summary>Enter settings manually</summary>
          <form id="ra-manual" autocomplete="off">
            <div class="ra-fields">
              <label>Profile name<input name="name" required maxlength="80" placeholder="Office"></label>
              <label>InfraBox VPN address<input name="address" required placeholder="10.80.0.2/32"></label>
              <label>Server endpoint<input name="endpoint" required placeholder="vpn.example.com:51820"></label>
              <label>Server public key<input name="public_key" required spellcheck="false"></label>
              <label>InfraBox private key<input name="private_key" type="password" required autocomplete="new-password"></label>
              <label>Preshared key (optional)<input name="preshared_key" type="password" autocomplete="new-password"></label>
              <label>Peer networks (AllowedIPs)<input name="allowed_ips" required placeholder="10.80.0.0/24"></label>
              <label>Keepalive (seconds)<input name="keepalive" type="number" min="0" max="65535" value="25" required></label>
            </div><button type="submit">Save profile</button>
          </form>
        </details>
      </details>
    </div>`;
  let state = null;
  let busy = false;
  let pendingId = null;
  let lastResultId = null;
  const node = id => panel.querySelector(`#ra-${id}`);
  const labels = {off:'Off',setup_required:'Setup required',disconnected:'Waiting for connection',
    waiting_handshake:'Waiting for VPN handshake',connected:'Connected',unavailable:'Module unavailable',
    stop_failed:'Could not stop VPN'};
  function message(text, failed = false) {
    node('message').textContent = text;
    node('message').classList.toggle('ra-error', failed);
  }
  function render() {
    if (!state) return;
    const unavailable = !state.installed || state.stale;
    const disabled = unavailable || busy || state.pending || Boolean(pendingId);
    node('toggle').disabled = disabled;
    node('toggle').textContent = state.enabled ? 'Turn off' : 'Turn on';
    node('toggle').setAttribute('aria-checked', String(state.enabled));
    node('boot').disabled = disabled;
    node('boot').checked = Boolean(state.autostart);
    node('state').textContent = unavailable ? 'Status unavailable' : labels[state.state] || state.state;
    node('profile-name').textContent = state.profile?.name || 'No profile configured';
    node('handshake').textContent = state.last_handshake
      ? `Last handshake: ${new Date(state.last_handshake * 1000).toLocaleString()}` : 'No handshake yet';
    node('transfer').textContent = `Received ${formatBytes(state.rx_bytes || 0)} · Sent ${formatBytes(state.tx_bytes || 0)}`;
    const wan = state.wan?.[0];
    node('wan').textContent = wan?.address ? 'USB network ready' : wan ? 'Waiting for IP address' : 'Waiting for USB tethering';
    node('wan-detail').textContent = wan ? `${wan.interface} · ${wan.address || 'No address'} · Gateway ${wan.gateway || '—'}` : 'Connect a phone to the Storage / WAN USB port and enable USB tethering.';
    node('uplink').textContent = `Preferred uplink: ${state.uplink || 'none'}. Ethernet is preferred; USB is the fallback. IP assignment alone does not verify internet access.`;
    node('url').hidden = !state.url;
    node('url').textContent = state.url || '';
    if (state.url) node('url').href = state.url;
    else node('url').removeAttribute('href');
    node('copy').disabled = !state.url;
    node('access-hint').textContent = state.state === 'connected'
      ? 'Connect your office computer to the same VPN, then open this address.'
      : 'The access address becomes reachable once the VPN connection is established.';
    panel.querySelectorAll('form button').forEach(button => { button.disabled = disabled || (state.enabled && Boolean(state.profile)); });
  }
  async function refresh() {
    try {
      state = await getJson('/api/v1/remote-assist');
      const result = state.last_result;
      if (result && result.request_id !== lastResultId) {
        lastResultId = result.request_id;
        if (!pendingId || result.request_id === pendingId) {
          pendingId = null;
          message(result.message, !result.ok);
        }
      }
      if (!state.installed || state.stale) message('Remote Assist status is unavailable. Check the host module.', true);
      else if (!result && !pendingId) message(state.enabled ? 'Remote Assist is enabled.' : 'Remote Assist is off. Configure your VPN profile below.');
      render();
    } catch (error) {
      if (state) { state.stale = true; render(); }
      message(error.message, true);
    }
  }
  async function send(path, method, payload) {
    if (busy || pendingId) return;
    busy = true; render();
    try {
      const response = await fetch(`/api/v1/remote-assist${path}`, {
        method, headers: {'Content-Type':'application/json'},
        ...(payload ? {body: JSON.stringify(payload)} : {}),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Request failed');
      pendingId = result.request_id;
      message('Applying settings…');
      return true;
    } catch (error) { message(error.message, true); return false; }
    finally { busy = false; render(); }
  }
  node('toggle').addEventListener('click', () => send(state.enabled ? '/disable' : '/enable', 'POST'));
  node('boot').addEventListener('change', event => send(event.target.checked ? '/boot-on' : '/boot-off', 'POST'));
  node('copy').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(state.url); message('Access address copied.'); }
    catch { message('Select the access address above and copy it.'); }
  });
  node('import').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const file = form.elements.config.files[0];
    if (!file || file.size > 16384) return message('Choose a .conf file smaller than 16 KiB.', true);
    const config = await file.text();
    if (await send('/profile', 'PUT', {name: form.elements.name.value, config})) form.reset();
  });
  node('manual').addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form));
    if (await send('/profile', 'PUT', payload)) form.reset();
  });
  document.querySelector('[data-view="remote-assist"]').addEventListener('click', refresh);
  window.setInterval(() => { if (!panel.hidden || pendingId) refresh(); }, 3000);
})();
