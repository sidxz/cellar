"use client";

/**
 * RDKit.js WASM singleton loader.
 *
 * Lazily initializes the RDKit WASM module once and caches the result.
 * Subsequent calls return the same promise/instance.
 */

import type { RDKitModule } from "@rdkit/rdkit";

let rdkitPromise: Promise<RDKitModule> | null = null;

export function getRDKit(): Promise<RDKitModule> {
  if (rdkitPromise) return rdkitPromise;

  rdkitPromise = (async () => {
    // Dynamic import — the main export IS the loader function
    const initRDKitModule = (
      (await import("@rdkit/rdkit")) as unknown as { default: () => Promise<RDKitModule> }
    ).default;
    const rdkit = await initRDKitModule();
    return rdkit;
  })();

  return rdkitPromise;
}
