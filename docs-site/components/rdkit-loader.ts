"use client";

/**
 * RDKit.js WASM singleton loader (ported from frontend/src/shared/lib/rdkit).
 *
 * Lazily initializes the RDKit WASM module once and caches the promise so
 * every widget on a page shares a single instance. The docs site keeps its own
 * copy rather than importing from the app, so it can build independently.
 */
import type { RDKitModule } from "@rdkit/rdkit";

let rdkitPromise: Promise<RDKitModule> | null = null;

export function getRDKit(): Promise<RDKitModule> {
  if (rdkitPromise) return rdkitPromise;

  rdkitPromise = (async () => {
    const initRDKitModule = (
      (await import("@rdkit/rdkit")) as unknown as {
        default: (opts?: { locateFile?: () => string }) => Promise<RDKitModule>;
      }
    ).default;
    const rdkit = await initRDKitModule({
      // WASM binary is copied to public/ by scripts/copy-rdkit-wasm.mjs.
      locateFile: () => "/RDKit_minimal.wasm",
    });
    return rdkit;
  })();

  return rdkitPromise;
}
