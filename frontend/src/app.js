const text = (value, fallback = "unknown") =>
  value === null || value === undefined || value === "" ? fallback : String(value);

const escapeHtml = (value) => text(value)
  .replace(/&/g, "&amp;")
  .replace(/</g, "&lt;")
  .replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;")
  .replace(/'/g, "&#039;");

async function getJson(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

function renderSystem(system) {
  document.querySelector("#system").innerHTML = [
    ["Hostname", system.hostname],
    ["Model", system.model],
    ["Architecture", system.architecture],
    ["Kernel", system.kernel],
    ["Uptime", `${Math.floor(system.uptime_seconds / 60)} min`],
  ].map(([key, value]) =>
    `<div><dt>${key}</dt><dd>${escapeHtml(value)}</dd></div>`
  ).join("");
}

function renderNetwork(network) {
  document.querySelector("#network").innerHTML = network.interfaces.map((item) =>
    `<div class="row"><span><strong>${escapeHtml(item.name)}</strong><br><span class="muted">${escapeHtml(item.addresses?.join(", ") || "no address")}</span></span><span class="state ${item.state === "up" ? "" : "offline"}">${escapeHtml(item.state)}</span></div>`
  ).join("");
}

function renderServices() {
  const services = [
    { name: "Web Interface", detail: "AP management access", status: "online", ready: true },
    { name: "Console Ports", detail: "Console 1 and Console 2 mapped", status: "mapped", ready: true },
    { name: "KVM OTG", detail: "USB-C SLAVE", status: "setup pending", ready: false },
    { name: "Video Input", detail: "HDMI-to-CSI hardware", status: "hardware pending", ready: false },
  ];
  document.querySelector("#services").innerHTML = services.map((item) =>
    `<div class="row"><span><strong>${escapeHtml(item.name)}</strong><br><span class="muted">${escapeHtml(item.detail)}</span></span><span class="state ${item.ready ? "" : "offline"}">${escapeHtml(item.status)}</span></div>`
  ).join("");
}

const portIcons = {
  console_1: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h14v12H5zM3 19h18M8 8h2m2 0h2m2 0h1M8 12h8"/></svg>`,
  console_2: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h14v12H5zM3 19h18M8 8h2m2 0h2m2 0h1M8 12h8"/></svg>`,
  service_usb: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v14m0-14-2.5 2.5M12 3l2.5 2.5M12 10h5m0 0-2-2m2 2-2 2M12 14H7m0 0 2-2m-2 2 2 2M12 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4z"/></svg>`,
  target_lan: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v10H4zM8 19h8m-4-4v4M8 9h2m2 0h4"/></svg>`,
  kvm_otg: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h16v11H4zM8 19h8m-4-4v4M9 9l2 2 4-4"/></svg>`,
};

const terminals = new Map();
let terminalZIndex = 20;
let portRetryTimer = null;

function serialProfile(portId) {
  const fallback = {
    display_name: "",
    baud_rate: portId === "console_1" ? 115200 : 9600,
    data_bits: 8,
    parity: "none",
    stop_bits: 1,
    flow_control: "none",
  };
  try {
    return { ...fallback, ...JSON.parse(localStorage.getItem(`kronoskvm.serial.${portId}`)) };
  } catch {
    return fallback;
  }
}

function showToast(message) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 3200);
}

