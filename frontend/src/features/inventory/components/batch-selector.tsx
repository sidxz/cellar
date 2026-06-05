"use client";

import { useBatchesByMolecule } from "../hooks/use-batches";
import type { Batch } from "../types";

interface BatchSelectorProps {
  moleculeId: string;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

export function BatchSelector({ moleculeId, selectedId, onSelect }: BatchSelectorProps) {
  const { data: batches, isLoading } = useBatchesByMolecule(moleculeId);

  return (
    <select
      className="h-9 min-w-[180px] rounded-md border border-input bg-background px-3 text-sm"
      value={selectedId ?? ""}
      onChange={(e) => onSelect(e.target.value || null)}
      disabled={isLoading}
    >
      <option value="">{isLoading ? "Loading batches..." : "Select batch..."}</option>
      {batches?.map((b: Batch) => (
        <option key={b.id} value={b.id}>
          {b.batch_number}
        </option>
      ))}
    </select>
  );
}
