"use client";

import { useEffect, useState } from "react";
import { RdkitProvider, useRdkit } from "./RdkitProvider";

export interface StructureViewerProps {
  /** SMILES (or CXSMILES) to render. When omitted, the widget shows an input. */
  smiles?: string;
  /** Render width in pixels. */
  width?: number;
  /** Render height in pixels. */
  height?: number;
  /** Optional SMARTS pattern to highlight matching atoms/bonds. */
  highlightSmarts?: string;
  /** Allow the reader to type/paste their own SMILES. Defaults to true. */
  editable?: boolean;
  /** Extra CSS class for the outer container. */
  className?: string;
}

type RenderState =
  | { kind: "idle" }
  | { kind: "rendering" }
  | { kind: "ready"; url: string }
  | { kind: "invalid" }
  | { kind: "error" };

/**
 * Renders a 2D chemical structure SVG from a SMILES string using the shared
 * RDKit.js WASM module (from RdkitProvider context). Generates an SVG blob URL
 * rather than using innerHTML — the SVG comes from the trusted RDKit WASM lib.
 *
 * Ported from frontend `structure-renderer.tsx`, but consumes the shared module
 * via `useRdkit()` instead of calling the loader a second time.
 */
function StructureCanvas({
  smiles,
  width,
  height,
  highlightSmarts,
}: {
  smiles: string;
  width: number;
  height: number;
  highlightSmarts?: string;
}) {
  const { rdkit, status } = useRdkit();
  const [render, setRender] = useState<RenderState>({ kind: "idle" });

  useEffect(() => {
    if (status === "error") {
      setRender({ kind: "error" });
      return;
    }
    if (status !== "ready" || !rdkit) {
      setRender({ kind: "rendering" });
      return;
    }
    if (!smiles.trim()) {
      setRender({ kind: "idle" });
      return;
    }

    let cancelled = false;
    let url: string | null = null;
    setRender({ kind: "rendering" });

    try {
      const mol = rdkit.get_mol(smiles);
      if (!mol || !mol.is_valid()) {
        mol?.delete();
        setRender({ kind: "invalid" });
        return;
      }

      let svgStr: string;
      if (highlightSmarts) {
        const qmol = rdkit.get_qmol(highlightSmarts);
        if (qmol && qmol.is_valid()) {
          const matchJson = mol.get_substruct_match(qmol);
          svgStr = mol.get_svg_with_highlights(matchJson);
          qmol.delete();
        } else {
          svgStr = mol.get_svg(width, height);
          qmol?.delete();
        }
      } else {
        svgStr = mol.get_svg(width, height);
      }
      mol.delete();

      const blob = new Blob([svgStr], { type: "image/svg+xml" });
      url = URL.createObjectURL(blob);
      if (!cancelled) {
        setRender({ kind: "ready", url });
      }
    } catch {
      if (!cancelled) setRender({ kind: "error" });
    }

    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [rdkit, status, smiles, width, height, highlightSmarts]);

  const frameStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width,
    height,
    borderRadius: "0.5rem",
    border: "1px solid color-mix(in srgb, currentColor 18%, transparent)",
    background: "color-mix(in srgb, currentColor 4%, transparent)",
    fontSize: "0.8125rem",
    color: "color-mix(in srgb, currentColor 60%, transparent)",
    overflow: "hidden",
  };

  if (render.kind === "ready") {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={render.url}
        alt={`Chemical structure for SMILES ${smiles}`}
        width={width}
        height={height}
        className="dark:invert"
        style={{ borderRadius: "0.5rem" }}
      />
    );
  }

  let message = "Loading RDKit…";
  if (render.kind === "idle") message = "Enter a SMILES to render";
  else if (render.kind === "invalid") message = "Invalid SMILES";
  else if (render.kind === "error") message = "RDKit failed to load";

  return (
    <div style={frameStyle} role="img" aria-label={message}>
      {message}
    </div>
  );
}

/**
 * StructureViewer — input/select a SMILES and render its 2D structure.
 *
 * Client-only; wraps its canvas in `RdkitProvider` so the WASM module loads
 * once per page and is shared with sibling chemistry widgets.
 */
export function StructureViewerImpl({
  smiles,
  width = 320,
  height = 220,
  highlightSmarts,
  editable = true,
  className,
}: StructureViewerProps) {
  // When there's no initial SMILES, an input is always needed regardless of
  // `editable` (the contract: "When omitted, the widget shows an input.").
  const showInput = editable || !smiles;
  const [value, setValue] = useState(smiles ?? "");

  // Keep in sync if the prop changes (e.g. MDX hot reload / different example).
  useEffect(() => {
    setValue(smiles ?? "");
  }, [smiles]);

  return (
    <RdkitProvider>
      <div
        className={className}
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "0.625rem",
          margin: "1rem 0",
        }}
      >
        {showInput ? (
          <label style={{ display: "block", fontSize: "0.8125rem" }}>
            <span
              style={{
                display: "block",
                marginBottom: "0.25rem",
                fontWeight: 600,
                opacity: 0.8,
              }}
            >
              SMILES
            </span>
            <input
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="e.g. CC(=O)Oc1ccccc1C(=O)O"
              spellCheck={false}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              style={{
                width: "100%",
                maxWidth: width,
                padding: "0.4rem 0.55rem",
                borderRadius: "0.375rem",
                border:
                  "1px solid color-mix(in srgb, currentColor 25%, transparent)",
                background: "transparent",
                color: "inherit",
                fontFamily:
                  "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
                fontSize: "0.8125rem",
              }}
            />
          </label>
        ) : null}

        <StructureCanvas
          smiles={value}
          width={width}
          height={height}
          highlightSmarts={highlightSmarts}
        />
      </div>
    </RdkitProvider>
  );
}
