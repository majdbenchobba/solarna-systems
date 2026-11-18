import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(
  new URL("../capacitor.config.js", import.meta.url),
  "utf8"
);

function loadConfig(environment = {}) {
  const module = { exports: {} };
  vm.runInNewContext(source, {
    module,
    exports: module.exports,
    process: { env: environment }
  });
  return module.exports;
}

const production = loadConfig();
assert.equal(production.appId, "tn.solarna.optimizer");
assert.equal(production.appName, "Solarna PV");
assert.equal(production.server.androidScheme, "https");
assert.equal(production.server.cleartext, false);
assert.equal(production.android.allowMixedContent, false);

const emulator = loadConfig({ SOLARNA_MOBILE_DEV_HTTP: "1" });
assert.equal(emulator.server.androidScheme, "http");
assert.equal(emulator.server.cleartext, true);
assert.equal(emulator.android.allowMixedContent, true);

console.log("Mobile production and emulator configurations are isolated.");
