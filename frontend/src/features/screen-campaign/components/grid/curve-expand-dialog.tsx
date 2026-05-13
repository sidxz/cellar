"use client";

/**
 * CurveExpandDialog — click-to-expand for the campaign grid's curve cell.
 *
 * Read-only modal that renders the same dose-response figure used by every
 * other surface (protocol Activity tab, search results, run DR, sparkline).
 * Delegates the actual drawing to <DoseResponseFigure size="expand" />
 * so a closed-campaign curve looks bit-identical to its protocol-tab
 * counterpart. Modal supplies the chrome (molecule + channel label,
 * curve-class badge, IC50 / R² / Hill / Top / Bottom strip) around it.
 */

import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { CurveClassBadge } from "@/features/screening-assay/components/curve-class-badge";
import {
  DoseResponseFigure,
  type CurveSnapshot,
} from "@/features/screening-assay/components/dose-response-figure";

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
  if (!data) return null;

  const showIc50 = Number.isFinite(data.fitted_value) && data.fitted_value > 0;

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
            <CurveClassBadge
              curveClass={data.curve_class ?? null}
              renderNullAs="nothing"
              className="ml-1"
            />
          </DialogTitle>
        </DialogHeader>

        <div className="flex items-baseline gap-4 text-sm font-mono">
          {showIc50 && (
            <span>
              <span className="text-muted-foreground">IC50</span>{" "}
              {data.fitted_value.toPrecision(4)}
              {data.unit ? ` ${data.unit}` : ""}
            </span>
          )}
          {data.r_squared != null && Number.isFinite(data.r_squared) && (
            <span>
              <span className="text-muted-foreground">R²</span>{" "}
              {data.r_squared.toFixed(3)}
            </span>
          )}
          <span>
            <span className="text-muted-foreground">Hill</span>{" "}
            {data.hill_slope.toFixed(2)}
          </span>
          <span>
            <span className="text-muted-foreground">Top/Bot</span>{" "}
            {data.top.toFixed(1)} / {data.bottom.toFixed(1)}
          </span>
        </div>

        <div className="flex justify-center pt-2">
          <DoseResponseFigure curve={data} size="expand" unit={data.unit ?? null} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
