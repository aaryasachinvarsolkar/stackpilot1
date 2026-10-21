// Copies Monaco's prebuilt runtime from node_modules into public/monaco so the editor is served
// by this app itself. Without this, @monaco-editor/react loads Monaco from a public CDN, which
// would need internet access and send requests to a third party.
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "node_modules", "monaco-editor", "min", "vs");
const target = join(root, "public", "monaco", "vs");

if (!existsSync(source)) {
  console.error(`copy-monaco: ${source} not found. Run "npm install" first.`);
  process.exit(1);
}

rmSync(target, { recursive: true, force: true });
mkdirSync(dirname(target), { recursive: true });
cpSync(source, target, { recursive: true });
console.log("copy-monaco: Monaco runtime copied to public/monaco/vs");
