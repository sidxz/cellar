"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { RDKitModule } from "@rdkit/rdkit";
import { getRDKit } from "./rdkit-loader";

type RdkitStatus = "loading" | "ready" | "error";

interface RdkitContextValue {
  rdkit: RDKitModule | null;
  status: RdkitStatus;
}

const RdkitContext = createContext<RdkitContextValue>({
  rdkit: null,
  status: "loading",
});

/**
 * Loads the RDKit WASM module once (client-only) and shares it via context.
 *
 * Wrap any subtree that contains chemistry widgets. Because the loader is a
 * cached singleton, multiple providers on a page are harmless — they all
 * resolve to the same module instance.
 */
export function RdkitProvider({ children }: { children: ReactNode }) {
  const [rdkit, setRdkit] = useState<RDKitModule | null>(null);
  const [status, setStatus] = useState<RdkitStatus>("loading");

  useEffect(() => {
    let cancelled = false;
    getRDKit()
      .then((mod) => {
        if (cancelled) return;
        setRdkit(mod);
        setStatus("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(() => ({ rdkit, status }), [rdkit, status]);

  return (
    <RdkitContext.Provider value={value}>{children}</RdkitContext.Provider>
  );
}

/** Access the shared RDKit module and its load status. */
export function useRdkit(): RdkitContextValue {
  return useContext(RdkitContext);
}
