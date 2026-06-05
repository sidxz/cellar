"use client";

import { getRDKit } from "@/shared/lib/rdkit/rdkit-loader";
import { memo, useEffect, useState } from "react";

interface StructureThumbnailProps {
  /** SMILES or CXSMILES string */
  smiles: string;
  /** Size in pixels (square) */
  size?: number;
  /** Additional CSS class */
  className?: string;
}

/**
 * Small inline structure thumbnail for table cells.
 *
 * Uses SVG blob URLs to render. Memoized to avoid re-renders in lists.
 * SVG is produced by the trusted RDKit.js WASM library.
 */
function StructureThumbnailInner({ smiles, size = 48, className }: StructureThumbnailProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
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
        const renderSize = size * 2;
        const drawOpts = JSON.stringify({
          width: renderSize,
          height: renderSize,
          bondLineWidth: 2.0,
          minFontSize: 14,
          addAtomIndices: false,
        });
        const svgStr = mol.get_svg_with_highlights(drawOpts);
        mol.delete();

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [smiles, size]);

  if (!blobUrl) {
    return (
      <div
        className={`rounded bg-muted ${className ?? ""}`}
        style={{ width: size, height: size }}
      />
    );
  }

  return (
    <img
      src={blobUrl}
      alt="Structure"
      width={size}
      height={size}
      className={`dark:invert ${className ?? ""}`}
    />
  );
}

export const StructureThumbnail = memo(StructureThumbnailInner);
