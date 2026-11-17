"use client";

import { Button } from "@/shared/components/ui/button";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import { X } from "lucide-react";
import type { CurvePosition } from "../lib/curve-plot";
import type { MeltingStep } from "../types";
import { peakKind, stepInput } from "./melting-steps-panel";

/** What a click on a trace picked: a drawn peak of that position, or (no
 *  `stepId`) the spot clicked. */
export type PeakPick = { wellId: string; x: number; stepId: string | null };

export interface PeakPickBarProps {
  pick: PeakPick;
  position: CurvePosition;
  /** The picked peak; null when a spot is picked. */
  step: MeltingStep | null;
  /** The temperature windows on the shown signal. */
  windows: readonly { window: string; low: number; high: number }[];
  /** The x unit of the shown signal. */
  unit: string;
  /** Saying which window the peak (or one added at the spot) is the Tm of can
   *  change something: see `canUseAsTm`. Without it those choices are not shown. */
  useAsTm: boolean;
  /** Why nothing can be changed; given, the bar has no buttons. */
  refusal: string | null;
  /** Move was chosen: the next click on this position's trace gives the new temperature. */
  moving: boolean;
  /** Null leaves the peak to be named by its temperature. */
  onAssign(window: string | null): void;
  onAccept(): void;
  onReject(): void;
  onMove(): void;
  onAdd(window: string | null): void;
  onClear(): void;
}

/** The line under the plot for what was picked on it: the facts, and buttons
 *  that open the peak list's forms. It has no form and saves nothing itself. */
export function PeakPickBar({
  pick,
  position,
  step,
  windows,
  useAsTm,
  unit,
  refusal,
  moving,
  onAssign,
  onAccept,
  onReject,
  onMove,
  onAdd,
  onClear,
}: PeakPickBarProps) {
  const title = step ? "Peak picked" : "Spot picked";
  // A name that is no window on this signal counts as no assignment.
  const assigned = windows.find((w) => w.window === step?.assigned_window)?.window ?? null;
  const facts = step
    ? [
        position.position_label,
        `peak at ${formatMeasurementValue(step.value, 4)} ${unit}`,
        peakKind(step),
        assigned && `used as Tm (${assigned})`,
      ]
    : [position.position_label, `${stepInput(pick.x)} ${unit}`];
  /** `Use as Tm`, naming the window when the signal has several. */
  const named = (verb: string, w: { window: string }) =>
    windows.length > 1 ? `${verb} (${w.window})` : verb;
  /** `current` marks the choice the peak has now. */
  const choice = (label: string, onClick: () => void, current = false) => (
    <Button
      key={label}
      type="button"
      size="xs"
      variant={current ? "secondary" : "outline"}
      aria-current={current || undefined}
      onClick={onClick}
    >
      {label}
    </Button>
  );

  return (
    <section aria-label={title} className="space-y-1.5 rounded-md border p-2 text-sm">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-muted-foreground">{title}</span>
        <span>{facts.filter(Boolean).join(" · ")}</span>
        {!refusal && (
          <Button
            type="button"
            size="icon-xs"
            variant="ghost"
            className="ml-auto"
            aria-label="Clear the pick"
            title="Clear the pick (Esc)"
            onClick={onClear}
          >
            <X />
          </Button>
        )}
      </div>
      {refusal ? (
        <p className="text-xs text-muted-foreground">{refusal}</p>
      ) : step ? (
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
          {useAsTm &&
            windows.map((w) =>
              choice(named("Use as Tm", w), () => onAssign(w.window), w.window === assigned),
            )}
          {/* Undoes a choice made by hand. */}
          {useAsTm && assigned !== null && choice("By temperature range", () => onAssign(null))}
          <span className="ml-auto flex gap-x-1">
            {step.status !== "accepted" && (
              <Button type="button" size="xs" variant="ghost" onClick={onAccept}>
                Mark reviewed
              </Button>
            )}
            <Button type="button" size="xs" variant="ghost" onClick={onReject}>
              Exclude
            </Button>
            <Button
              type="button"
              size="xs"
              variant={moving ? "secondary" : "ghost"}
              aria-pressed={moving}
              onClick={onMove}
            >
              Move
            </Button>
          </span>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
          <Button type="button" size="xs" variant="outline" onClick={() => onAdd(null)}>
            Add a peak here
          </Button>
          {useAsTm &&
            windows.map((w) => choice(named("Add and use as Tm", w), () => onAdd(w.window)))}
        </div>
      )}
      {step && moving && !refusal && (
        <p className="text-xs text-muted-foreground">
          Click the new temperature on this position's trace.
        </p>
      )}
    </section>
  );
}
