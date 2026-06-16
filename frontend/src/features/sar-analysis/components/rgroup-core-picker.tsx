"use client";

import { StructureEditorDialog, StructureThumbnail } from "@/shared/components/chemistry";
import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/utils";
import { Pencil } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useScaffoldTree } from "../hooks/use-scaffold-tree";
import {
  type CoreCandidate,
  DEFAULT_COVERAGE_FLOOR,
  buildCoreCandidates,
  pickDefaultCore,
} from "../lib/sar-core-candidates";

export interface RGroupCorePickerProps {
  /** Saved collection — server-side expansion to all members (preferred). */
  collectionId?: string;
  /** Ad-hoc explicit id list. Exactly one of {collectionId, moleculeIds} set. */
  moleculeIds?: string[];
  /** Current core. `null` triggers the on-mount auto-suggest. */
  coreSmiles: string | null;
  onCoreChange: (coreSmiles: string) => void;
}

/** Max candidate chips shown before the "+N more" expander. */
const MAX_VISIBLE = 8;

/**
 * R-group decomposition core picker.
 *
 * Enumerates candidate cores from the scaffold tree ranked by COVERAGE — how
 * many molecules *contain* the scaffold (its subtree mol-id union), not how many
 * have it as their exact Murcko scaffold. This surfaces generic frameworks with
 * their real coverage and filters out the unusable 0-/singleton-coverage tail
 * (see {@link buildCoreCandidates}). Each candidate renders as a structure tile
 * with a coverage badge; the SMILES is demoted to the hover tooltip.
 *
 * On mount, while no core is selected, the most-specific broadly-shared core is
 * auto-suggested ({@link pickDefaultCore}). When no scaffold clears the coverage
 * floor — a diverse, non-congeneric set — no core is suggested and the chemist
 * is guided to draw one instead of being shown a wall of singletons.
 */
export function RGroupCorePicker({
  collectionId,
  moleculeIds,
  coreSmiles,
  onCoreChange,
}: RGroupCorePickerProps) {
  const { tree, isStarting, isPolling, error } = useScaffoldTree({ collectionId, moleculeIds });
  const [editOpen, setEditOpen] = useState(false);
  const [showAll, setShowAll] = useState(false);

  // Compute coverage for every ring scaffold once (floor 1), then derive the
  // usable candidate set + the best-available coverage for the empty-state copy.
  const { candidates, total, bestCoverage } = useMemo(() => {
    if (!tree) return { candidates: [] as CoreCandidate[], total: 0, bestCoverage: 0 };
    const all = buildCoreCandidates(tree, { floor: 1 });
    return {
      candidates: all.candidates.filter((c) => c.coverage >= DEFAULT_COVERAGE_FLOOR),
      total: all.total,
      bestCoverage: all.candidates[0]?.coverage ?? 0,
    };
  }, [tree]);

  // Auto-suggest the default core once, only while no core is set. When there
  // are no candidates (diverse set) nothing is suggested → guidance shows.
  // biome-ignore lint/correctness/useExhaustiveDependencies: re-run only when the candidate set or the (null-ness of the) core changes; `onCoreChange` is intentionally omitted so a parent passing a fresh callback identity each render can't re-fire the suggestion.
  useEffect(() => {
    if (coreSmiles == null && candidates.length > 0) {
      const next = pickDefaultCore(candidates);
      if (next) onCoreChange(next);
    }
  }, [candidates, coreSmiles]);

  // Cap the chip list, but always keep the selected core visible.
  const visible = useMemo(() => {
    if (showAll || candidates.length <= MAX_VISIBLE) return candidates;
    const head = candidates.slice(0, MAX_VISIBLE);
    if (coreSmiles && !head.some((c) => c.scaffoldSmiles === coreSmiles)) {
      const selected = candidates.find((c) => c.scaffoldSmiles === coreSmiles);
      if (selected) return [...head, selected];
    }
    return head;
  }, [candidates, showAll, coreSmiles]);
  const hiddenCount = candidates.length - visible.length;

  if (isStarting || isPolling) {
    return <p className="text-xs text-muted-foreground">Finding scaffolds…</p>;
  }

  if (error) {
    return <p className="text-xs text-destructive">Could not load scaffold candidates.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-xs uppercase tracking-wide text-muted-foreground">Core</span>
        <Button
          variant="outline"
          size="sm"
          className="ml-auto h-7 gap-1.5"
          onClick={() => setEditOpen(true)}
        >
          <Pencil className="h-3.5 w-3.5" />
          {coreSmiles ? "Edit core" : "Draw core"}
        </Button>
      </div>

      {candidates.length > 0 && (
        <div className="flex flex-wrap items-start gap-2">
          {visible.map((c) => {
            const isSelected = coreSmiles === c.scaffoldSmiles;
            return (
              <button
                key={c.scaffoldSmiles}
                type="button"
                onClick={() => onCoreChange(c.scaffoldSmiles)}
                aria-pressed={isSelected}
                aria-label={`Select core ${c.scaffoldSmiles} — covers ${c.coverage} of ${total} compounds`}
                title={`${c.coverage} of ${total} compounds contain this scaffold\n${c.scaffoldSmiles}`}
                className={cn(
                  "flex flex-col items-center gap-1 rounded-md border p-1.5 hover:bg-muted",
                  isSelected ? "border-primary bg-primary/5" : "border-input",
                )}
              >
                <StructureThumbnail
                  smiles={c.scaffoldSmiles}
                  size={56}
                  className="rounded border bg-background"
                />
                <span
                  className={cn(
                    "tabular-nums text-[11px]",
                    isSelected ? "font-semibold text-foreground" : "text-muted-foreground",
                  )}
                >
                  {c.coverage}/{total}
                </span>
              </button>
            );
          })}

          {hiddenCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 self-center"
              onClick={() => setShowAll(true)}
            >
              +{hiddenCount} more
            </Button>
          )}
        </div>
      )}

      {candidates.length === 0 && (
        <div className="rounded-md border border-dashed border-amber-300 bg-amber-50/50 p-3 text-xs dark:border-amber-800 dark:bg-amber-950/30">
          <p className="font-medium text-amber-900 dark:text-amber-100">
            No shared scaffold across these compounds.
          </p>
          <p className="mt-1 text-amber-800 dark:text-amber-200">
            {bestCoverage > 0 && total > 0
              ? `The best common scaffold covers only ${bestCoverage} of ${total} compounds. `
              : ""}
            SAR works best on a focused analog series — use{" "}
            <span className="font-medium">Draw core</span> to decompose against a core you choose.
          </p>
        </div>
      )}

      <StructureEditorDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        initialStructure={coreSmiles ?? ""}
        onApply={(structure, _format) => {
          const trimmed = structure.trim();
          if (trimmed) onCoreChange(trimmed);
        }}
        outputFormat="smiles"
      />
    </div>
  );
}
