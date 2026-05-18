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

  const filtered =
    selectedIds.size > 0
      ? allMolecules.filter((m) => selectedIds.has(m.id))
      : allMolecules;

  return (
    <div className="flex h-full flex-col">
      {selectedIds.size === 0 && (
        <p className="px-4 py-2 text-xs text-muted-foreground">
          Lasso a region or click Diversify to make a selection.
        </p>
      )}
      <div className="flex-1 overflow-auto">
        <CardGrid
          molecules={filtered}
          selectedIds={gridSelectedIds}
          onSelectChange={handleSelectChange}
          onOpen={handleOpen}
        />
      </div>
    </div>
  );
}
