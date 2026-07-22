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
  document.querySelector("#network").innerHTML = network.interfaces
    .filter((item) => item.name !== "lo")
    .map((item) =>
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
    const displayStatus = isConsole && connected ? "adapter connected" : port.status.replaceAll("_", " ");
    return `<tr>
      <td data-label="Port"><div class="port-name"><span class="port-icon">${portIcons[port.id] || "IO"}</span><strong>${escapeHtml(port.name)}</strong></div></td>
      <td data-label="Interface"><span class="interface-label">${escapeHtml(port.physical_label)}</span>${port.usb_path ? `<code>${escapeHtml(port.usb_path)}</code>` : ""}</td>
      <td data-label="Connected device" class="device-cell">${escapeHtml(detail || "No device detected")}</td>
      <td data-label="State"><span class="port-state ${statusClass}">${escapeHtml(displayStatus)}</span></td>
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

function renderStorage(storage) {
  const mediaReady = storage.status === "ready";
  const percent = storage.total_bytes ? Math.round((storage.used_bytes / storage.total_bytes) * 100) : 0;
  document.querySelector("#storage-state").textContent = mediaReady ? "✓ Ready" : "Media missing";
  document.querySelector("#storage-choose").disabled = !mediaReady;
  document.querySelector("#storage-dropzone").classList.toggle("storage-disabled", !mediaReady);
  if (!mediaReady) {
    document.querySelector("#storage-capacity").textContent = "No removable media";
    document.querySelector("#storage-free").textContent = "Connect an initialized USB microSD reader";
    document.querySelector("#storage-capacity-bar").style.width = "0%";
    document.querySelector("#storage-file-count").textContent = "0";
    document.querySelector("#storage-files").innerHTML = '<tr><td colspan="5" class="loading-cell">Removable staging media is not connected.</td></tr>';
    return;
  }
  document.querySelector("#storage-capacity").textContent = `${formatBytes(storage.used_bytes)} / ${formatBytes(storage.total_bytes)}`;
  document.querySelector("#storage-free").textContent = `${formatBytes(storage.free_bytes)} free · 1 GB system reserve protected`;
  document.querySelector("#storage-capacity-bar").style.width = `${percent}%`;
  document.querySelector("#storage-file-count").textContent = storage.file_count;
  const body = document.querySelector("#storage-files");
  if (!storage.files.length) {
    body.innerHTML = '<tr><td colspan="5" class="loading-cell">No staged files. Upload an ISO or firmware package to begin.</td></tr>';
    return;
  }
  body.innerHTML = storage.files.map((file) => {
    const extension = file.name.includes(".") ? file.name.split(".").pop().slice(0, 4).toUpperCase() : "FILE";
    return `<tr><td><div class="file-name"><i>${escapeHtml(extension)}</i><span title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span></div></td><td>${escapeHtml(file.media_type)}</td><td>${formatBytes(file.size_bytes)}</td><td>${new Date(file.modified_at).toLocaleString()}</td><td><div class="file-actions"><a href="/api/v1/storage/files/${encodeURIComponent(file.name)}" download>↓ Download</a><button class="delete-file" type="button" data-filename="${escapeHtml(file.name)}">Delete</button></div></td></tr>`;
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
}

async function loadStorage() {
  try {
    renderStorage(await getJson("/api/v1/storage"));
  } catch (error) {
    document.querySelector("#storage-state").textContent = "Unavailable";
    document.querySelector("#storage-files").innerHTML = '<tr><td colspan="5" class="loading-cell">Staging storage unavailable.</td></tr>';
    console.error("Storage request failed", error);
  }
}

function uploadStorageFile(file) {
  return new Promise((resolve, reject) => {
    const status = document.querySelector("#upload-status");
    const progress = document.querySelector("#upload-progress");
    const percent = document.querySelector("#upload-percent");
    status.hidden = false;
    document.querySelector("#upload-name").textContent = `Uploading ${file.name}`;
    progress.style.width = "0%";
    percent.textContent = "0%";
    const request = new XMLHttpRequest();
    request.open("PUT", `/api/v1/storage/files/${encodeURIComponent(file.name)}`);
    request.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    request.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) return;
      const value = Math.round((event.loaded / event.total) * 100);
      progress.style.width = `${value}%`;
      percent.textContent = `${value}%`;
    });
    request.addEventListener("load", () => request.status >= 200 && request.status < 300
      ? resolve() : reject(new Error(`HTTP ${request.status}`)));
    request.addEventListener("error", () => reject(new Error("Network error")));
    request.send(file);
  });
}

async function uploadStorageFiles(files) {
  for (const file of files) {
    try {
      await uploadStorageFile(file);
      showToast(`${file.name}: upload complete`);
    } catch (error) {
      showToast(`${file.name}: upload failed`);
      console.error("Storage upload failed", error);
      break;
    }
  }
  document.querySelector("#upload-status").hidden = true;
  document.querySelector("#storage-file-input").value = "";
  await loadStorage();
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
      <div class="terminal-heading"><div><strong>${escapeHtml(label)}</strong><span>${escapeHtml(button.dataset.portName)} · ${profile.baud_rate} · ${profile.data_bits}${profile.parity[0].toUpperCase()}${profile.stop_bits}</span></div></div>
      <div class="terminal-controls"><button class="terminal-minimize" title="Minimize">−</button><button class="terminal-maximize" title="Maximize">□</button><button class="terminal-close" title="Close">×</button></div>
    </header>
    <pre class="terminal" tabindex="0" aria-label="${escapeHtml(label)} interactive serial terminal">Connecting…\n</pre>
    <footer class="terminal-footer"><div class="terminal-log-controls"><button class="log-start" type="button">● Start log</button><button class="log-stop" type="button" disabled>■ Stop log</button><button class="log-download" type="button" disabled>↓ Download TXT</button></div><span class="terminal-connection connecting"><i></i><b>Connecting</b></span></footer>`;
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
  session.element.querySelector(".log-download").disabled = session.logging || session.logParts.length === 0;
}

