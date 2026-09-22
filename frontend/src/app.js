const startupSplash = document.querySelector("#startup-splash");
const startupShell = document.querySelector(".app-shell");
let startupFinished = false;
let startupTimeout;

function dismissStartupSplash() {
  if (startupFinished) return;
  startupFinished = true;
  window.clearTimeout(startupTimeout);
  const restoreFocus = startupSplash.contains(document.activeElement);
  startupShell.inert = false;
  document.body.classList.remove("startup-pending");
  startupSplash.hidden = true;
  if (restoreFocus) document.querySelector("#session-search").focus({ preventScroll: true });
}

startupSplash.hidden = false;
startupShell.inert = true;
document.body.classList.add("startup-pending");
document.querySelector("#startup-skip").addEventListener("click", dismissStartupSplash);
// Keep the dashboard reachable even if initialization fails or requests stall.
startupTimeout = window.setTimeout(dismissStartupSplash, 8000);
const startupMinimum = new Promise((resolve) => window.setTimeout(resolve, 2500));

const text = (value, fallback = "unknown") =>
  value === null || value === undefined || value === "" ? fallback : String(value);

const escapeHtml = (value) => text(value)
  .replace(/&/g, "&amp;")
  .replace(/</g, "&lt;")
  .replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;")
  .replace(/'/g, "&#039;");

const themeStorageKey = "kronoskvm.theme";

function applyTheme(theme) {
  const selected = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = selected;
  document.querySelector('meta[name="theme-color"]').content =
    selected === "dark" ? "#08100d" : "#f4f7f6";
  document.querySelectorAll("[data-theme-choice]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.themeChoice === selected));
  });
}

applyTheme(localStorage.getItem(themeStorageKey) || "light");
document.querySelector("#footer-address").textContent = location.hostname;
document.querySelector("#copyright-year").textContent = new Date().getFullYear();

function setCollapsed(panel, collapsed) {
  panel.classList.toggle("collapsed", collapsed);
  const button = panel.querySelector(":scope > .collapse-heading .collapse-button");
  if (!button) return;
  button.setAttribute("aria-expanded", String(!collapsed));
  const title = panel.querySelector(":scope > .collapse-heading h2")?.textContent || "panel";
  button.setAttribute("aria-label", `${collapsed ? "Expand" : "Collapse"} ${title}`);
}

document.querySelectorAll("[data-collapse-id]").forEach((panel) => {
  const storageKey = `kronoskvm.panel.${panel.dataset.collapseId}.collapsed`;
  const savedState = localStorage.getItem(storageKey);
  const initiallyCollapsed = savedState === null
    ? panel.dataset.defaultCollapsed === "true"
    : savedState === "true";
  setCollapsed(panel, initiallyCollapsed);
  panel.querySelector(":scope > .collapse-heading").addEventListener("click", (event) => {
    if (event.target.closest("a, input, select")) return;
    const clickedButton = event.target.closest("button");
    if (clickedButton && !clickedButton.classList.contains("collapse-button")) return;
    const collapsed = !panel.classList.contains("collapsed");
    if (!collapsed && panel.dataset.collapseGroup) {
      document.querySelectorAll(`[data-collapse-group="${panel.dataset.collapseGroup}"]`).forEach((sibling) => {
        if (sibling === panel) return;
        setCollapsed(sibling, true);
        localStorage.setItem(`kronoskvm.panel.${sibling.dataset.collapseId}.collapsed`, "true");
      });
    }
    setCollapsed(panel, collapsed);
    localStorage.setItem(storageKey, String(collapsed));
  });
});

async function getJson(path) {
  const response = await fetch(path, {
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

let latestLogEntries = [];

function logDetails(entry) {
  const hidden = new Set(["timestamp", "level", "logger", "message", "event"]);
  return Object.entries(entry)
    .filter(([key]) => !hidden.has(key))
    .map(([key, value]) => `${key}=${typeof value === "object" ? JSON.stringify(value) : value}`)
    .join(" · ") || entry.message || "—";
}

function logGroup(entry) {
  if (["ERROR", "CRITICAL", "WARNING"].includes(entry.level)) return "Errors & warnings";
  if (entry.logger === "kronoskvm.audit") return "Audit events";
  if (entry.logger === "kronoskvm.api") return "API requests";
  return "Runtime";
}

function groupedLogRows(entries) {
  const groups = new Map();
  entries.forEach((entry) => {
    const name = logGroup(entry);
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(entry);
  });
  return [...groups.entries()].map(([name, items]) =>
    `<tr class="log-group-row"><td colspan="4"><strong>${escapeHtml(name)}</strong><span>${items.length}</span></td></tr>`
    + items.map((entry) => `<tr><td>${escapeHtml(new Date(entry.timestamp).toLocaleString())}</td><td><span class="log-level log-${escapeHtml((entry.level || "info").toLowerCase())}">${escapeHtml(entry.level)}</span></td><td>${escapeHtml(entry.event || entry.logger || entry.message)}</td><td><code>${escapeHtml(logDetails(entry))}</code></td></tr>`).join("")
  ).join("");
}

async function loadLogs() {
  const level = document.querySelector("#logs-level").value;
  const search = document.querySelector("#logs-search").value.trim();
  const query = new URLSearchParams({ limit: "300" });
  if (level) query.set("level", level);
  if (search) query.set("search", search);
  try {
    const payload = await getJson(`/api/v1/logs?${query}`);
    latestLogEntries = payload.entries;
    document.querySelector("#logs-entries").innerHTML = payload.entries.length
      ? groupedLogRows(payload.entries)
      : '<tr><td colspan="4" class="loading-cell">No matching log entries</td></tr>';
    document.querySelector("#logs-state").innerHTML = `<i></i> Active · ${payload.count}`;
  } catch (error) {
    document.querySelector("#logs-state").textContent = "Unavailable";
    document.querySelector("#logs-entries").innerHTML = '<tr><td colspan="4" class="loading-cell">Logs could not be loaded</td></tr>';
  }
}

async function loadSessionLogs() {
  try {
    const payload = await getJson("/api/v1/session-logs");
    document.querySelector("#session-log-files").innerHTML = payload.entries.length
      ? payload.entries.map((entry) => `<a class="staged-log-file" href="${escapeHtml(entry.download_url)}" download><span><strong>${escapeHtml(entry.filename)}</strong><small>${escapeHtml(formatBytes(entry.size_bytes))} · temporary</small></span><b>↓ TXT</b></a>`).join("")
      : '<span class="muted">No staged session logs</span>';
  } catch (error) {
    document.querySelector("#session-log-files").innerHTML = '<span class="muted">Session logs unavailable</span>';
  }
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
  document.querySelector("#network").innerHTML = network.interfaces
    .filter((item) => item.name !== "lo")
    .map((item) =>
    `<div class="row"><span><strong>${escapeHtml(item.name)}</strong><br><span class="muted">${escapeHtml(item.addresses?.join(", ") || "no address")}</span></span><span class="state ${item.state === "up" ? "" : "offline"}">${escapeHtml(item.state)}</span></div>`
  ).join("");
}

function renderServices(hidStatus = null) {
  const services = [
    { name: "Web Interface", detail: "AP management access", status: "online", ready: true },
    { name: "Console Ports", detail: "Console 1 and Console 2 mapped", status: "mapped", ready: true },
    {
      name: "KVM OTG",
      detail: "USB-C HID · Witty Pi GPIO power",
      status: hidStatus === null ? "status unavailable" : hidStatus.ready === true ? "ready" : "HID not ready",
      ready: hidStatus?.ready === true,
    },
    { name: "Video Input", detail: "HDMI capture · /dev/video0", status: "ready", ready: true },
    { name: "Internal Stage", detail: "32 GiB SD pool · 10 GiB reserve", status: "ready", ready: true },
  ];
  document.querySelector("#services").innerHTML = services.map((item) =>
    `<div class="row"><span><strong>${escapeHtml(item.name)}</strong><br><span class="muted">${escapeHtml(item.detail)}</span></span><span class="state ${item.ready ? "" : "offline"}">${escapeHtml(item.status)}</span></div>`
  ).join("");
}

const portIcons = {
  console_1: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h14v12H5zM3 19h18M8 8h2m2 0h2m2 0h1M8 12h8"/></svg>`,
  console_2: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h14v12H5zM3 19h18M8 8h2m2 0h2m2 0h1M8 12h8"/></svg>`,
  service_usb: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v14m0-14-2.5 2.5M12 3l2.5 2.5M12 10h5m0 0-2-2m2 2-2 2M12 14H7m0 0 2-2m-2 2 2 2M12 17a2 2 0 1 0 0 4 2 2 0 0 0 0-4z"/></svg>`,
  expansion_usb: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v10H4zM8 19h8m-4-4v4M8 9h2m2 0h4"/></svg>`,
  video_capture: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h14v12H3zM17 10l4-2v8l-4-2zM7 10h6m-6 4h4"/></svg>`,
  kvm_otg: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h16v11H4zM8 19h8m-4-4v4M9 9l2 2 4-4"/></svg>`,
};

const terminals = new Map();
let connectionProfiles = [];
let terminalZIndex = 20;
let portRetryTimer = null;

function serialProfile(portId) {
  const fallback = {
    display_name: "",
    baud_rate: "auto",
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

async function getPhysicalPortInventory() {
  const [inventory, remote] = await Promise.all([
    getJson("/api/v1/hardware/ports"),
    getJson("/api/v1/remote-assist").catch(() => null),
  ]);
  const shared = inventory.ports.find((port) => port.id === "expansion_usb");
  if (!shared) return inventory;
  shared.name = "External Storage / WAN";
  shared.physical_label = "USB-A 3.0 · Storage / WAN";
  const fresh = remote?.installed && !remote.stale && Date.now() / 1000 - remote.updated_at < 30;
  const wan = fresh && shared.connected ? remote.wan?.[0] : null;
  if (wan && !shared.network_interface) {
    shared.mode = "wan";
    shared.network_interface = wan.interface;
    shared.addresses = (wan.address || "").split(/[\s,;]+/).filter(Boolean);
    shared.gateway = wan.gateway || null;
    shared.status = shared.addresses.length ? "usb_wan_ready" : "waiting_for_ip";
  }
  shared.vpn = {
    state: fresh ? remote.state : "unavailable",
    address: remote?.profile?.address || null,
    uplink: fresh ? remote.uplink : null,
    lastHandshake: fresh ? remote.last_handshake : null,
  };
  return inventory;
}

function portVpnLabel(vpn) {
  const states = {connected: "Connected", off: "Off", waiting_handshake: "Waiting for handshake",
    disconnected: "Disconnected", setup_required: "Setup required", unavailable: "Status unavailable",
    stop_failed: "Could not stop"};
  return states[vpn.state] || "Unknown";
}

async function showPortStatus(portId) {
  let dialog = document.querySelector("#physical-port-status");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "physical-port-status";
    dialog.className = "physical-port-status";
    dialog.setAttribute("aria-labelledby", "physical-port-status-title");
    dialog.innerHTML = `<header><h2 id="physical-port-status-title">Port status</h2><button type="button" data-close>Close</button></header><div data-details aria-live="polite"></div><button type="button" data-refresh>Refresh</button>`;
    document.body.appendChild(dialog);
    dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
    dialog.querySelector("[data-refresh]").addEventListener("click", () => showPortStatus(dialog.dataset.portId));
  }
  dialog.dataset.portId = portId;
  const request = String(Number(dialog.dataset.request || 0) + 1);
  dialog.dataset.request = request;
  const content = dialog.querySelector("[data-details]");
  const refresh = dialog.querySelector("[data-refresh]");
  content.textContent = "Reading current port status…";
  refresh.disabled = true;
  if (!dialog.open) dialog.showModal();
  try {
    const inventory = await getPhysicalPortInventory();
    if (dialog.dataset.request !== request) return;
    const port = inventory.ports.find((item) => item.id === portId);
    if (!port) throw new Error("Port is unavailable");
    document.querySelector("#physical-port-status-title").textContent = `${port.name} · Status`;
    const rows = [
      ["Device", port.device_name || "No device connected"],
      ["Mode", port.mode === "wan" ? "USB WAN" : port.mode === "storage" ? "USB Storage" : port.mode || "—"],
      ["State", port.status.replaceAll("_", " ")],
      ["Physical port", port.physical_label],
    ];
    if (port.network_interface) rows.push(
      ["Network interface", port.network_interface],
      ["IP address", port.addresses?.join(", ") || "Waiting for DHCP"],
      ["Gateway", port.gateway || "Not assigned"],
    );
    if (port.vpn) rows.push(
      ["VPN state", portVpnLabel(port.vpn)],
      ["VPN IP (configured)", port.vpn.address || "Not configured"],
      ["Preferred uplink", port.vpn.uplink || "Unavailable"],
      ["Last handshake", port.vpn.lastHandshake ? new Date(port.vpn.lastHandshake * 1000).toLocaleString() : "No current handshake"],
    );
    content.innerHTML = `<dl>${rows.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}</dl>${port.mode === "wan" ? "<p>IP assignment does not verify internet access. VPN settings are in Remote Assist.</p>" : ""}`;
  } catch (error) {
    if (dialog.dataset.request === request) content.textContent = `Status unavailable: ${error.message}`;
  } finally {
    if (dialog.dataset.request === request) refresh.disabled = false;
  }
}

function renderPorts(inventory) {
  document.querySelector("#ports").innerHTML = inventory.ports.map((port) => {
    const connected = port.connected;
    const isConsole = port.id === "console_1" || port.id === "console_2";
    const statusClass = ["setup_pending", "waiting_for_gpio_power", "waiting_for_ip"].includes(port.status)
      ? "pending-state"
      : connected ? "" : "disconnected-state";
    const detail = port.device_name ||
      [port.physical_label, port.usb_path].filter(Boolean).join(" · ");
    const networkDetail = port.network_interface
      ? [`Interface: ${port.network_interface}`, `IP: ${port.addresses?.join(", ") || "Waiting for DHCP"}`, `Gateway: ${port.gateway || "—"}`].join(" · ")
      : "";
    const connectionAction = connected ? "Disconnect" : "Connect";
    const displayStatus = isConsole && connected ? "adapter connected" : port.status.replaceAll("_", " ");
    return `<tr>
      <td data-label="Port"><div class="port-name"><span class="port-icon">${portIcons[port.id] || "IO"}</span><strong>${escapeHtml(port.name)}</strong></div></td>
      <td data-label="Interface"><span class="interface-label">${escapeHtml(port.physical_label)}</span>${port.usb_path ? `<code>${escapeHtml(port.usb_path)}</code>` : ""}</td>
      <td data-label="Connected device" class="device-cell">${escapeHtml(detail || "No device detected")}${networkDetail ? `<code>${escapeHtml(networkDetail)}</code>` : ""}</td>
      <td data-label="State"><button type="button" class="port-state port-status-action ${statusClass}" data-port-id="${escapeHtml(port.id)}" aria-label="Show ${escapeHtml(port.name)} status">${escapeHtml(displayStatus)}</button>${port.vpn ? `<code>VPN: ${escapeHtml(portVpnLabel(port.vpn))}${port.vpn.address ? ` · ${escapeHtml(port.vpn.address)}` : ""}</code>` : ""}${port.mode === "wan" ? `<code>${escapeHtml(port.addresses?.join(", ") || "Waiting for IP")}</code>` : ""}</td>
      <td data-label="Actions"><details class="action-menu">
        <summary aria-label="Open actions for ${escapeHtml(port.name)}" title="Actions">⋯</summary>
        <div class="action-menu-list" role="menu">
          <button class="config-action" type="button" role="menuitem"
            data-port-id="${escapeHtml(port.id)}" data-port-name="${escapeHtml(port.name)}"
            data-device="${escapeHtml(port.serial_device || "")}" ${isConsole ? "" : "disabled"}>⚙ Config</button>
          <button class="port-status-action" type="button" role="menuitem" data-port-id="${escapeHtml(port.id)}"
            data-message="${escapeHtml(`${port.name}: ${port.status}${port.device_name ? ` — ${port.device_name}` : ""}${networkDetail ? ` — ${networkDetail}` : ""}`)}">◎ Status</button>
          ${port.id === "expansion_usb" ? `<button class="storage-action" type="button" role="menuitem" data-target-view="storage">Open Storage</button><button class="storage-action" type="button" role="menuitem" data-target-view="remote-assist">WAN / VPN · Remote Assist</button>` : ""}
          ${isConsole ? `<button class="connect-action" type="button" role="menuitem"
            data-port-id="${escapeHtml(port.id)}" data-port-name="${escapeHtml(port.name)}"
            data-device="${escapeHtml(port.serial_device || "")}" ${port.console_available ? "" : "disabled"}>→ Connect</button>
          <button class="disconnect-action" type="button" role="menuitem"
            data-port-id="${escapeHtml(port.id)}" data-port-name="${escapeHtml(port.name)}"
            data-device="${escapeHtml(port.serial_device || "")}" ${port.console_available ? "" : "disabled"}>⊘ Disconnect</button>
          <button class="console-action" type="button" role="menuitem"
            data-port-id="${escapeHtml(port.id)}" data-port-name="${escapeHtml(port.name)}"
            data-device="${escapeHtml(port.serial_device || "")}" ${port.console_available ? "" : "disabled"}>⌘ Console</button>
          <button class="reset-action" type="button" role="menuitem"
            data-port-id="${escapeHtml(port.id)}" data-port-name="${escapeHtml(port.name)}"
            data-device="${escapeHtml(port.serial_device || "")}" ${port.console_available ? "" : "disabled"}>↻ Re-detect &amp; connect</button>` :
            `<button type="button" role="menuitem" title="Port control backend is not enabled yet" disabled>${connected ? "⊘ Disconnect" : `→ ${connectionAction}`}</button>`}
        </div>
      </details></td>
    </tr>`;
  }).join("");

  document.querySelectorAll(".port-status-action").forEach((button) => {
    button.addEventListener("click", () => {
      button.closest("details")?.removeAttribute("open");
      showPortStatus(button.dataset.portId);
    });
  });
  document.querySelectorAll(".storage-action").forEach((button) => {
    button.addEventListener("click", () => document.querySelector(`.side-link[data-view="${button.dataset.targetView || "storage"}"]`).click());
  });
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
    button.addEventListener("click", () => disconnectSerialSession(button));
  });
  document.querySelectorAll(".reset-action").forEach((button) => {
    button.addEventListener("click", () => redetectAndConnect(button));
  });
  setConnectionControls();
  updateSessionCards(inventory);
  filterPortRows(document.querySelector("#session-search").value);
}

function updateSessionCards(inventory) {
  ["console_1", "console_2"].forEach((portId) => {
    const port = inventory.ports.find((item) => item.id === portId);
    const card = document.querySelector(`[data-session-port="${portId}"]`);
    if (!port || !card) return;
    card.classList.toggle("session-connected", port.connected);
    card.querySelector("small").textContent = port.connected
      ? (port.device_name || "Serial adapter connected")
      : "Adapter disconnected";
    card.querySelectorAll("[data-session-action]").forEach((button) => {
      button.disabled = button.dataset.sessionAction !== "config"
        && button.dataset.sessionAction !== "status"
        && !port.console_available;
    });
  });
}

function filterPortRows(query) {
  const normalized = query.trim().toLowerCase();
  document.querySelectorAll("#ports tr").forEach((row) => {
    row.hidden = Boolean(normalized) && !row.textContent.toLowerCase().includes(normalized);
  });
}

const connectionDefaults = {
  ssh: { port: 22, name: "SSH connection" },
  telnet: { port: 23, name: "Telnet connection" },
  rdp: { port: 3389, name: "RDP connection" },
  vnc: { port: 5900, name: "VNC connection" },
  web: { port: 443, name: "Web connection" },
};

function connectionUri(profile) {
  const user = profile.username ? `${encodeURIComponent(profile.username)}@` : "";
  if (profile.type === "web") {
    const scheme = profile.port === 443 ? "https" : "http";
    const defaultPort = (scheme === "https" && profile.port === 443) || (scheme === "http" && profile.port === 80);
    return `${scheme}://${profile.host}${defaultPort ? "" : `:${profile.port}`}${profile.path || "/"}`;
  }
  if (profile.type === "rdp") return `rdp://full%20address=s:${profile.host}:${profile.port}`;
  return `${profile.type}://${user}${profile.host}:${profile.port}`;
}

function launchConnection(profile) {
  if (profile.type === "ssh") {
    openSshTerminal(profile);
    return;
  }
  const uri = connectionUri(profile);
  if (profile.type === "web") window.open(uri, "_blank", "noopener,noreferrer");
  else window.location.href = uri;
}

function renderConnections(profiles) {
  connectionProfiles = profiles;
  const container = document.querySelector("#network-connections");
  container.innerHTML = profiles.map((profile) => `<article class="session-card network-session" data-connection-id="${escapeHtml(profile.id)}"><button type="button" class="launch-connection"><span class="session-dot"></span><span><b>${escapeHtml(profile.name)}</b><small>${escapeHtml(profile.type.toUpperCase())} · ${escapeHtml(profile.host)}:${profile.port}</small></span></button><button type="button" class="connection-menu-trigger" aria-label="${escapeHtml(profile.name)} actions" aria-expanded="false">⋯</button></article>`).join("");
  container.querySelectorAll(".launch-connection").forEach((button) => {
    button.addEventListener("click", () => launchConnection(
      connectionProfiles.find((item) => item.id === button.closest("[data-connection-id]").dataset.connectionId)
    ));
  });
  container.querySelectorAll(".connection-menu-trigger").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const profile = connectionProfiles.find(
        (item) => item.id === button.closest("[data-connection-id]").dataset.connectionId
      );
      openConnectionMenu(button, profile);
    });
  });
}

