"use client";

import { errorText } from "@/features/visualization/lib/api-errors";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import { Plot } from "@/shared/lib/plotly";
import { Loader2, Plus } from "lucide-react";
import { useTheme } from "next-themes";
import Link from "next/link";
import { useCallback, useId, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { useAddMeltingStep } from "../hooks/use-melting-analysis";
import { useAddTemperatureWindow } from "../hooks/use-protocols";
import { useRecomputeRun } from "../hooks/use-runs";
import {
  type CurveSet,
  buildCurveFigure,
  currentChannel,
  nearestPeak,
  orderedPositions,
  pickFromClick,
  positionName,
  xSpan,
} from "../lib/curve-plot";
import { proposeWindows, windowLabel } from "../lib/window-proposal";
import type { MeltingAnalysis, MeltingStep } from "../types";
import { stepInput } from "./melting-steps-panel";

export interface NamePeaksDialogProps {
  open: boolean;
  onOpenChange(open: boolean): void;
  runId: string;
  protocolId: string;
  /** The run's traces for the signal on screen: every position's, drawn or not. */
  set: CurveSet;
  analysis: MeltingAnalysis;
  /** The run is neither approved nor locked. */
  canRecalculate: boolean;
}

/** What was typed in a row. A limit left alone follows the proposal. */
interface RowEdit {
  name?: string;
  low?: string;
  high?: string;
  tm?: boolean;
  deltaTm?: boolean;
  /** The server's sentence when saving the row failed; any edit clears it. */
  error?: string;
}
type Edits = Record<string, RowEdit>;

interface Row {
  key: string;
  /** Null for a window without a peak. */
  peak: MeltingStep | null;
  name: string;
  low: string;
  high: string;
  tm: boolean;
  deltaTm: boolean;
  error?: string;
}

const PLOT_CONFIG = { displaylogo: false, responsive: true };
const PLOT_STYLE = { width: "100%", height: 260 };

const num = (text: string) => (text.trim() === "" ? Number.NaN : Number(text));
/** A limit as its field shows it: one decimal; empty when there is none to propose. */
const limit = (v: number) => (Number.isFinite(v) ? v.toFixed(1) : "");
const fmt = (v: number) => formatMeasurementValue(v, 4);
const patched = (all: Edits, key: string, patch: RowEdit): Edits => ({
  ...all,
  [key]: { ...all[key], error: undefined, ...patch },
});

/** Name the peaks of one reference position to create the signal's temperature
 *  windows on the protocol. Nothing is saved before Save windows; a row without
 *  a name creates nothing. */
export function NamePeaksDialog(props: NamePeaksDialogProps) {
  // Mounted only while open, so each opening starts from the proposal.
  return props.open ? <NamePeaks {...props} /> : null;
}

function NamePeaks({
  onOpenChange,
  runId,
  protocolId,
  set,
  analysis,
  canRecalculate,
}: NamePeaksDialogProps) {
  const ids = useId();
  const channelKey = set.channel ?? "";
  const add = useAddTemperatureWindow(protocolId);
  const addPeak = useAddMeltingStep(runId);
  const recompute = useRecomputeRun();
  const { resolvedTheme } = useTheme();
  const palette = resolvedTheme === "light" ? "light" : "dark";

  const references = useMemo(
    () => orderedPositions(set).filter((p) => p.well_type === "reference"),
    [set],
  );
  const [chosen, setChosen] = useState<string | null>(null);
  const reference = references.find((p) => p.well_id === chosen) ?? references[0] ?? null;
  const refId = reference?.well_id ?? null;

  const [edits, setEdits] = useState<Edits>({});
  /** The keys of the rows without a peak. */
  const [free, setFree] = useState<string[]>([]);
  const nextFree = useRef(0);
  /** Windows saved here, shown as existing before the analysis is read again. */
  const [saved, setSaved] = useState<{ window: string; low: number; high: number }[]>([]);
  const [saving, setSaving] = useState(false);
  /** The low or high field that has focus; a click on the trace fills it. */
  const [armed, setArmed] = useState<{ key: string; field: "low" | "high" } | null>(null);
  /** A clicked temperature with no peak near it. */
  const [spot, setSpot] = useState<number | null>(null);
  const [peakNote, setPeakNote] = useState<string | null>(null);

  const existing = useMemo(() => {
    const onSignal = analysis.windows.filter((w) => w.channel_key === channelKey);
    return [...onSignal, ...saved.filter((s) => !onSignal.some((w) => w.window === s.window))];
  }, [analysis.windows, channelKey, saved]);
  // The chosen reference's counted peaks on the signal, by temperature.
  const peaks = useMemo(
    () =>
      analysis.steps
        .filter(
          (s) => s.well_id === refId && s.channel_key === channelKey && s.status !== "rejected",
        )
        .sort((a, b) => a.value - b.value),
    [analysis.steps, refId, channelKey],
  );
  const curve = refId ? set.curves.get(refId) : undefined;
  // The trace's ends; infinite without a trace, which leaves the outer limits empty.
  const range = useMemo<[number, number]>(() => {
    let low = Number.POSITIVE_INFINITY;
    let high = Number.NEGATIVE_INFINITY;
    for (const x of curve?.x ?? []) {
      if (x < low) low = x;
      if (x > high) high = x;
    }
    return [low, high];
  }, [curve]);

  const rows = useMemo<Row[]>(() => {
    const row = (key: string, peak: MeltingStep | null, low: string, high: string): Row => {
      const e = edits[key] ?? {};
      return {
        key,
        peak,
        name: e.name ?? "",
        low: e.low ?? low,
        high: e.high ?? high,
        tm: e.tm ?? true,
        deltaTm: e.deltaTm ?? true,
        error: e.error,
      };
    };
    const pool = [...peaks];
    const proposed = proposeWindows(
      peaks.map((s) => s.value),
      range,
      existing,
    );
    return [
      ...proposed.map((p) => {
        // The proposal knows its peak by temperature; two at one temperature each get a row.
        const [peak] = pool.splice(
          pool.findIndex((s) => s.value === p.peak),
          1,
        );
        return row(peak.id, peak, limit(p.low), limit(p.high));
      }),
      ...free.map((key) => row(key, null, "", "")),
    ];
  }, [peaks, range, existing, edits, free]);

  const figure = useMemo(() => {
    if (!refId || !curve) return null;
    return buildCurveFigure({
      set,
      drawn: new Set([refId]),
      showReported: true,
      canvas: "screen",
      steps: new Map([
        [refId, peaks.map((s) => ({ value: s.value, reviewed: s.status === "accepted" }))],
      ]),
      windows: rows.flatMap((r) => {
        const low = num(r.low);
        const high = num(r.high);
        return low < high ? [{ low, high, label: r.name.trim() }] : [];
      }),
      colourMode: "highlight",
      slots: new Map(),
      focusedId: null,
      palette,
    });
  }, [set, refId, curve, peaks, rows, palette]);

  // react-plotly re-attaches handlers only when the figure changes, so the
  // click handler never changes and reads what is current here.
  const latest = useRef({ armed, peaks, traces: figure?.data ?? [] });
  latest.current = { armed, peaks, traces: figure?.data ?? [] };
  // ponytail: "near a peak" is 2% of the whole trace, also when zoomed in; track
  // the zoom as the viewer does if a peak must be added closer to another.
  const onClick = useCallback((ev: unknown) => {
    const pick = pickFromClick(ev);
    if (!pick) return;
    const { armed, peaks, traces } = latest.current;
    flushSync(() => {
      if (armed) {
        setEdits((all) => patched(all, armed.key, { [armed.field]: pick.x.toFixed(1) }));
      } else {
        setSpot(nearestPeak(peaks, pick.x, xSpan(traces)) ? null : pick.x);
      }
    });
  }, []);

  const edit = (key: string, patch: RowEdit) => setEdits((all) => patched(all, key, patch));
  const chooseReference = (id: string) => {
    setChosen(id);
    setSpot(null);
    setPeakNote(null);
  };
  const addPeakHere = () => {
    if (spot === null || !refId) return;
    setPeakNote(null);
    addPeak.mutate(
      { well_id: refId, channel_key: channelKey, value: Number(stepInput(spot)) },
      {
        // The page reads the analysis again; the new peak then has a row.
        onSuccess: (change) => {
          setSpot(null);
          setPeakNote(change.compute_warning);
        },
        onError: (e) => setPeakNote(errorText(e)),
      },
    );
  };

  const named = rows.filter((r) => r.name.trim() !== "");
  const canSave =
    !saving &&
    channelKey !== "" &&
    named.length > 0 &&
    named.every((r) => num(r.low) < num(r.high) && (r.tm || r.deltaTm));

  /** One request per named row, in row order, stopping at the first refusal. */
  const save = async () => {
    if (!canSave) return;
    setSaving(true);
    let savedAny = false;
    let failed = false;
    for (const r of named) {
      const window = { window: r.name.trim(), low: num(r.low), high: num(r.high) };
      try {
        await add.mutateAsync({
          ...window,
          channel_key: channelKey,
          measures: [
            ...(r.tm ? (["tm"] as const) : []),
            ...(r.deltaTm ? (["delta_tm"] as const) : []),
          ],
        });
      } catch (e) {
        setEdits((all) => patched(all, r.key, { error: errorText(e) }));
        failed = true;
        break;
      }
      savedAny = true;
      setSaved((all) => [...all, window]);
      setEdits((all) => Object.fromEntries(Object.entries(all).filter(([key]) => key !== r.key)));
      setFree((keys) => keys.filter((key) => key !== r.key));
    }
    setSaving(false);
    if (!savedAny || !canRecalculate) return;
    // The run's stored readouts follow the new windows.
    recompute.mutate({ runId });
    if (!failed) onOpenChange(false);
  };

  const tick = (id: string, label: string, checked: boolean, onChange: (v: boolean) => void) => (
    <div className="flex items-center gap-1.5">
      <Checkbox id={id} checked={checked} onCheckedChange={(v) => onChange(v === true)} />
      <Label htmlFor={id}>{label}</Label>
    </div>
  );
  const limitField = (r: Row, field: "low" | "high", label: string) => (
    <Input
      aria-label={label}
      type="number"
      step={0.1}
      className="h-8 w-24"
      value={r[field]}
      onFocus={() => setArmed({ key: r.key, field })}
      onBlur={() => setArmed(null)}
      onChange={(e) => edit(r.key, { [field]: e.target.value })}
    />
  );

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (next || !saving) onOpenChange(next);
      }}
    >
      <DialogContent className="flex max-h-[90vh] w-[min(95vw,1000px)] max-w-[1000px] flex-col overflow-y-auto sm:max-w-[1000px]">
        <DialogHeader>
          <DialogTitle>{`Set up windows · ${currentChannel(set)?.label ?? ""}`}</DialogTitle>
          <DialogDescription>
            Name the reference's peaks. Each named row becomes a temperature window on the protocol.
            A row without a name creates nothing.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
          {references.length > 1 ? (
            <div className="flex items-center gap-2">
              <Label htmlFor={`${ids}-reference`}>Reference</Label>
              <Select value={refId ?? ""} onValueChange={chooseReference}>
                <SelectTrigger id={`${ids}-reference`} className="h-8 w-56">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {references.map((p) => (
                    <SelectItem key={p.well_id} value={p.well_id}>
                      {positionName(p)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : (
            reference && <span>{`Reference: ${positionName(reference)}`}</span>
          )}
          <div data-testid="existing-windows" className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground">
              {`Existing windows on this signal:${existing.length ? "" : " none"}`}
            </span>
            {existing.map((w) => (
              <span key={w.window} className="rounded border px-1.5 py-0.5 tabular-nums">
                {windowLabel(w)}
              </span>
            ))}
            {existing.length > 0 && (
              <Link
                href={`/assays/protocols/${protocolId}#setup`}
                className="text-muted-foreground underline underline-offset-4"
              >
                Changing a published window's limits needs a new protocol version
              </Link>
            )}
          </div>
        </div>

        {/* The rows scroll; the trace and the buttons stay in view. */}
        <div className="min-h-24 flex-1 space-y-2 overflow-y-auto pr-1">
          {!reference ? (
            <p className="text-sm text-muted-foreground">
              This run has no reference position. Mark one in Edit labeling, or add a window by
              typing its range.
            </p>
          ) : (
            peaks.length === 0 && (
              <p className="text-sm text-muted-foreground">
                {`The reference has no peak on this signal. ${
                  canRecalculate ? "Click its trace to add one, or add" : "Add"
                } a window by typing its range.`}
              </p>
            )
          )}
          {rows.map((r) => {
            const id = `${ids}-${r.key}`;
            return (
              <fieldset
                key={r.key}
                aria-label={r.peak ? `Peak at ${fmt(r.peak.value)} °C` : "Window without a peak"}
                className="min-w-0 rounded-md border px-3 py-2"
              >
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                  {r.peak ? (
                    <span className="flex w-40 gap-2">
                      <span className="font-medium tabular-nums">{`${fmt(r.peak.value)} °C`}</span>
                      <span className="text-muted-foreground">
                        {r.peak.source === "manual" ? "Manual" : "Instrument"}
                      </span>
                    </span>
                  ) : (
                    <span className="w-40 text-muted-foreground">No peak</span>
                  )}
                  <div className="flex items-center gap-2">
                    <Label htmlFor={`${id}-name`}>Name</Label>
                    <Input
                      id={`${id}-name`}
                      className="h-8 w-44"
                      maxLength={60}
                      value={r.name}
                      onChange={(e) => edit(r.key, { name: e.target.value })}
                    />
                  </div>
                  <div className="flex items-center gap-1.5">
                    {limitField(r, "low", "Low (°C)")}
                    <span aria-hidden>–</span>
                    {limitField(r, "high", "High (°C)")}
                    <span className="text-muted-foreground">°C</span>
                  </div>
                  {tick(`${id}-tm`, "Tm", r.tm, (tm) => edit(r.key, { tm }))}
                  {tick(`${id}-dtm`, "ΔTm", r.deltaTm, (deltaTm) => edit(r.key, { deltaTm }))}
                </div>
                {num(r.low) >= num(r.high) && (
                  <p className="mt-1 text-destructive text-sm">Low must be below High.</p>
                )}
                {r.error && (
                  <p role="alert" className="mt-1 text-destructive text-sm">
                    {r.error}
                  </p>
                )}
              </fieldset>
            );
          })}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              const key = `free-${nextFree.current++}`;
              setFree((keys) => [...keys, key]);
            }}
          >
            <Plus className="size-4" />
            Add a window without a peak
          </Button>
        </div>

        {figure && (
          <div className="shrink-0 space-y-1">
            {/* A click on the plot must not take the focus from the limit it fills. */}
            <div onMouseDown={(e) => e.preventDefault()}>
              <Plot
                data={figure.data}
                layout={figure.layout}
                config={PLOT_CONFIG}
                style={PLOT_STYLE}
                useResizeHandler
                onClick={onClick}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              {`A click on the trace fills the low or high field in focus.${
                canRecalculate ? " With none in focus, it offers a new peak there." : ""
              }`}
            </p>
            {spot !== null && canRecalculate && (
              <p className="flex items-center gap-3 text-sm">
                {`No peak at ${stepInput(spot)} °C.`}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={addPeak.isPending}
                  onClick={addPeakHere}
                >
                  Add a peak here
                </Button>
              </p>
            )}
            {peakNote && (
              <p role="alert" className="text-destructive text-sm">
                {peakNote}
              </p>
            )}
          </div>
        )}
        {saved.length > 0 && !canRecalculate && (
          <p className="text-sm">
            This run is approved (or locked), so its stored results do not change. The new windows
            apply to later runs; the values shown here are for viewing.
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            {saved.length > 0 ? "Done" : "Cancel"}
          </Button>
          <Button onClick={save} disabled={!canSave}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save windows
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
