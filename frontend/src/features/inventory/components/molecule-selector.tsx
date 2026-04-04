"use client";

import { useMolecules } from "@/features/chemical-registration/hooks/use-molecules";
import type { Molecule } from "@/features/chemical-registration/types";

interface MoleculeSelectorProps {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

export function MoleculeSelector({
  selectedId,
  onSelect,
}: MoleculeSelectorProps) {
  const { data: molecules, isLoading } = useMolecules();

  return (
    <select
      className="h-9 min-w-[240px] rounded-md border border-input bg-background px-3 text-sm"
      value={selectedId ?? ""}
      onChange={(e) => onSelect(e.target.value || null)}
      disabled={isLoading}
    >
      <option value="">
        {isLoading ? "Loading compounds..." : "Select compound..."}
      </option>
      {molecules?.map((mol: Molecule) => (
        <option key={mol.id} value={mol.id}>
          {mol.registration_number} — {mol.name}
        </option>
      ))}
    </select>
  );
}