function closeConnectionMenu() {
  document.querySelector("#connection-action-popover")?.remove();
  document.querySelectorAll(".connection-menu-trigger[aria-expanded='true']").forEach((button) => {
    button.setAttribute("aria-expanded", "false");
  });
}

function openConnectionMenu(trigger, profile) {
  closeConnectionMenu();
  trigger.setAttribute("aria-expanded", "true");
  const menu = document.createElement("div");
  menu.id = "connection-action-popover";
  menu.className = "connection-action-popover";
  menu.innerHTML = `<button type="button" data-action="open">↗ Open</button><button type="button" data-action="edit">⚙ Edit</button><button class="delete-connection" type="button" data-action="delete">⊘ Delete connection</button>`;
  document.body.appendChild(menu);
  const rectangle = trigger.getBoundingClientRect();
  const menuWidth = 190;
  menu.style.left = `${Math.max(8, Math.min(rectangle.right - menuWidth, window.innerWidth - menuWidth - 8))}px`;
  menu.style.top = `${Math.min(rectangle.bottom + 6, window.innerHeight - menu.offsetHeight - 8)}px`;
  menu.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      closeConnectionMenu();
      if (button.dataset.action === "open") launchConnection(profile);
      if (button.dataset.action === "edit") openConnectionForm(profile.type, profile);
      if (button.dataset.action === "delete" && window.confirm(`Delete ${profile.name}?`)) {
        const response = await fetch(`/api/v1/connections/${encodeURIComponent(profile.id)}`, { method: "DELETE" });
        if (response.ok) {
          showToast(`${profile.name}: deleted`);
          loadConnections();
        } else showToast(`${profile.name}: delete failed`);
      }
    });
  });
}

async function loadConnections() {
  try {
    renderConnections(await getJson("/api/v1/connections"));
  } catch (error) {
    console.error("Connection registry request failed", error);
  }
}

function openConnectionForm(type, profile = null) {
  const defaults = connectionDefaults[type];
  document.querySelector(".connection-types").hidden = true;
  document.querySelector("#connection-form").hidden = false;
  document.querySelector("#connection-id").value = profile?.id || "";
  document.querySelector("#connection-type").value = type;
  document.querySelector("#connection-name").value = profile?.name || defaults.name;
  document.querySelector("#connection-host").value = profile?.host || "";
  document.querySelector("#connection-port").value = profile?.port || defaults.port;
  document.querySelector("#connection-username").value = profile?.username || "";
  document.querySelector("#connection-path").value = profile?.path || "/";
  document.querySelector("#connection-path-label").hidden = type !== "web";
  if (!document.querySelector("#session-dialog").open) document.querySelector("#session-dialog").showModal();
  document.querySelector("#connection-host").focus();
}

function showConnectionTypes() {
  document.querySelector("#connection-form").hidden = true;
  document.querySelector(".connection-types").hidden = false;
}

const formatBytes = (value) => {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length);
  return `${(bytes / (1024 ** exponent)).toFixed(exponent > 2 ? 1 : 0)} ${units[exponent - 1]}`;
};

let virtualMediaStatus = { status: "ejected", filename: null };

async function loadVirtualMediaStatus() {
  try {
    virtualMediaStatus = await getJson("/api/v1/storage/virtual-media");
  } catch (error) {
    virtualMediaStatus = { status: "unavailable", filename: null, message: "Status unavailable" };
  }
  renderMediaActivity();
  return virtualMediaStatus;
}

function renderMediaActivity() {
  const media = virtualMediaStatus;
  const activity = media.activity || {};
  const fresh = activity.updated_at && Date.now() / 1000 - activity.updated_at <= 20;
  let state = media.status === "attached" ? (fresh ? activity.state : "unknown") : media.status;
  const labels = { reading: "Media: Reading", idle: "Media: Idle", disconnected: "Media: USB disconnected",
    unknown: "Media: Activity unavailable", unavailable: "Media: Status unavailable",
    error: "Media: Error", ejected: "Media: No image", attaching: "Media: Mounting", ejecting: "Media: Ejecting" };
  let detail = media.filename || "";
  if (state === "reading") detail += ` · ${formatBytes(activity.read_bytes_per_second)}/s`;
  if (fresh && activity.last_read_at) detail += ` · Last read ${Math.max(0, Math.floor(Date.now() / 1000 - activity.last_read_at))}s ago`;
  document.querySelectorAll(".media-activity").forEach((indicator) => {
    indicator.dataset.state = state;
    indicator.textContent = `● ${labels[state] || "Media: Checking"}${detail ? ` · ${detail}` : ""}`;
    indicator.title = "USB image read activity sampled about every 5 seconds, including cached reads. Idle does not mean an error. This is not OS installation progress.";
  });
}

async function setVirtualMedia(filename = null, force = false) {
  const attaching = Boolean(filename);
  const response = await fetch(`/api/v1/storage/virtual-media${force ? "?force=true" : ""}`, {
    method: attaching ? "POST" : "DELETE",
    headers: attaching ? { "Content-Type": "application/json" } : {},
    body: attaching ? JSON.stringify({ filename }) : null,
  });
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    throw new Error(result.detail || `HTTP ${response.status}`);
  }
  virtualMediaStatus = await response.json();
  showToast(attaching ? `${filename}: attaching read-only media…` : "Ejecting virtual media…");
  for (let attempt = 0; attempt < 12; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 500));
    await loadVirtualMediaStatus();
    const confirmed = attaching
      ? virtualMediaStatus.status === "attached" && virtualMediaStatus.filename === filename
      : virtualMediaStatus.status === "ejected";
    if (confirmed || ["error", "unavailable"].includes(virtualMediaStatus.status)) break;
  }
  if (attaching && virtualMediaStatus.status === "attached" && virtualMediaStatus.filename === filename) showToast(`${virtualMediaStatus.filename}: mounted read-only`);
  else if (!attaching && virtualMediaStatus.status === "ejected") showToast("Virtual media ejected");
  else throw new Error(virtualMediaStatus.message || "Virtual media operation failed");
  await loadStorage();
}

function renderStorage(storage) {
  const mediaReady = storage.status === "ready";
  const percent = storage.total_bytes ? Math.round((storage.used_bytes / storage.total_bytes) * 100) : 0;
  document.querySelector("#storage-state").textContent = mediaReady ? `✓ ${storage.label}` : "Storage unavailable";
  document.querySelector("#storage-choose").disabled = !mediaReady;
  document.querySelector("#storage-dropzone").classList.toggle("storage-disabled", !mediaReady);
  if (!mediaReady) {
    document.querySelector("#storage-capacity").textContent = "Internal stage unavailable";
    document.querySelector("#storage-free").textContent = "Check appliance storage service";
    document.querySelector("#storage-capacity-bar").style.width = "0%";
    const fileCount = document.querySelector("#storage-file-count");
    if (fileCount) fileCount.textContent = "0";
    document.querySelector("#storage-files").innerHTML = '<tr><td colspan="5" class="loading-cell">Internal staging storage is unavailable.</td></tr>';
    return;
  }
  document.querySelector("#storage-capacity").textContent = `${formatBytes(storage.used_bytes)} / ${formatBytes(storage.total_bytes)}`;
  document.querySelector("#storage-free").textContent = `${formatBytes(storage.free_bytes)} available · ${formatBytes(storage.system_reserve_bytes)} system reserve protected`;
  document.querySelector("#storage-capacity-bar").style.width = `${percent}%`;
  const fileCount = document.querySelector("#storage-file-count");
  if (fileCount) fileCount.textContent = storage.file_count;
  const mediaSummary = document.querySelector("#virtual-media-summary");
  if (mediaSummary) {
    mediaSummary.textContent = virtualMediaStatus.status === "attached"
      ? `${virtualMediaStatus.filename} · read-only`
      : virtualMediaStatus.status === "ejected" ? "No media mounted" : (virtualMediaStatus.message || virtualMediaStatus.status);
  }
  const body = document.querySelector("#storage-files");
  if (!storage.files.length) {
    body.innerHTML = '<tr><td colspan="5" class="loading-cell">No staged files. Upload an ISO or firmware package to begin.</td></tr>';
    return;
  }
  body.innerHTML = storage.files.map((file) => {
    const extension = file.name.includes(".") ? file.name.split(".").pop().slice(0, 4).toUpperCase() : "FILE";
    const mountable = /\.(iso|img)$/i.test(file.name);
    const mounted = virtualMediaStatus.status === "attached" && virtualMediaStatus.filename === file.name;
    const mediaAction = mounted
      ? `<button class="eject-media" type="button">Eject</button>`
      : mountable ? `<button class="mount-media" type="button" data-filename="${escapeHtml(file.name)}">Mount</button>` : "";
    return `<tr><td><div class="file-name"><i>${escapeHtml(extension)}</i><span title="${escapeHtml(file.name)}">${escapeHtml(file.name)}${mounted ? " · Mounted" : ""}</span></div></td><td>${escapeHtml(file.media_type)}</td><td>${formatBytes(file.size_bytes)}</td><td>${new Date(file.modified_at).toLocaleString()}</td><td><div class="file-actions">${mediaAction}<button type="button" data-storage-checksum="${escapeHtml(file.name)}">SHA256</button><a href="/api/v1/storage/files/${encodeURIComponent(file.name)}" download>Download</a><button class="delete-file" type="button" data-filename="${escapeHtml(file.name)}" ${mounted ? "disabled" : ""}>Delete</button></div></td></tr>`;
  }).join("");
  document.querySelectorAll(".delete-file").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!window.confirm(`Delete ${button.dataset.filename}?`)) return;
      button.disabled = true;
      try {
        const response = await fetch(`/api/v1/storage/files/${encodeURIComponent(button.dataset.filename)}`, { method: "DELETE" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        showToast(`${button.dataset.filename}: deleted`);
        await loadStorage();
      } catch (error) {
        button.disabled = false;
        showToast(`${button.dataset.filename}: delete failed`);
        console.error("Storage delete failed", error);
      }
    });
  });
  document.querySelectorAll(".mount-media").forEach((button) => button.addEventListener("click", async () => {
    button.disabled = true;
    try { await setVirtualMedia(button.dataset.filename); }
    catch (error) { showToast(`${button.dataset.filename}: ${error.message}`); button.disabled = false; }
  }));
  document.querySelectorAll(".eject-media").forEach((button) => button.addEventListener("click", async () => {
    button.disabled = true;
    try { await setVirtualMedia(); }
    catch (error) { showToast(`Eject failed: ${error.message}`); button.disabled = false; }
  }));
}

async function loadStorage() {
  try {
    await loadVirtualMediaStatus();
    const stage = await getJson("/api/v1/storage");
    renderStorage(stage);
    updateRecoverySources(stage.files);
  } catch (error) {
    document.querySelector("#storage-state").textContent = "Unavailable";
    document.querySelector("#storage-files").innerHTML = '<tr><td colspan="5" class="loading-cell">Staging storage unavailable.</td></tr>';
    console.error("Storage request failed", error);
  }
}

let externalDevice = "";
let externalPath = "";
let externalRequest = 0;
let externalImportRunning = false;

