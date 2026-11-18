import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const mobileDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);

// Resolve through Capacitor so a nested dependency install is tested correctly.
const capacitorRequire = createRequire(require.resolve("@capacitor/cli"));
const xcode = capacitorRequire("xcode");
const xcodeRequire = createRequire(capacitorRequire.resolve("xcode"));
const uuid = xcodeRequire("uuid");
const project = xcode.project(path.join(
  mobileDirectory, "ios", "App", "App.xcodeproj", "project.pbxproj"
));
project.parseSync();
const projectIds = new Set(project.allUuids());
for (let index = 0; index < 32; index += 1) {
  const id = project.generateUuid();
  assert.match(id, /^[A-F0-9]{24}$/, "Xcode project identifiers must retain their format.");
  assert.equal(projectIds.has(id), false, "Generated project identifiers must be unique.");
  projectIds.add(id);
}

// GHSA-w5hq-g745-h8pq: invalid output ranges must fail before modifying a buffer.
const namespace = "6ba7b810-9dad-11d1-80b4-00c04fd430c8";
const generators = [
  (buffer, offset) => uuid.v3("solarna-test", namespace, buffer, offset),
  (buffer, offset) => uuid.v5("solarna-test", namespace, buffer, offset),
  (buffer, offset) => uuid.v6({}, buffer, offset),
];
for (const generate of generators) {
  for (const [length, offset] of [[8, 4], [16, -1], [16, 1]]) {
    const buffer = new Uint8Array(length).fill(0xaa);
    assert.throws(() => generate(buffer, offset), RangeError);
    assert.equal(buffer.every((value) => value === 0xaa), true);
  }
}

console.log("Capacitor/Xcode UUID generation and buffer-bounds security checks passed.");
