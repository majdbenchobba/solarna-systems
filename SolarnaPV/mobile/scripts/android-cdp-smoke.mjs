import { writeFile } from "node:fs/promises";

const cdpBase = process.env.SOLARNA_CDP_URL || "http://127.0.0.1:9222";
const serverUrl = process.env.SOLARNA_TEST_SERVER_URL;
const loginEmail = process.env.SOLARNA_TEST_LOGIN_EMAIL;
const loginPassword = process.env.SOLARNA_TEST_LOGIN_PASSWORD;
const outputPath = process.env.SOLARNA_SMOKE_OUTPUT;

if (!serverUrl || !loginEmail || !loginPassword) {
  throw new Error(
    "Set SOLARNA_TEST_SERVER_URL, SOLARNA_TEST_LOGIN_EMAIL and " +
    "SOLARNA_TEST_LOGIN_PASSWORD."
  );
}

const targets = await fetch(`${cdpBase}/json/list`).then(response => {
  if (!response.ok) throw new Error(`CDP target request failed (${response.status}).`);
  return response.json();
});
const target = targets.find(item => item.type === "page");
if (!target?.webSocketDebuggerUrl) {
  throw new Error("No debuggable Android WebView page was found.");
}

const socket = new WebSocket(target.webSocketDebuggerUrl);
const pending = new Map();
let commandId = 0;

socket.addEventListener("message", event => {
  const message = JSON.parse(event.data);
  if (!message.id || !pending.has(message.id)) return;
  const { resolve, reject } = pending.get(message.id);
  pending.delete(message.id);
  if (message.error) reject(new Error(message.error.message));
  else resolve(message.result);
});

await new Promise((resolve, reject) => {
  socket.addEventListener("open", resolve, { once: true });
  socket.addEventListener("error", reject, { once: true });
});

function command(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++commandId;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });
}

async function evaluate(expression) {
  const result = await command("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
    userGesture: true
  });
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.text || "WebView evaluation failed.");
  }
  return result.result?.value;
}

async function waitFor(check, timeoutMs, label) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await check();
    if (value) return value;
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  throw new Error(`${label} timed out.`);
}