async function loadExternalStorage() {
  if (externalImportRunning) return;
  const request = ++externalRequest;
  const badge = document.querySelector("#external-storage-state");
  const message = document.querySelector("#external-message");
  const body = document.querySelector("#external-files");
  try {
    const [inventory, ports] = await Promise.all([
      getJson("/api/v1/external-storage"),
      getPhysicalPortInventory().catch(() => ({ports: []})),
    ]);
    const wan = ports.ports.find((port) => port.id === "expansion_usb" && port.mode === "wan");
    if (request !== externalRequest) return;
    const volumes = inventory.devices;
    const selection = document.querySelector("#external-volume");
    if (!volumes.some((volume) => volume.id === externalDevice)) {
      externalDevice = volumes[0]?.id || "";
      externalPath = "";
    }
    selection.innerHTML = volumes.length ? volumes.map((volume) =>
      `<option value="${escapeHtml(volume.id)}">${escapeHtml(volume.label)} · ${escapeHtml(volume.filesystem || "Unknown filesystem")}</option>`
    ).join("") : '<option value="">No USB volume</option>';
    selection.value = externalDevice;
    selection.disabled = !volumes.length || externalImportRunning;
    const volume = volumes.find((item) => item.id === externalDevice);
    const ready = volume?.status === "ready";
    badge.textContent = ready ? "Mounted · Read-only" : volume ? "Not mounted" : inventory.status === "unavailable" ? "Unavailable" : "Disconnected";
    badge.className = `badge ${ready ? "ready" : "pending"}`;
    document.querySelector("#external-capacity").textContent = ready
      ? `${formatBytes(volume.used_bytes)} / ${formatBytes(volume.total_bytes)} · ${formatBytes(volume.free_bytes)} free`
      : "";
    message.textContent = ready ? "Files are accessible. The original USB contents are preserved."
      : volume?.message || (inventory.status === "unavailable" ? "USB mount service is unavailable. Check the external storage service on the appliance." : "Insert a USB drive into the Storage / WAN port, or connect a phone with USB tethering enabled. Supported formats: exFAT, FAT and ext4; volumes mount automatically.");
    if (wan && !volume) {
      badge.textContent = wan.status === "usb_wan_ready" ? "USB WAN · IP assigned" : "USB WAN · Waiting for IP";
      badge.className = `badge ${wan.status === "usb_wan_ready" ? "ready" : "pending"}`;
      message.textContent = `${wan.device_name || "USB network device"} · ${wan.network_interface} · IP: ${wan.addresses.join(", ") || "Waiting for DHCP"} · Gateway: ${wan.gateway || "—"}. VPN settings are in Remote Assist.`;
    }
    document.querySelector("#external-path").textContent = `/${externalPath}`;
    document.querySelector("#external-up").disabled = !ready || !externalPath || externalImportRunning;
    if (!ready) {
      body.innerHTML = `<tr><td colspan="3" class="loading-cell">${wan ? 'Port is in USB WAN mode.' : 'No readable USB volume available.'}</td></tr>`;
      return;
    }
    const listing = await getJson(`/api/v1/external-storage/${encodeURIComponent(externalDevice)}/files?path=${encodeURIComponent(externalPath)}`);
    if (request !== externalRequest) return;
    const internal = await getJson("/api/v1/storage").catch(() => null);
    if (request !== externalRequest) return;
    document.querySelector("#external-stage-space").textContent = internal?.status === "ready"
      ? `Internal Stage: ${formatBytes(internal.free_bytes)} available · ${formatBytes(internal.system_reserve_bytes)} reserved for the system. Copies remain until you delete them.`
      : "Internal Stage unavailable. Copy and mount are disabled.";
    if (listing.limited) message.textContent = "Showing the first 1,000 entries in this folder.";
    body.innerHTML = listing.files.length ? listing.files.map((file) => {
      const path = [externalPath, file.name].filter(Boolean).join("/");
      const copyBlocked = internal?.status !== "ready" || file.size_bytes > internal.free_bytes;
      const copyReason = internal?.status !== "ready" ? "Internal Stage unavailable" : copyBlocked ? `Not enough space: needs ${formatBytes(file.size_bytes)}, available ${formatBytes(internal.free_bytes)}` : "";
      const endpoint = `/api/v1/external-storage/${encodeURIComponent(externalDevice)}`;
      return `<tr><td>${file.directory ? `<button class="external-folder" data-path="${escapeHtml(path)}" type="button">▸ ${escapeHtml(file.name)}</button>` : escapeHtml(file.name)}</td><td>${file.directory ? "Folder" : formatBytes(file.size_bytes)}</td><td>${file.directory ? "" : `<div class="file-actions"><a href="${endpoint}/download?path=${encodeURIComponent(path)}" download>Download</a><button class="external-import" data-path="${escapeHtml(path)}" type="button" ${externalImportRunning || copyBlocked ? "disabled" : ""} title="${escapeHtml(copyReason)}" data-size="${file.size_bytes}">Copy to Internal Stage</button>${/\.(iso|img)$/i.test(file.name) ? `<button class="external-import" data-mount="true" data-path="${escapeHtml(path)}" type="button" ${externalImportRunning || copyBlocked ? "disabled" : ""} title="${escapeHtml(copyReason)}" data-size="${file.size_bytes}">Copy &amp; Mount</button>` : ""}</div>${copyBlocked ? `<small class="storage-space-warning">${escapeHtml(copyReason)}</small>` : ""}`}</td></tr>`;
    }).join("") : '<tr><td colspan="3" class="loading-cell">This folder is empty.</td></tr>';
    body.querySelectorAll(".external-folder").forEach((button) => button.addEventListener("click", () => {
      if (externalImportRunning) return;
      externalPath = button.dataset.path;
      loadExternalStorage();
    }));
    body.querySelectorAll(".external-import").forEach((button) => button.addEventListener("click", async () => {
      if (externalImportRunning) return;
      const device = externalDevice;
      externalImportRunning = true;
      ++externalRequest;
      document.querySelector("#external-volume").disabled = true;
      document.querySelector("#external-refresh").disabled = true;
      document.querySelector("#external-up").disabled = true;
      let copied = false;
      const copyTask = {
        id: newStorageTaskId(), file: { name: button.dataset.path.split("/").pop(), size: Number(button.dataset.size) },
        status: "running", progress: 0, loaded: 0, externalCopy: true, phase: "Checking capacity",
      };
      storageTasks.set(copyTask.id, copyTask);
      renderStorageTasks();
      body.querySelectorAll(".external-import").forEach((item) => { item.disabled = true; });
      message.textContent = button.dataset.mount ? "Copying to internal staging, then mounting on the target PC…" : "Copying to internal staging… Progress is available in Tasks.";
      try {
        const capacity = await getJson("/api/v1/storage");
        if (capacity.status !== "ready") throw new Error("Internal Stage unavailable");
        if (Number(button.dataset.size) > capacity.free_bytes) {
          throw new Error(`Not enough space: needs ${formatBytes(Number(button.dataset.size))}, available ${formatBytes(capacity.free_bytes)}. Delete unused files from Internal Stage and retry.`);
        }
        copyTask.phase = "Copying USB → Internal Stage";
        renderStorageTasks();
        const response = await fetch(`/api/v1/external-storage/${encodeURIComponent(device)}/import`, {
          method: "POST", headers: { "Content-Type": "application/json", "X-Kronos-Task-ID": copyTask.id },
          body: JSON.stringify({ path: button.dataset.path }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
        copied = true;
        showToast(`${result.name}: copied to Internal Stage`);
        copyTask.loaded = copyTask.file.size;
        copyTask.progress = 100;
        if (button.dataset.mount) {
          copyTask.phase = "Copy complete · Mounting on target PC";
          renderStorageTasks();
          await setVirtualMedia(result.name);
        }
        copyTask.status = "completed";
        copyTask.finishedAt = new Date();
        message.textContent = button.dataset.mount ? `${result.name}: copied and mounted` : `${result.name}: copied to Internal Stage`;
        renderStorageTasks();
        await loadStorage();
      } catch (error) {
        copyTask.status = "failed";
        copyTask.error = `${copied ? "Copied, but mount failed" : "Copy failed"}: ${error.message}`;
        copyTask.finishedAt = new Date();
        renderStorageTasks();
        showToast(copyTask.error);
      } finally {
        externalImportRunning = false;
        document.querySelector("#external-refresh").disabled = false;
        loadExternalStorage();
      }
    }));
  } catch (error) {
    if (request !== externalRequest) return;
    badge.textContent = "Unavailable";
    badge.className = "badge pending";
    message.textContent = "USB storage could not be read. Reconnect the drive or return to the parent folder and refresh.";
    body.innerHTML = '<tr><td colspan="3" class="loading-cell">USB files unavailable.</td></tr>';
  }
}

const storageTasks = new Map();
let recoveryPublishRunning = false;
const storageTaskQueue = [];
const maxParallelStorageTasks = 2;
let activeStorageTasks = 0;
const supportedStorageExtensions = new Set([
  "iso", "img", "bin", "fw", "rom", "efi", "zip", "tar", "gz", "tgz", "xz",
  "bz2", "7z", "pkg", "swi", "stk", "qcow2", "ova",
]);

window.addEventListener("beforeunload", (event) => {
  if (!externalImportRunning && activeStorageTasks === 0 && storageTaskQueue.every((task) => task.status !== "queued")) return;
  event.preventDefault();
  event.returnValue = "";
});

function newStorageTaskId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (digit) =>
    (Number(digit) ^ Math.random() * 16 >> Number(digit) / 4).toString(16)
  );
}

function renderStorageTasks() {
  const center = document.querySelector("#task-center");
  const tasks = [...storageTasks.values()];
  center.hidden = tasks.length === 0;
  const active = tasks.filter((task) => ["queued", "running", "cancelling"].includes(task.status)).length;
  const completed = tasks.filter((task) => task.status === "completed").length;
  const unsuccessful = tasks.filter((task) => ["failed", "cancelled"].includes(task.status)).length;
  document.querySelector("#task-summary").textContent = `${active} active · ${completed} successful · ${unsuccessful} unsuccessful`;
  const statusLabels = {
    queued: "Waiting",
    running: "In progress",
    cancelling: "Cancelling",
    completed: "Completed · Successful",
    failed: "Completed · Failed",
    cancelled: "Cancelled",
  };
  document.querySelector("#task-list").innerHTML = tasks.map((task) => {
    const cancellable = !task.serverManaged && !task.externalCopy && ["queued", "running"].includes(task.status);
    const result = task.error ? ` · ${task.error}` : task.finishedAt ? ` · ${task.finishedAt.toLocaleTimeString()}` : "";
    const action = cancellable
      ? '<button type="button" class="task-cancel">Cancel</button>'
      : (task.serverManaged || task.externalCopy) && task.status === "running" ? "" : '<button type="button" class="task-dismiss">Dismiss</button>';
    return `<article class="task-row task-${escapeHtml(task.status)}" data-task-id="${escapeHtml(task.id)}"><div><strong>${escapeHtml(task.file?.name || task.title || "Service operation")}</strong><small><b>${escapeHtml(task.status === "running" && task.phase ? task.phase : statusLabels[task.status] || task.status)}</b> · ${task.serverManaged ? "Service operation" : `${formatBytes(task.loaded)} / ${formatBytes(task.file.size)}`}${escapeHtml(result)}</small></div>${action}<div class="task-progress"><i style="width:${task.progress}%"></i></div></article>`;
  }).join("");
  document.querySelectorAll(".task-cancel").forEach((button) => {
    button.addEventListener("click", () => cancelStorageTask(button.closest("[data-task-id]").dataset.taskId));
  });
  document.querySelectorAll(".task-dismiss").forEach((button) => {
    button.addEventListener("click", () => {
      storageTasks.delete(button.closest("[data-task-id]").dataset.taskId);
      renderStorageTasks();
    });
  });
}

function finishStorageTask(task, status, error = null) {
  task.status = status;
  task.error = error;
  task.finishedAt = new Date();
  if (status === "completed") {
    task.progress = 100;
    task.loaded = task.file.size;
    showToast(`${task.file.name}: upload complete`);
  } else if (status !== "cancelled") {
    showToast(`${task.file.name}: upload failed`);
  }
  activeStorageTasks = Math.max(0, activeStorageTasks - 1);
  renderStorageTasks();
  loadStorage();
  pumpStorageTasks();
}

function runStorageTask(task) {
  activeStorageTasks += 1;
  task.status = "running";
  const request = new XMLHttpRequest();
  task.request = request;
  request.open("PUT", `/api/v1/storage/files/${encodeURIComponent(task.file.name)}`);
  request.setRequestHeader("Content-Type", task.file.type || "application/octet-stream");
  request.setRequestHeader("X-Kronos-Task-ID", task.id);
  request.upload.addEventListener("progress", (event) => {
    task.loaded = event.loaded;
    task.progress = event.lengthComputable ? Math.round(event.loaded / event.total * 100) : 0;
    renderStorageTasks();
  });
  request.addEventListener("load", () => finishStorageTask(
    task,
    request.status >= 200 && request.status < 300 ? "completed" : "failed",
    request.status >= 200 && request.status < 300 ? null : `HTTP ${request.status}`,
  ));
  request.addEventListener("error", () => finishStorageTask(task, "failed", "Network error"));
  request.addEventListener("abort", () => finishStorageTask(task, "cancelled"));
  request.send(task.file);
  renderStorageTasks();
}

function pumpStorageTasks() {
  while (activeStorageTasks < maxParallelStorageTasks && storageTaskQueue.length) {
    const task = storageTaskQueue.shift();
    if (task.status === "queued") runStorageTask(task);
  }
}

function uploadStorageFiles(files) {
  files.forEach((file) => {
    const extension = file.name.includes(".") ? file.name.split(".").pop().toLowerCase() : "";
    if (!supportedStorageExtensions.has(extension)) {
      showToast(`${file.name}: unsupported staging file type`);
      return;
    }
    const duplicate = [...storageTasks.values()].some(
      (task) => task.file.name === file.name && ["queued", "running"].includes(task.status)
    );
    if (duplicate) {
      showToast(`${file.name}: already queued`);
      return;
    }
    const task = {
      id: newStorageTaskId(), file, status: "queued", progress: 0, loaded: 0, request: null,
    };
    storageTasks.set(task.id, task);
    storageTaskQueue.push(task);
  });
  document.querySelector("#storage-file-input").value = "";
  renderStorageTasks();
  pumpStorageTasks();
}

function cancelStorageTask(taskId) {
  const task = storageTasks.get(taskId);
  if (!task || !["queued", "running"].includes(task.status)) return;
  if (task.status === "queued") {
    task.status = "cancelled";
    renderStorageTasks();
    return;
  }
  task.status = "cancelling";
  fetch(`/api/v1/storage/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" }).catch(() => {});
  task.request?.abort();
  renderStorageTasks();
}

function consoleButtonForPort(portId) {
  return document.querySelector(`.console-action[data-port-id="${portId}"]`);
}

function openPortConsole(portId) {
  const button = consoleButtonForPort(portId);
  if (!button || button.disabled) {
    showToast(`${portId === "console_2" ? "Console 2" : "Console 1"}: adapter not detected`);
    return;
  }
  openConsole(button);
}

async function loadPorts(attempt = 0) {
  window.clearTimeout(portRetryTimer);
  try {
    renderPorts(await getPhysicalPortInventory());
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
    button.disabled = !button.dataset.device;
  });
}

const ansiColors = {
  30: "ansi-black", 31: "ansi-red", 32: "ansi-green", 33: "ansi-yellow",
  34: "ansi-blue", 35: "ansi-magenta", 36: "ansi-cyan", 37: "ansi-white",
  90: "ansi-bright-black", 91: "ansi-bright-red", 92: "ansi-bright-green",
  93: "ansi-bright-yellow", 94: "ansi-bright-blue", 95: "ansi-bright-magenta",
  96: "ansi-bright-cyan", 97: "ansi-bright-white",
};

function terminalMarkup(session, value) {
  const input = `${session.ansiPending || ""}${value}`
    .replace(/\x1b\][^\x07]*(?:\x07|\x1b\\)/g, "")
    .replace(/\x1b\[\??[0-9;]*[A-HJKSTfhlnsu]/g, "");
  session.ansiPending = "";
  let output = "";
  let position = 0;
  input.replace(/\x1b\[([0-9;]*)m/g, (match, parameters, offset) => {
    output += escapeHtml(input.slice(position, offset));
    const codes = (parameters || "0").split(";").map(Number);
    for (const code of codes) {
      if (code === 0) session.ansiClasses = [];
      else if (code === 1 && !session.ansiClasses?.includes("ansi-bold")) {
        session.ansiClasses = [...(session.ansiClasses || []), "ansi-bold"];
      } else if (code === 22) session.ansiClasses = (session.ansiClasses || []).filter((item) => item !== "ansi-bold");
      else if (code === 39) session.ansiClasses = (session.ansiClasses || []).filter((item) => !item.startsWith("ansi-") || item === "ansi-bold");
      else if (ansiColors[code]) {
        session.ansiClasses = (session.ansiClasses || []).filter((item) => !item.startsWith("ansi-") || item === "ansi-bold");
        session.ansiClasses.push(ansiColors[code]);
      }
    }
    position = offset + match.length;
    return match;
  });
  output += escapeHtml(input.slice(position));
  const plain = input.replace(/\x1b\[[0-9;]*m/g, "").replace(/\r(?!\n)/g, "");
  return { html: session.ansiClasses?.length ? `<span class="${session.ansiClasses.join(" ")}">${output}</span>` : output, plain };
}

function appendTerminal(session, value) {
  const terminal = session.element.querySelector(".terminal");
  const rendered = terminalMarkup(session, String(value));
  terminal.insertAdjacentHTML("beforeend", rendered.html);
  if (session.logging) session.logParts.push(rendered.plain);
  if (terminal.textContent.length > 100000) terminal.textContent = terminal.textContent.slice(-80000);
  terminal.scrollTop = terminal.scrollHeight;
}

function focusTerminal(element) {
  terminalZIndex += 1;
  element.style.zIndex = terminalZIndex;
}

const compactLayout = window.matchMedia("(max-width: 760px), (max-width: 1024px) and (pointer: coarse)");

function enableTerminalDrag(element) {
  const handle = element.querySelector(".terminal-titlebar");
  handle.addEventListener("pointerdown", (event) => {
    if (compactLayout.matches || event.target.closest("button") || element.classList.contains("maximized")) return;
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
      <div class="terminal-heading"><div><strong>${escapeHtml(label)}</strong><span>${escapeHtml(button.dataset.portName)} · ${profile.baud_rate} · ${profile.data_bits}${profile.parity[0].toUpperCase()}${profile.stop_bits}</span></div></div>
      <div class="terminal-controls"><button class="terminal-minimize" title="Minimize">−</button><button class="terminal-maximize" title="Maximize">□</button><button class="terminal-close" title="Close">×</button></div>
    </header>
    <pre class="terminal" tabindex="0" aria-label="${escapeHtml(label)} interactive serial terminal">Connecting…\n</pre>
    <footer class="terminal-footer"><div class="terminal-log-controls"><button class="log-start" type="button">● Start log</button><button class="log-stop" type="button" disabled>■ Stop log</button><span class="log-file-name">No active log</span><button class="log-download" type="button" disabled>↓ Download Active Log</button></div><span class="terminal-connection connecting"><i></i><b>Connecting</b></span></footer>`;
  document.querySelector("#terminal-layer").appendChild(element);
  focusTerminal(element);
  enableTerminalDrag(element);
  element.addEventListener("pointerdown", () => focusTerminal(element));
  return element;
}

function openSshTerminal(profile) {
  const portId = `ssh-${profile.id}`;
  if (terminals.has(portId)) {
    focusTerminal(terminals.get(portId).element);
    return;
  }
  const username = window.prompt(`SSH username for ${profile.host}`, profile.username || "");
  if (username === null || !username.trim()) return;
  const password = window.prompt(`SSH password for ${username}@${profile.host}\n(Not saved)`);
  if (password === null) return;

  const button = { dataset: { portId, portName: `SSH · ${profile.host}` } };
  const terminalProfile = {
    display_name: profile.name, baud_rate: "SSH", data_bits: "", parity: " ", stop_bits: "",
  };
  const element = createTerminalWindow(button, terminalProfile);
  element.querySelector(".terminal-heading span").textContent = `${username}@${profile.host}:${profile.port}`;
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${location.host}/api/v1/ssh/ws`);
  const session = {
    socket, element, device: profile.host, label: profile.name,
    profile: { ...profile, username: username.trim() }, logging: false, logParts: [],
  };
  terminals.set(portId, session);
  socket.addEventListener("open", () => socket.send(JSON.stringify({
    host: profile.host, port: profile.port, username: username.trim(), password,
  })));
  socket.addEventListener("message", (event) => {
    appendTerminal(session, event.data);
    if (String(event.data).includes("SSH connected")) {
      const status = element.querySelector(".terminal-connection");
      status.className = "terminal-connection connected";
      status.querySelector("b").textContent = "Connected";
      element.querySelector(".terminal").focus();
    }
  });
  socket.addEventListener("close", () => {
    const status = element.querySelector(".terminal-connection");
    status.className = "terminal-connection disconnected";
    status.querySelector("b").textContent = "Disconnected";
    session.socket = null;
  });
  socket.addEventListener("error", () => appendTerminal(session, "\nSSH WebSocket error.\n"));
  const send = (value) => {
    if (session.socket?.readyState === WebSocket.OPEN) session.socket.send(value);
  };
  const specialKeys = {
    Enter: "\r", Backspace: "\x7f", Tab: "\t", Escape: "\x1b",
    ArrowUp: "\x1b[A", ArrowDown: "\x1b[B", ArrowRight: "\x1b[C", ArrowLeft: "\x1b[D",
    Home: "\x1b[H", End: "\x1b[F", Delete: "\x1b[3~", PageUp: "\x1b[5~", PageDown: "\x1b[6~",
  };
  element.querySelector(".terminal").addEventListener("keydown", (event) => {
    let value = specialKeys[event.key];
    if (event.ctrlKey && event.key.length === 1 && /[a-z]/i.test(event.key)) {
      value = String.fromCharCode(event.key.toUpperCase().charCodeAt(0) - 64);
    } else if (!event.ctrlKey && !event.metaKey && !event.altKey && event.key.length === 1) {
      value = event.key;
    }
    if (value !== undefined) { event.preventDefault(); send(value); }
  });
  element.querySelector(".terminal").addEventListener("paste", (event) => {
    event.preventDefault();
    send(event.clipboardData.getData("text"));
  });
  element.querySelector(".terminal-close").addEventListener("click", () => closeTerminal(portId));
  element.querySelector(".terminal-minimize").addEventListener("click", () => element.classList.toggle("minimized"));
  element.querySelector(".terminal-maximize").addEventListener("click", () => element.classList.toggle("maximized"));
  element.querySelector(".log-start").addEventListener("click", () => startTerminalLog(session));
  element.querySelector(".log-stop").addEventListener("click", () => stopTerminalLog(session));
  element.querySelector(".log-download").addEventListener("click", () => downloadTerminalLog(session));
}

function openConsole(button, profileOverride = null) {
  if (!button.dataset.device) return;
  if (terminals.has(button.dataset.portId)) {
    const existing = terminals.get(button.dataset.portId).element;
    existing.classList.remove("minimized");
    focusTerminal(existing);
    return;
  }
  const conflictingEntry = [...terminals.entries()].find(
    ([, session]) => session.device === button.dataset.device
  );
  if (conflictingEntry) {
    const [conflictingPortId, conflictingSession] = conflictingEntry;
    if (conflictingSession.socket && conflictingSession.socket.readyState !== WebSocket.CLOSED) {
      conflictingSession.socket.addEventListener(
        "close", () => window.setTimeout(() => openConsole(button, profileOverride), 100),
        { once: true }
      );
      closeTerminal(conflictingPortId);
      showToast("Serial adapter moved; previous terminal closed");
      return;
    }
    closeTerminal(conflictingPortId);
  }
  const profile = profileOverride || serialProfile(button.dataset.portId);
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
  const label = profile.display_name.trim() || button.dataset.portName;
  const element = createTerminalWindow(button, profile);
  const session = {
    socket,
    element,
    device: button.dataset.device,
    label,
    profile,
    logging: false,
    logParts: [],
  };
  terminals.set(button.dataset.portId, session);
  button.closest("details").removeAttribute("open");
  setConnectionControls();
  const decoder = new TextDecoder();
  socket.binaryType = "arraybuffer";
  const markConnected = () => {
    const status = element.querySelector(".terminal-connection");
    status.className = "terminal-connection connected";
    status.querySelector("b").textContent = "Connected";
  };
  socket.addEventListener("open", () => {
    if (profile.baud_rate === "auto") {
      appendTerminal(session, "Testing common baud rates…\n");
      return;
    }
    markConnected();
    appendTerminal(session, "Connected. Press Enter to request the prompt.\n");
    socket.send(new TextEncoder().encode("\r"));
    element.querySelector(".terminal").focus();
  });
  socket.addEventListener("message", (event) => {
    const output = event.data instanceof ArrayBuffer ? decoder.decode(event.data, { stream: true }) : event.data;
    if (typeof output === "string" && output.includes("auto-detected")) {
      markConnected();
      element.querySelector(".terminal").focus();
    }
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
  element.querySelector(".log-start").addEventListener("click", () => startTerminalLog(session));
  element.querySelector(".log-stop").addEventListener("click", () => stopTerminalLog(session));
  element.querySelector(".log-download").addEventListener("click", () => downloadTerminalLog(session));
}

async function disconnectSerialSession(button, announce = true) {
  const deviceName = button.dataset.device.split("/").pop();
  button.closest("details").removeAttribute("open");
  [...terminals.entries()]
    .filter(([, session]) => session.device === button.dataset.device)
    .forEach(([portId]) => closeTerminal(portId));
  try {
    const response = await fetch(`/api/v1/serial/sessions/${encodeURIComponent(deviceName)}`, {
      method: "DELETE",
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    if (announce) showToast(`${button.dataset.portName}: disconnected`);
    return true;
  } catch (error) {
    showToast(`${button.dataset.portName}: disconnect failed`);
    console.error("Serial session disconnect failed", error);
    return false;
  }
}

async function redetectAndConnect(button) {
  if (!await disconnectSerialSession(button, false)) return;
  const profile = { ...serialProfile(button.dataset.portId), baud_rate: "auto" };
  showToast(`${button.dataset.portName}: detecting console speed`);
  window.setTimeout(() => openConsole(button, profile), 100);
}

function setLogButtons(session) {
  session.element.querySelector(".log-start").disabled = session.logging;
  session.element.querySelector(".log-stop").disabled = !session.logging;
  session.element.querySelector(".log-download").disabled = session.logging || session.logStaging || !session.stagedLog;
}

function terminalLogProfile(session) {
  if (session.profile.type === "ssh") {
    return `Profile: SSH ${session.profile.username || "user"}@${session.profile.host}:${session.profile.port}`;
  }
  const profile = session.profile;
  return `Profile: ${profile.baud_rate} baud, ${profile.data_bits}${profile.parity[0].toUpperCase()}${profile.stop_bits}, flow=${profile.flow_control}`;
}

function pendingTerminalLogName(session, started) {
  const slug = session.label.toLowerCase().replace(/[^a-z0-9]+/g, "") || "console";
  const stamp = started.toISOString().replace(/[-:]/g, "").replace("T", "-").slice(0, 15);
  return `${slug}-${stamp}.txt`;
}

function startTerminalLog(session) {
  const started = new Date();
  session.logging = true;
  session.logStartedAt = started;
  session.stagedLog = null;
  session.logStaging = false;
  session.pendingLogName = pendingTerminalLogName(session, started);
  session.logParts = [
    `KDX InfraBox terminal session log\n`,
    `Terminal: ${session.label}\n`,
    `Started: ${started.toISOString()}\n`,
    `${terminalLogProfile(session)}\n`,
    `${"-".repeat(72)}\n`,
  ];
  session.element.querySelector(".log-file-name").textContent = session.pendingLogName;
  setLogButtons(session);
  showToast(`${session.label}: logging started`);
}

function stopTerminalLog(session) {
  if (!session.logging) return;
  session.logParts.push(`\n${"-".repeat(72)}\nStopped: ${new Date().toISOString()}\n`);
  session.logging = false;
  session.logStaging = true;
  session.element.querySelector(".log-file-name").textContent = `Staging ${session.pendingLogName}…`;
  setLogButtons(session);
  showToast(`${session.label}: staging temporary log`);
  stageTerminalLog(session);
}

async function stageTerminalLog(session) {
  try {
    session.stagedLog = await stageSessionLog(
      session.label, session.logStartedAt, session.logParts.join("")
    );
    session.element.querySelector(".log-file-name").textContent = session.stagedLog.filename;
    showToast(`${session.stagedLog.filename}: ready to download`);
    loadSessionLogs();
  } catch (error) {
    console.error("Session log staging failed", error);
    session.element.querySelector(".log-file-name").textContent = "Log staging failed";
    showToast(`${session.label}: session log could not be staged`);
  } finally {
    session.logStaging = false;
    setLogButtons(session);
  }
}

async function stageSessionLog(label, startedAt, content) {
  const response = await fetch("/api/v1/session-logs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label, started_at: startedAt?.toISOString(), content }),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function downloadTerminalLog(session) {
  if (session.logging || !session.stagedLog) return;
  const link = document.createElement("a");
  link.href = session.stagedLog.download_url;
  link.download = session.stagedLog.filename;
  link.click();
}

function closeTerminal(portId) {
  const session = terminals.get(portId);
  if (!session) return;
  if (session.logging) stopTerminalLog(session);
  terminals.delete(portId);
  session.element.remove();
  setConnectionControls();
  if (!session.socket) return;
  if (session.socket.readyState === WebSocket.CONNECTING) {
    session.socket.addEventListener(
      "open", () => session.socket.close(1000, "operator disconnect"), { once: true }
    );
  } else if (session.socket.readyState === WebSocket.OPEN) {
    session.socket.close(1000, "operator disconnect");
  }
}

let videoWindow = null;
let stagingStorage = null;
const hidKeyCodes = {
  KeyA: 4, KeyB: 5, KeyC: 6, KeyD: 7, KeyE: 8, KeyF: 9, KeyG: 10, KeyH: 11,
  KeyI: 12, KeyJ: 13, KeyK: 14, KeyL: 15, KeyM: 16, KeyN: 17, KeyO: 18, KeyP: 19,
  KeyQ: 20, KeyR: 21, KeyS: 22, KeyT: 23, KeyU: 24, KeyV: 25, KeyW: 26, KeyX: 27,
  KeyY: 28, KeyZ: 29, Digit1: 30, Digit2: 31, Digit3: 32, Digit4: 33, Digit5: 34,
  Digit6: 35, Digit7: 36, Digit8: 37, Digit9: 38, Digit0: 39, Enter: 40, Escape: 41,
  Backspace: 42, Tab: 43, Space: 44, Minus: 45, Equal: 46, BracketLeft: 47,
  BracketRight: 48, Backslash: 49, Semicolon: 51, Quote: 52, Backquote: 53, Comma: 54,
  Period: 55, Slash: 56, CapsLock: 57, F1: 58, F2: 59, F3: 60, F4: 61, F5: 62,
  F6: 63, F7: 64, F8: 65, F9: 66, F10: 67, F11: 68, F12: 69, PrintScreen: 70,
  ScrollLock: 71, Pause: 72, Insert: 73, Home: 74, PageUp: 75, Delete: 76, End: 77,
  PageDown: 78, ArrowRight: 79, ArrowLeft: 80, ArrowDown: 81, ArrowUp: 82,
};
const hidModifierCodes = {
  ControlLeft: 1, ShiftLeft: 2, AltLeft: 4, MetaLeft: 8,
  ControlRight: 16, ShiftRight: 32, AltRight: 64, MetaRight: 128,
};
const screenKeyboardRows = [
  [["Esc", "Escape"], ["F1", "F1"], ["F2", "F2"], ["F3", "F3"], ["F4", "F4"], ["F5", "F5"], ["F6", "F6"], ["F7", "F7"], ["F8", "F8"], ["F9", "F9"], ["F10", "F10"], ["F11", "F11"], ["F12", "F12"], ["Del", "Delete"]],
  [["`", "Backquote"], ["1", "Digit1"], ["2", "Digit2"], ["3", "Digit3"], ["4", "Digit4"], ["5", "Digit5"], ["6", "Digit6"], ["7", "Digit7"], ["8", "Digit8"], ["9", "Digit9"], ["0", "Digit0"], ["-", "Minus"], ["=", "Equal"], ["Backspace", "Backspace"]],
  [["Tab", "Tab"], ["Q", "KeyQ"], ["W", "KeyW"], ["E", "KeyE"], ["R", "KeyR"], ["T", "KeyT"], ["Y", "KeyY"], ["U", "KeyU"], ["I", "KeyI"], ["O", "KeyO"], ["P", "KeyP"], ["[", "BracketLeft"], ["]", "BracketRight"], ["\\", "Backslash"]],
  [["Caps", "CapsLock"], ["A", "KeyA"], ["S", "KeyS"], ["D", "KeyD"], ["F", "KeyF"], ["G", "KeyG"], ["H", "KeyH"], ["J", "KeyJ"], ["K", "KeyK"], ["L", "KeyL"], [";", "Semicolon"], ["'", "Quote"], ["Enter", "Enter"]],
  [["Shift", "ShiftLeft", "modifier"], ["Z", "KeyZ"], ["X", "KeyX"], ["C", "KeyC"], ["V", "KeyV"], ["B", "KeyB"], ["N", "KeyN"], ["M", "KeyM"], [",", "Comma"], [".", "Period"], ["/", "Slash"], ["↑", "ArrowUp"], ["Shift", "ShiftRight", "modifier"]],
  [["Ctrl", "ControlLeft", "modifier"], ["Alt", "AltLeft", "modifier"], ["Space", "Space"], ["AltGr", "AltRight", "modifier"], ["Ctrl", "ControlRight", "modifier"], ["←", "ArrowLeft"], ["↓", "ArrowDown"], ["→", "ArrowRight"], ["Ctrl+Alt+Del", "cad", "special"]],
];

function screenKeyboardMarkup() {
  return screenKeyboardRows.map((row) => `<div class="keyboard-row">${row.map(([label, code, kind = "key"]) =>
    `<button type="button" class="keyboard-key ${kind}" data-hid-code="${code}">${label}</button>`
  ).join("")}</div>`).join("");
}

async function loadVideoStatus() {
  const card = document.querySelector("#video-session-card");
  const button = document.querySelector("#open-video");
  const label = document.querySelector("#video-session-status");
  try {
    const status = await getJson("/api/v1/video/status");
    button.disabled = !status.signal;
    card.classList.toggle("pending-session", !status.signal);
    label.textContent = status.signal
      ? `${status.width}×${status.height} · capture ready`
      : status.ready ? "Waiting for HDMI signal" : "Video capture unavailable";
  } catch (error) {
    button.disabled = true;
    card.classList.add("pending-session");
    label.textContent = "Video capture status unavailable";
    console.error(error);
  }
}

function closeVideoWindow() {
  if (!videoWindow) return;
  const closingSession = videoWindow;
  videoWindow.stopRecording?.();
  videoWindow.aspectObserver?.disconnect();
  window.clearInterval(videoWindow.resolutionTimer);
  window.clearTimeout(videoWindow.streamRetryTimer);
  videoWindow.image.src = "";
  window.clearInterval(videoWindow.keepAwakeTimer);
  videoWindow.clearMouseMotion?.();
  videoWindow.mouseMotionAbort?.abort();
  videoWindow.releaseAllKeys?.();
  videoWindow.closeHid?.();
  videoWindow.keyboard?.remove();
  videoWindow.element.remove();
  videoWindow = null;
  const endedAt = new Date();
  const content = [
    "KDX InfraBox KVM session log\n",
    `Started: ${closingSession.startedAt.toISOString()}\n`,
    `Stopped: ${endedAt.toISOString()}\n`,
    `Duration: ${Math.round((endedAt - closingSession.startedAt) / 1000)} seconds\n`,
    `Last resolution: ${closingSession.image.naturalWidth || 0}x${closingSession.image.naturalHeight || 0}\n`,
    `Keyboard reports: ${closingSession.keyboardReports}\n`,
    `Mouse reports: ${closingSession.mouseReports}\n`,
  ].join("");
  stageSessionLog("KVM", closingSession.startedAt, content)
    .then(() => loadSessionLogs())
    .catch((error) => console.error("KVM session log staging failed", error));
}

function openVideoWindow() {
  if (videoWindow) {
    videoWindow.element.classList.remove("minimized");
    focusTerminal(videoWindow.element);
    return;
  }
  const element = document.createElement("section");
  element.className = "terminal-window video-window";
  element.style.left = `${Math.max(12, Math.min(110, window.innerWidth - 420))}px`;
  element.style.top = "105px";
  element.innerHTML = `<header class="terminal-titlebar">
      <div class="terminal-heading"><div><strong>KDX InfraBox Remote Console</strong><span>VGA KVM · HDMI capture</span></div></div>
      <div class="terminal-controls"><button class="terminal-minimize" title="Minimize">−</button><button class="terminal-maximize" title="Maximize">□</button><button class="terminal-close" title="Close">×</button></div>
    </header>
    <div class="kvm-toolbar">
      <button type="button" data-kvm-action="sensitivity" title="Change mouse sensitivity">Mouse: 0.2×</button>
      <button type="button" data-kvm-action="snapshot">▣ Snapshot</button>
      <button type="button" data-kvm-action="record">● Record</button>
      <button type="button" data-kvm-action="play">Ⅱ Pause</button>
      <button type="button" data-kvm-action="fullscreen">⛶ Full screen</button>
      <button type="button" data-kvm-action="view">▣ View: Fit</button>
      <button type="button" data-kvm-action="aspect">◇ Lock ratio</button>
      <button type="button" data-kvm-action="keyboard">⌨ Hot keys</button>
      <button type="button" data-kvm-action="media">▤ Virtual media</button>
    </div>
    <div class="media-activity" role="status">● Media: Checking…</div>
    <div class="video-stage"><img class="video-frame" tabindex="0" draggable="false" alt="KDX InfraBox target video"></div>
    <aside class="virtual-media-drawer" hidden><div><strong>Virtual media</strong><button type="button" class="force-media-eject">Force Eject</button><button type="button" class="media-close">×</button></div><p>ISO and IMG files from staging storage</p><div class="virtual-media-files">Loading staged media…</div></aside>
    <div class="video-keyboard" hidden><div class="keyboard-heading terminal-titlebar"><span>Raw HID · US physical layout</span><div><button type="button" class="keyboard-release">Release all keys</button><button type="button" class="keyboard-hide" aria-label="Close keyboard">×</button></div></div>${screenKeyboardMarkup()}</div>
    <footer class="terminal-footer kvm-footer"><div class="video-footer-tools"><button type="button" class="kvm-modifier" data-modifier="4">Alt</button><button type="button" class="kvm-modifier" data-modifier="2">Shift</button><button type="button" class="kvm-modifier" data-modifier="1">Ctrl</button><button type="button" class="kvm-caps-lock" title="Toggle Caps Lock on the target computer">Caps Lock</button><button type="button" class="kvm-hotkey-cad">Ctrl Alt Del</button><button type="button" class="keep-awake-toggle active">◉ Keep awake</button></div><div class="kvm-footer-state"><span class="video-resolution">—</span><span class="video-frame-status">Loading video…</span><span class="terminal-connection connecting"><i></i><b>Connecting HID</b></span></div></footer>`;
  document.querySelector("#terminal-layer").appendChild(element);
  loadVirtualMediaStatus();
  const image = element.querySelector(".video-frame");
  const status = element.querySelector(".video-frame-status");
  const keyboard = element.querySelector(".video-keyboard");
  let playing = true;
  let streamRetryTimer = 0;
  let currentWidth = 0;
  let currentHeight = 0;
  let signalAvailable = true;
  let suppressStreamError = false;
  const kvmStartedAt = new Date();
  let keyboardReports = 0;
  let mouseReports = 0;
  const startVideoStream = (message = "Connecting video…", delay = 120) => {
    window.clearTimeout(streamRetryTimer);
    if (!playing) return;
    status.textContent = message;
    suppressStreamError = true;
    image.src = "";
    streamRetryTimer = window.setTimeout(() => {
      suppressStreamError = false;
      if (playing) image.src = `/api/v1/video/stream.mjpg?t=${Date.now()}`;
    }, delay);
  };
  keyboard.remove();
  keyboard.style.left = `${Math.max(8, (window.innerWidth - Math.min(900, window.innerWidth - 16)) / 2)}px`;
  keyboard.style.top = `${Math.max(90, window.innerHeight - 310)}px`;
  document.querySelector("#terminal-layer").appendChild(keyboard);
  enableTerminalDrag(keyboard);
  keyboard.addEventListener("pointerdown", () => focusTerminal(keyboard));
  image.addEventListener("load", () => {
    status.textContent = "Live stream · 12 FPS";
    currentWidth = image.naturalWidth;
    currentHeight = image.naturalHeight;
    element.querySelector(".video-resolution").textContent = `${image.naturalWidth} × ${image.naturalHeight}`;
  });
  image.addEventListener("error", () => {
    if (playing && !suppressStreamError) startVideoStream("Video signal changed · reconnecting…", 900);
  });
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const connection = element.querySelector(".terminal-connection");
  let socket = null;
  let hidClosing = false;
  let hidReconnectTimer = 0;
  const connectHid = () => {
    if (hidClosing) return;
    connection.className = "terminal-connection connecting";
    connection.querySelector("b").textContent = "Connecting HID";
    socket = new WebSocket(`${protocol}://${location.host}/api/v1/hid/ws`);
    socket.addEventListener("open", () => {
      connection.className = "terminal-connection connected";
      connection.querySelector("b").textContent = "HID connected";
    });
    socket.addEventListener("close", () => {
      if (hidClosing) return;
      connection.className = "terminal-connection disconnected";
      connection.querySelector("b").textContent = "HID reconnecting";
      hidReconnectTimer = window.setTimeout(connectHid, 1500);
    });
  };
  const closeHid = () => {
    hidClosing = true;
    window.clearTimeout(hidReconnectTimer);
    socket?.close();
  };
  connectHid();
  let lastOperatorActivity = Date.now();
  const sendHid = (message, operatorActivity = true) => {
    if (operatorActivity) lastOperatorActivity = Date.now();
    if (message.type === "keyboard") keyboardReports += 1;
    if (message.type === "mouse") mouseReports += 1;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
  };
  const pressedKeys = new Set();
  let physicalModifiers = 0;
  let stickyModifiers = 0;
  const sendKeyboardReport = () => sendHid({
    type: "keyboard",
    modifiers: physicalModifiers | stickyModifiers,
    keys: [...pressedKeys].slice(0, 6),
  });
  const releaseAllKeys = () => {
    pressedKeys.clear();
    physicalModifiers = 0;
    stickyModifiers = 0;
    keyboard.querySelectorAll(".keyboard-key.modifier").forEach((key) => key.classList.remove("active"));
    element.querySelectorAll(".kvm-modifier").forEach((key) => key.classList.remove("active"));
    sendKeyboardReport();
  };
  image.addEventListener("keydown", (event) => {
    const modifier = hidModifierCodes[event.code];
    if (modifier) {
      event.preventDefault();
      physicalModifiers |= modifier;
      sendKeyboardReport();
      return;
    }
    const key = hidKeyCodes[event.code];
    if (!key) return;
    event.preventDefault();
    pressedKeys.add(key);
    sendKeyboardReport();
  });
  image.addEventListener("keyup", (event) => {
    const modifier = hidModifierCodes[event.code];
    if (modifier) {
      event.preventDefault();
      physicalModifiers &= ~modifier;
      sendKeyboardReport();
      return;
    }
    const key = hidKeyCodes[event.code];
    if (!key) return;
    event.preventDefault();
    pressedKeys.delete(key);
    sendKeyboardReport();
  });
  image.addEventListener("blur", releaseAllKeys);
  let buttons = 0;
  let relativeSyncing = false;
  const displayedVideoPoint = (event) => {
    const rect = image.getBoundingClientRect();
    if (!element.classList.contains("view-fit")) {
      return {
        x: Math.round(Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) * (image.naturalWidth || 1024)),
        y: Math.round(Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)) * (image.naturalHeight || 768)),
      };
    }
    const ratio = image.naturalWidth && image.naturalHeight ? image.naturalWidth / image.naturalHeight : 4 / 3;
    const width = Math.min(rect.width, rect.height * ratio);
    const height = width / ratio;
    const left = rect.left + (rect.width - width) / 2;
    const top = rect.top + (rect.height - height) / 2;
    return {
      x: Math.round(Math.max(0, Math.min(1, (event.clientX - left) / width)) * (image.naturalWidth || 1024)),
      y: Math.round(Math.max(0, Math.min(1, (event.clientY - top) / height)) * (image.naturalHeight || 768)),
    };
  };
  const syncRelativePointer = (event) => {
    const target = displayedVideoPoint(event);
    const clickedButtons = event.button === 0 ? 1 : event.button === 2 ? 2 : 4;
    const reports = Array.from({ length: 24 }, () => ({ x: -100, y: -100 }));
    let remainingX = target.x;
    let remainingY = target.y;
    while (remainingX || remainingY) {
      const x = Math.min(16, remainingX);
      const y = Math.min(16, remainingY);
      reports.push({ x, y });
      remainingX -= x;
      remainingY -= y;
    }
    relativeSyncing = true;
    status.textContent = "Syncing BIOS pointer…";
    reports.forEach((report, index) => {
      window.setTimeout(() => {
        sendHid({ type: "mouse", mode: "relative", buttons: 0, x: report.x, y: report.y, wheel: 0 });
      }, index * 7);
    });
    window.setTimeout(() => {
      sendHid({ type: "mouse", mode: "relative", buttons: clickedButtons, x: 0, y: 0, wheel: 0 });
      window.setTimeout(() => {
        sendHid({ type: "mouse", mode: "relative", buttons: 0, x: 0, y: 0, wheel: 0 });
        relativeSyncing = false;
        status.textContent = "Live stream · 12 FPS";
      }, 45);
    }, reports.length * 7 + 20);
  };
  const sensitivityLevels = [0.2, 0.35, 0.5, 0.75, 1];
  const savedSensitivity = Number(localStorage.getItem("kronoskvm.mouse-sensitivity-v2"));
  let mouseSensitivity = sensitivityLevels.includes(savedSensitivity) ? savedSensitivity : 0.2;
  const sensitivityButton = element.querySelector('[data-kvm-action="sensitivity"]');
  const renderSensitivity = () => { sensitivityButton.textContent = `Mouse: ${mouseSensitivity}×`; };
  renderSensitivity();
  sensitivityButton.addEventListener("click", () => {
    mouseSensitivity = sensitivityLevels[(sensitivityLevels.indexOf(mouseSensitivity) + 1) % sensitivityLevels.length];
    localStorage.setItem("kronoskvm.mouse-sensitivity-v2", String(mouseSensitivity));
    clearMouseMotion();
    renderSensitivity();
  });
  const mouseMotionAbort = new AbortController();
  let mouseTimer = null;
  let pendingMouseX = 0;
  let pendingMouseY = 0;
  const clearMouseMotion = () => {
    window.clearTimeout(mouseTimer);
    mouseTimer = null;
    pendingMouseX = pendingMouseY = 0;
  };
  const sendMouse = (event, wheel = 0) => {
    if (relativeSyncing) { clearMouseMotion(); return; }
    window.clearTimeout(mouseTimer);
    mouseTimer = null;
    pendingMouseX += (event.movementX || 0) * mouseSensitivity;
    pendingMouseY += (event.movementY || 0) * mouseSensitivity;
    const x = Math.round(Math.max(-127, Math.min(127, pendingMouseX)));
    const y = Math.round(Math.max(-127, Math.min(127, pendingMouseY)));
    pendingMouseX -= x;
    pendingMouseY -= y;
    sendHid({ type: "mouse", mode: "relative", buttons, x, y, wheel });
    if (Math.abs(pendingMouseX) >= 1 || Math.abs(pendingMouseY) >= 1) {
      mouseTimer = window.setTimeout(() => sendMouse({}), 16);
    }
  };
  image.addEventListener("mousemove", (event) => {
    if (relativeSyncing) return;
    pendingMouseX += (event.movementX || 0) * mouseSensitivity;
    pendingMouseY += (event.movementY || 0) * mouseSensitivity;
    if (mouseTimer === null) mouseTimer = window.setTimeout(() => sendMouse({}), 16);
  });
  image.addEventListener("blur", clearMouseMotion);
  document.addEventListener("pointerlockchange", () => {
    if (document.pointerLockElement !== image) clearMouseMotion();
  }, { signal: mouseMotionAbort.signal });
  image.addEventListener("mousedown", (event) => {
    event.preventDefault();
    image.focus();
    if (document.pointerLockElement !== image) {
      image.requestPointerLock();
      syncRelativePointer(event);
      return;
    }
    buttons |= event.button === 0 ? 1 : event.button === 2 ? 2 : 4;
    sendMouse(event);
  });
  image.addEventListener("mouseup", (event) => {
    if (relativeSyncing) return;
    buttons &= ~(event.button === 0 ? 1 : event.button === 2 ? 2 : 4);
    sendMouse(event);
  });
  image.addEventListener("contextmenu", (event) => event.preventDefault());
  image.addEventListener("wheel", (event) => {
    event.preventDefault();
    sendMouse(event, event.deltaY > 0 ? 1 : -1);
  }, { passive: false });
  element.querySelector('[data-kvm-action="keyboard"]').addEventListener("click", () => {
    keyboard.hidden = !keyboard.hidden;
    if (!keyboard.hidden) focusTerminal(keyboard);
  });
  keyboard.querySelector(".keyboard-hide").addEventListener("click", () => { keyboard.hidden = true; });
  keyboard.querySelector(".keyboard-release").addEventListener("click", releaseAllKeys);
  keyboard.querySelectorAll(".keyboard-key").forEach((keyButton) => {
    keyButton.addEventListener("click", () => {
      const code = keyButton.dataset.hidCode;
      if (code === "cad") {
        sendHid({ type: "keyboard", modifiers: 5, keys: [hidKeyCodes.Delete] });
        window.setTimeout(releaseAllKeys, 90);
        return;
      }
      const modifier = hidModifierCodes[code];
      if (modifier) {
        stickyModifiers ^= modifier;
        keyButton.classList.toggle("active", Boolean(stickyModifiers & modifier));
        sendKeyboardReport();
        return;
      }
      const usage = hidKeyCodes[code];
      if (!usage) return;
      pressedKeys.add(usage);
      sendKeyboardReport();
      window.setTimeout(() => {
        pressedKeys.delete(usage);
        sendKeyboardReport();
      }, 75);
    });
  });
  element.querySelectorAll(".kvm-modifier").forEach((button) => {
    button.addEventListener("click", () => {
      const modifier = Number(button.dataset.modifier);
      stickyModifiers ^= modifier;
      button.classList.toggle("active", Boolean(stickyModifiers & modifier));
      sendKeyboardReport();
    });
  });
  element.querySelector(".kvm-caps-lock").addEventListener("click", () => {
    if (socket?.readyState !== WebSocket.OPEN) {
      showToast("HID is disconnected; wait for reconnection");
      return;
    }
    releaseAllKeys();
    image.focus();
    // Send a complete tap; the target owns the Caps Lock state.
    sendHid({ type: "keyboard", modifiers: 0, keys: [hidKeyCodes.CapsLock] });
    sendKeyboardReport();
  });
  element.querySelector(".kvm-hotkey-cad").addEventListener("click", () => {
    sendHid({ type: "keyboard", modifiers: 5, keys: [hidKeyCodes.Delete] });
    window.setTimeout(releaseAllKeys, 90);
  });
  const keepAwakeButton = element.querySelector(".keep-awake-toggle");
  let keepAwake = localStorage.getItem("kronoskvm.keep-awake") !== "false";
  const renderKeepAwake = () => {
    keepAwakeButton.classList.toggle("active", keepAwake);
    keepAwakeButton.textContent = keepAwake ? "◉ Keep awake" : "○ Keep awake";
    keepAwakeButton.title = keepAwake
      ? "Prevents target sleep after two minutes of operator inactivity"
      : "Target sleep prevention is disabled";
  };
  keepAwakeButton.addEventListener("click", () => {
    keepAwake = !keepAwake;
    localStorage.setItem("kronoskvm.keep-awake", String(keepAwake));
    lastOperatorActivity = Date.now();
    renderKeepAwake();
  });
  renderKeepAwake();
  const keepAwakeTimer = window.setInterval(() => {
    if (!keepAwake || socket?.readyState !== WebSocket.OPEN || Date.now() - lastOperatorActivity < 120000) return;
    sendHid({ type: "keyboard", modifiers: 2, keys: [] }, false);
    window.setTimeout(() => sendHid({ type: "keyboard", modifiers: 0, keys: [] }, false), 80);
    lastOperatorActivity = Date.now();
  }, 30000);
  const toolbarButton = (action) => element.querySelector(`[data-kvm-action="${action}"]`);
  const mediaDrawer = element.querySelector(".virtual-media-drawer");
  const downloadBlob = (blob, name) => {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = name;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  };
  toolbarButton("snapshot").addEventListener("click", () => {
    if (!playing || !image.naturalWidth) return showToast("Video frame is not ready");
    try {
      const canvas = document.createElement("canvas");
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      canvas.getContext("2d").drawImage(image, 0, 0);
      canvas.toBlob((blob) => {
        if (!blob) return showToast("Snapshot could not be created");
        downloadBlob(blob, `kronoskvm-snapshot-${new Date().toISOString().replaceAll(":", "-")}.png`);
        showToast("Snapshot download started");
      }, "image/png");
    } catch (error) { showToast(`Snapshot failed: ${error.message}`); }
  });
  let recording = null;
  const stopRecording = (download = true) => {
    const current = recording;
    if (!current || current.stopping) return;
    current.stopping = true;
    current.download = download;
    window.clearInterval(current.timer);
    if (current.recorder.state !== "inactive") current.recorder.stop();
    current.stream.getTracks().forEach((track) => track.stop());
    toolbarButton("record").classList.remove("active");
    toolbarButton("record").textContent = "● Record";
  };
  toolbarButton("record").title = "Record to this computer; automatically saves after 15 minutes or 128 MiB";
  toolbarButton("record").addEventListener("click", () => {
    if (recording) { stopRecording(); return; }
    if (!playing || !image.naturalWidth || !window.MediaRecorder) return showToast("Browser recording is unavailable or video is paused");
    let stream;
    try {
      const canvas = document.createElement("canvas");
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext("2d");
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      stream = canvas.captureStream(12);
      const mimeType = ["video/mp4", "video/webm;codecs=vp8", "video/webm"].find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
      const current = { recorder, stream, chunks: [], bytes: 0, download: true, stopping: false, started: Date.now(), timer: null };
      recording = current;
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size) { current.chunks.push(event.data); current.bytes += event.data.size; }
        if (current.bytes >= 128 * 1024 * 1024 && !current.stopping) {
          showToast("Recording size limit reached; downloading recording");
          stopRecording();
        }
      });
      recorder.addEventListener("stop", () => {
        window.clearInterval(current.timer);
        current.stream.getTracks().forEach((track) => track.stop());
        if (recording === current) recording = null;
        toolbarButton("record").classList.remove("active");
        toolbarButton("record").textContent = "● Record";
        if (current.download && current.chunks.length) {
          const type = recorder.mimeType || current.chunks[0].type || "video/webm";
          const extension = type.includes("mp4") ? "mp4" : "webm";
          downloadBlob(new Blob(current.chunks, { type }), `kronoskvm-recording-${new Date().toISOString().replaceAll(":", "-")}.${extension}`);
          showToast("Recording download started");
        } else if (current.download) showToast("No video data was recorded");
        current.chunks.length = 0;
      });
      recorder.addEventListener("error", () => {
        showToast("Recording interrupted; saving available video");
        stopRecording();
      });
      recorder.start(1000);
      let framePending = false;
      current.timer = window.setInterval(async () => {
        if (Date.now() - current.started >= 15 * 60 * 1000) {
          showToast("15 minute recording limit reached; downloading recording");
          stopRecording();
          return;
        }
        if (framePending || current.stopping) return;
        framePending = true;
        try {
          const response = await fetch("/api/v1/video/latest.jpg", { cache: "no-store", signal: AbortSignal.timeout(3000) });
          if (!response.ok) throw new Error("No current video frame");
          const frame = await createImageBitmap(await response.blob());
          try {
            if (!current.stopping) context.drawImage(frame, 0, 0, canvas.width, canvas.height);
          } finally { frame.close(); }
        } catch (error) {
          if (!current.stopping) { showToast("Video unavailable; saving recording"); stopRecording(); }
        } finally { framePending = false; }
        if (current.stopping) return;
        const seconds = Math.floor((Date.now() - current.started) / 1000);
        toolbarButton("record").textContent = `■ Stop ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
      }, 84);
      toolbarButton("record").classList.add("active");
      showToast(`Recording started · ${recorder.mimeType.includes("mp4") ? "MP4" : "WebM (MP4 recording is not supported by this browser)"} · maximum 15 minutes / 128 MiB`);
    } catch (error) {
      stream?.getTracks().forEach((track) => track.stop());
      recording = null;
      showToast(`Recording failed: ${error.message}`);
    }
  });
  toolbarButton("play").addEventListener("click", () => {
    playing = !playing;
    if (playing) {
      startVideoStream("Reconnecting video…");
      toolbarButton("play").textContent = "Ⅱ Pause";
    } else {
      stopRecording();
      window.clearTimeout(streamRetryTimer);
      image.src = "";
      toolbarButton("play").textContent = "▷ Play";
      status.textContent = "Video paused";
    }
  });
  toolbarButton("fullscreen").addEventListener("click", async () => {
    if (document.fullscreenElement === element) await document.exitFullscreen();
    else await element.requestFullscreen();
  });
  const viewModes = ["fit", "stretch", "actual"];
  const viewLabels = { fit: "Fit", stretch: "Stretch", actual: "1:1" };
  let viewMode = localStorage.getItem("kronoskvm.video-view");
  if (compactLayout.matches || !viewModes.includes(viewMode)) viewMode = "fit";
  const renderViewMode = () => {
    viewModes.forEach((mode) => element.classList.toggle(`view-${mode}`, mode === viewMode));
    toolbarButton("view").textContent = `▣ View: ${viewLabels[viewMode]}`;
    toolbarButton("view").title = viewMode === "fit"
      ? "Fit the complete target image inside the console"
      : viewMode === "stretch" ? "Stretch the target image to fill the console" : "Show one target pixel per browser pixel";
  };
  toolbarButton("view").addEventListener("click", () => {
    viewMode = viewModes[(viewModes.indexOf(viewMode) + 1) % viewModes.length];
    localStorage.setItem("kronoskvm.video-view", viewMode);
    renderViewMode();
  });
  renderViewMode();
  let aspectLocked = false;
  let adjustingAspect = false;
  const applyAspectRatio = () => {
    if (compactLayout.matches || !aspectLocked || adjustingAspect || element.classList.contains("maximized")) return;
    adjustingAspect = true;
    const chromeHeight = element.querySelector(".terminal-titlebar").offsetHeight
      + element.querySelector(".kvm-toolbar").offsetHeight
      + element.querySelector(".media-activity").offsetHeight
      + element.querySelector(".terminal-footer").offsetHeight;
    const ratio = image.naturalWidth && image.naturalHeight ? image.naturalWidth / image.naturalHeight : 4 / 3;
    element.style.height = `${Math.round(element.offsetWidth / ratio + chromeHeight)}px`;
    window.requestAnimationFrame(() => { adjustingAspect = false; });
  };
  const aspectObserver = new ResizeObserver(applyAspectRatio);
  aspectObserver.observe(element);
  toolbarButton("aspect").addEventListener("click", () => {
    aspectLocked = !aspectLocked;
    toolbarButton("aspect").classList.toggle("active", aspectLocked);
    toolbarButton("aspect").textContent = aspectLocked ? "◆ Ratio locked" : "◇ Lock ratio";
    applyAspectRatio();
  });
  const renderVirtualMedia = async () => {
    const list = mediaDrawer.querySelector(".virtual-media-files");
    list.textContent = "Loading staged media…";
    try {
      await loadVirtualMediaStatus();
      stagingStorage = await getJson("/api/v1/storage");
      const files = stagingStorage.files.filter((file) => /\.(iso|img)$/i.test(file.name));
      list.innerHTML = files.length ? files.map((file) => {
        const mounted = virtualMediaStatus.status === "attached" && virtualMediaStatus.filename === file.name;
        return `<div class="virtual-media-item"><span><b>${escapeHtml(file.name)}</b><small>${formatBytes(file.size_bytes)}${mounted ? " · Mounted read-only" : ""}</small></span><button type="button" ${mounted ? "data-media-eject" : `data-media-name="${escapeHtml(file.name)}"`}>${mounted ? "Eject" : "Mount"}</button></div>`;
      }).join("") : "<p>No ISO or IMG files in staging storage.</p>";
      list.querySelectorAll("[data-media-name]").forEach((button) => button.addEventListener("click", async () => {
        button.disabled = true;
        try { await setVirtualMedia(button.dataset.mediaName); await renderVirtualMedia(); }
        catch (error) { showToast(`${button.dataset.mediaName}: ${error.message}`); button.disabled = false; }
      }));
      list.querySelectorAll("[data-media-eject]").forEach((button) => button.addEventListener("click", async () => {
        button.disabled = true;
        try { await setVirtualMedia(); await renderVirtualMedia(); }
        catch (error) { showToast(`Eject failed: ${error.message}`); button.disabled = false; }
      }));
    } catch (error) {
      list.textContent = "Staging storage is unavailable.";
    }
  };
  toolbarButton("media").addEventListener("click", () => {
    mediaDrawer.hidden = !mediaDrawer.hidden;
    if (!mediaDrawer.hidden) renderVirtualMedia();
  });
  mediaDrawer.querySelector(".media-close").addEventListener("click", () => { mediaDrawer.hidden = true; });
  const resolutionTimer = window.setInterval(async () => {
    if (!playing) return;
    try {
      const videoStatus = await getJson("/api/v1/video/status");
      if (!videoStatus.signal) {
        signalAvailable = false;
        suppressStreamError = true;
        image.src = "";
        status.textContent = "Waiting for video signal…";
        return;
      }
      if (!signalAvailable) {
        signalAvailable = true;
        currentWidth = videoStatus.width;
        currentHeight = videoStatus.height;
        element.querySelector(".video-resolution").textContent = `${currentWidth} × ${currentHeight}`;
        startVideoStream("Video signal restored · reconnecting…", 250);
        return;
      }
      const changed = currentWidth && currentHeight
        && (videoStatus.width !== currentWidth || videoStatus.height !== currentHeight);
      if (changed) {
        currentWidth = videoStatus.width;
        currentHeight = videoStatus.height;
        element.querySelector(".video-resolution").textContent = `${currentWidth} × ${currentHeight}`;
        startVideoStream(`Resolution changed to ${currentWidth} × ${currentHeight} · reconnecting…`, 250);
      }
    } catch (error) {
      console.debug("Video timing check failed", error);
    }
  }, 2000);
  videoWindow = {
    element, image, keepAwakeTimer, keyboard, releaseAllKeys, closeHid,
    clearMouseMotion, mouseMotionAbort,
    stopRecording, aspectObserver, resolutionTimer,
    startedAt: kvmStartedAt,
    get keyboardReports() { return keyboardReports; },
    get mouseReports() { return mouseReports; },
    get streamRetryTimer() { return streamRetryTimer; },
  };
  startVideoStream();
  focusTerminal(element);
  enableTerminalDrag(element);
  element.addEventListener("pointerdown", () => focusTerminal(element));
  element.querySelector(".terminal-close").addEventListener("click", closeVideoWindow);
  element.querySelector(".terminal-minimize").addEventListener("click", () => element.classList.toggle("minimized"));
  element.querySelector(".terminal-maximize").addEventListener("click", () => element.classList.toggle("maximized"));
}

function taskDisplayName(task) {
  const path = task.detail || "";
  if (path.includes("/storage/virtual-media")) return task.title.startsWith("DELETE") ? "Eject virtual media" : "Mount virtual media";
  if (path.includes("/storage/files/")) return task.title.startsWith("DELETE") ? "Delete staged file" : "Upload staged file";
  if (path.includes("/system/power")) return "Appliance power action";
  if (path.includes("/connections")) return "Update connection profile";
  if (path.includes("/session-logs")) return "Stage session log";
  if (path.includes("/serial/")) return "Serial console operation";
  return task.title;
}

function renderTasks(tasks) {
  const active = tasks.filter((task) => task.status === "running").length;
  const successful = tasks.filter((task) => task.status === "successful").length;
  const failed = tasks.filter((task) => ["failed", "cancelled"].includes(task.status)).length;
  document.querySelector("#tasks-summary").textContent = `${active} active · ${successful} successful · ${failed} failed/cancelled · ${tasks.length} total`;
  const body = document.querySelector("#tasks-entries");
  if (!tasks.length) {
    body.innerHTML = '<tr><td colspan="6" class="loading-cell">No task activity in this appliance session.</td></tr>';
    return;
  }
  body.innerHTML = tasks.map((task) => {
    const result = task.error || (task.status === "successful" ? "Completed" : task.status === "running" ? "In progress" : "—");
    return `<tr><td class="task-title-cell"><strong>${escapeHtml(taskDisplayName(task))}</strong><small title="${escapeHtml(task.id)}">${escapeHtml(task.detail || task.id)}</small></td><td>${escapeHtml(task.source)}</td><td><span class="task-status-pill ${escapeHtml(task.status)}">${escapeHtml(task.status)}</span></td><td><div class="task-table-progress"><i style="width:${Math.max(0, Math.min(100, Number(task.progress) || 0))}%"></i></div></td><td>${new Date(task.created_at).toLocaleString()}</td><td>${escapeHtml(result)}</td></tr>`;
  }).join("");
}

async function loadTasks() {
  try {
    const response = await getJson("/api/v1/tasks");
    renderTasks(response.tasks);
    for (const remote of response.tasks) {
      if (remote.status === "running" && remote.filename && remote.detail?.includes("/external-storage/") && !storageTasks.has(remote.id)) {
        storageTasks.set(remote.id, { id: remote.id, file: { name: remote.filename, size: remote.bytes_total }, status: "running", externalCopy: true, detached: true, phase: "Copying USB → Internal Stage", progress: remote.progress, loaded: remote.bytes_done || 0 });
      }
    }
    for (const [id, local] of storageTasks) {
      if (!local.externalCopy || local.status !== "running" || local.phase.includes("Mounting")) continue;
      const remote = response.tasks.find((task) => task.id === id);
      if (!remote) continue;
      local.loaded = remote.bytes_done || 0;
      local.progress = remote.progress;
      if (local.detached && ["successful", "failed", "cancelled"].includes(remote.status)) {
        local.status = remote.status === "successful" ? "completed" : remote.status;
        local.error = remote.error;
        local.finishedAt = remote.completed_at ? new Date(remote.completed_at) : new Date();
      }
      if (externalImportRunning) document.querySelector("#external-message").textContent = `${local.file.name}: ${local.progress}% · ${formatBytes(local.loaded)} / ${formatBytes(local.file.size)} copied`;
    }
    for (const [id, local] of storageTasks) {
      if (!local.serverManaged) continue;
      const remote = response.tasks.find((task) => task.id === id);
      if (!remote) { storageTasks.delete(id); continue; }
      local.status = remote.status === "successful" ? "completed" : remote.status;
      local.progress = remote.progress;
      local.error = remote.error;
      local.finishedAt = remote.completed_at ? new Date(remote.completed_at) : null;
      if (local.status === "completed" && !local.dismissScheduled) {
        local.dismissScheduled = true;
        window.setTimeout(() => { storageTasks.delete(id); renderStorageTasks(); }, 4000);
      }
    }
    renderStorageTasks();
    document.querySelector("#tasks-state").innerHTML = "<i></i> Monitoring";
  } catch (error) {
    document.querySelector("#tasks-state").textContent = "Unavailable";
    document.querySelector("#tasks-entries").innerHTML = '<tr><td colspan="6" class="loading-cell">Task service unavailable.</td></tr>';
  }
}

function bindNetworkSettingsForms() {
  document.querySelectorAll(".network-interface-form").forEach((form) => {
    const mode = form.querySelector('[name="mode"]');
    const staticFields = form.querySelector(".network-static-fields");
    const updateMode = () => {
      const isStatic = mode.value === "static";
      staticFields.classList.toggle("disabled-fields", !isStatic);
      staticFields.querySelectorAll("input").forEach((input) => { input.disabled = !isStatic; });
    };
    mode.addEventListener("change", updateMode);
    updateMode();
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const interfaceName = form.dataset.interface;
      const selectedMode = mode.value;
      const warning = selectedMode === "dhcp"
        ? `Apply DHCP to ${interfaceName}? Its current address may change.`
        : `Apply static IPv4 to ${interfaceName}? Your current Ethernet session may disconnect. The management AP at 192.168.34.100 will remain available.`;
      if (!window.confirm(warning)) return;
      const button = form.querySelector('button[type="submit"]');
      button.disabled = true;
      const payload = {
        interface: interfaceName,
        mode: selectedMode,
        address: form.querySelector('[name="address"]').value.trim() || null,
        gateway: form.querySelector('[name="gateway"]').value.trim() || null,
        dns: form.querySelector('[name="dns"]').value.split(",").map((item) => item.trim()).filter(Boolean),
        confirmed: true,
      };
      try {
        const response = await fetch("/api/v1/network/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
        showToast(`${interfaceName}: network configuration accepted`);
        window.setTimeout(loadNetworkSettings, 2500);
      } catch (error) {
        button.disabled = false;
        showToast(`${interfaceName}: ${error.message}`);
      }
    });
  });
}

async function loadNetworkSettings() {
  const container = document.querySelector("#network-settings");
  try {
    const response = await getJson("/api/v1/network/settings");
    if (!response.interfaces.length) {
      container.innerHTML = '<span class="muted">No configurable Ethernet interface detected.</span>';
      return;
    }
    container.innerHTML = response.interfaces.map((item) => `
      <form class="network-interface-form" data-interface="${escapeHtml(item.interface)}">
        <div class="network-interface-heading"><div><strong>${escapeHtml(item.interface)}</strong><small>${escapeHtml(item.mac_address || "No MAC")} · ${escapeHtml(item.state)} · ${escapeHtml(item.current_addresses.join(", ") || "No address")}</small></div><span class="task-status-pill ${item.apply_status === "failed" ? "failed" : "successful"}">${escapeHtml(item.apply_status)}</span></div>
        <div class="network-form-grid"><label>IPv4 mode<select name="mode"><option value="dhcp" ${item.mode === "dhcp" ? "selected" : ""}>DHCP</option><option value="static" ${item.mode === "static" ? "selected" : ""}>Static</option></select></label><div class="network-static-fields"><label>Address / prefix<input name="address" value="${escapeHtml(item.address || "")}" placeholder="192.168.1.50/24" inputmode="decimal"></label><label>Gateway<input name="gateway" value="${escapeHtml(item.gateway || "")}" placeholder="192.168.1.1" inputmode="decimal"></label><label>DNS servers<input name="dns" value="${escapeHtml(item.dns.join(", "))}" placeholder="1.1.1.1, 8.8.8.8"></label></div></div>
        <div class="network-form-footer"><small>${escapeHtml(item.message || "Changes are applied through NetworkManager")}</small><button type="submit">Apply</button></div>
      </form>`).join("");
    bindNetworkSettingsForms();
  } catch (error) {
    container.innerHTML = '<span class="muted">Network settings are unavailable.</span>';
  }
}

function renderServiceCards(payload, target = "#service-cards") {
  const container = document.querySelector(target);
  container.innerHTML = payload.services.map((service) => {
    const healthy = ["active", "activating"].includes(service.state);
    const unavailable = ["not_configured", "not_installed"].includes(service.state);
    return `<article class="service-card"><div><strong>${escapeHtml(service.name)}</strong><p>${escapeHtml(service.description)}</p><small>${escapeHtml(service.detail || "No runtime detail")}</small></div><div class="service-card-actions"><span class="task-status-pill ${healthy ? "successful" : unavailable ? "" : "failed"}">${escapeHtml(service.state)}</span><button type="button" data-service-log="${escapeHtml(service.id)}">View Logs</button>${["tftp", "recovery_http", "recovery_ftp"].includes(service.id) ? `<a class="recovery-browse-link" href="#recovery-browse=${service.id}" data-recovery-browse="${service.id}">Browse Files</a>` : ""}${service.controllable ? `<button type="button" data-recovery-service="${escapeHtml(service.id)}" data-action="${healthy ? "stop" : "start"}">${healthy ? "Stop" : "Start"}</button>` : ""}<button type="button" data-service-restart="${escapeHtml(service.id)}" data-service-name="${escapeHtml(service.name)}" ${service.restartable ? "" : "disabled"}>↻ Restart</button></div></article>`;
  }).join("");
  document.querySelector("#services-state").innerHTML = `<i></i> ${payload.updated_at ? `Updated ${escapeHtml(new Date(payload.updated_at).toLocaleTimeString())}` : "Status pending"}`;
  container.querySelectorAll("[data-recovery-service]").forEach((button) => button.addEventListener("click", async () => {
    button.disabled = true;
    try { await queueServiceAction(`/api/v1/services/${button.dataset.recoveryService}/${button.dataset.action}`); }
    catch (error) { showToast(error.message); button.disabled = false; }
  }));
  container.querySelectorAll("[data-recovery-browse]").forEach((link) => link.addEventListener("click", (event) => {
    event.preventDefault();
    history.replaceState(null, "", link.hash);
    openRecoveryBrowser(link.dataset.recoveryBrowse);
  }));
  container.querySelectorAll("[data-service-restart]").forEach((button) => button.addEventListener("click", () => restartManagedService(button)));
  container.querySelectorAll("[data-service-log]").forEach((button) => button.addEventListener("click", () => target === "#recovery-service-cards" ? openRecoveryLog(button.dataset.serviceLog) : loadServiceLogs(button.dataset.serviceLog)));
}

let selectedServiceLog = null;
async function loadServiceLogs(serviceId, background = false) {
  selectedServiceLog = serviceId;
  const viewer = document.querySelector("#service-log-viewer");
  const output = document.querySelector("#service-log-lines");
  viewer.hidden = false;
  if (!background) output.textContent = "Loading…";
  try {
    const payload = await getJson(`/api/v1/services/${encodeURIComponent(serviceId)}/logs`);
    document.querySelector("#service-log-title").textContent = `${payload.name} logs`;
    output.textContent = payload.lines.length ? payload.lines.join("\n") : "No journal entries captured yet. Refresh service status and try again.";
  } catch (error) {
    output.textContent = "Service logs are unavailable.";
  }
  if (!background) viewer.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function loadManagedServices() {
  try {
    renderServiceCards(await getJson("/api/v1/services"));
  } catch (error) {
    document.querySelector("#service-cards").innerHTML = '<span class="muted">Service status is unavailable.</span>';
  }
}

async function queueServiceAction(path, options = {}) {
  const response = await fetch(path, { method: "POST", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify(options) });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
  if (result.task) { storageTasks.set(result.task.id, { ...result.task, serverManaged: true }); renderStorageTasks(); }
  window.setTimeout(() => { loadManagedServices(); loadTasks(); if (!document.querySelector("#recovery-panel").hidden) loadRecoveryMonitoring(); }, 1200);
  return result;
}

async function restartManagedService(button) {
  const name = button.dataset.serviceName;
  if (!window.confirm(`Restart ${name}? Active sessions using this service may be interrupted.`)) return;
  button.disabled = true;
  try {
    await queueServiceAction(`/api/v1/services/${encodeURIComponent(button.dataset.serviceRestart)}/restart`, { confirmed: true });
    showToast(`${name}: restart queued`);
  } catch (error) {
    showToast(`${name}: ${error.message}`);
    button.disabled = false;
  }
}

async function load() {
  const health = document.querySelector("#health");
  loadPorts();
  loadStorage();
  loadConnections();
  loadVideoStatus();
  loadTasks();
  const results = await Promise.allSettled([
    getJson("/api/v1/health"),
    getJson("/api/v1/system/info"),
    getJson("/api/v1/system/network"),
    getJson("/api/v1/hid/status"),
  ]);
  const [healthResult, systemResult, networkResult, hidResult] = results;

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
    renderServices(hidResult.status === "fulfilled" ? hidResult.value : null);
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
document.querySelector("#open-video").addEventListener("click", openVideoWindow);
document.querySelectorAll("[data-theme-choice]").forEach((button) => {
  button.addEventListener("click", () => {
    localStorage.setItem(themeStorageKey, button.dataset.themeChoice);
    applyTheme(button.dataset.themeChoice);
  });
});
document.querySelector("#sidebar-toggle").addEventListener("click", () => {
  const sidebar = document.querySelector("#sidebar");
  sidebar.classList.toggle("compact");
  localStorage.setItem("kronoskvm.sidebar.compact", String(sidebar.classList.contains("compact")));
});
if (localStorage.getItem("kronoskvm.sidebar.compact") === "true") {
  document.querySelector("#sidebar").classList.add("compact");
}
document.querySelector("#mobile-menu").addEventListener("click", () => {
  document.querySelector("#sidebar").classList.toggle("mobile-open");
});
document.addEventListener("pointerdown", (event) => {
  if (compactLayout.matches && !event.target.closest("#sidebar, #mobile-menu")) {
    document.querySelector("#sidebar").classList.remove("mobile-open");
  }
});
function showView(view) {
  const sections = [...document.querySelectorAll("[data-view-section]")];
  let firstVisible = null;
  sections.forEach((section) => {
    const views = section.dataset.viewSection.split(/\s+/);
    section.hidden = !views.includes(view);
    if (!section.hidden && !firstVisible) firstVisible = section;
  });
  if (firstVisible) firstVisible.scrollIntoView({ behavior: "smooth", block: "start" });
  if (view === "storage") {
    setCollapsed(document.querySelector("#storage-panel"), false);
    loadStorage();
    loadExternalStorage();
  }
  if (view === "logs") {
    loadManagedServices();
    loadLogs();
    loadSessionLogs();
  }
  if (view === "recovery") { loadRecovery(); loadRecoveryMonitoring(); }
  if (view === "tasks") loadTasks();
  if (view === "services") loadManagedServices();
  if (view === "settings") {
    loadNetworkSettings();
    document.querySelector("#settings-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  }
}
document.querySelectorAll(".side-link[data-view]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".side-link[data-view]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    showView(button.dataset.view);
    document.querySelector("#sidebar").classList.remove("mobile-open");
  });
});
async function requestAppliancePower(action) {
  const reboot = action === "reboot";
  const warning = reboot
    ? "Restart the appliance now? Active KVM, console, upload and log sessions will be interrupted."
    : "Power off the appliance now? Active sessions will stop and GPIO power must be physically cycled to start it again.";
  if (!window.confirm(warning)) return;
  const button = document.querySelector(reboot ? "#appliance-reboot" : "#appliance-poweroff");
  button.disabled = true;
  try {
    const response = await fetch("/api/v1/system/power", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, confirmed: true }),
    });
    if (!response.ok) throw new Error(`Power request failed (${response.status})`);
    showToast(reboot ? "Appliance reboot accepted" : "Appliance power off accepted");
  } catch (error) {
    button.disabled = false;
    showToast(error.message || "Power control failed");
  }
}
document.querySelector("#appliance-reboot").addEventListener("click", () => requestAppliancePower("reboot"));
document.querySelector("#appliance-poweroff").addEventListener("click", () => requestAppliancePower("poweroff"));
document.querySelector("#logs-refresh").addEventListener("click", loadLogs);
document.querySelector("#session-logs-refresh").addEventListener("click", loadSessionLogs);
document.querySelector("#tasks-refresh").addEventListener("click", loadTasks);
document.querySelector("#network-settings-refresh").addEventListener("click", loadNetworkSettings);
document.querySelector("#services-refresh").addEventListener("click", async () => {
  try { await queueServiceAction("/api/v1/services/refresh"); showToast("Service status refresh queued"); }
  catch (error) { showToast(error.message); }
});
document.querySelector("#service-log-close").addEventListener("click", () => { document.querySelector("#service-log-viewer").hidden = true; });
document.querySelector("#tasks-clear").addEventListener("click", async () => {
  const response = await fetch("/api/v1/tasks/completed", { method: "DELETE" });
  if (!response.ok) return showToast("Unable to clear completed tasks");
  await loadTasks();
  showToast("Completed tasks cleared");
});
document.querySelector("#logs-level").addEventListener("change", loadLogs);
document.querySelector("#logs-search").addEventListener("input", () => {
  clearTimeout(window.kronosLogSearchTimer);
  window.kronosLogSearchTimer = setTimeout(loadLogs, 250);
});
document.querySelector("#logs-download").addEventListener("click", () => {
  const body = latestLogEntries.map((entry) => JSON.stringify(entry)).join("\n") + "\n";
  const url = URL.createObjectURL(new Blob([body], { type: "application/x-ndjson" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `kronoskvm-logs-${new Date().toISOString().replace(/[:.]/g, "-")}.jsonl`;
  anchor.click();
  URL.revokeObjectURL(url);
});
const storageInput = document.querySelector("#storage-file-input");
const storageDropzone = document.querySelector("#storage-dropzone");
document.querySelector("#task-center-toggle").addEventListener("click", () => {
  const center = document.querySelector("#task-center");
  center.classList.toggle("minimized");
  document.querySelector("#task-center-toggle").textContent = center.classList.contains("minimized") ? "+" : "−";
});
document.querySelector("#storage-choose").addEventListener("click", () => storageInput.click());
storageInput.addEventListener("change", () => uploadStorageFiles([...storageInput.files]));
storageDropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    storageInput.click();
  }
});
["dragenter", "dragover"].forEach((name) => storageDropzone.addEventListener(name, (event) => {
  event.preventDefault();
  storageDropzone.classList.add("dragging");
}));
["dragleave", "drop"].forEach((name) => storageDropzone.addEventListener(name, (event) => {
  event.preventDefault();
  storageDropzone.classList.remove("dragging");
}));
storageDropzone.addEventListener("drop", (event) => uploadStorageFiles([...event.dataTransfer.files]));
document.querySelector("#session-search").addEventListener("input", (event) => {
  filterPortRows(event.currentTarget.value);
  if (event.currentTarget.value.trim()) document.querySelector("#devices-panel").scrollIntoView({ behavior: "smooth", block: "start" });
});
document.querySelectorAll("[data-open-port]").forEach((button) => {
  button.addEventListener("click", () => openPortConsole(button.dataset.openPort));
});
const sessionActionSelectors = {
  config: ".config-action",
  status: ".menu-action",
  console: ".console-action",
  disconnect: ".disconnect-action",
  reset: ".reset-action",
};
document.querySelectorAll("[data-session-action]").forEach((button) => {
  button.addEventListener("click", () => {
    const card = button.closest("[data-session-port]");
    const target = document.querySelector(
      `${sessionActionSelectors[button.dataset.sessionAction]}[data-port-id="${card.dataset.sessionPort}"]`
    );
    button.closest("details").removeAttribute("open");
    if (!target || target.disabled) {
      showToast(`${card.dataset.sessionPort === "console_1" ? "Console 1" : "Console 2"}: adapter not detected`);
      return;
    }
    target.click();
  });
});
document.querySelector("#new-session").addEventListener("click", () => {
  showConnectionTypes();
  document.querySelector("#session-dialog").showModal();
});
document.querySelectorAll("[data-close-dialog]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelector(`#${button.dataset.closeDialog}`).close();
    showConnectionTypes();
  });
});
document.querySelectorAll(".session-types [data-session-port]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelector("#session-dialog").close();
    openPortConsole(button.dataset.sessionPort);
  });
});
document.querySelectorAll("[data-connection-type]").forEach((button) => {
  button.addEventListener("click", () => openConnectionForm(button.dataset.connectionType));
});
document.querySelector("#connection-back").addEventListener("click", showConnectionTypes);
document.querySelector("#connection-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = document.querySelector("#connection-id").value;
  const payload = {
    type: document.querySelector("#connection-type").value,
    name: document.querySelector("#connection-name").value,
    host: document.querySelector("#connection-host").value,
    port: Number(document.querySelector("#connection-port").value),
    username: document.querySelector("#connection-username").value || null,
    path: document.querySelector("#connection-path").value || "/",
  };
  const response = await fetch(id ? `/api/v1/connections/${encodeURIComponent(id)}` : "/api/v1/connections", {
    method: id ? "PUT" : "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    showToast("Connection could not be saved");
    return;
  }
  document.querySelector("#session-dialog").close();
  showConnectionTypes();
  showToast(`${payload.name}: saved`);
  loadConnections();
});
document.querySelector("#config-form").addEventListener("submit", (event) => {
  if (event.submitter?.value === "cancel") return;
  event.preventDefault();
  const form = event.currentTarget;
  const profile = {
    display_name: document.querySelector("#config-display-name").value.trim(),
    baud_rate: document.querySelector("#config-baud").value === "auto"
      ? "auto" : Number(document.querySelector("#config-baud").value),
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
  if (!event.target.closest("#connection-action-popover, .connection-menu-trigger")) closeConnectionMenu();
  document.querySelectorAll(".action-menu[open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.removeAttribute("open");
  });
});
Promise.allSettled([load(), startupMinimum]).then(dismissStartupSplash);
window.setInterval(loadTasks, 3000);
window.setInterval(() => {
  if (!document.hidden) loadVirtualMediaStatus();
}, 3000);