function terminalLogProfile(session) {
  if (session.profile.type === "ssh") {
    return `Profile: SSH ${session.profile.username || "user"}@${session.profile.host}:${session.profile.port}`;
  }
  const profile = session.profile;
  return `Profile: ${profile.baud_rate} baud, ${profile.data_bits}${profile.parity[0].toUpperCase()}${profile.stop_bits}, flow=${profile.flow_control}`;
}

function startTerminalLog(session) {
  const started = new Date();
  session.logging = true;
  session.logStartedAt = started;
  session.logParts = [
    `KronosKVM terminal session log\n`,
    `Terminal: ${session.label}\n`,
    `Started: ${started.toISOString()}\n`,
    `${terminalLogProfile(session)}\n`,
    `${"-".repeat(72)}\n`,
  ];
  setLogButtons(session);
  showToast(`${session.label}: logging started`);
}

function stopTerminalLog(session) {
  if (!session.logging) return;
  session.logParts.push(`\n${"-".repeat(72)}\nStopped: ${new Date().toISOString()}\n`);
  session.logging = false;
  setLogButtons(session);
  showToast(`${session.label}: log ready to download`);
}

function downloadTerminalLog(session) {
  if (!session.logParts.length || session.logging) return;
  const safeName = session.label.replace(/[^a-z0-9_-]+/gi, "-").replace(/^-|-$/g, "") || "console";
  const timestamp = (session.logStartedAt || new Date()).toISOString().replace(/[:.]/g, "-");
  const url = URL.createObjectURL(new Blob(session.logParts, { type: "text/plain;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `${safeName}-${timestamp}.txt`;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
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

async function load() {
  const health = document.querySelector("#health");
  loadPorts();
  loadStorage();
  loadConnections();
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
document.querySelectorAll(".side-link[data-view]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".side-link[data-view]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    const target = button.dataset.view === "storage"
      ? document.querySelector("#storage-panel")
      : button.dataset.view === "devices"
      ? document.querySelector("#devices-panel")
      : button.dataset.view === "dashboard" ? document.querySelector("#status-panel") : document.querySelector(".session-strip");
    if (target.matches("[data-collapse-id]")) {
      setCollapsed(target, false);
      localStorage.setItem(`kronoskvm.panel.${target.dataset.collapseId}.collapsed`, "false");
    }
    target.scrollIntoView({ behavior: "smooth", block: "start" });
    document.querySelector("#sidebar").classList.remove("mobile-open");
  });
});
const storageInput = document.querySelector("#storage-file-input");
const storageDropzone = document.querySelector("#storage-dropzone");
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
load();
