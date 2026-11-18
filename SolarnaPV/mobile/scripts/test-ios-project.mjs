import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const mobileDirectory = path.resolve(scriptDirectory, "..");
const projectDirectory = path.resolve(mobileDirectory, "..");
const iosAppDirectory = path.join(mobileDirectory, "ios", "App", "App");

async function text(relativePath) {
  return readFile(path.join(projectDirectory, relativePath), "utf8");
}

async function digest(relativePath) {
  return createHash("sha256")
    .update(await readFile(path.join(projectDirectory, relativePath)))
    .digest("hex");
}

const icon = await readFile(path.join(
  iosAppDirectory,
  "Assets.xcassets",
  "AppIcon.appiconset",
  "AppIcon-512@2x.png"
));
assert.equal(icon.readUInt32BE(16), 1024);
assert.equal(icon.readUInt32BE(20), 1024);
assert.equal(icon[24], 8, "The iOS icon must use 8-bit PNG channels.");
assert.equal(
  icon[25],
  2,
  "The iOS App Store icon must be opaque RGB without an alpha channel."
);

const info = await text("mobile/ios/App/App/Info.plist");
assert.match(info, /<key>CFBundleDisplayName<\/key>\s*<string>Solarna<\/string>/);
assert.match(info, /<key>NSLocationWhenInUseUsageDescription<\/key>/);
assert.doesNotMatch(info, /NSAllowsArbitraryLoads/);

const privacy = await text("mobile/ios/App/App/PrivacyInfo.xcprivacy");
assert.match(privacy, /<key>NSPrivacyTracking<\/key>\s*<false\/>/);
assert.match(privacy, /NSPrivacyCollectedDataTypePreciseLocation/);
assert.match(privacy, /NSPrivacyCollectedDataTypeOtherUserContent/);
assert.match(privacy, /NSPrivacyCollectedDataTypePurposeAppFunctionality/);
assert.doesNotMatch(privacy, /<key>NSPrivacyTracking<\/key>\s*<true\/>/);

const project = await text("mobile/ios/App/App.xcodeproj/project.pbxproj");
assert.match(project, /PRODUCT_BUNDLE_IDENTIFIER = tn\.solarna\.optimizer;/);
assert.match(project, /MARKETING_VERSION = 0\.5\.0;/);
assert.match(project, /CURRENT_PROJECT_VERSION = 12;/);
assert.match(project, /IPHONEOS_DEPLOYMENT_TARGET = 15\.0;/);
assert.match(project, /SceneDelegate\.swift in Sources/);
assert.match(project, /PrivacyInfo\.xcprivacy in Resources/);

const capacitor = JSON.parse(
  await text("mobile/ios/App/App/capacitor.config.json")
);
assert.equal(capacitor.appId, "tn.solarna.optimizer");
assert.equal(capacitor.server.iosScheme, "capacitor");
assert.equal(capacitor.server.cleartext, false);

const iosConfig = await text("mobile/ios/App/App/public/config.js");
assert.match(iosConfig, /["']?apiBaseUrl["']?\s*:\s*""/);
assert.doesNotMatch(iosConfig, /trycloudflare|http:\/\//);

for (const name of [
  "app.css",
  "app.js",
  "cloud-storage.js",
  "index.html",
  "install-support.js",
  "login.html",
  "login.js",
  "manifest.webmanifest",
  "privacy.html",
  "reset-password.html",
  "reset-password.js",
  "result-summary.js",
  "solarna-mark.svg",
  "supabase-client.js",
  "system-config.js",
]) {
  assert.equal(
    await digest(`solarna/web/${name}`),
    await digest(`mobile/ios/App/App/public/${name}`),
    `${name} is not synchronized with the web application.`
  );
}

console.log("iOS project metadata, icon and synchronized web bundle passed.");
