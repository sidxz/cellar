"use client";

import type { ReactNode } from "react";

import { StructureRenderer } from "@/shared/components/chemistry/structure-renderer";
import { cn } from "@/shared/lib/utils";

/**
 * MoleculeThumbnail — size-presetted wrapper around StructureRenderer (B1).
 *
 * Three discrete sizes used across the screen-campaign feature so cell rows,
 * decision panels, and preview tables stay visually consistent. Falls back to
 * the supplied fallback (default: text registration id badge) when SMILES is
 * missing.
 */

export type MoleculeThumbnailSize = "sm" | "md" | "lg";

interface MoleculeThumbnailProps {
  smiles: string | null | undefined;
  size?: MoleculeThumbnailSize;
  fallback?: ReactNode;
  className?: string;
}

const DIMENSIONS: Record<MoleculeThumbnailSize, { width: number; height: number }> = {
  sm: { width: 56, height: 40 },
  md: { width: 200, height: 150 },
  lg: { width: 320, height: 240 },
};

export function MoleculeThumbnail({
  smiles,
  size = "sm",
  fallback = null,
  className,
}: MoleculeThumbnailProps) {
  const { width, height } = DIMENSIONS[size];
  if (!smiles) {
    return (
      <div
        className={cn(
          "inline-flex items-center justify-center rounded border border-dashed text-[10px] text-muted-foreground",
          className,
        )}
        style={{ width, height }}
      >
        {fallback ?? "no structure"}
      </div>
    );
  }
  return <StructureRenderer smiles={smiles} width={width} height={height} className={className} />;
}
