"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { CardGrid } from "@/features/research-organization/components/results/card-grid";
import type { Molecule } from "@/features/chemical-registration/types";

interface ClusterSelectionPaneProps {
  allMolecules: Molecule[];
  selectedIds: Set<string>;
}

export function ClusterSelectionPane({
  allMolecules,
  selectedIds,
}: ClusterSelectionPaneProps) {
  const router = useRouter();
  const [gridSelectedIds, setGridSelectedIds] = useState<Set<string>>(
    new Set()
  );

  const handleSelectChange = useCallback(
    (moleculeId: string, selected: boolean) => {
      setGridSelectedIds((prev) => {
        const next = new Set(prev);
        if (selected) {
          next.add(moleculeId);
        } else {
          next.delete(moleculeId);
        }
        return next;
      });
    },
    []
  );

  const handleOpen = useCallback(
    (moleculeId: string) => {
      router.push(`/compounds/${moleculeId}`);
    },
    [router]
  );

  const hasSelection = selectedIds.size > 0;
  const filtered = hasSelection
    ? allMolecules.filter((m) => selectedIds.has(m.id))
    : [];

  return (
    <div className="flex h-full flex-col">
      {!hasSelection ? (
        // No selection yet → show only the hint. Rendering the full collection
        // here would mass-mount thousands of structure thumbnails (the pane is
        // for the SELECTION, not the whole set).
        <p className="px-4 py-2 text-xs text-muted-foreground">
          Lasso a region or click Diversify to make a selection.
        </p>
      ) : (
        // min-h-0 lets this flex child shrink so CardGrid gets a DEFINITE
        // height and its virtualizer can window — otherwise it grows to fit
        // every selected card. See feedback_virtualized_list_definite_height.
        <div className="flex-1 min-h-0 overflow-auto">
          <CardGrid
            molecules={filtered}
            selectedIds={gridSelectedIds}
            onSelectChange={handleSelectChange}
            onOpen={handleOpen}
          />
        </div>
      )}
    </div>
  );
}
