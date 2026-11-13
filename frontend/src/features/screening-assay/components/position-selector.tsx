"use client";

import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/utils";
import { type ReactNode, useMemo } from "react";
import { type SelectionState, applyClick, holderOrder } from "../lib/curve-selection";
import { rowLabel } from "../lib/plate-dimensions";
import { type RunCurves, WELL_TYPE_LABELS } from "../types";

type Position = RunCurves["positions"][number];

const ROLE_MARKS: Record<string, string> = { reference: "R", blank: "B" };

interface PositionSelectorProps {
  holder: RunCurves["holder"];
  positions: RunCurves["positions"];
  selection: SelectionState;
  /** Every position of every group, so a shift range can cross groups. */
  orderedIds: readonly string[];
  /** Filtered out: dimmed, cannot be clicked. */
  disabledIds?: ReadonlySet<string>;
  /** Above the selector, for example the run's heading. */
  heading?: ReactNode;
  onChange: (next: SelectionState) => void;
  focusedId: string | null;
  onFocus: (id: string | null) => void;
  /** A selected position's curve colour, shown on its slot. */
  colourOf?: (id: string) => string;
}

/** The holder drawn slot by slot: a cassette as one line, a plate as rows by
 *  columns. A slot with no position is drawn and cannot be selected. Each used
 *  slot prints the API's position label. */
export function PositionSelector({
  holder,
  positions,
  selection,
  orderedIds,
  disabledIds,
  heading,
  onChange,
  focusedId,
  onFocus,
  colourOf,
}: PositionSelectorProps) {
  const groupIds = useMemo(() => holderOrder(positions).map((p) => p.well_id), [positions]);
  // A shift range skips what the filter hides.
  const clickableIds = useMemo(
    () => (disabledIds ? orderedIds.filter((id) => !disabledIds.has(id)) : orderedIds),
    [orderedIds, disabledIds],
  );
  const selectedHere = groupIds.filter((id) => selection.selected.has(id)).length;
  // All adds this group's selectable positions; None removes this group's.
  const selectGroup = () =>
    onChange({
      selected: new Set([...selection.selected, ...groupIds.filter((id) => !disabledIds?.has(id))]),
      anchor: null,
    });
  const clearGroup = () => {
    const ids = new Set(groupIds);
    onChange({
      selected: new Set([...selection.selected].filter((id) => !ids.has(id))),
      anchor: null,
    });
  };
  const isCassette = holder.kind === "cassette";
  const columns = holder.columns ?? Math.max(0, ...positions.map((p) => p.column));
  const rows = isCassette ? 1 : (holder.rows ?? 1);

  const at = useMemo(() => {
    const m = new Map<string, Position>();
    // A cassette is one line: its positions are placed by column alone.
    for (const p of positions) m.set(isCassette ? `${p.column}` : `${p.row}:${p.column}`, p);
    return m;
  }, [positions, isCassette]);

  const slot = (p: Position | undefined, key: string, columnNumber: number) => {
    if (!p) {
      return (
        <span
          key={key}
          data-testid="empty-slot"
          aria-hidden
          className={cn(
            "flex shrink-0 items-center justify-center border border-dashed font-mono text-muted-foreground opacity-60",
            isCassette ? "h-12 w-10 rounded-md text-xs" : "size-8 rounded-full",
          )}
        >
          {isCassette ? columnNumber : null}
        </span>
      );
    }
    const id = p.well_id;
    const on = selection.selected.has(id);
    const disabled = disabledIds?.has(id) ?? false;
    const focused = focusedId === id;
    const colour = on || focused ? colourOf?.(id) : undefined;
    const mark = ROLE_MARKS[p.well_type];
    return (
      <button
        key={key}
        type="button"
        aria-pressed={on}
        disabled={disabled}
        data-focused={focused || undefined}
        title={p.label ? `${p.position_label} · ${p.label}` : p.position_label}
        onClick={(e) =>
          onChange(
            applyClick(selection, clickableIds, id, {
              shift: e.shiftKey,
              toggle: e.metaKey || e.ctrlKey,
            }),
          )
        }
        onMouseEnter={() => onFocus(id)}
        onMouseLeave={() => onFocus(null)}
        onFocus={() => onFocus(id)}
        onBlur={() => onFocus(null)}
        style={focused ? { boxShadow: `0 0 0 2px ${colour ?? "currentColor"}` } : undefined}
        className={cn(
          "relative flex shrink-0 cursor-pointer flex-col items-center justify-center gap-1 border bg-muted/40 font-mono text-muted-foreground transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring",
          isCassette
            ? "h-12 min-w-10 rounded-md px-2 text-xs"
            : "size-8 rounded-full text-[10px] leading-none",
          on && "border-primary bg-primary/10 text-foreground",
          disabled && "cursor-not-allowed opacity-40 hover:bg-muted/40",
        )}
      >
        <span>{p.position_label}</span>
        {isCassette && (
          <span
            aria-hidden
            className="h-1 w-4 rounded-sm bg-border"
            style={on && colour ? { background: colour } : undefined}
          />
        )}
        {mark && (
          <span
            aria-hidden
            title={WELL_TYPE_LABELS[p.well_type as keyof typeof WELL_TYPE_LABELS]}
            className={cn(
              "absolute font-mono text-[9px] leading-none",
              isCassette ? "top-0.5 right-1" : "-top-0.5 -right-0.5",
              p.well_type === "reference" ? "text-primary" : "text-muted-foreground",
            )}
          >
            {mark}
          </span>
        )}
      </button>
    );
  };

  return (
    <div className="space-y-2">
      {heading && <div className="text-sm">{heading}</div>}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h3 className="text-sm font-medium">
          {selectedHere} of {groupIds.length} selected
        </h3>
        <Button type="button" variant="ghost" size="sm" onClick={selectGroup}>
          All
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={clearGroup}>
          None
        </Button>
        <span className="text-xs text-muted-foreground">
          Click one · <kbd className="rounded border px-1 font-mono text-[11px]">Shift</kbd> click a
          range · <kbd className="rounded border px-1 font-mono text-[11px]">Ctrl</kbd>/
          <kbd className="rounded border px-1 font-mono text-[11px]">⌘</kbd> click to add or remove
        </span>
      </div>
      <div className={cn("space-y-1", !isCassette && "overflow-x-auto pb-1")}>
        {!isCassette && (
          <div aria-hidden className="flex gap-1 font-mono text-[10px] text-muted-foreground">
            <span className="w-5 shrink-0" />
            {Array.from({ length: columns }, (_, ci) => (
              <span key={ci} className="w-8 shrink-0 text-center">
                {ci + 1}
              </span>
            ))}
          </div>
        )}
        {Array.from({ length: rows }, (_, ri) => (
          <div
            key={ri}
            data-testid="holder-row"
            className={cn("flex gap-1", isCassette && "flex-wrap")}
          >
            {!isCassette && (
              <span
                aria-hidden
                className="flex w-5 shrink-0 items-center font-mono text-[10px] text-muted-foreground"
              >
                {rowLabel(ri)}
              </span>
            )}
            {Array.from({ length: columns }, (_, ci) =>
              slot(
                at.get(isCassette ? `${ci + 1}` : `${rowLabel(ri)}:${ci + 1}`),
                `${ri}:${ci}`,
                ci + 1,
              ),
            )}
          </div>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">R = reference, B = blank.</p>
    </div>
  );
}