document.querySelector("#external-refresh").addEventListener("click", loadExternalStorage);
document.querySelector("#external-volume").addEventListener("change", (event) => {
  externalDevice = event.target.value;
  externalPath = "";
  loadExternalStorage();
});
document.querySelector("#external-up").addEventListener("click", () => {
  externalPath = externalPath.split("/").slice(0, -1).join("/");
  loadExternalStorage();
});
window.setInterval(() => {
  if (!document.querySelector("#external-storage-panel").hidden && !externalImportRunning) loadExternalStorage();
}, 5000);


async function loadRecovery() {
  try {
    const [recovery, stage] = await Promise.all([getJson("/api/v1/recovery"), getJson("/api/v1/storage")]);
    updateRecoverySources(stage.files);
    renderStorage(stage);
    document.querySelector("#recovery-files").innerHTML = recovery.files.map((file) => `<tr><td>${escapeHtml(file.path)}</td><td>${formatBytes(file.size_bytes)}</td><td><code>${escapeHtml(file.http_url)}</code></td><td><div class="file-actions"><button data-copy-recovery="${escapeHtml(file.http_url)}">Copy URL</button><button data-copy-recovery="${escapeHtml(file.tftp_path)}">Copy TFTP/FTP path</button><button data-copy-recovery="${escapeHtml(file.ftp_url)}">Copy FTP URL</button><button data-recovery-hash="${escapeHtml(file.path)}">SHA256</button><button data-recovery-restore="${escapeHtml(file.path)}">Unpublish</button></div></td></tr>`).join("") || '<tr><td colspan="4">No published files. Upload in Storage or copy from USB there, then publish the staged file.</td></tr>';
  } catch (error) { document.querySelector("#recovery-message").textContent = error.message; }
}

