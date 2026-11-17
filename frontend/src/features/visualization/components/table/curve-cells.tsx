"use client";

import { DoseResponseFigure } from "@/features/screening-assay/components/dose-response-figure";
import { Button } from "@/shared/components/ui/button";
import { ChartSpline } from "lucide-react";
import { useMemo } from "react";
import { siblingAt } from "../../lib/dataset";
import { curveSnapshotAt } from "../../lib/value-description";
import type { Dataset } from "../../types";

interface CurveCellProps {
  ds: Dataset;
  /** The dose-response value column. */
  valueKey: string;
  i: number;
  onOpen: (valueKey: string, i: number) => void;
}

/** Runs: this run's curve as a sparkline (a "Curve" button in compact rows); opens the
 * curves dialog for the compound in this run. */
export function CurveSparklineCell({
  ds,
  valueKey,
  i,
  onOpen,
  compact,
}: CurveCellProps & { compact: boolean }) {
  const curve = useMemo(() => curveSnapshotAt(ds, valueKey, i), [ds, valueKey, i]);
  if (!curve) return null;
  const name = `Curve of ${String(ds.values.compound?.[i] ?? "this compound")} in run ${String(ds.values.run?.[i] ?? "")}`;
  return (
    <div className="flex h-full items-center">
      {compact ? (
        <Button
          size="sm"
          variant="outline"
          className="h-6 px-2 text-xs"
          aria-label={name}
          onClick={() => onOpen(valueKey, i)}
        >
          <ChartSpline className="h-3.5 w-3.5" />
          Curve
        </Button>
      ) : (
        <button
          type="button"
          aria-label={name}
          className="rounded-md border bg-background hover:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => onOpen(valueKey, i)}
        >
          <DoseResponseFigure curve={curve} size="sparkline" width={140} height={92} />
        </button>
      )}
    </div>
  );
}

/** Batches and Compounds: "Curves (n)" over the runs that tested the compound. */
export function CurvesCountCell({ ds, valueKey, i, onOpen }: CurveCellProps) {
  const n = siblingAt(ds, valueKey, "n_tested", i);
  if (typeof n !== "number" || n === 0) return null;
  return (
    <div className="flex h-full items-center">
      <Button
        size="sm"
        variant="outline"
        className="h-6 px-2 text-xs"
        onClick={() => onOpen(valueKey, i)}
      >
        <ChartSpline className="h-3.5 w-3.5" />
        Curves ({n})
      </Button>
    </div>
  );
}
