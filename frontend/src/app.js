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
          <button class="menu-action" type="button" role="menuitem"
            data-message="${escapeHtml(`${port.name}: configuration panel is the next milestone`)}">⚙ Config</button>
          <button class="menu-action" type="button" role="menuitem"
            data-message="${escapeHtml(`${port.name}: ${port.status}${port.device_name ? ` — ${port.device_name}` : ""}`)}">◎ Status</button>
          <button type="button" role="menuitem" title="Port control backend is not enabled yet" disabled>
            ${connected ? "⊘" : "→"} ${connectionAction}</button>
          ${isConsole ? `<button type="button" role="menuitem"
            title="Serial terminal transport is not enabled yet" disabled>⌘ Console</button>` : ""}
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
}

async function load() {
  const health = document.querySelector("#health");
  const results = await Promise.allSettled([
    getJson("/api/v1/health"),
    getJson("/api/v1/system/info"),
    getJson("/api/v1/system/network"),
    getJson("/api/v1/hardware/ports"),
  ]);
  const [healthResult, systemResult, networkResult, portsResult] = results;

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
  if (portsResult.status === "fulfilled") {
    try {
      renderPorts(portsResult.value);
    } catch (error) {
      document.querySelector("#ports").innerHTML =
        '<tr><td colspan="5" class="loading-cell">Port status could not be displayed.</td></tr>';
      console.error("Port render failed", error);
    }
  }
}

document.querySelector("#refresh").addEventListener("click", load);
document.addEventListener("click", (event) => {
  document.querySelectorAll(".action-menu[open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.removeAttribute("open");
  });
});
load();
