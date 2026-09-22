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

const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const url = `${base.replace(/\/$/, "")}/openapi.json`;

console.log(`Reading the schema from ${url}`);

const result = spawnSync(
  "npx",
  ["openapi-typescript", url, "-o", "lib/api-types.ts"],
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
