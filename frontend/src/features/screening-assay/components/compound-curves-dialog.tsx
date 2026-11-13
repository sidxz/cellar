"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { shortId } from "@/shared/lib/utils";
import { type ReactNode, createContext, useContext, useState } from "react";
import { MultiRunCurves } from "./multi-run-curves";

const HIDDEN_STATUSES = ["rejected"] as const;

export interface CompoundCurvesTarget {
  protocol: { id: string; name: string };
  molecules: { id: string; name: string }[];
}

/** "A", "A and B", "A, B and C". */
function listNames(names: readonly string[]): string {
  if (names.length < 2) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;
}

export function compoundCurvesTitle(target: CompoundCurvesTarget): string {
  const names = listNames(target.molecules.map((m) => m.name));
  return `All runs of ${target.protocol.name} with curves for ${names}`;
}

const OpenContext = createContext<((target: CompoundCurvesTarget) => void) | null>(null);

/** Opens the compound curves dialog; null outside a CompoundCurvesProvider. */
export function useOpenCompoundCurves() {
  return useContext(OpenContext);
}

/** Holds the open target and renders the one compound curves dialog. */
export function CompoundCurvesProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<CompoundCurvesTarget | null>(null);
  return (
    <OpenContext.Provider value={setTarget}>
      {children}
      <Dialog open={target !== null} onOpenChange={(open) => !open && setTarget(null)}>
        {target && <CompoundCurvesContent target={target} />}
      </Dialog>
    </OpenContext.Provider>
  );
}

function CompoundCurvesContent({ target }: { target: CompoundCurvesTarget }) {
  const moleculeIds = target.molecules.map((m) => m.id);
  const names = listNames(target.molecules.map((m) => m.name));
  return (
    <DialogContent className="flex max-h-[90vh] w-[min(95vw,1280px)] max-w-[1280px] flex-col overflow-hidden sm:max-w-[1280px]">
      <DialogHeader>
        <DialogTitle>{compoundCurvesTitle(target)}</DialogTitle>
        <DialogDescription>
          A live view of every run with curves, except rejected runs. It can include runs that this
          search&apos;s run scope and aggregation rule did not count.
        </DialogDescription>
      </DialogHeader>
      <div className="flex min-h-0 min-w-0 flex-col overflow-y-auto">
        <MultiRunCurves
          protocolId={target.protocol.id}
          filter={{ moleculeIds }}
          hideStatuses={HIDDEN_STATUSES}
          initial={{
            select: "compounds",
            showReferences: true,
            colour: {
              mode: "group",
              groupBy: target.molecules.length === 1 ? "batch" : "compound",
            },
          }}
          exportName={`compound-curves-${shortId(target.protocol.id)}`}
          empty={
            <p className="py-8 text-center text-sm text-muted-foreground">
              No curves for {names} in runs that are not rejected.
            </p>
          }
        />
      </div>
    </DialogContent>
  );
}
