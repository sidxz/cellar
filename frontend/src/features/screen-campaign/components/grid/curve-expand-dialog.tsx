"use client";

/**
 * CurveExpandDialog — click-to-expand for the campaign grid's curve cell.
 *
 * Read-only dialog that renders via the same `<DoseResponseChart
 * isInteractive={false}>` that protocol-runs and search use, so a
 * closed-campaign curve looks bit-identical to its protocol-tab
 * counterpart. The chart's SummaryCard already supplies the molecule /
 * intercept label, CI strip, secondary intercept chips, and
 * fit-quality badges — this file just supplies the dialog chrome.
 *
 * The campaign measurement carries a frozen `curve_snapshot` JSONB; the
 * `snapshotToDoseResponseCurve` adapter widens it to the chart's
 * expected `DoseResponseCurve` shape (with placeholder UUIDs for the
 * FK fields the chart never reads). Pre-2026-05-14 snapshots that
 * don't carry curve_type / intercept_values / CI / warnings still
 * render — the chart degrades gracefully (no chip strip, no CI strip,
 * legacy curve_type label).
 */

import { useMemo } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { DoseResponseChart } from "@/features/screening-assay/components/dose-response-chart";
import type { CurveSnapshot } from "@/features/screening-assay/components/dose-response-figure";
import { snapshotToDoseResponseCurve } from "../../lib/snapshot-adapter";

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
  const adapted = useMemo(() => {
    if (!data) return null;
    return snapshotToDoseResponseCurve(data, {
      moleculeLabel: data.moleculeLabel,
      channelLabel: data.channelLabel,
      unit: data.unit ?? null,
    });
  }, [data]);

  if (!data || !adapted) return null;

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span>{data.moleculeLabel}</span>
            <span className="text-muted-foreground">·</span>
            <span className="text-muted-foreground font-normal">
              {data.channelLabel}
            </span>
          </DialogTitle>
        </DialogHeader>
        <DoseResponseChart curves={[adapted]} isInteractive={false} />
      </DialogContent>
    </Dialog>
  );
}
