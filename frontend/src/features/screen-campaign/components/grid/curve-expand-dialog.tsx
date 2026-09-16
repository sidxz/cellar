"use client";

/**
 * CurveExpandDialog — click-to-expand for the campaign grid's curve cell.
 *
 * Renders the suite's shared read-only chart (`DoseResponseChartView`), the
 * same renderer the run page and search use, so a campaign curve is pixel-
 * identical to its protocol-tab counterpart. The chart's summary card supplies
 * the intercept label, CI strip, secondary intercept chips and fit-quality
 * badges; this file supplies the dialog chrome.
 *
 * The frozen `curve_snapshot` JSONB goes in as it is — the chart reads both
 * wire shapes, so there is no adapter and no placeholder UUIDs. Pre-2026-05-14
 * snapshots without curve_type / intercept_values / CI / warnings still render;
 * the chart degrades to the legacy label.
 */

import type { CurveSnapshot } from "@/features/screening-assay/components/dose-response-figure";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/shared/components/ui/dialog";
import { Plot } from "@/shared/lib/plotly";
import { type CurveLike, DoseResponseChartView } from "@structflo/components/dose-response";
import { useMemo } from "react";

export interface ExpandedCurve extends CurveSnapshot {
  unit?: string | null;
  /** Header context — molecule registration number and channel label. */
  moleculeLabel: string;
  channelLabel: string;
}

interface Props {
  data: ExpandedCurve | null;
  onOpenChange: (open: boolean) => void;
}

export function CurveExpandDialog({ data, onOpenChange }: Props) {
  const curves = useMemo<CurveLike[]>(() => {
    if (!data) return [];
    // The snapshot is already a CurveLike; it only lacks the display label and
    // the unit, which the campaign holds on the measurement.
    return [{ ...data, label: data.moleculeLabel, fitted_unit: data.unit ?? "" }];
  }, [data]);

  if (!data) return null;

  return (
    <Dialog open onOpenChange={onOpenChange}>
      {/* The summary card sits below the plot, so the dialog has to scroll —
          without a height cap it rendered past the bottom of the viewport. */}
      <DialogContent className="sm:max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span>{data.moleculeLabel}</span>
            <span className="text-muted-foreground">·</span>
            <span className="text-muted-foreground font-normal">{data.channelLabel}</span>
          </DialogTitle>
        </DialogHeader>
        <DoseResponseChartView curves={curves} plot={Plot} />
      </DialogContent>
    </Dialog>
  );
}