document.querySelector("#recovery-refresh").addEventListener("click", () => { loadRecovery(); loadRecoveryMonitoring(); });
document.querySelector("#recovery-publish").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (recoveryPublishRunning) return;
  const filenames = [...document.querySelectorAll("#recovery-source input:checked")].map((input) => input.value);
  if (!filenames.length) return;
  const folder = document.querySelector("#recovery-folder").value.trim();
  const message = document.querySelector("#recovery-message");
  const results = document.querySelector("#recovery-publish-results");
  results.replaceChildren();
  recoveryPublishRunning = true;
  updateRecoverySelection();
  let successful = 0;
  try {
    for (const [index, filename] of filenames.entries()) {
      message.textContent = `Publishing ${index + 1}/${filenames.length}: ${filename}`;
      const item = document.createElement("li");
      try {
        const response = await fetch("/api/v1/recovery/files", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename, folder }) });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || "Publish failed");
        successful += 1;
        item.textContent = `Published: ${result.path}`;
      } catch (error) {
        item.textContent = `${filename}: ${error.message}`;
        item.classList.add("publish-failed");
      }
      results.append(item);
    }
    message.textContent = `${successful}/${filenames.length} files published for FTP / TFTP / HTTP${successful < filenames.length ? "; see individual results above." : "."}`;
    await loadRecovery();
  } finally {
    recoveryPublishRunning = false;
    updateRecoverySelection();
  }
});
document.querySelector("#recovery-files").addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  button.disabled = true;
  const message = document.querySelector("#recovery-message");
  try {
    if (button.dataset.copyRecovery) {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(button.dataset.copyRecovery);
      message.textContent = button.dataset.copyRecovery;
    } else if (button.dataset.recoveryHash) {
      message.textContent = "Calculating SHA256…";
      const result = await getJson(`/api/v1/recovery/checksum/${button.dataset.recoveryHash.split("/").map(encodeURIComponent).join("/")}`);
      message.textContent = `${result.path} · SHA256: ${result.sha256}`;
    } else if (button.dataset.recoveryRestore) {
      const response = await fetch(`/api/v1/recovery/restore/${button.dataset.recoveryRestore.split("/").map(encodeURIComponent).join("/")}`, { method: "POST" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Move failed");
      message.textContent = `${result.name}: moved to Stage`;
      await loadRecovery();
    }
  } catch (error) { message.textContent = error.message; }
  finally { button.disabled = false; }
});
let serviceRefreshRunning = false;
window.setInterval(async () => {
  if (document.hidden || document.querySelector("#services-panel").hidden || serviceRefreshRunning) return;
  serviceRefreshRunning = true;
  try {
    await loadManagedServices();
    if (selectedServiceLog && !document.querySelector("#service-log-viewer").hidden) await loadServiceLogs(selectedServiceLog, true);
  } finally { serviceRefreshRunning = false; }
}, 5000);


