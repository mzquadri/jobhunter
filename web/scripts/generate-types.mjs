/**
 * Regenerate `lib/api-types.ts` from the API's live OpenAPI document.
 *
 * A script rather than an inline npm command: the inline version used POSIX
 * `${NEXT_PUBLIC_API_URL:-...}` expansion, which npm hands to cmd.exe on
 * Windows unexpanded. The generator then tried to read a *file* literally
 * named `${NEXT_PUBLIC_API_URL:-http:/localhost:8000}/openapi.json`, failed,
 * and left the checked-in types untouched — a regeneration that looked like it
 * ran and did nothing at all.
 */

import { spawnSync } from "node:child_process";
import { readFileSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const url = process.env.OPENAPI_FILE || `${base.replace(/\/$/, "")}/openapi.json`;
const checking = process.argv.includes("--check");
const temporary = checking ? mkdtempSync(join(tmpdir(), "careeros-contract-")) : null;
const output = temporary ? join(temporary, "api-types.ts") : "lib/api-types.ts";

console.log(`Reading the schema from ${url}`);

const result = spawnSync(
  "npx",
  ["openapi-typescript", url, "-o", output],
  { stdio: "inherit", shell: process.platform === "win32" },
);

if (result.error) {
  console.error(`Could not run openapi-typescript: ${result.error.message}`);
  process.exit(1);
}
if (result.status !== 0) {
  console.error(
    `\nThe schema could not be read. Is the API running?  docker compose ps`,
  );
  process.exit(result.status ?? 1);
}
if (checking) {
  const same = readFileSync(output, "utf8").replaceAll("\r\n", "\n") ===
    readFileSync("lib/api-types.ts", "utf8").replaceAll("\r\n", "\n");
  rmSync(temporary, { recursive: true, force: true });
  if (!same) { console.error("OpenAPI contract differs from checked-in types."); process.exit(1); }
  console.log("OpenAPI contract matches checked-in types.");
}
