"use client";

import { useBatchesByMolecule } from "../hooks/use-batches";
import type { Batch } from "../types";

interface BatchSelectorProps {
  moleculeId: string;
  selectedId: string | null;
  /** The chosen batch comes second, so a caller can keep its number. */
  onSelect: (id: string | null, batch?: Batch) => void;
}

export function BatchSelector({ moleculeId, selectedId, onSelect }: BatchSelectorProps) {
  const { data: batches, isLoading } = useBatchesByMolecule(moleculeId);

  return (
    <select
      className="h-9 min-w-[180px] rounded-md border border-input bg-background px-3 text-sm"
      value={selectedId ?? ""}
      onChange={(e) => {
        const id = e.target.value || null;
        onSelect(
          id,
          batches?.find((b: Batch) => b.id === id),
        );
      }}
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
