import { cpSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const mobileDirectory = resolve(scriptDirectory, "..");
const sourceDirectory = resolve(mobileDirectory, "..", "solarna", "web");
const outputDirectory = resolve(mobileDirectory, "www");

function argumentValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? "" : process.argv[index + 1] || "";
}

function normalizeServerUrl(value) {
  const text = value.trim();
  if (!text) return "";
  const parsed = new URL(text);
  if (!["http:", "https:"].includes(parsed.protocol) ||
      parsed.username || parsed.password || parsed.search || parsed.hash ||
      !parsed.hostname || parsed.pathname !== "/") {
    throw new Error(
      "The server URL must be an origin such as https://solarna.example.com"
    );
  }
  return parsed.origin;
}

const apiBaseUrl = normalizeServerUrl(
  argumentValue("--api-url") || process.env.SOLARNA_API_URL || ""
);
const allowInsecureApi =
  process.argv.includes("--allow-http") ||
  process.env.SOLARNA_ALLOW_HTTP === "1";

if (apiBaseUrl.startsWith("http:") && !allowInsecureApi) {
  throw new Error(
    "Mobile production builds require HTTPS. Use --allow-http only for local development."
  );
}

rmSync(outputDirectory, { recursive: true, force: true });
mkdirSync(outputDirectory, { recursive: true });
cpSync(sourceDirectory, outputDirectory, { recursive: true });
writeFileSync(
  resolve(outputDirectory, "config.js"),
  `window.SOLARNA_CONFIG = Object.freeze(${JSON.stringify({
    apiBaseUrl,
    nativeShell: true,
    allowInsecureApi
  }, null, 2)});\n`,
  "utf8"
);

console.log(
  apiBaseUrl
    ? `Prepared mobile web assets for ${apiBaseUrl}`
    : "Prepared mobile web assets; the server URL will be entered in the application"
);