function updateRecoverySources(files) {
  const list = document.querySelector("#recovery-source");
  const selected = new Set([...list.querySelectorAll("input:checked")].map((input) => input.value));
  list.innerHTML = files.map((file) => `<label><input type="checkbox" value="${escapeHtml(file.name)}" ${selected.has(file.name) ? "checked" : ""}><span>${escapeHtml(file.name)}</span><small>${formatBytes(file.size_bytes)}</small></label>`).join("") || '<p>No staged files. Upload in Storage or copy from USB there.</p>';
  updateRecoverySelection();
}
function updateRecoverySelection() {
  const inputs = [...document.querySelectorAll("#recovery-source input")];
  const count = inputs.filter((input) => input.checked).length;
  document.querySelector("#recovery-selected-count").textContent = `${count} selected`;
  inputs.forEach((input) => { input.disabled = recoveryPublishRunning; });
  document.querySelector("#recovery-folder").disabled = recoveryPublishRunning;
  document.querySelector("#recovery-select-all").disabled = recoveryPublishRunning || !inputs.length;
  document.querySelector("#recovery-select-none").disabled = recoveryPublishRunning || !count;
  const button = document.querySelector("#recovery-publish button[type=submit]");
  button.disabled = recoveryPublishRunning || !count;
  button.textContent = recoveryPublishRunning ? "Publishing…" : `Publish selected${count ? ` (${count})` : ""}`;
}
document.querySelector("#recovery-source").addEventListener("change", updateRecoverySelection);
for (const [id, checked] of [["recovery-select-all", true], ["recovery-select-none", false]]) {
  document.getElementById(id).addEventListener("click", () => {
    document.querySelectorAll("#recovery-source input").forEach((input) => { input.checked = checked; });
    updateRecoverySelection();
  });
}

