"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { CardGrid } from "@/features/research-organization/components/results/card-grid";
import type { Molecule } from "@/features/chemical-registration/types";

interface ClusterSelectionPaneProps {
  allMolecules: Molecule[];
  /** The cherry-pick basket — the durable set the chemist is building. */
  basketIds: Set<string>;
}

export function ClusterSelectionPane({
  allMolecules,
  basketIds,
}: ClusterSelectionPaneProps) {
  const router = useRouter();
  const [gridSelectedIds, setGridSelectedIds] = useState<Set<string>>(
    new Set(),
  );

  const handleSelectChange = useCallback(
    (moleculeId: string, selected: boolean) => {
      setGridSelectedIds((prev) => {
        const next = new Set(prev);
        if (selected) next.add(moleculeId);
        else next.delete(moleculeId);
        return next;
      });
    },
    [],
  );

  const handleOpen = useCallback(
    (moleculeId: string) => router.push(`/compounds/${moleculeId}`),
    [router],
  );

  const hasBasket = basketIds.size > 0;
  const filtered = hasBasket
    ? allMolecules.filter((m) => basketIds.has(m.id))
    : [];

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-4 py-2 text-xs font-medium text-foreground">
        Basket ({basketIds.size})
      </div>
      {!hasBasket ? (
        <p className="px-4 py-2 text-xs text-muted-foreground">
          Your cherry-pick basket is empty. Lasso a region and add diverse picks,
          or seed it from the Diversify representatives.
        </p>
      ) : (
        // min-h-0 lets this flex child shrink so CardGrid gets a DEFINITE
        // height and its virtualizer can window — otherwise it grows to fit
        // every card. See feedback_virtualized_list_definite_height.
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
