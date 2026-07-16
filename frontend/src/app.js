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
    `<div class="row"><span><strong>${escapeHtml(item.name)}</strong><br><span class="muted">${escapeHtml(item.addresses?.join(", ") || "no address")}</span></span><span class="state">${escapeHtml(item.state)}</span></div>`
  ).join("");
}

function renderCapabilities(capabilities) {
  document.querySelector("#capabilities").innerHTML = capabilities.map((item) =>
    `<div class="row"><span>${escapeHtml(item.name)}</span><span class="state">${escapeHtml(item.status)}</span></div>`
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

load();
