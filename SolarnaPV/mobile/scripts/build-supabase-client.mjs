import { build } from "esbuild";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));

await build({
  entryPoints: [resolve(scriptDirectory, "supabase-client-entry.js")],
  outfile: resolve(scriptDirectory, "..", "..", "solarna", "web", "supabase-client.js"),
  bundle: true,
  format: "iife",
  platform: "browser",
  target: ["es2020"],
  minify: true,
  legalComments: "none",
});

console.log("Built the browser Supabase client.");
