// Copies the RDKit WASM binary into public/ so it is served as a static asset.
// The RDKit loader references it at "/RDKit_minimal.wasm". Mirrors the
// frontend's postinstall step. Fails soft if the package is not yet installed.
import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const src = resolve(root, "node_modules/@rdkit/rdkit/dist/RDKit_minimal.wasm");
const dest = resolve(root, "public/RDKit_minimal.wasm");

try {
  await mkdir(dirname(dest), { recursive: true });
  await copyFile(src, dest);
  console.log("[copy-rdkit-wasm] copied RDKit_minimal.wasm -> public/");
} catch (err) {
  console.warn(
    "[copy-rdkit-wasm] skipped (RDKit not installed yet?):",
    err.message,
  );
}
