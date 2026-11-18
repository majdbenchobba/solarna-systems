import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const mobileDirectory = path.resolve(scriptDirectory, "..");

async function text(name) {
  return readFile(path.join(mobileDirectory, name), "utf8");
}

const android = await text("build-android-release.ps1");
assert.match(android, /\[string\]\$ApiUrl\s*=\s*""/);
assert.doesNotMatch(android, /Parameter\(Mandatory\s*=\s*\$true\)[\s\S]*ApiUrl/);
assert.match(android, /if \(\$ApiUrl\) \{[\s\S]*--api-url/);
assert.match(android, /npm\.cmd @prepareArguments/);

const ios = await text("build-ios-release.sh");
assert.match(ios, /if \[ "\$#" -gt 1 \]/);
assert.match(ios, /api_url=\$\{1:-\}/);
assert.match(ios, /repository_mode=0/);
assert.match(ios, /xcode_project="App\/App\.xcodeproj"/);
assert.match(ios, /A fixed server URL can only be embedded from the full repository/);
assert.match(ios, /if \[ -n "\$api_url" \]; then[\s\S]*npm run prepare:web -- --api-url/);
assert.match(ios, /else\s+npm run prepare:web\s+fi/);

const play = await text("ANDROID-STORE-SUBMISSION.md");
assert.match(play, /Package: `tn\.solarna\.optimizer`/);
assert.match(play, /Target Android: API 36/);
assert.match(play, /Precise location/);
assert.match(play, /Android Location Button/);
assert.match(play, /contain no native `\.so` libraries/);

console.log("Android and iOS release scripts support URL-neutral builds.");
