"use client";

import { Editor } from "ketcher-react";
import { StandaloneStructServiceProvider } from "ketcher-standalone";
import { useCallback } from "react";
import "ketcher-react/dist/index.css";
import type { Ketcher } from "ketcher-core";

interface KetcherEditorProps {
  initialStructure?: string;
  onInit?: () => void;
  ketcherRef: React.MutableRefObject<Ketcher | null>;
}

const structServiceProvider = new StandaloneStructServiceProvider();

// Ketcher's onInit fires before the standalone StructService finishes warming
// up (Indigo WASM). setMolecule called during that window rejects silently and
// the canvas stays blank -- the bug chemists hit when clicking "Edit
// structure" with a SMILES already typed. Retry with a short backoff so we
// land on the first ready tick.
const RETRY_DELAYS_MS = [0, 100, 250, 500, 1000];

async function loadInitialStructure(ketcher: Ketcher, structStr: string): Promise<void> {
  let lastError: unknown;
  for (const delay of RETRY_DELAYS_MS) {
    if (delay > 0) await new Promise((r) => setTimeout(r, delay));
    try {
      await ketcher.setMolecule(structStr);
      return;
    } catch (e) {
      lastError = e;
    }
  }
  // All retries exhausted — surface the failure so the chemist (or dev)
  // can see why the canvas didn't pre-load. Silent failure is what masked
  // this bug for so long.
  console.warn("[Ketcher] failed to load initial structure after retries:", {
    structStr,
    error: lastError,
  });
}

export function KetcherEditor({ initialStructure, onInit, ketcherRef }: KetcherEditorProps) {
  const handleInit = useCallback(
    (ketcher: Ketcher) => {
      ketcherRef.current = ketcher;
      if (initialStructure) {
        // Fire-and-forget — the dialog gates the Apply button on
        // editorReady, not on initial-load completion. The canvas
        // populates as soon as the retry ladder lands.
        void loadInitialStructure(ketcher, initialStructure);
      }
      onInit?.();
    },
    [initialStructure, ketcherRef, onInit],
  );

  return (
    <div className="ketcher-scope" style={{ height: "100%", width: "100%" }}>
      <Editor
        staticResourcesUrl=""
        structServiceProvider={structServiceProvider}
        onInit={handleInit}
        errorHandler={(message: string) => {
          if (process.env.NODE_ENV === "development") {
            console.debug("[Ketcher]", message);
          }
        }}
      />
    </div>
  );
}
