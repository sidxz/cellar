"use client";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { cn } from "@/shared/lib/utils";

import type { McsResult } from "../hooks/use-mcs";

interface McsCoreChipProps {
  mcs: McsResult;
  isSelected: boolean;
  onSelect: (coreSmiles: string) => void;
}

/**
 * The maximum common substructure, offered as a core candidate.
 *
 * Deliberately reads differently from the scaffold chips beside it, because it
 * promises something different. A scaffold chip's "18/23" means eighteen
 * compounds *contain* that scaffold — decompose against it and five fall out
 * of the table. The MCS is shared by every compound by construction, so
 * nothing falls out; that guarantee is the label, not a look-alike fraction.
 *
 * A timed-out MCS never reaches this component (see `isUsableCore`): the
 * search returned its best-so-far, which is smaller than the true answer, and
 * a partial core would silently produce more R-group variation than the series
 * really has.
 *
 * Drawn larger than the scaffold chips beside it, and captioned with its atom
 * count, because this is the candidate that needs judging. An MCS has more
 * atoms than a Murcko scaffold by construction, so at the scaffold chips' size
 * RDKit scales it down until it cannot be read — and "is this a real backbone
 * or just a benzene?" is exactly the question the chemist answers by looking.
 * The atom count answers it without squinting.
 */
export function McsCoreChip({ mcs, isSelected, onSelect }: McsCoreChipProps) {
  // isUsableCore guarantees this at the call site; narrow for the type.
  const coreSmiles = mcs.core_smiles;
  if (!coreSmiles) return null;

  return (
    <button
      type="button"
      onClick={() => onSelect(coreSmiles)}
      aria-pressed={isSelected}
      aria-label={`Select the shared substructure as the core — ${mcs.num_atoms} atoms, shared by all ${mcs.molecule_count} compounds`}
      title={
        `The largest substructure all ${mcs.molecule_count} compounds share ` +
        `(${mcs.num_atoms} atoms).\nDecomposing against it keeps every compound ` +
        `in the table.\n${coreSmiles}`
      }
      className={cn(
        "flex flex-col items-center gap-1 rounded-md border p-1.5 hover:bg-muted",
        isSelected ? "border-primary bg-primary/5" : "border-primary/40 bg-primary/[0.03]",
      )}
    >
      <span className="text-[10px] font-medium uppercase tracking-wide text-primary">Shared</span>
      <StructureThumbnail smiles={coreSmiles} size={96} className="rounded border bg-background" />
      <span
        className={cn(
          "tabular-nums text-[11px]",
          isSelected ? "font-semibold text-foreground" : "text-muted-foreground",
        )}
      >
        all {mcs.molecule_count}
      </span>
      <span className="tabular-nums text-[10px] text-muted-foreground">{mcs.num_atoms} atoms</span>
    </button>
  );
}
