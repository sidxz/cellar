"use client";

import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Skeleton } from "@/shared/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { MEASURED_CURVE_COLORS } from "@/shared/lib/chart-colors";
import { Plot, getPlotlyGlobal } from "@/shared/lib/plotly";
import { cn } from "@/shared/lib/utils";
import { useTheme } from "next-themes";
import { useCallback, useMemo, useState } from "react";
import { flushSync } from "react-dom";
import { type CurveView, useRunCurves } from "../hooks/use-run-curves";
import {
  type ColourMode,
  type CurveColouring,
  type CurvePalette,
  buildCurveFigure,
  currentChannel,
  curveStyle,
  focusIdFromHover,
  positionName,
  reportedColumns,
  tableRows,
} from "../lib/curve-plot";
import {
  COLOUR_SLOT_COUNT,
  EMPTY_SELECTION,
  type SelectionState,
  assignColourSlots,
  holderOrder,
} from "../lib/curve-selection";
import { DOSE_UNIT_LABELS, type DoseUnit } from "../types";
import { PositionSelector } from "./position-selector";

const PLOT_CONFIG = { displaylogo: false, responsive: true };
const PLOT_STYLE = { width: "100%", height: 400 };
const PLOT_HEIGHT = "h-[400px]";

interface SegmentOption<T extends string> {
  value: T;
  label: string;
  disabled?: boolean;
}

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: SegmentOption<T>[];
  onChange: (value: T) => void;
}) {
  return (
    <Tabs value={value} onValueChange={(v) => onChange(v as T)}>
      <TabsList aria-label={label}>
        {options.map((o) => (
          <TabsTrigger key={o.value} value={o.value} disabled={o.disabled} className="text-xs">
            {o.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

function Swatch({ colour, line = false }: { colour: string; line?: boolean }) {
  return line ? (
    <i
      aria-hidden
      className="mr-1.5 inline-block w-[18px] border-t-2 align-middle"
      style={{ borderColor: colour }}
    />
  ) : (
    <span
      aria-hidden
      className="mr-1.5 inline-block size-2.5 rounded-xs align-[-1px]"
      style={{ background: colour }}
    />
  );
}

function formatValue(v: number | undefined): string {
  return v === undefined ? "" : v.toFixed(2);
}

/** The Curves tab: pick positions, overlay their curves for one signal with
 *  the instrument's reported values as lines, read a table of them, export
 *  the figure. */
export function RunCurvesPanel({ runId }: { runId: string }) {
  const [channel, setChannel] = useState<string | undefined>();
  const [view, setView] = useState<CurveView>("measured");
  // The committed window; undefined lets the API choose. The draft is what is
  // being typed, sent only on blur or Enter.
  const [derivativeWindow, setDerivativeWindow] = useState<number | undefined>();
  const [windowDraft, setWindowDraft] = useState<string | null>(null);
  const { data, isLoading, isPlaceholderData, error } = useRunCurves(runId, {
    channel,
    view,
    window: view === "derivative" ? derivativeWindow : undefined,
  });

  const [selection, setSelection] = useState<SelectionState>(EMPTY_SELECTION);
  const [slots, setSlots] = useState<ReadonlyMap<string, number>>(() => new Map());
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const [showReported, setShowReported] = useState(true);
  const [colourMode, setColourMode] = useState<ColourMode>("highlight");
  const { resolvedTheme } = useTheme();
  const palette: CurvePalette = resolvedTheme === "light" ? "light" : "dark";

  const ordered = useMemo(() => holderOrder(data?.positions ?? []), [data?.positions]);
  const byId = useMemo(() => new Map(ordered.map((p) => [p.well_id, p])), [ordered]);

  const changeSelection = (next: SelectionState) => {
    setSelection(next);
    const selectedIds = ordered.filter((p) => next.selected.has(p.well_id)).map((p) => p.well_id);
    setSlots((prev) => assignColourSlots(prev, selectedIds));
  };

  const distinctAvailable = selection.selected.size <= COLOUR_SLOT_COUNT;
  const effectiveMode: ColourMode =
    colourMode === "distinct" && distinctAvailable ? "distinct" : "highlight";

  const colouring = useMemo<CurveColouring>(
    () => ({ colourMode: effectiveMode, slots, focusedId, palette }),
    [effectiveMode, slots, focusedId, palette],
  );

  // Memoised on its real inputs: a re-render for anything else hands Plotly
  // the same figure, and the constant uirevision keeps the user's zoom.
  const figure = useMemo(
    () =>
      data
        ? buildCurveFigure({
            data,
            selected: selection.selected,
            showReported,
            canvas: "screen",
            ...colouring,
          })
        : null,
    [data, selection.selected, showReported, colouring],
  );
  const columns = useMemo(() => (data ? reportedColumns(data) : []), [data]);
  const rows = useMemo(
    () => (data ? tableRows(data, selection.selected) : []),
    [data, selection.selected],
  );

  // Plotly fires hover from its own emitter, outside React; flushSync makes
  // the focus render now rather than on some later event.
  const onHover = useCallback(
    (ev: unknown) => flushSync(() => setFocusedId(focusIdFromHover(ev))),
    [],
  );
  const onUnhover = useCallback(() => flushSync(() => setFocusedId(null)), []);

  if (isLoading && !data) return <Skeleton className={cn("w-full", PLOT_HEIGHT)} />;
  if (error || !data) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">Could not load the curves.</p>
    );
  }

  const colourOf = (id: string) => {
    const p = byId.get(id);
    return p ? curveStyle(p, colouring).color : MEASURED_CURVE_COLORS[palette].neutral;
  };

  const exportImage = (format: "png" | "svg") => {
    const exported = buildCurveFigure({
      data,
      selected: selection.selected,
      showReported,
      canvas: "export",
      ...colouring,
    });
    getPlotlyGlobal()?.downloadImage?.(exported, {
      format,
      width: 1200,
      height: 600,
      filename: "run-curves",
    });
  };

  const commitWindow = () => {
    if (windowDraft === null) return;
    const n = Number(windowDraft);
    if (windowDraft.trim() !== "" && Number.isFinite(n) && n > 0) setDerivativeWindow(n);
    setWindowDraft(null);
  };

  const hasTraces = (figure?.data.length ?? 0) > 0;
  const colours = MEASURED_CURVE_COLORS[palette];
  const selectedPositions = ordered.filter((p) => selection.selected.has(p.well_id));

  return (
    <div className="space-y-4">
      <PositionSelector
        holder={data.holder}
        positions={data.positions}
        selection={selection}
        onChange={changeSelection}
        focusedId={focusedId}
        onFocus={setFocusedId}
        colourOf={colourOf}
      />

      <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
        {data.channels.length > 0 && (
          <Field label="Signal">
            <Segmented
              label="Signal"
              value={channel ?? data.channel ?? ""}
              options={data.channels.map((c) => ({ value: c.key, label: c.label }))}
              onChange={setChannel}
            />
          </Field>
        )}
        <Field label="View">
          <div className="flex items-center gap-2">
            <Segmented
              label="View"
              value={view}
              options={[
                { value: "measured", label: "Measured" },
                { value: "derivative", label: "Derivative" },
              ]}
              onChange={setView}
            />
            {view === "derivative" && (
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                window
                <Input
                  type="number"
                  aria-label="Window"
                  min={0}
                  step="any"
                  className="h-8 w-20"
                  value={windowDraft ?? data.window ?? ""}
                  onChange={(e) => setWindowDraft(e.target.value)}
                  onBlur={commitWindow}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitWindow();
                  }}
                />
                {currentChannel(data)?.x_unit}
              </span>
            )}
          </div>
        </Field>
        <Field label="Reported values">
          <Segmented
            label="Reported values"
            value={showReported ? "on" : "off"}
            options={[
              { value: "on", label: "Lines on" },
              { value: "off", label: "Off" },
            ]}
            onChange={(v) => setShowReported(v === "on")}
          />
        </Field>
        <Field label="Colour">
          <div className="flex items-center gap-2">
            <Segmented
              label="Colour"
              value={effectiveMode}
              options={[
                { value: "highlight", label: "Highlight" },
                {
                  value: "distinct",
                  label: `Distinct (${COLOUR_SLOT_COUNT} or fewer)`,
                  disabled: !distinctAvailable,
                },
              ]}
              onChange={setColourMode}
            />
            {!distinctAvailable && (
              <span className="text-xs text-muted-foreground">
                More than {COLOUR_SLOT_COUNT} selected
              </span>
            )}
          </div>
        </Field>
        <div className="ml-auto">
          <Field label="Export, white background">
            <div className="flex gap-2">
              {(["png", "svg"] as const).map((format) => (
                <Button
                  key={format}
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!hasTraces}
                  onClick={() => exportImage(format)}
                >
                  {format.toUpperCase()}
                </Button>
              ))}
            </div>
          </Field>
        </div>
      </div>

      {hasTraces && figure ? (
        <div className={cn("transition-opacity", isPlaceholderData && "opacity-60")}>
          <Plot
            data={figure.data}
            layout={figure.layout}
            config={PLOT_CONFIG}
            style={PLOT_STYLE}
            useResizeHandler
            onHover={onHover}
            onUnhover={onUnhover}
          />
        </div>
      ) : (
        <div
          className={cn(
            "flex items-center justify-center rounded-lg border border-dashed text-sm text-muted-foreground",
            PLOT_HEIGHT,
          )}
        >
          {selection.selected.size === 0
            ? "Select positions above to draw their curves"
            : "The selected positions have no curves for this signal."}
        </div>
      )}

      {hasTraces && (
        <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
          {effectiveMode === "distinct" ? (
            selectedPositions.map((p) => (
              <span key={p.well_id}>
                <Swatch line colour={colourOf(p.well_id)} />
                {positionName(p)}
              </span>
            ))
          ) : (
            <>
              <span>
                <Swatch line colour={colours.reference} />
                Reference positions
              </span>
              <span>
                <Swatch line colour={colours.neutral} />
                Other positions
              </span>
              <span>
                <Swatch line colour={colours.focus} />
                The curve under the pointer
              </span>
              {colourMode === "distinct" && (
                <span>More than {COLOUR_SLOT_COUNT} selected: distinct colours are off</span>
              )}
            </>
          )}
        </div>
      )}

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Position</TableHead>
              <TableHead>Label</TableHead>
              <TableHead>Compound</TableHead>
              <TableHead>Batch</TableHead>
              <TableHead className="text-right">
                Conc. ({DOSE_UNIT_LABELS[data.dose_unit as DoseUnit] ?? data.dose_unit})
              </TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Note</TableHead>
              {columns.map((c) => (
                <TableHead key={c.key} className="text-right">
                  {c.unit ? `${c.label} (${c.unit})` : c.label}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7 + columns.length} className="text-muted-foreground">
                  No positions selected.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => (
                <TableRow
                  key={r.wellId}
                  data-focused={focusedId === r.wellId || undefined}
                  className={cn(focusedId === r.wellId && "bg-primary/10")}
                  onMouseEnter={() => setFocusedId(r.wellId)}
                  onMouseLeave={() => setFocusedId(null)}
                >
                  <TableCell>
                    <Swatch colour={colourOf(r.wellId)} />
                    {r.positionLabel}
                  </TableCell>
                  <TableCell>{r.label}</TableCell>
                  <TableCell className={cn(!r.compound && "text-muted-foreground")}>
                    {r.compound ?? "No compound"}
                  </TableCell>
                  <TableCell className={cn(!r.batch && "text-muted-foreground")}>
                    {r.batch ?? "None"}
                  </TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {r.dose ?? ""}
                  </TableCell>
                  <TableCell>{r.role}</TableCell>
                  <TableCell className="whitespace-normal">{r.note}</TableCell>
                  {columns.map((c) => (
                    <TableCell key={c.key} className="text-right font-mono tabular-nums">
                      {formatValue(r.reported[c.key])}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
