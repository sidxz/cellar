"use client";

import { getRDKit } from "@/shared/lib/rdkit/rdkit-loader";
import { cn } from "@/shared/lib/utils";
import { memo, useEffect, useState } from "react";

interface StructureThumbnailProps {
  /** SMILES or CXSMILES string */
  smiles: string;
  /** Size in pixels (square) */
  size?: number;
  /** Height in pixels of a box that is not square; `size` is then its width. */
  height?: number;
  /** Additional CSS class */
  className?: string;
  /** Query to highlight; SMILES queries must be parsed as molecules to perceive aromaticity. */
  highlightQuery?: string;
  queryKind?: "smiles" | "smarts";
}

/**
 * Small inline structure thumbnail for table cells.
 *
 * Uses SVG blob URLs to render. Memoized to avoid re-renders in lists.
 * SVG is produced by the trusted RDKit.js WASM library.
 */
function StructureThumbnailInner({
  smiles,
  size = 48,
  height = size,
  className,
  highlightQuery,
  queryKind = "smarts",
}: StructureThumbnailProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    setBlobUrl(null);
    let cancelled = false;
    let url: string | null = null;

    (async () => {
      try {
        const rdkit = await getRDKit();
        if (cancelled) return;

        const mol = rdkit.get_mol(smiles);
        if (!mol || !mol.is_valid()) {
          mol?.delete();
          return;
        }

        // Render at 2x for HiDPI crispness, display at CSS size
        const drawOpts: Record<string, unknown> = {
          width: size * 2,
          height: height * 2,
          bondLineWidth: 2.0,
          minFontSize: 14,
          addAtomIndices: false,
          clearBackground: false, // transparent — the app background shows through
        };
        let svgStr: string;
        try {
          if (highlightQuery) {
            // A generalized server match can have no literal match in the
            // browser. In that case render the structure without highlights.
            try {
              const query =
                queryKind === "smiles"
                  ? rdkit.get_mol(highlightQuery)
                  : rdkit.get_qmol(highlightQuery);
              try {
                if (query?.is_valid())
                  Object.assign(drawOpts, JSON.parse(mol.get_substruct_match(query)));
              } finally {
                query?.delete();
              }
            } catch {
              // An unsupported query must not hide an otherwise valid molecule.
            }
          }
          svgStr = mol.get_svg_with_highlights(JSON.stringify(drawOpts));
        } finally {
          mol.delete();
        }

        if (!cancelled) {
          const blob = new Blob([svgStr], { type: "image/svg+xml" });
          url = URL.createObjectURL(blob);
          setBlobUrl(url);
        }
      } catch {
        // Silently fail for thumbnails
      }
    })();

    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [smiles, size, height, highlightQuery, queryKind]);

  if (!blobUrl) {
    return <div className={cn("rounded bg-muted", className)} style={{ width: size, height }} />;
  }

  return (
    <img
      src={blobUrl}
      alt="Structure"
      width={size}
      height={height}
      className={cn("dark:invert", className)}
    />
  );
}

export const StructureThumbnail = memo(StructureThumbnailInner);
