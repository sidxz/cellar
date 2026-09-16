"use client";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { Button } from "@/shared/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { useState } from "react";

import { useMcs } from "../hooks/use-mcs";

interface RegionCommonCoreProps {
  /** Molecule ids currently lassoed on the map. */
  regionIds: string[];
  /** Hand the core to the R-group workbench for this same set. */
  onUseAsCore: (coreSmiles: string, moleculeIds: string[]) => void;
}

/**
 * "What do these compounds share?" for a lassoed region of the cluster map.
 *
 * Informational, so unlike the R-group core picker this shows whatever comes
 * back — a small answer is a useful result here, not a failure. "These 40
 * share only a benzene" tells the chemist their lasso crossed cluster
 * boundaries or their Butina threshold is too loose, which is worth knowing.
 *
 * Computed on demand rather than with the lasso: dragging a selection around
 * the map would otherwise fire a request per drag.
 */
export function RegionCommonCore({ regionIds, onUseAsCore }: RegionCommonCoreProps) {
  const [open, setOpen] = useState(false);
  const { mcs, isLoading, error, outOfRange } = useMcs({
    moleculeIds: regionIds,
    enabled: open,
  });

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button size="sm" variant="outline" disabled={regionIds.length < 2}>
          Common core
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72" align="start">
        {outOfRange && (
          <p className="text-xs text-muted-foreground">
            Select between 2 and 10,000 compounds to find their common core.
          </p>
        )}
        {!outOfRange && isLoading && (
          <p className="text-xs text-muted-foreground">Finding the common core…</p>
        )}
        {!outOfRange && error && (
          <p className="text-xs text-destructive">Could not compute a common core.</p>
        )}
        {!outOfRange && !isLoading && !error && mcs && (
          <div className="flex flex-col gap-2">
            {mcs.num_atoms === 0 || !mcs.core_smiles ? (
              <p className="text-xs text-muted-foreground">
                These {mcs.molecule_count} compounds share no common substructure — the region spans
                more than one chemotype.
              </p>
            ) : (
              <>
                <div className="flex items-start gap-3">
                  <StructureThumbnail
                    smiles={mcs.core_smiles}
                    size={96}
                    className="shrink-0 rounded border bg-background"
                  />
                  <div className="flex flex-col gap-0.5 text-xs">
                    <span className="font-medium text-foreground">
                      Shared by all {mcs.molecule_count}
                    </span>
                    <span className="text-muted-foreground">
                      {mcs.num_atoms} atoms, {mcs.num_bonds} bonds
                    </span>
                    {mcs.timed_out && (
                      // A partial answer must never read as the answer: the
                      // search returned its best-so-far, so the true shared
                      // core is at least this big and probably bigger.
                      <span className="text-amber-600 dark:text-amber-500">
                        Partial — search timed out
                      </span>
                    )}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  className="w-full"
                  disabled={mcs.timed_out}
                  title={
                    mcs.timed_out
                      ? "A partial core would overstate how much the series varies"
                      : undefined
                  }
                  onClick={() => {
                    if (mcs.core_smiles) onUseAsCore(mcs.core_smiles, regionIds);
                    setOpen(false);
                  }}
                >
                  Use as R-group core
                </Button>
              </>
            )}
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
