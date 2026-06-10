"use client";

import { StructureEditorDialog, StructureThumbnail } from "@/shared/components/chemistry";
import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/utils";
import { Pencil } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useScaffoldTree } from "../hooks/use-scaffold-tree";
import { NO_SCAFFOLD_SENTINEL } from "../types/scaffold-tree";

export interface RGroupCorePickerProps {
  /** Saved collection — server-side expansion to all members (preferred). */
  collectionId?: string;
  /** Ad-hoc explicit id list. Exactly one of {collectionId, moleculeIds} set. */
  moleculeIds?: string[];
  /** Current core. `null` triggers the on-mount auto-suggest. */
  coreSmiles: string | null;
  onCoreChange: (coreSmiles: string) => void;
  /** When both provided, renders the "N of M match this core" advisory line. */
  matchedCount?: number;
  totalCount?: number;
}

/**
 * R-group decomposition core picker.
 *
 * Enumerates candidate cores from the existing scaffold tree (ringed Murcko
 * scaffolds, the NO_SCAFFOLD bucket excluded), ranked by direct
 * `molecule_count` DESC so the dominant chemotype heads the list. On mount,
 * when no core is selected yet, the dominant candidate is auto-suggested via a
 * single `onCoreChange`. The chemist can click any other candidate or open the
 * Ketcher editor to draw/edit an arbitrary core.
 */
export function RGroupCorePicker({
  collectionId,
  moleculeIds,
  coreSmiles,
  onCoreChange,
  matchedCount,
  totalCount,
}: RGroupCorePickerProps) {
  const { tree, isStarting, isPolling } = useScaffoldTree({ collectionId, moleculeIds });
  const [editOpen, setEditOpen] = useState(false);

  const candidates = useMemo(
    () =>
      (tree?.nodes ?? [])
        .filter((n) => n.scaffold_smiles !== NO_SCAFFOLD_SENTINEL)
        .sort((a, b) => {
          if (b.molecule_count !== a.molecule_count) {
            return b.molecule_count - a.molecule_count;
          }
          return a.scaffold_smiles.localeCompare(b.scaffold_smiles);
        }),
    [tree],
  );

  // Auto-suggest the dominant scaffold once, only while no core is set.
  // biome-ignore lint/correctness/useExhaustiveDependencies: re-run only when the candidate set or the (null-ness of the) core changes; `onCoreChange` is intentionally omitted so a parent passing a fresh callback identity each render can't re-fire the suggestion.
  useEffect(() => {
    if (coreSmiles == null && candidates.length > 0) {
      onCoreChange(candidates[0].scaffold_smiles);
    }
  }, [candidates, coreSmiles]);

  if (isStarting || isPolling) {
    return <p className="text-xs text-muted-foreground">Finding scaffolds…</p>;
  }

  const showMatchLine = matchedCount != null && totalCount != null;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs uppercase tracking-wide text-muted-foreground">Core</span>

        {candidates.map((n) => {
          const isSelected = coreSmiles === n.scaffold_smiles;
          return (
            <button
              key={n.scaffold_smiles}
              type="button"
              onClick={() => onCoreChange(n.scaffold_smiles)}
              aria-pressed={isSelected}
              className={cn(
                "flex items-center gap-2 rounded-md border px-2 py-1 text-xs hover:bg-muted",
                isSelected ? "border-primary bg-primary/5 font-semibold" : "border-input",
              )}
            >
              <StructureThumbnail
                smiles={n.scaffold_smiles}
                size={44}
                className="shrink-0 rounded border bg-background"
              />
              <span className="font-mono">{n.scaffold_smiles}</span>
              <span className="tabular-nums text-muted-foreground">{n.molecule_count}</span>
            </button>
          );
        })}

        <Button
          variant="outline"
          size="sm"
          className="h-7 gap-1.5"
          onClick={() => setEditOpen(true)}
        >
          <Pencil className="h-3.5 w-3.5" />
          {coreSmiles ? "Edit core" : "Draw core"}
        </Button>
      </div>

      {showMatchLine && (
        <p className="text-xs text-amber-700">
          {matchedCount} of {totalCount} match this core
          {(matchedCount ?? 0) < (totalCount ?? 0) ? " · others shown separately, not dropped" : ""}
        </p>
      )}

      <StructureEditorDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        initialStructure={coreSmiles ?? ""}
        onApply={(structure) => {
          const trimmed = structure.trim();
          if (trimmed) onCoreChange(trimmed);
        }}
        outputFormat="smiles"
      />
    </div>
  );
}