async function loadRecoveryLog() {
  const select = document.querySelector("#recovery-log-service");
  const selected = select.value;
  const output = document.querySelector("#recovery-log-lines");
  try {
    const payload = await getJson(`/api/v1/services/${selected}/logs`);
    if (select.value === selected) output.textContent = payload.lines.join("\n") || "No transfer entries yet.";
  } catch (error) { output.textContent = "Logs unavailable: " + error.message; }
}
function openRecoveryLog(service) {
  document.querySelector("#recovery-log-service").value = service;
  loadRecoveryLog();
  document.querySelector("#recovery-log-panel").scrollIntoView({ behavior: "smooth", block: "start" });
}
let recoveryMonitoring = false;
async function loadRecoveryMonitoring() {
  if (recoveryMonitoring) return;
  recoveryMonitoring = true;
  try {
    const results = await Promise.allSettled([getJson("/api/v1/services"), getJson("/api/v1/recovery/network"), loadRecoveryLog()]);
    if (results[0].status === "fulfilled") {
      const payload = results[0].value;
      renderServiceCards({ ...payload, services: payload.services.filter((service) => ["tftp", "recovery_http", "recovery_ftp"].includes(service.id)) }, "#recovery-service-cards");
    } else document.querySelector("#recovery-service-cards").textContent = "Service status unavailable";
    if (results[1].status === "fulfilled") {
      const network = results[1].value;
      document.querySelector("#recovery-network").innerHTML = `<strong>${network.stale ? "Network snapshot unavailable or out of date" : network.ports.some((port) => port.connected) ? "Service Ethernet: link connected" : "Service Ethernet: no cable detected"}</strong><p>DHCP leases · Shared service-port / recovery Wi-Fi network. A lease does not confirm that a device is currently online.</p><div class="storage-table-wrap"><table class="storage-table"><thead><tr><th>Device</th><th>IP address</th><th>MAC</th><th>Lease expires</th></tr></thead><tbody>${network.leases.map((lease) => `<tr><td>${escapeHtml(lease.hostname)}</td><td>${escapeHtml(lease.ip)}</td><td>${escapeHtml(lease.mac)}</td><td>${lease.expires_at ? escapeHtml(new Date(lease.expires_at * 1000).toLocaleString()) : "Permanent"}</td></tr>`).join("") || '<tr><td colspan="4">No current DHCP leases</td></tr>'}</tbody></table></div>`;
    } else document.querySelector("#recovery-network").textContent = "Network information unavailable";
  } finally { recoveryMonitoring = false; }
}
document.querySelector("#recovery-log-service").addEventListener("change", loadRecoveryLog);
document.querySelectorAll("[data-recovery-jump]").forEach((button) => button.addEventListener("click", () => {
  const target = document.getElementById(button.dataset.recoveryJump);
  if (["storage-panel", "external-storage-panel"].includes(target.id)) {
    document.querySelector('.side-link[data-view="storage"]').click();
  }
  if (target.classList.contains("collapsible")) setCollapsed(target, false);
  target.scrollIntoView({ behavior: "smooth", block: "start" });
}));
window.setInterval(() => {
  if (!document.hidden && !document.querySelector("#recovery-panel").hidden) loadRecoveryMonitoring();
}, 5000);