function renderPorts(inventory) {
  document.querySelector("#ports").innerHTML = inventory.ports.map((port) => {
    const connected = port.connected;
    const isConsole = port.id === "console_1" || port.id === "console_2";
    const statusClass = port.status === "setup_pending"
      ? "pending-state"
      : connected ? "" : "disconnected-state";
    const detail = port.device_name ||
      [port.physical_label, port.usb_path].filter(Boolean).join(" · ");
    const connectionAction = connected ? "Disconnect" : "Connect";
    return `<tr>
      <td data-label="Port"><div class="port-name"><span class="port-icon">${portIcons[port.id] || "IO"}</span><strong>${escapeHtml(port.name)}</strong></div></td>
      <td data-label="Interface"><span class="interface-label">${escapeHtml(port.physical_label)}</span>${port.usb_path ? `<code>${escapeHtml(port.usb_path)}</code>` : ""}</td>
      <td data-label="Connected device" class="device-cell">${escapeHtml(detail || "No device detected")}</td>
      <td data-label="State"><span class="port-state ${statusClass}">${escapeHtml(port.status.replaceAll("_", " "))}</span></td>
      <td data-label="Actions"><details class="action-menu">
        <summary aria-label="Open actions for ${escapeHtml(port.name)}" title="Actions">⋯</summary>
        <div class="action-menu-list" role="menu">
          <button class="config-action" type="button" role="menuitem"
            data-port-id="${escapeHtml(port.id)}" data-port-name="${escapeHtml(port.name)}"
            data-device="${escapeHtml(port.serial_device || "")}" ${isConsole ? "" : "disabled"}>⚙ Config</button>
          <button class="menu-action" type="button" role="menuitem"
            data-message="${escapeHtml(`${port.name}: ${port.status}${port.device_name ? ` — ${port.device_name}` : ""}`)}">◎ Status</button>
          ${isConsole ? `<button class="connect-action" type="button" role="menuitem"
            data-port-id="${escapeHtml(port.id)}" data-port-name="${escapeHtml(port.name)}"
            data-device="${escapeHtml(port.serial_device || "")}" ${port.console_available ? "" : "disabled"}>→ Connect</button>
          <button class="disconnect-action" type="button" role="menuitem"
            data-port-id="${escapeHtml(port.id)}" disabled>⊘ Disconnect</button>
          <button class="console-action" type="button" role="menuitem"
            data-port-id="${escapeHtml(port.id)}" data-port-name="${escapeHtml(port.name)}"
            data-device="${escapeHtml(port.serial_device || "")}" ${port.console_available ? "" : "disabled"}>⌘ Console</button>` :
            `<button type="button" role="menuitem" title="Port control backend is not enabled yet" disabled>${connected ? "⊘ Disconnect" : `→ ${connectionAction}`}</button>`}
        </div>
      </details></td>
    </tr>`;
  }).join("");

  document.querySelectorAll(".menu-action").forEach((button) => {
    button.addEventListener("click", () => {
      showToast(button.dataset.message);
      button.closest("details").removeAttribute("open");
    });
  });
  document.querySelectorAll(".config-action").forEach((button) => {
    button.addEventListener("click", () => openConfig(button));
  });
  document.querySelectorAll(".connect-action, .console-action").forEach((button) => {
    button.addEventListener("click", () => openConsole(button));
  });
  document.querySelectorAll(".disconnect-action").forEach((button) => {
    button.addEventListener("click", () => closeTerminal(button.dataset.portId));
  });
  setConnectionControls();
}

async function loadPorts(attempt = 0) {
  window.clearTimeout(portRetryTimer);
  try {
    renderPorts(await getJson("/api/v1/hardware/ports"));
  } catch (error) {
    document.querySelector("#ports").innerHTML =
      `<tr><td colspan="5" class="loading-cell">Port status unavailable${attempt < 3 ? "; retrying…" : ". Use Refresh to try again."}</td></tr>`;
    console.error("Port status request failed", error);
    if (attempt < 3) portRetryTimer = window.setTimeout(() => loadPorts(attempt + 1), 1500);
  }
}

function openConfig(button) {
  const profile = serialProfile(button.dataset.portId);
  document.querySelector("#config-port-name").textContent = button.dataset.portName;
  document.querySelector("#config-device").value = button.dataset.device;
  document.querySelector("#config-form").dataset.portId = button.dataset.portId;
  document.querySelector("#config-display-name").value = profile.display_name;
  document.querySelector("#config-baud").value = profile.baud_rate;
  document.querySelector("#config-bits").value = profile.data_bits;
  document.querySelector("#config-parity").value = profile.parity;
  document.querySelector("#config-stop").value = profile.stop_bits;
  document.querySelector("#config-flow").value = profile.flow_control;
  button.closest("details").removeAttribute("open");
  document.querySelector("#config-dialog").showModal();
}

function setConnectionControls() {
  document.querySelectorAll(".connect-action, .console-action").forEach((button) => {
    button.disabled = !button.dataset.device || terminals.has(button.dataset.portId);
  });
  document.querySelectorAll(".disconnect-action").forEach((button) => {
    button.disabled = !terminals.has(button.dataset.portId);
  });
}