try {
  await command("Runtime.enable");
  const connectionInput = JSON.stringify({
    serverUrl,
    loginEmail,
    loginPassword
  });
  await evaluate(`(() => {
    const input = ${connectionInput};
    const setValue = (id, value) => {
      const node = document.getElementById(id);
      node.value = value;
      node.dispatchEvent(new Event("input", { bubbles: true }));
      node.dispatchEvent(new Event("change", { bubbles: true }));
    };
    setValue("native-api-url", input.serverUrl);
    setValue("login-email", input.loginEmail);
    setValue("login-password", input.loginPassword);
    document.getElementById("native-connect-button").click();
    return true;
  })()`);

  const connected = await waitFor(
    () => evaluate(`(() => {
      const optimizer = document.getElementById("optimizer-form");
      const connectionNode = document.getElementById("connection-status");
      if (!optimizer || !connectionNode) return null;
      const connection = connectionNode.textContent.trim();
      return connection === "Online" ? { status: "Connected", connection } : null;
    })()`),
    30000,
    "Android server connection"
  );

  const sizingModes = await evaluate(`(() => {
    const setValue = (id, value) => {
      const node = document.getElementById(id);
      node.value = value;
      node.dispatchEvent(new Event("input", { bubbles: true }));
      node.dispatchEvent(new Event("change", { bubbles: true }));
    };
    setValue("system-size-mode", "capacity");
    setValue("capacity", "4.5");
    const direct = {
      capacity: document.getElementById("capacity").value,
      countHidden: document.getElementById("panel-count-field").classList.contains("hidden"),
      powerHidden: document.getElementById("panel-power-field").classList.contains("hidden"),
      summary: document.getElementById("system-size-summary").textContent.trim()
    };
    setValue("system-size-mode", "normalized");
    const normalized = {
      capacity: document.getElementById("capacity").value,
      countHidden: document.getElementById("panel-count-field").classList.contains("hidden"),
      powerHidden: document.getElementById("panel-power-field").classList.contains("hidden"),
      capacityHidden: document.getElementById("capacity-field").classList.contains("hidden"),
      inverterHidden: document.getElementById("inverter-model-field").classList.contains("hidden"),
      ratingHidden: document.getElementById("inverter-ac-rating-field").classList.contains("hidden"),
      summary: document.getElementById("system-size-summary").textContent.trim()
    };
    setValue("system-size-mode", "panels");
    setValue("panel-count", "10");
    setValue("panel-power", "450");
    const comparisonEnabled = document.getElementById("existing-orientation-enabled");
    comparisonEnabled.checked = true;
    comparisonEnabled.dispatchEvent(new Event("change", { bubbles: true }));
    setValue("existing-tilt", "20");
    setValue("existing-azimuth", "180");
    const historicalRange = document.getElementById("historical-range");
    historicalRange.checked = true;
    historicalRange.dispatchEvent(new Event("change", { bubbles: true }));
    const panels = {
      capacity: document.getElementById("capacity").value,
      countHidden: document.getElementById("panel-count-field").classList.contains("hidden"),
      powerHidden: document.getElementById("panel-power-field").classList.contains("hidden"),
      summary: document.getElementById("system-size-summary").textContent.trim()
    };
    setValue("system-size-mode", "normalized");
    document.getElementById("run-button").click();
    return { direct, normalized, panels };
  })()`);
  if (Number(sizingModes.direct.capacity) !== 4.5 ||
      !sizingModes.direct.countHidden ||
      !sizingModes.direct.powerHidden ||
      Number(sizingModes.normalized.capacity) !== 1 ||
      !sizingModes.normalized.countHidden ||
      !sizingModes.normalized.powerHidden ||
      !sizingModes.normalized.capacityHidden ||
      !sizingModes.normalized.inverterHidden ||
      !sizingModes.normalized.ratingHidden ||
      sizingModes.normalized.summary !== "Orientation only · results shown per kWp" ||
      Number(sizingModes.panels.capacity) !== 4.5 ||
      sizingModes.panels.countHidden ||
      sizingModes.panels.powerHidden) {
    throw new Error("Android system sizing modes failed.");
  }

  const result = await waitFor(
    () => evaluate(`(() => {
      const statusBox = document.getElementById("job-status");
      if (statusBox.classList.contains("failed")) {
        throw new Error(document.getElementById("job-message").textContent.trim());
      }
      const results = document.getElementById("results");
      if (results.classList.contains("hidden")) return null;
      return {
        title: document.getElementById("results-title").textContent.trim(),
        tilt: document.getElementById("best-tilt").textContent.trim(),
        azimuth: document.getElementById("best-azimuth").textContent.trim(),
        annualLabel: document.getElementById("annual-energy-label").textContent.trim(),
        annualEnergy: document.getElementById("annual-energy").textContent.trim(),
        specificYield: document.getElementById("specific-yield").textContent.trim(),
        existingComparison:
          document.getElementById("existing-orientation-summary").textContent.trim(),
        comparisonDetails:
          document.getElementById("timing-details").textContent.trim()
      };
    })()`),
    180000,
    "Android optimization"
  );

  const summary = {
    target: target.url,
    connected,
    capacityKw: Number(sizingModes.normalized.capacity),
    sizingModes,
    result
  };
  if (result.annualLabel !== "Annual yield" ||
      !result.annualEnergy.endsWith(" kWh/kWp") ||
      result.specificYield !== "Normalized 1 kWp model") {
    throw new Error("Android normalized-yield result failed.");
  }
  if (!result.existingComparison.startsWith("Current 20° / 180°:")) {
    throw new Error("Android existing-orientation comparison failed.");
  }
  if (!result.comparisonDetails.includes("Historical range") ||
      !result.comparisonDetails.includes("2005–2023") ||
      !result.comparisonDetails.includes("not a confidence interval")) {
    throw new Error("Android historical-range result failed.");
  }
  const serialized = JSON.stringify(summary, null, 2) + "\n";
  if (outputPath) await writeFile(outputPath, serialized, "utf8");
  process.stdout.write(serialized);
} finally {
  socket.close();
}
