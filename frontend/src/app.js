const text = (value, fallback = "unknown") =>
  value === null || value === undefined || value === "" ? fallback : String(value);

const escapeHtml = (value) => text(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

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

function renderCapabilities(capabilities) {
  const ready = capabilities.filter((item) =>
    ["ready", "running"].includes(item.status)
  ).length;
  document.querySelector("#capability-count").textContent = text(capabilities.length);
  document.querySelector("#capability-summary").textContent =
    `${ready} ready · ${capabilities.length - ready} awaiting hardware`;
  document.querySelector("#capabilities").innerHTML = capabilities.map((item) =>
    `<div class="row"><span>${escapeHtml(item.name)}</span><span class="state ${["ready", "running"].includes(item.status) ? "" : "offline"}">${escapeHtml(item.status)}</span></div>`
  ).join("");
}

async function load() {
  const health = document.querySelector("#health");
  try {
    const [healthData, system, network, capabilities] = await Promise.all([
      getJson("/api/v1/health"),
      getJson("/api/v1/system/info"),
      getJson("/api/v1/system/network"),
      getJson("/api/v1/capabilities"),
    ]);
    health.textContent = `API ${text(healthData.status)}`;
    health.className = "badge ready";
    renderSystem(system);
    renderNetwork(network);
    renderCapabilities(capabilities);
  } catch (error) {
    health.textContent = "API unavailable";
    health.className = "badge error";
    console.error(error);
  }
}

document.querySelector("#refresh").addEventListener("click", load);
load();
