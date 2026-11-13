"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
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

/** "Protocol · A and B": what the dialog shows, under its title. */
export function compoundCurvesSummary(target: CompoundCurvesTarget): string {
  return `${target.protocol.name} · ${listNames(target.molecules.map((m) => m.name))}`;
}

/** A file name part: runs of anything but letters, digits, "." and "-" become one "-". */
function fileNamePart(text: string): string {
  return text
    .replace(/[^\p{L}\p{N}.-]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}

const OpenContext = createContext<((target: CompoundCurvesTarget) => void) | null>(null);

/** Opens the compound curves dialog; null outside a CompoundCurvesProvider. */
export function useOpenCompoundCurves() {
  return useContext(OpenContext);
}

/** The "Curves" control: shown only with a target and inside a provider. */
export function CompoundCurvesButton({
  target,
  className,
}: {
  target: CompoundCurvesTarget | null | undefined;
  className?: string;
}) {
  const open = useOpenCompoundCurves();
  if (!target || !open) return null;
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className={className}
      onClick={(event) => {
        // A search row or card around the control must not react too.
        event.stopPropagation();
        open(target);
      }}
    >
      Traces
    </Button>
  );
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
        <DialogTitle>Traces across runs</DialogTitle>
        <DialogDescription>
          {compoundCurvesSummary(target)}. Includes every run except rejected runs, regardless of
          this search&apos;s run scope or aggregation.
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
          exportName={`traces-${fileNamePart(target.protocol.name)}-${fileNamePart(names)}`}
          empty={
            <p className="py-8 text-center text-sm text-muted-foreground">
              No traces for {names} in runs that are not rejected.
            </p>
          }
        />
      </div>
    </DialogContent>
  );
}