let recoveryBrowserFiles = [];
let recoveryBrowserFolder = "";
let recoveryBrowserService = "tftp";
let recoveryBrowserRequest = 0;
async function openRecoveryBrowser(service) {
  if (!["tftp", "recovery_http", "recovery_ftp"].includes(service)) return;
  recoveryBrowserService = service;
  recoveryBrowserFolder = "";
  const dialog = document.querySelector("#recovery-browser");
  if (!dialog.open) dialog.showModal();
  await refreshRecoveryBrowser();
}
async function refreshRecoveryBrowser() {
  const request = ++recoveryBrowserRequest;
  const body = document.querySelector("#recovery-browser-files");
  body.innerHTML = '<tr><td colspan="3">Loading published files…</td></tr>';
  try {
    const payload = await getJson("/api/v1/recovery");
    if (request !== recoveryBrowserRequest) return;
    recoveryBrowserFiles = payload.files;
    renderRecoveryBrowser();
  } catch (error) {
    if (request === recoveryBrowserRequest) body.innerHTML = `<tr><td colspan="3">${escapeHtml(error.message)}</td></tr>`;
  }
}
function renderRecoveryBrowser() {
  const protocol = {tftp: "TFTP", recovery_http: "HTTP", recovery_ftp: "FTP"}[recoveryBrowserService];
  document.querySelector("#recovery-browser-title").textContent = `${protocol} · Published files`;
  document.querySelector("#recovery-browser-path").textContent = "/" + recoveryBrowserFolder;
  document.querySelector("#recovery-browser-up").disabled = !recoveryBrowserFolder;
  document.querySelector("#recovery-browser-message").textContent = "All three services share this folder. Browsing does not start a service; start it before transferring files.";
  const prefix = recoveryBrowserFolder ? recoveryBrowserFolder + "/" : "";
  const folders = new Set();
  const files = [];
  for (const file of recoveryBrowserFiles) {
    if (!file.path.startsWith(prefix)) continue;
    const relative = file.path.slice(prefix.length);
    if (relative.includes("/")) folders.add(relative.split("/")[0]);
    else files.push({...file, name: relative});
  }
  const rows = [...folders].sort().map((folder) => `<tr><td><button type="button" data-browse-folder="${escapeHtml(prefix + folder)}">▸ ${escapeHtml(folder)}</button></td><td>Folder</td><td></td></tr>`);
  for (const file of files) {
    const address = recoveryBrowserService === "recovery_http" ? file.http_url : recoveryBrowserService === "recovery_ftp" ? file.ftp_url : file.tftp_path;
    rows.push(`<tr><td>${escapeHtml(file.name)}<small class="recovery-browser-address">${escapeHtml(address)}</small></td><td>${formatBytes(file.size_bytes)}</td><td><button type="button" data-browse-copy="${escapeHtml(address)}">Copy ${protocol === "TFTP" ? "path" : "URL"}</button>${protocol === "HTTP" ? `<a href="${escapeHtml(file.http_url)}" target="_blank" rel="noopener noreferrer">Open HTTP</a>` : ""}</td></tr>`);
  }
  document.querySelector("#recovery-browser-files").innerHTML = rows.join("") || '<tr><td colspan="3">No published files in this folder. Publish files from Recovery first.</td></tr>';
}
document.querySelector("#recovery-browser-close").addEventListener("click", () => document.querySelector("#recovery-browser").close());
document.querySelector("#recovery-browser").addEventListener("close", () => {
  if (document.querySelector("#recovery-browser").open) return;
  recoveryBrowserRequest += 1;
  if (location.hash === `#recovery-browse=${recoveryBrowserService}`) history.replaceState(null, "", location.pathname + location.search);
});
document.querySelector("#recovery-browser-refresh").addEventListener("click", refreshRecoveryBrowser);
document.querySelector("#recovery-browser-up").addEventListener("click", () => {
  recoveryBrowserFolder = recoveryBrowserFolder.split("/").slice(0, -1).join("/");
  renderRecoveryBrowser();
});
document.querySelector("#recovery-browser-files").addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  if (button.dataset.browseFolder !== undefined) {
    recoveryBrowserFolder = button.dataset.browseFolder;
    renderRecoveryBrowser();
  } else if (button.dataset.browseCopy) {
    const address = button.dataset.browseCopy;
    let copied = false;
    try { if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(address); copied = true; } } catch (_) { /* Address remains selectable below. */ }
    document.querySelector("#recovery-browser-message").textContent = (copied ? "Copied: " : "Select and copy: ") + address;
  }
});
window.addEventListener("hashchange", () => {
  if (location.hash.startsWith("#recovery-browse=")) openRecoveryBrowser(location.hash.split("=")[1]);
});
if (location.hash.startsWith("#recovery-browse=")) openRecoveryBrowser(location.hash.split("=")[1]);

// Available even when the mounted file was deleted or a normal eject failed.
document.addEventListener("click", async (event) => {
  const button = event.target.closest(".force-media-eject");
  if (!button || !window.confirm("Force eject virtual media? This disconnects the image even if the target has locked it and may interrupt an active OS installation. Stop the target installation first.")) return;
  button.disabled = true;
  try { await setVirtualMedia(null, true); }
  catch (error) { showToast(`Force eject failed: ${error.message}`); }
  finally { button.disabled = false; }
});

let checksumBusy = false;
const checksumDialog = document.querySelector("#storage-checksum-dialog");
const checksumValue = document.querySelector("#storage-checksum-value");
const checksumExpected = document.querySelector("#storage-checksum-expected");
function compareChecksum() {
  const expected = checksumExpected.value.trim().toLowerCase();
  const result = document.querySelector("#storage-checksum-match");
  result.textContent = !expected ? "Paste the publisher's SHA256 to verify this file."
    : !/^[a-f0-9]{64}$/.test(expected) ? "Enter a valid 64-character SHA256."
    : !checksumValue.value ? "Waiting for checksum…"
    : expected === checksumValue.value ? "✓ Match — SHA256 values are identical."
    : "Mismatch — the file differs from this reference checksum.";
}
checksumExpected.addEventListener("input", compareChecksum);
document.querySelector("#storage-checksum-close").addEventListener("click", () => checksumDialog.close());
document.querySelector("#storage-checksum-copy").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(checksumValue.value); showToast("SHA256 copied"); }
  catch { checksumValue.focus(); checksumValue.select(); showToast("Select and copy the SHA256 manually"); }
});
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-storage-checksum]");
  if (!button) return;
  if (checksumBusy) { checksumDialog.showModal(); return; }
  checksumBusy = true;
  const filename = button.dataset.storageChecksum;
  document.querySelector("#storage-checksum-name").textContent = filename;
  const status = document.querySelector("#storage-checksum-status");
  const copy = document.querySelector("#storage-checksum-copy");
  checksumValue.value = ""; checksumExpected.value = ""; copy.disabled = true;
  status.textContent = "Calculating SHA256… Large images may take several minutes. Progress is shown in Tasks. Closing this window does not cancel calculation.";
  compareChecksum(); checksumDialog.showModal();
  try {
    const response = await fetch(`/api/v1/storage/checksum/${encodeURIComponent(filename)}`, { method: "POST" });
    const value = await response.json();
    if (!response.ok) throw new Error(value.detail || `HTTP ${response.status}`);
    checksumValue.value = value.sha256; copy.disabled = false;
    status.textContent = `SHA256 calculated · ${formatBytes(value.size_bytes)}. Compare with a trusted reference to verify integrity.`;
    compareChecksum();
  } catch (error) { status.textContent = `Checksum failed: ${error.message}`; }
  finally { checksumBusy = false; loadTasks(); }
});
