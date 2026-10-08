(() => {
  const panel = document.querySelector('#auth-panel');
  const loginForm = document.querySelector('#auth-login');
  const passwordForm = document.querySelector('#auth-password');
  const message = document.querySelector('#auth-message');
  const shell = document.querySelector('.app-shell');
  const nativeFetch = window.fetch.bind(window);
  let dashboardStarted = false;

  // Every application mutation uses an explicit same-origin request header.
  window.fetch = async (input, options = {}) => {
    const target = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (target.origin === location.origin) {
      const headers = new Headers(options.headers || (input instanceof Request ? input.headers : {}));
      headers.set('X-InfraBox-Request', '1');
      options = { ...options, headers };
    }
    const response = await nativeFetch(input, options);
    if (dashboardStarted && target.pathname.startsWith('/api/') && response.status === 401) {
      dashboardStarted = false;
      shell.hidden = true;
      location.replace('/');
    }
    return response;
  };

  function notice(text) { message.textContent = text; }
  function showPassword(required) {
    loginForm.hidden = true;
    passwordForm.hidden = false;
    document.querySelector('#auth-title').textContent = 'Change password';
    notice(required ? 'Set a personal admin password before opening InfraBox.' : 'Changing your password signs out other sessions.');
    document.querySelector('#auth-password-cancel').hidden = required;
    document.querySelector('#auth-current-password').focus();
  }
  async function api(path, data) {
    const response = await fetch(`/api/v1/auth/${path}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    });
    const value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Check the form and try again.');
    return value;
  }
  function script(path) {
    return new Promise((resolve, reject) => {
      const element = document.createElement('script');
      element.src = path;
      element.onload = resolve;
      element.onerror = () => reject(new Error('Could not load the dashboard. Reload to try again.'));
      document.body.append(element);
    });
  }
  async function openDashboard() {
    if (dashboardStarted) return;
    dashboardStarted = true;
    panel.hidden = true;
    shell.hidden = false;
    try {
      await script('/kvm-video.js?v=complete-frames-1');
      await script('/app-0.3.45-live-record.js?v=complete-frames-1');
      await script('/remote-assist.js?v=admin-auth-1');
    } catch (error) {
      shell.hidden = true;
      panel.hidden = false;
      notice(error.message);
    }
  }
  async function submit(form, action) {
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    notice('Please wait…');
    try { await action(); }
    catch (error) { notice(error.message); }
    finally { button.disabled = false; }
  }
  loginForm.addEventListener('submit', (event) => {
    event.preventDefault();
    submit(loginForm, async () => {
      await api('login', {
        username: document.querySelector('#auth-username').value,
        password: document.querySelector('#auth-login-password').value,
      });
      loginForm.reset();
      await openDashboard();
    });
  });
  passwordForm.addEventListener('submit', (event) => {
    event.preventDefault();
    submit(passwordForm, async () => {
      const next = document.querySelector('#auth-new-password').value;
      if (next !== document.querySelector('#auth-confirm-password').value) throw new Error('Passwords do not match.');
      await api('password', { current_password: document.querySelector('#auth-current-password').value, new_password: next });
      passwordForm.reset();
      location.replace('/');
    });
  });
  const account = document.querySelector('.admin-account');
  const accountToggle = document.querySelector('#auth-admin-toggle');
  const accountMenu = document.querySelector('#auth-admin-menu');
  function closeAccountMenu() {
    accountMenu.hidden = true;
    accountToggle.setAttribute('aria-expanded', 'false');
  }
  accountToggle.addEventListener('click', () => {
    accountMenu.hidden = !accountMenu.hidden;
    accountToggle.setAttribute('aria-expanded', String(!accountMenu.hidden));
  });
  document.addEventListener('click', (event) => {
    if (!account.contains(event.target)) closeAccountMenu();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !accountMenu.hidden) {
      closeAccountMenu();
      accountToggle.focus();
    }
  });
  account.addEventListener('focusout', (event) => {
    if (!account.contains(event.relatedTarget)) closeAccountMenu();
  });
  document.querySelector('#auth-logout').addEventListener('click', async () => {
    try { await api('logout', {}); location.replace('/'); }
    catch (error) { window.alert(error.message); }
  });
  document.querySelector('#auth-change-password').addEventListener('click', () => location.assign('/?password=1'));

  async function initialize() {
    if (location.protocol !== 'https:') {
      location.replace(`https://${location.host}${location.pathname}${location.search}`);
      return;
    }
    try {
      const response = await fetch('/api/v1/auth/session', { cache: 'no-store' });
      if (!response.ok) throw new Error('Sign-in service is unavailable. Reload to try again.');
      const value = await response.json();
      if (!value.authenticated) {
        notice('Sign in to manage this appliance.');
        document.querySelector('#auth-username').focus();
      } else if (new URLSearchParams(location.search).has('password')) {
        showPassword(false);
      } else await openDashboard();
    } catch (error) { notice(error.message); }
  }
  initialize();
})();
