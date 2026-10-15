/* Browser sessions use the appliance's authenticated WebSocket gateway. */
(() => {
  const sessions = new Map();
  let credentialDialog = null;
  const guac = window.Guacamole;
  const encode = (...parts) => parts.map((part) => {
    const value = String(part);
    return `${Array.from(value).length}.${value}`;
  }).join(',') + ';';

  function createTunnel(credentials) {
    const tunnel = new guac.Tunnel();
    let socket;
    let timer;
    const stop = () => {
      clearTimeout(timer);
      if (socket && socket.readyState < WebSocket.CLOSING) socket.close();
      tunnel.setState(guac.Tunnel.State.CLOSED);
    };
    tunnel.connect = () => {
      tunnel.setState(guac.Tunnel.State.CONNECTING);
      const parser = new guac.Parser();
      parser.oninstruction = (opcode, parameters) => {
        if (opcode === '') {
          clearTimeout(timer);
          tunnel.setUUID(parameters[0]);
          tunnel.setState(guac.Tunnel.State.OPEN);
        } else if (tunnel.oninstruction) tunnel.oninstruction(opcode, parameters);
      };
      socket = new WebSocket(`wss://${location.host}/api/v1/remote/ws`);
      timer = setTimeout(() => {
        if (tunnel.onerror) tunnel.onerror(new guac.Status(519, 'Connection timed out.'));
        stop();
      }, 45000);
      socket.onopen = () => {
        socket.send(JSON.stringify(credentials));
        credentials.password = '';
      };
      socket.onmessage = (event) => {
        try { parser.receive(event.data); }
        catch (_) {
          if (tunnel.onerror) tunnel.onerror(new guac.Status(519, 'Invalid gateway response.'));
          stop();
        }
      };
      socket.onerror = () => {
        if (tunnel.onerror) tunnel.onerror(new guac.Status(519, 'Connection gateway is unavailable.'));
      };
      socket.onclose = () => {
        credentials.password = '';
        clearTimeout(timer);
        if (tunnel.state === guac.Tunnel.State.CONNECTING && tunnel.onerror)
          tunnel.onerror(new guac.Status(519, 'Connection closed before the session opened.'));
        tunnel.setState(guac.Tunnel.State.CLOSED);
      };
    };
    tunnel.disconnect = stop;
    tunnel.sendMessage = (...parts) => {
      if (socket?.readyState === WebSocket.OPEN) socket.send(encode(...parts));
    };
    return tunnel;
  }

  function start(profile, credentials) {
    const element = document.createElement('section');
    element.className = 'terminal-window remote-window';
    element.innerHTML = `<header class="terminal-titlebar"><div class="terminal-heading"><div><strong></strong><span></span></div></div><div class="terminal-controls"><button class="terminal-minimize" type="button" title="Minimize">−</button><button class="terminal-maximize" type="button" title="Maximize">□</button><button class="terminal-close" type="button" title="Disconnect and close">×</button></div></header><div class="remote-display" tabindex="0" role="application"></div><footer class="remote-footer"><span class="remote-status" role="status">Connecting…</span><button class="remote-cad" type="button">Ctrl+Alt+Del</button><form class="remote-text-form"><input type="password" autocomplete="off" aria-label="Text to send to the remote session" placeholder="Type text"><button type="submit">Send ↵</button></form></footer>`;
    element.querySelector('strong').textContent = profile.name;
    element.querySelector('.terminal-heading span').textContent = `${profile.type.toUpperCase()} · ${profile.host}:${profile.port}`;
    const viewport = element.querySelector('.remote-display');
    viewport.setAttribute('aria-label', `${profile.type.toUpperCase()} session for ${profile.name}`);
    document.querySelector('#terminal-layer').appendChild(element);
    focusTerminal(element);
    enableTerminalDrag(element);
    const status = element.querySelector('.remote-status');
    const tunnel = createTunnel(credentials);
    const client = new guac.Client(tunnel);
    const display = client.getDisplay();
    viewport.appendChild(display.getElement());
    const keyboard = new guac.Keyboard(viewport);
    keyboard.onkeydown = (keysym) => { client.sendKeyEvent(1, keysym); return false; };
    keyboard.onkeyup = (keysym) => client.sendKeyEvent(0, keysym);
    viewport.addEventListener('blur', () => keyboard.reset());
    viewport.addEventListener('pointerdown', () => { focusTerminal(element); viewport.focus(); });
    const mouse = new guac.Mouse(display.getElement());
    mouse.onEach(['mousedown', 'mousemove', 'mouseup'], (event) => client.sendMouseState(event.state, true));
    const touch = new guac.Mouse.Touchpad(display.getElement());
    touch.onEach(['mousedown', 'mousemove', 'mouseup'], (event) => client.sendMouseState(event.state, true));
    const fit = () => {
      if (!display.getWidth() || !display.getHeight()) return;
      display.scale(Math.min(viewport.clientWidth / display.getWidth(), viewport.clientHeight / display.getHeight(), 1));
    };
    display.onresize = fit;
    const observer = new ResizeObserver(fit);
    observer.observe(viewport);
    let failed = false;
    client.onerror = (error) => {
      failed = true;
      status.textContent = error.message || 'Connection failed.';
      client.disconnect();
    };
    client.onstatechange = (state) => {
      if (state === guac.Client.State.CONNECTED) {
        status.textContent = 'Connected';
        viewport.focus();
      } else if (state === guac.Client.State.DISCONNECTED) {
        keyboard.reset();
        if (!failed) status.textContent = 'Disconnected';
      }
    };
    const close = () => {
      keyboard.reset();
      client.disconnect();
      observer.disconnect();
      sessions.delete(profile.id);
      element.remove();
    };
    sessions.set(profile.id, { element, close });
    element.querySelector('.terminal-close').onclick = close;
    element.querySelector('.terminal-minimize').onclick = () => {
      keyboard.reset();
      element.classList.toggle('minimized');
    };
    element.querySelector('.terminal-maximize').onclick = () => element.classList.toggle('maximized');
    element.querySelector('.remote-cad').onclick = () => {
      [0xffe3, 0xffe9, 0xffff].forEach((key) => client.sendKeyEvent(1, key));
      [0xffff, 0xffe9, 0xffe3].forEach((key) => client.sendKeyEvent(0, key));
      viewport.focus();
    };
    element.querySelector('.remote-text-form').onsubmit = (event) => {
      event.preventDefault();
      const input = event.currentTarget.querySelector('input');
      for (const character of input.value) {
        const code = character.codePointAt(0);
        const keysym = code > 255 ? 0x01000000 | code : code;
        client.sendKeyEvent(1, keysym);
        client.sendKeyEvent(0, keysym);
      }
      client.sendKeyEvent(1, 0xff0d);
      client.sendKeyEvent(0, 0xff0d);
      input.value = '';
    };
    client.connect();
  }

  function open(profile) {
    if (sessions.has(profile.id)) {
      const element = sessions.get(profile.id).element;
      element.classList.remove('minimized');
      focusTerminal(element);
      return;
    }
    if (credentialDialog) credentialDialog.close();
    const dialog = document.createElement('dialog');
    credentialDialog = dialog;
    dialog.className = 'modal remote-login';
    dialog.innerHTML = `<form><div class="modal-heading"><div><h2></h2><p></p></div><button class="modal-close" type="button" aria-label="Close">×</button></div><div class="remote-login-fields"><label>Username<input name="username" autocomplete="off" maxlength="64"></label><label>Password<input name="password" type="password" autocomplete="off" maxlength="4096"></label><label class="remote-rdp-option">Domain (optional)<input name="domain" autocomplete="off" maxlength="64"></label><label class="remote-rdp-option">Security<select name="security"><option value="any">Automatic</option><option value="nla">NLA</option><option value="tls">TLS</option><option value="rdp">Legacy RDP</option></select></label><label class="remote-rdp-option remote-certificate"><input name="ignore_certificate" type="checkbox">Trust this target's unverified certificate</label><p class="remote-login-note">The appliance connects to the target. Passwords are used for this session only.</p><button class="primary-action" type="submit">Connect</button></div></form>`;
    dialog.querySelector('h2').textContent = `Connect ${profile.type.toUpperCase()}`;
    dialog.querySelector('.modal-heading p').textContent = `${profile.name} · ${profile.host}:${profile.port}`;
    dialog.querySelector('[name="username"]').value = profile.username || '';
    dialog.querySelectorAll('.remote-rdp-option').forEach((field) => { field.hidden = profile.type !== 'rdp'; });
    if (profile.type === 'vnc') dialog.querySelector('[name="username"]').closest('label').hidden = true;
    if (profile.type === 'telnet') dialog.querySelector('.remote-login-note').textContent += ' You can also leave credentials empty and sign in at the terminal prompt.';
    dialog.querySelector('.modal-close').onclick = () => dialog.close();
    dialog.addEventListener('close', () => {
      dialog.querySelector('form').reset();
      dialog.remove();
      if (credentialDialog === dialog) credentialDialog = null;
    });
    dialog.querySelector('form').onsubmit = (event) => {
      event.preventDefault();
      const data = new FormData(event.currentTarget);
      const credentials = {
        profile_id: profile.id, username: data.get('username'), password: data.get('password'),
        domain: data.get('domain'), security: data.get('security'),
        ignore_certificate: data.has('ignore_certificate'),
        width: Math.max(640, Math.min(2560, window.innerWidth - 64)),
        height: Math.max(480, Math.min(1440, window.innerHeight - 180)),
      };
      dialog.close();
      start(profile, credentials);
    };
    document.body.appendChild(dialog);
    dialog.showModal();
  }
  window.InfraBoxRemote = { open };
  window.addEventListener('pagehide', () => {
    [...sessions.values()].forEach((session) => session.close());
  });
})();
