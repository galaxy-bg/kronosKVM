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
      ? `${status.width}×${status.height} · X630 ready`
      : status.ready ? "X630 · waiting for HDMI signal" : "X630 · capture unavailable";
  } catch (error) {
    button.disabled = true;
    card.classList.add("pending-session");
    label.textContent = "X630 · status unavailable";
    console.error(error);
  }
}

function closeVideoWindow() {
  if (!videoWindow) return;
  videoWindow.stopRecording?.(false);
  videoWindow.aspectObserver?.disconnect();
  videoWindow.image.src = "";
  window.clearInterval(videoWindow.keepAwakeTimer);
  videoWindow.releaseAllKeys?.();
  videoWindow.closeHid?.();
  videoWindow.keyboard?.remove();
  videoWindow.element.remove();
  videoWindow = null;
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
      <div class="terminal-heading"><div><strong>KronosKVM Remote Console</strong><span>VGA KVM · X630 HDMI capture</span></div></div>
      <div class="terminal-controls"><button class="terminal-minimize" title="Minimize">−</button><button class="terminal-maximize" title="Maximize">□</button><button class="terminal-close" title="Close">×</button></div>
    </header>
    <div class="kvm-toolbar">
      <button type="button" data-kvm-action="snapshot">▣ Snapshot</button>
      <button type="button" data-kvm-action="record">● Record</button>
      <button type="button" data-kvm-action="play">Ⅱ Pause</button>
      <button type="button" data-kvm-action="fullscreen">⛶ Full screen</button>
      <button type="button" data-kvm-action="aspect">◇ Lock ratio</button>
      <button type="button" data-kvm-action="media">▤ Virtual media</button>
    </div>
    <div class="video-stage"><img class="video-frame" tabindex="0" draggable="false" alt="KronosKVM target video"></div>
    <aside class="virtual-media-drawer" hidden><div><strong>Virtual media</strong><button type="button" class="media-close">×</button></div><p>ISO and IMG files from staging storage</p><div class="virtual-media-files">Loading staged media…</div></aside>
    <div class="video-keyboard" hidden><div class="keyboard-heading terminal-titlebar"><span>Raw HID · US physical layout</span><div><button type="button" class="keyboard-release">Release all keys</button><button type="button" class="keyboard-hide" aria-label="Close keyboard">×</button></div></div>${screenKeyboardMarkup()}</div>
    <footer class="terminal-footer kvm-footer"><div class="video-footer-tools"><button type="button" class="kvm-modifier" data-modifier="4">Alt</button><button type="button" class="kvm-modifier" data-modifier="2">Shift</button><button type="button" class="kvm-modifier" data-modifier="1">Ctrl</button><button type="button" class="kvm-hotkey-cad">Ctrl Alt Del</button><button type="button" class="keyboard-toggle">⌨ Keyboard</button><button type="button" class="mouse-mode-toggle">Mouse: Absolute</button><button type="button" class="keep-awake-toggle active">◉ Keep awake</button></div><div class="kvm-footer-state"><span class="video-resolution">—</span><span class="video-frame-status">Loading video…</span><span class="terminal-connection connecting"><i></i><b>Connecting HID</b></span></div></footer>`;
  document.querySelector("#terminal-layer").appendChild(element);
  const image = element.querySelector(".video-frame");
  const status = element.querySelector(".video-frame-status");
  const keyboard = element.querySelector(".video-keyboard");
  keyboard.remove();
  keyboard.style.left = `${Math.max(8, (window.innerWidth - Math.min(900, window.innerWidth - 16)) / 2)}px`;
  keyboard.style.top = `${Math.max(90, window.innerHeight - 310)}px`;
  document.querySelector("#terminal-layer").appendChild(keyboard);
  enableTerminalDrag(keyboard);
  keyboard.addEventListener("pointerdown", () => focusTerminal(keyboard));
  image.addEventListener("load", () => {
    status.textContent = "Live stream · 12 FPS";
    element.querySelector(".video-resolution").textContent = `${image.naturalWidth} × ${image.naturalHeight}`;
  });
  image.addEventListener("error", () => { status.textContent = "Stream unavailable; reopen to retry"; });
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
    element.querySelectorAll(".keyboard-key.modifier").forEach((key) => key.classList.remove("active"));
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
  let mouseMode = localStorage.getItem("kronoskvm.mouse-mode") === "relative" ? "relative" : "absolute";
  const mouseModeButton = element.querySelector(".mouse-mode-toggle");
  const renderMouseMode = () => {
    mouseModeButton.textContent = mouseMode === "relative" ? "Mouse: BIOS" : "Mouse: Absolute";
    mouseModeButton.classList.toggle("active", mouseMode === "relative");
    mouseModeButton.title = mouseMode === "relative"
      ? "BIOS boot mouse active. Click video to capture the pointer; press Escape to release."
      : "Absolute pointer mode for operating systems.";
  };
  renderMouseMode();
  mouseModeButton.addEventListener("click", () => {
    mouseMode = mouseMode === "absolute" ? "relative" : "absolute";
    localStorage.setItem("kronoskvm.mouse-mode", mouseMode);
    buttons = 0;
    sendHid({ type: "mouse", mode: mouseMode, buttons: 0, x: 0, y: 0, wheel: 0 });
    if (mouseMode === "absolute" && document.pointerLockElement === image) document.exitPointerLock();
    renderMouseMode();
    image.focus();
  });
  const displayedVideoPoint = (event) => {
    const rect = image.getBoundingClientRect();
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
  let lastMouseSent = 0;
  const sendMouse = (event, wheel = 0) => {
    if (relativeSyncing) return;
    if (mouseMode === "relative") {
      const x = Math.round(Math.max(-127, Math.min(127, event.movementX || 0)));
      const y = Math.round(Math.max(-127, Math.min(127, event.movementY || 0)));
      sendHid({ type: "mouse", mode: "relative", buttons, x, y, wheel });
      return;
    }
    const rect = image.getBoundingClientRect();
    const ratio = image.naturalWidth && image.naturalHeight ? image.naturalWidth / image.naturalHeight : 4 / 3;
    const width = Math.min(rect.width, rect.height * ratio);
    const height = width / ratio;
    const left = rect.left + (rect.width - width) / 2;
    const top = rect.top + (rect.height - height) / 2;
    const x = Math.round(Math.max(0, Math.min(1, (event.clientX - left) / width)) * 32767);
    const y = Math.round(Math.max(0, Math.min(1, (event.clientY - top) / height)) * 32767);
    sendHid({ type: "mouse", mode: "absolute", buttons, x, y, wheel });
  };
  image.addEventListener("mousemove", (event) => {
    if (performance.now() - lastMouseSent < 30) return;
    lastMouseSent = performance.now();
    sendMouse(event);
  });
  image.addEventListener("mousedown", (event) => {
    event.preventDefault();
    image.focus();
    if (mouseMode === "relative" && document.pointerLockElement !== image) {
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
  element.querySelector(".keyboard-toggle").addEventListener("click", () => {
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
    if (!image.naturalWidth) return showToast("Video frame is not ready");
    const canvas = document.createElement("canvas");
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    canvas.getContext("2d").drawImage(image, 0, 0);
    canvas.toBlob((blob) => {
      if (blob) downloadBlob(blob, `kronoskvm-snapshot-${new Date().toISOString().replaceAll(":", "-")}.png`);
    }, "image/png");
    showToast("Snapshot captured");
  });
  let recording = null;
  const stopRecording = (download = true) => {
    if (!recording) return;
    window.clearInterval(recording.timer);
    if (recording.recorder.state !== "inactive") recording.recorder.stop();
    recording.download = download;
    toolbarButton("record").classList.remove("active");
    toolbarButton("record").textContent = "● Record";
  };
  toolbarButton("record").addEventListener("click", () => {
    if (recording) {
      stopRecording();
      return;
    }
    if (!image.naturalWidth || !window.MediaRecorder) return showToast("Browser recording is unavailable");
    const canvas = document.createElement("canvas");
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext("2d");
    const timer = window.setInterval(() => {
      try { context.drawImage(image, 0, 0, canvas.width, canvas.height); } catch (error) { console.debug(error); }
    }, 84);
    const options = MediaRecorder.isTypeSupported("video/webm;codecs=vp8")
      ? { mimeType: "video/webm;codecs=vp8" }
      : {};
    const recorder = new MediaRecorder(canvas.captureStream(12), options);
    const chunks = [];
    recording = { recorder, timer, chunks, download: true };
    recorder.addEventListener("dataavailable", (event) => { if (event.data.size) chunks.push(event.data); });
    recorder.addEventListener("stop", () => {
      const completed = recording;
      recording = null;
      if (completed?.download && chunks.length) {
        downloadBlob(new Blob(chunks, { type: "video/webm" }), `kronoskvm-recording-${new Date().toISOString().replaceAll(":", "-")}.webm`);
        showToast("Recording saved");
      }
    });
    recorder.start(1000);
    toolbarButton("record").classList.add("active");
    toolbarButton("record").textContent = "■ Stop";
    showToast("Screen recording started");
  });
  let playing = true;
  toolbarButton("play").addEventListener("click", () => {
    playing = !playing;
    if (playing) {
      image.src = `/api/v1/video/stream.mjpg?t=${Date.now()}`;
      toolbarButton("play").textContent = "Ⅱ Pause";
      status.textContent = "Reconnecting video…";
    } else {
      image.src = "";
      toolbarButton("play").textContent = "▷ Play";
      status.textContent = "Video paused";
    }
  });
  toolbarButton("fullscreen").addEventListener("click", async () => {
    if (document.fullscreenElement === element) await document.exitFullscreen();
    else await element.requestFullscreen();
  });
  let aspectLocked = false;
  let adjustingAspect = false;
  const applyAspectRatio = () => {
    if (!aspectLocked || adjustingAspect || element.classList.contains("maximized")) return;
    adjustingAspect = true;
    const chromeHeight = element.querySelector(".terminal-titlebar").offsetHeight
      + element.querySelector(".kvm-toolbar").offsetHeight
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
      stagingStorage = await getJson("/api/v1/storage");
      const files = stagingStorage.files.filter((file) => /\.(iso|img)$/i.test(file.name));
      list.innerHTML = files.length ? files.map((file) => `<div class="virtual-media-item"><span><b>${escapeHtml(file.name)}</b><small>${formatBytes(file.size_bytes)}</small></span><button type="button" data-media-name="${escapeHtml(file.name)}">Mount</button></div>`).join("") : "<p>No ISO or IMG files in staging storage.</p>";
      list.querySelectorAll("[data-media-name]").forEach((button) => button.addEventListener("click", () => {
        showToast(`${button.dataset.mediaName}: USB mass-storage service setup pending`);
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
  videoWindow = { element, image, keepAwakeTimer, keyboard, releaseAllKeys, closeHid, stopRecording, aspectObserver };
  image.src = `/api/v1/video/stream.mjpg?t=${Date.now()}`;
  focusTerminal(element);
  enableTerminalDrag(element);
  element.addEventListener("pointerdown", () => focusTerminal(element));
  element.querySelector(".terminal-close").addEventListener("click", closeVideoWindow);
  element.querySelector(".terminal-minimize").addEventListener("click", () => element.classList.toggle("minimized"));
  element.querySelector(".terminal-maximize").addEventListener("click", () => element.classList.toggle("maximized"));
}

async function load() {
  const health = document.querySelector("#health");
  loadPorts();
  loadStorage();
  loadConnections();
  loadVideoStatus();
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