function appendTerminal(session, value) {
  const terminal = session.element.querySelector(".terminal");
  terminal.textContent += value;
  if (terminal.textContent.length > 100000) terminal.textContent = terminal.textContent.slice(-80000);
  terminal.scrollTop = terminal.scrollHeight;
}

function focusTerminal(element) {
  terminalZIndex += 1;
  element.style.zIndex = terminalZIndex;
}

function enableTerminalDrag(element) {
  const handle = element.querySelector(".terminal-titlebar");
  handle.addEventListener("pointerdown", (event) => {
    if (event.target.closest("button") || element.classList.contains("maximized")) return;
    const startX = event.clientX;
    const startY = event.clientY;
    const startLeft = element.offsetLeft;
    const startTop = element.offsetTop;
    handle.setPointerCapture(event.pointerId);
    const move = (moveEvent) => {
      element.style.left = `${Math.max(0, startLeft + moveEvent.clientX - startX)}px`;
      element.style.top = `${Math.max(84, startTop + moveEvent.clientY - startY)}px`;
    };
    const stop = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", stop);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", stop);
  });
}

function createTerminalWindow(button, profile) {
  const element = document.createElement("section");
  const label = profile.display_name.trim() || button.dataset.portName;
  const offset = terminals.size * 34;
  element.className = "terminal-window";
  element.dataset.portId = button.dataset.portId;
  element.style.left = `${Math.max(12, Math.min(120 + offset, window.innerWidth - 420))}px`;
  element.style.top = `${120 + offset}px`;
  element.innerHTML = `<header class="terminal-titlebar">
      <div class="terminal-heading"><div><strong>${escapeHtml(label)}</strong><span>${escapeHtml(button.dataset.portName)} · ${profile.baud_rate} · ${profile.data_bits}${profile.parity[0].toUpperCase()}${profile.stop_bits}</span></div><span class="terminal-connection connecting"><i></i><b>Connecting</b></span></div>
      <div class="terminal-controls"><button class="terminal-minimize" title="Minimize">−</button><button class="terminal-maximize" title="Maximize">□</button><button class="terminal-close" title="Close">×</button></div>
    </header>
    <pre class="terminal" tabindex="0" aria-label="${escapeHtml(label)} interactive serial terminal">Connecting…\n</pre>`;
  document.querySelector("#terminal-layer").appendChild(element);
  focusTerminal(element);
  enableTerminalDrag(element);
  element.addEventListener("pointerdown", () => focusTerminal(element));
  return element;
}

