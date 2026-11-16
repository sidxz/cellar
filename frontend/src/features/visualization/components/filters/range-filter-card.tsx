"use client";

import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import { Slider } from "@/shared/components/ui/slider";
import { CHART_COLORS } from "@/shared/lib/chart-colors";
import { Plot } from "@/shared/lib/plotly";
import { useId, useMemo, useState } from "react";
import { column, numberAt } from "../../lib/dataset";
import { type Filter, binCounts, computePassMask, fixedBins } from "../../lib/filters";
import { useWorkbench } from "../../store/workbench-context";
import type { Dataset } from "../../types";
import { FilterCard } from "./filter-card";

type RangeFilter = Extract<Filter, { kind: "range" }>;

const CONFIG = { staticPlot: true, responsive: true };
const STYLE = { width: "100%", height: 48 };
const OUTSIDE = "rgba(113,113,122,0.35)";

/** Slider scale over the column's span: a power-of-ten step (~100 per span) and ends
 * snapped to it, so dragged bounds come out as round numbers. */
function scale(lo: number, hi: number) {
  const step = 10 ** Math.floor(Math.log10((hi - lo) / 100));
  const round = (v: number) => Number(v.toFixed(Math.max(0, Math.round(-Math.log10(step)))));
  return {
    step,
    min: round(Math.floor(lo / step) * step),
    max: round(Math.ceil(hi / step) * step),
  };
}

/** A numeric range: a fixed-bin histogram of the rows the other filters keep, a two-thumb
 * slider and inclusive min/max inputs (one undo entry per release or committed input),
 * and an "Include missing (n)" toggle. */
export function RangeFilterCard({
  ds,
  filter,
  active,
}: {
  ds: Dataset;
  filter: RangeFilter;
  active: boolean;
}) {
  const filters = useWorkbench((s) => s.filters);
  const upsertFilter = useWorkbench((s) => s.upsertFilter);
  const col = column(ds, filter.key);
  const unit = col?.unit;
  const label = col?.label ?? filter.key;
  const [draft, setDraft] = useState<number[] | null>(null);
  const missingId = useId();

  const { edges } = useMemo(() => fixedBins(ds, filter.key), [ds, filter.key]);
  const s = useMemo(() => scale(edges[0], edges[edges.length - 1]), [edges]);
  const { counts, missing } = useMemo(() => {
    const others = computePassMask(ds, filters, filter.id);
    let missing = 0;
    for (let i = 0; i < others.length; i++) {
      if (others[i] && numberAt(ds, filter.key, i) === null) missing += 1;
    }
    return { counts: binCounts(ds, filter.key, edges, others), missing };
  }, [ds, filters, filter.id, filter.key, edges]);

  const clamp = (v: number) => Math.min(s.max, Math.max(s.min, v));
  const [lo, hi] = draft ?? [clamp(filter.min ?? s.min), clamp(filter.max ?? s.max)];

  const figure = useMemo(() => {
    const width = edges[1] - edges[0];
    const x = counts.map((_, k) => edges[k] + width / 2);
    return {
      data: [
        {
          type: "bar",
          x,
          y: counts,
          width,
          marker: { color: x.map((c) => (c >= lo && c <= hi ? CHART_COLORS.primary : OUTSIDE)) },
          hoverinfo: "skip",
        },
      ],
      layout: {
        autosize: true,
        height: 48,
        margin: { l: 0, r: 0, t: 0, b: 0 },
        bargap: 0.05,
        showlegend: false,
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        xaxis: { visible: false, range: [s.min, s.max] },
        // Log counts keep a long tail of hits visible next to the bulk.
        yaxis: { visible: false, type: "log" },
      },
    };
  }, [counts, edges, lo, hi, s]);

  const commit = (
    min: number | null,
    max: number | null,
    includeMissing = filter.includeMissing,
  ) => {
    if (min === filter.min && max === filter.max && includeMissing === filter.includeMissing)
      return;
    upsertFilter({ ...filter, min, max, includeMissing });
  };

  return (
    <FilterCard ds={ds} filter={filter} active={active}>
      <Plot data={figure.data} layout={figure.layout} config={CONFIG} style={STYLE} />
      <Slider
        min={s.min}
        max={s.max}
        step={s.step}
        value={[lo, hi]}
        minStepsBetweenThumbs={0}
        thumbLabels={[`Minimum ${label}`, `Maximum ${label}`]}
        onValueChange={setDraft}
        onValueCommit={([a, b]) => {
          setDraft(null);
          commit(a <= s.min ? null : a, b >= s.max ? null : b);
        }}
      />
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        <span>≥</span>
        <BoundInput
          label="Minimum (inclusive)"
          value={draft ? lo : filter.min}
          placeholder={s.min}
          onCommit={(min) => commit(min, filter.max)}
        />
        {unit && <span>{unit}</span>}
        <span className="ml-auto">≤</span>
        <BoundInput
          label="Maximum (inclusive)"
          value={draft ? hi : filter.max}
          placeholder={s.max}
          onCommit={(max) => commit(filter.min, max)}
        />
        {unit && <span>{unit}</span>}
      </div>
      <div className="flex items-center gap-2 text-xs">
        <Checkbox
          id={missingId}
          checked={filter.includeMissing}
          onCheckedChange={(on) => commit(filter.min, filter.max, on === true)}
        />
        <label htmlFor={missingId}>Include missing ({missing.toLocaleString()})</label>
      </div>
    </FilterCard>
  );
}

/** One bound: commits when left or on Enter, never per keystroke; blank = no bound. */
function BoundInput({
  label,
  value,
  placeholder,
  onCommit,
}: {
  label: string;
  value: number | null;
  placeholder: number;
  onCommit: (value: number | null) => void;
}) {
  const commit = (input: HTMLInputElement) => {
    const raw = input.value.trim();
    const v = raw === "" ? null : Number(raw);
    if (v !== null && !Number.isFinite(v)) {
      input.value = value === null ? "" : String(value);
      return;
    }
    onCommit(v);
  };
  return (
    <Input
      // A new value from outside (drag, undo) replaces whatever the input shows.
      key={value ?? "none"}
      aria-label={label}
      type="number"
      step="any"
      defaultValue={value ?? ""}
      placeholder={String(placeholder)}
      className="h-7 w-20 px-1.5 text-right text-xs"
      onKeyDown={(e) => {
        if (e.key === "Enter") commit(e.currentTarget);
      }}
      onBlur={(e) => commit(e.currentTarget)}
    />
  );
}
