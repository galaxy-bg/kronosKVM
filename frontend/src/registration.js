(() => {
  const card = document.querySelector('#registration-card');
  if (!card) return;
  const label = {ACTIVE: 'Active', PENDING: 'Pending approval', ACTIVATION_REQUIRED: 'Activation required',
    REVOKED: 'Revoked', SUSPENDED: 'Suspended', EXPIRED: 'License expired',
    HARDWARE_MISMATCH: 'Hardware mismatch', NOT_CONFIGURED: 'Not configured',
    UNAVAILABLE: 'Unavailable', DENIED: 'Authorization denied'};
  const errors = {TLS_VALIDATION_FAILED: 'The server certificate could not be verified.',
    TLS_TRUST_ANCHOR_MISMATCH: 'The configured server CA does not match its trusted fingerprint.',
    STATUS_STALE: 'The registration agent has not reported recently.',
    AUTHORIZATION_EXPIRED: 'The signed authorization has expired. Reconnect to the server.',
    HARDWARE_MISMATCH: 'This installation is bound to different Raspberry Pi hardware.',
    OFFLINE_AUTHORIZATION_INVALID_OR_EXPIRED: 'No valid offline authorization is available.'};
  let running = false;
  const set = (id, value) => { document.querySelector(id).textContent = value || '—'; };
  const stamp = value => value ? new Date(value * 1000).toLocaleString() : '—';
  async function load() {
    if (running) return;
    running = true;
    try {
      const response = await fetch('/api/v1/system/registration');
      if (!response.ok) throw new Error('Registration status could not be loaded.');
      const state = await response.json();
      const badge = document.querySelector('#registration-state');
      badge.textContent = label[state.status] || 'Unavailable';
      badge.className = `badge ${state.authorized ? 'ready' : 'pending'}`;
      set('#registration-message', state.authorized
        ? state.mode === 'offline-grace' ? 'Server unreachable. Using a verified, time-limited offline authorization.'
          : 'The central server has verified this device and its license.'
        : errors[state.error] || (state.status === 'PENDING' ? 'An administrator must approve this device.'
          : state.status === 'ACTIVATION_REQUIRED' ? 'Approval received. Complete activation with the one-time token.'
          : state.installed ? 'This device is not currently authorized. Review its central registration status.'
          : 'The registration agent has not been configured.'));
      set('#registration-mode', `${state.mode === 'online' ? 'Online' : state.mode === 'offline-grace' ? 'Offline grace' : 'Offline'}${state.transport === 'https' ? ' · HTTPS' : ''}`);
      set('#registration-checked', stamp(state.checked_at));
      set('#registration-until', stamp(state.authorization_expires_at));
      set('#registration-serial', state.serial);
      set('#registration-installation', state.installation_id);
      set('#registration-device', state.device_id);
      set('#registration-license', state.license_id);
    } catch (error) {
      const badge = document.querySelector('#registration-state');
      badge.textContent = 'Unavailable'; badge.className = 'badge pending';
      set('#registration-message', error.message);
    } finally { running = false; }
  }
  document.querySelector('[data-view="settings"]')?.addEventListener('click', load);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });
  setInterval(() => { if (!document.hidden && !document.querySelector('#settings-panel').hidden) load(); }, 30000);
  load();
})();
