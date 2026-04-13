"use client";

import { useRef, useCallback } from "react";
import { Editor } from "ketcher-react";
import { StandaloneStructServiceProvider } from "ketcher-standalone";
import "ketcher-react/dist/index.css";
import type { Ketcher } from "ketcher-core";

interface KetcherEditorProps {
  initialStructure?: string;
  onInit?: () => void;
  ketcherRef: React.MutableRefObject<Ketcher | null>;
}

const structServiceProvider = new StandaloneStructServiceProvider();

export function KetcherEditor({
  initialStructure,
  onInit,
  ketcherRef,
}: KetcherEditorProps) {
  const initCalled = useRef(false);

  const handleInit = useCallback(
    (ketcher: Ketcher) => {
      ketcherRef.current = ketcher;
      if (initialStructure && !initCalled.current) {
        initCalled.current = true;
        setTimeout(() => {
          ketcher.setMolecule(initialStructure).catch(() => {});
        }, 100);
      }
      onInit?.();
    },
    [initialStructure, ketcherRef, onInit]
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
