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
  document.querySelector("#system-model").textContent =
    text(system.model).replace("Raspberry Pi ", "").replace(" Rev 1.1", "");
  document.querySelector("#system-hostname").textContent =
    `${text(system.hostname)} · ${text(system.architecture)}`;
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
  const active = network.interfaces.filter((item) => item.state === "up");
  document.querySelector("#network-count").textContent = text(active.length);
  document.querySelector("#network-summary").textContent =
    `${active.length} active of ${network.interfaces.length} detected`;
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
  const ready = services.filter((item) => item.ready).length;
  document.querySelector("#readiness-count").textContent = `${ready}/${services.length}`;
  document.querySelector("#readiness-summary").textContent =
    `${ready} operational · ${services.length - ready} pending`;
  document.querySelector("#services").innerHTML = services.map((item) =>
    `<div class="row"><span><strong>${escapeHtml(item.name)}</strong><br><span class="muted">${escapeHtml(item.detail)}</span></span><span class="state ${item.ready ? "" : "offline"}">${escapeHtml(item.status)}</span></div>`
  ).join("");
}

const portIcons = {
  console_1: "⌨",
  console_2: "⌨",
  service_usb: "USB",
  target_lan: "↔",
  kvm_otg: "KVM",
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
    const consoleTitle = port.console_available
      ? "Serial adapter detected; terminal transport is the next milestone"
      : connected
        ? "Connected device is not a serial console adapter"
        : "Connect a USB serial adapter first";
    return `<article class="port-card ${port.id === "kvm_otg" ? "otg-card" : ""}">
      <span class="port-icon">${escapeHtml(portIcons[port.id] || "IO")}</span>
      <div>
        <strong>${escapeHtml(port.name)}</strong>
        <p>${escapeHtml(port.physical_label)}${port.usb_path ? ` · <code>${escapeHtml(port.usb_path)}</code>` : ""}</p>
        <div class="port-meta">
          <span class="port-state ${statusClass}">${escapeHtml(port.status.replace("_", " "))}</span>
          <span class="muted">${escapeHtml(detail)}</span>
        </div>
      </div>
      <div class="port-actions">
        ${isConsole ? `<button class="port-action" type="button"
          title="Serial session transport is not enabled yet" disabled>Connect</button>
        <button class="port-action console-action" type="button"
          data-port="${escapeHtml(port.name)}" data-available="${port.console_available}"
          title="${escapeHtml(consoleTitle)}" disabled>⌨ Console</button>` : ""}
        <button class="port-action status-action" type="button"
          data-message="${escapeHtml(`${port.name}: ${port.status}${port.device_name ? ` — ${port.device_name}` : ""}`)}">Status</button>
      </div>
    </article>`;
  }).join("");

  document.querySelectorAll(".status-action").forEach((button) => {
    button.addEventListener("click", () => showToast(button.dataset.message));
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
      document.querySelector("#ports").textContent = "Port status could not be displayed.";
      console.error("Port render failed", error);
    }
  }
}

document.querySelector("#refresh").addEventListener("click", load);
load();
