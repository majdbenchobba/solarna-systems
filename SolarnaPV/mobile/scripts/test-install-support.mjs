import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const install = require("../../solarna/web/install-support.js");
const standalone = () => ({ matches: true });
const browser = () => ({ matches: false });

assert.equal(
  install.shouldOfferIosInstall(
    false,
    { userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)" },
    browser
  ),
  true
);
assert.equal(
  install.shouldOfferIosInstall(
    false,
    { platform: "MacIntel", maxTouchPoints: 5 },
    browser
  ),
  true
);
assert.equal(
  install.shouldOfferIosInstall(
    false,
    { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" },
    browser
  ),
  false
);
assert.equal(
  install.shouldOfferIosInstall(
    false,
    { userAgent: "Mozilla/5.0 (iPhone)", standalone: true },
    browser
  ),
  false
);
assert.equal(
  install.shouldOfferIosInstall(
    false,
    { userAgent: "Mozilla/5.0 (iPhone)" },
    standalone
  ),
  false
);
assert.equal(
  install.shouldOfferIosInstall(
    true,
    { userAgent: "Mozilla/5.0 (iPhone)" },
    browser
  ),
  false
);

console.log("iPhone install support detection passed.");