function openConsole(button) {
  if (!button.dataset.device) return;
  if (terminals.has(button.dataset.portId)) {
    const existing = terminals.get(button.dataset.portId).element;
    existing.classList.remove("minimized");
    focusTerminal(existing);
    return;
  }
  const profile = serialProfile(button.dataset.portId);
  const deviceName = button.dataset.device.split("/").pop();
  const query = new URLSearchParams({
    baud_rate: profile.baud_rate,
    data_bits: profile.data_bits,
    parity: profile.parity,
    stop_bits: profile.stop_bits,
    flow_control: profile.flow_control,
  }).toString();
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/api/v1/serial/ws/${encodeURIComponent(deviceName)}?${query}`);
  const element = createTerminalWindow(button, profile);
  const session = { socket, element };
  terminals.set(button.dataset.portId, session);
  button.closest("details").removeAttribute("open");
  setConnectionControls();
  const decoder = new TextDecoder();
  socket.binaryType = "arraybuffer";
  socket.addEventListener("open", () => {
    const status = element.querySelector(".terminal-connection");
    status.className = "terminal-connection connected";
    status.querySelector("b").textContent = "Connected";
    appendTerminal(session, "Connected. Press Enter to request the prompt.\n");
    socket.send(new TextEncoder().encode("\r"));
    element.querySelector(".terminal").focus();
  });
  socket.addEventListener("message", (event) => {
    const output = event.data instanceof ArrayBuffer ? decoder.decode(event.data, { stream: true }) : event.data;
    appendTerminal(session, output);
  });
  socket.addEventListener("close", (event) => {
    const status = element.querySelector(".terminal-connection");
    status.className = "terminal-connection disconnected";
    status.querySelector("b").textContent = "Disconnected";
    appendTerminal(session, `\nConnection closed (${event.code}).\n`);
    session.socket = null;
    setConnectionControls();
  });
  socket.addEventListener("error", () => appendTerminal(session, "\nSerial connection error.\n"));
  const terminal = element.querySelector(".terminal");
  const send = (value) => {
    if (!session.socket || session.socket.readyState !== WebSocket.OPEN || !value) return;
    session.socket.send(new TextEncoder().encode(value));
  };
  const specialKeys = {
    Enter: "\r", Backspace: "\x7f", Tab: "\t", Escape: "\x1b",
    ArrowUp: "\x1b[A", ArrowDown: "\x1b[B", ArrowRight: "\x1b[C", ArrowLeft: "\x1b[D",
    Home: "\x1b[H", End: "\x1b[F", Delete: "\x1b[3~", PageUp: "\x1b[5~", PageDown: "\x1b[6~",
  };
  terminal.addEventListener("keydown", (event) => {
    let value = specialKeys[event.key];
    if (event.ctrlKey && event.key.length === 1 && /[a-z]/i.test(event.key)) {
      value = String.fromCharCode(event.key.toUpperCase().charCodeAt(0) - 64);
    } else if (!event.ctrlKey && !event.metaKey && !event.altKey && event.key.length === 1) {
      value = event.key;
    }
    if (value !== undefined) {
      event.preventDefault();
      send(value);
    }
  });
  terminal.addEventListener("paste", (event) => {
    event.preventDefault();
    send(event.clipboardData.getData("text"));
  });
  element.querySelector(".terminal-close").addEventListener("click", () => closeTerminal(button.dataset.portId));
  element.querySelector(".terminal-minimize").addEventListener("click", () => element.classList.toggle("minimized"));
  element.querySelector(".terminal-maximize").addEventListener("click", () => element.classList.toggle("maximized"));
}

function closeTerminal(portId) {
  const session = terminals.get(portId);
  if (!session) return;
  if (session.socket) session.socket.close(1000, "operator disconnect");
  session.element.remove();
  terminals.delete(portId);
  setConnectionControls();
}

async function load() {
  const health = document.querySelector("#health");
  loadPorts();
  const results = await Promise.allSettled([
    getJson("/api/v1/health"),
    getJson("/api/v1/system/info"),
    getJson("/api/v1/system/network"),
  ]);
  const [healthResult, systemResult, networkResult] = results;

  if (healthResult.status === "fulfilled") {
    const healthData = healthResult.value;
    health.textContent = `API ${text(healthData.status)}`;
    health.className = "badge ready";
  } else {
    health.textContent = "API unavailable";
    health.className = "badge error";
    console.error(healthResult.reason);
  }

  try {
    renderServices();
  } catch (error) {
    console.error("Service readiness render failed", error);
  }

  if (systemResult.status === "fulfilled") {
    try {
      renderSystem(systemResult.value);
    } catch (error) {
      console.error("System render failed", error);
    }
  }
  if (networkResult.status === "fulfilled") {
    try {
      renderNetwork(networkResult.value);
    } catch (error) {
      console.error("Network render failed", error);
    }
  }
}

document.querySelector("#refresh").addEventListener("click", load);
document.querySelector("#config-form").addEventListener("submit", (event) => {
  if (event.submitter?.value === "cancel") return;
  event.preventDefault();
  const form = event.currentTarget;
  const profile = {
    display_name: document.querySelector("#config-display-name").value.trim(),
    baud_rate: Number(document.querySelector("#config-baud").value),
    data_bits: Number(document.querySelector("#config-bits").value),
    parity: document.querySelector("#config-parity").value,
    stop_bits: Number(document.querySelector("#config-stop").value),
    flow_control: document.querySelector("#config-flow").value,
  };
  localStorage.setItem(`kronoskvm.serial.${form.dataset.portId}`, JSON.stringify(profile));
  document.querySelector("#config-dialog").close();
  showToast("Serial configuration saved");
});
document.addEventListener("click", (event) => {
  document.querySelectorAll(".action-menu[open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.removeAttribute("open");
  });
});
load();
