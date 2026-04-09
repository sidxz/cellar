"use client";

import dynamic from "next/dynamic";
import React, { useState, useRef, useCallback } from "react";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { cn } from "@/shared/lib/utils";
import {
  type DoseResponseCurve,
  type CurveType,
  type CurveClass,
  CURVE_TYPE_LABELS,
  CURVE_CLASS_LABELS,
} from "../types";
import { useRefitDoseResponse, useClassifyDoseResponse } from "../hooks/use-refit-dose-response";

// ─── Dynamic import — Plotly must NOT be SSR'd ─────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const Plot = dynamic<any>(
  () => import("react-plotly.js").then((mod) => mod.default as any),
  {
    ssr: false,
    loading: () => <Skeleton className="h-[350px] w-full" />,
  }
) as React.ComponentType<{
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  layout: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  config?: any;
  style?: React.CSSProperties;
  useResizeHandler?: boolean;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onClick?: (event: any) => void;
}>;

// ─── Types ────────────────────────────────────────────────────────────────────

interface DoseResponseChartProps {
  curves: DoseResponseCurve[];
  className?: string;
  isInteractive?: boolean;
}

interface CurveConstraints {
  fixTop: boolean;
  topValue: number;
  fixBottom: boolean;
  bottomValue: number;
  hillSlope: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Generate 100-point 4PL sigmoid on log scale between min/max concentration */
function generate4PLCurve(
  curve: DoseResponseCurve,
  xMin: number,
  xMax: number
): { x: number[]; y: number[] } {
  const { fitted_value, hill_slope, top, bottom } = curve;
  const logMin = Math.log10(xMin);
  const logMax = Math.log10(xMax);
  const xs: number[] = [];
  const ys: number[] = [];

  for (let i = 0; i <= 100; i++) {
    const logX = logMin + (logMax - logMin) * (i / 100);
    const x = Math.pow(10, logX);
    const y = bottom + (top - bottom) / (1 + Math.pow(x / fitted_value, hill_slope));
    xs.push(x);
    ys.push(y);
  }
  return { x: xs, y: ys };
}

/** Extract (concentration, response) pairs from raw_data / excluded_points */
function extractPoints(
  points: Array<Record<string, unknown>> | null
): { x: number[]; y: number[] } {
  if (!points || points.length === 0) return { x: [], y: [] };
  const xs: number[] = [];
  const ys: number[] = [];
  for (const pt of points) {
    const conc = pt["concentration"] ?? pt["x"];
    const resp = pt["response"] ?? pt["y"];
    if (typeof conc === "number" && typeof resp === "number") {
      xs.push(conc);
      ys.push(resp);
    }
  }
  return { x: xs, y: ys };
}

/** R² color class */
function rSquaredColor(r2: number): string {
  if (r2 >= 0.9) return "text-green-400";
  if (r2 >= 0.8) return "text-yellow-400";
  return "text-red-400";
}

const TRACE_COLORS = [
  "#3b82f6",
  "#22c55e",
  "#f59e0b",
  "#ef4444",
  "#a855f7",
  "#06b6d4",
  "#ec4899",
  "#84cc16",
];

const CURVE_CLASS_OPTIONS: CurveClass[] = ["full", "partial", "bell_shaped", "inactive"];

const HILL_SLOPE_OPTIONS: { value: string; label: string }[] = [
  { value: "unconstrained", label: "Unconstrained" },
  { value: "negative_only", label: "Negative only" },
  { value: "positive_only", label: "Positive only" },
  { value: "fixed_at_one", label: "Fixed at -1" },
];

// ─── Interactive single-curve controls ────────────────────────────────────────

interface CurveControlsProps {
  curve: DoseResponseCurve;
  excludedIndices: Set<number>;
  constraints: CurveConstraints;
  onConstraintChange: (next: Partial<CurveConstraints>) => void;
  onReset: () => void;
  isPending: boolean;
}

function CurveControls({
  curve,
  excludedIndices,
  constraints,
  onConstraintChange,
  onReset,
  isPending,
}: CurveControlsProps) {
  const [open, setOpen] = useState(false);
  const totalPoints = (curve.raw_data?.length ?? 0) + (curve.excluded_points?.length ?? 0);
  const includedCount = totalPoints - excludedIndices.size;

  return (
    <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-3">
      {/* Toggle header */}
      <div className="flex items-center justify-between">
        <button
          type="button"
          className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
          onClick={() => setOpen((v) => !v)}
        >
          <span>{open ? "▾" : "▸"}</span>
          Fit Constraints
          {isPending && (
            <span className="ml-1 h-2 w-2 rounded-full bg-blue-400 animate-pulse inline-block" />
          )}
        </button>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>
            {includedCount}/{totalPoints} points
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs"
            onClick={onReset}
            disabled={isPending}
          >
            Reset
          </Button>
        </div>
      </div>

      {/* Collapsible constraint panel */}
      {open && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 pt-1">
          {/* Fix Top */}
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Checkbox
                id={`fix-top-${curve.id}`}
                checked={constraints.fixTop}
                onCheckedChange={(checked) =>
                  onConstraintChange({ fixTop: checked === true })
                }
              />
              <Label htmlFor={`fix-top-${curve.id}`} className="text-xs">
                Fix Top
              </Label>
            </div>
            <Input
              type="number"
              className="h-7 text-xs"
              value={constraints.topValue}
              disabled={!constraints.fixTop}
              onChange={(e) =>
                onConstraintChange({ topValue: parseFloat(e.target.value) || 0 })
              }
            />
          </div>

          {/* Fix Bottom */}
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Checkbox
                id={`fix-bottom-${curve.id}`}
                checked={constraints.fixBottom}
                onCheckedChange={(checked) =>
                  onConstraintChange({ fixBottom: checked === true })
                }
              />
              <Label htmlFor={`fix-bottom-${curve.id}`} className="text-xs">
                Fix Bottom
              </Label>
            </div>
            <Input
              type="number"
              className="h-7 text-xs"
              value={constraints.bottomValue}
              disabled={!constraints.fixBottom}
              onChange={(e) =>
                onConstraintChange({ bottomValue: parseFloat(e.target.value) || 0 })
              }
            />
          </div>

          {/* Hill Slope */}
          <div className="space-y-1">
            <Label className="text-xs">Hill Slope</Label>
            <Select
              value={constraints.hillSlope}
              onValueChange={(v) => onConstraintChange({ hillSlope: v })}
            >
              <SelectTrigger className="h-7 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {HILL_SLOPE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value} className="text-xs">
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Summary card with interactive curve class badge ─────────────────────────

interface SummaryCardProps {
  curve: DoseResponseCurve;
  excludedCount: number;
  totalPoints: number;
  isInteractive: boolean;
  onClassify: (curveId: string, curveClass: string) => void;
  isClassifying: boolean;
}

function SummaryCard({
  curve,
  excludedCount,
  totalPoints,
  isInteractive,
  onClassify,
  isClassifying,
}: SummaryCardProps) {
  const [showClassify, setShowClassify] = useState(false);
  const includedCount = totalPoints - excludedCount;

  return (
    <Card key={curve.id} className="py-4">
      <CardHeader className="pb-0">
        <CardTitle className="text-sm">
          {curve.molecule_name ?? CURVE_TYPE_LABELS[curve.curve_type as CurveType] ?? curve.curve_type}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-2 space-y-1">
        <p className="text-sm font-mono">
          {curve.fitted_value} {curve.fitted_unit}
        </p>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className={cn("font-medium", rSquaredColor(curve.r_squared))}>
            R² = {curve.r_squared.toFixed(3)}
          </span>
          {isInteractive && (
            <span className="text-muted-foreground">
              {includedCount}/{totalPoints} pts
            </span>
          )}
          {curve.curve_class && !isInteractive && (
            <Badge variant="outline" className="text-xs">
              {CURVE_CLASS_LABELS[curve.curve_class as CurveClass] ?? curve.curve_class}
            </Badge>
          )}
          {curve.curve_class && isInteractive && (
            <div className="relative">
              <Badge
                variant="outline"
                className="text-xs cursor-pointer hover:bg-accent transition-colors"
                onClick={() => setShowClassify((v) => !v)}
              >
                {CURVE_CLASS_LABELS[curve.curve_class as CurveClass] ?? curve.curve_class}
                <span className="ml-1 opacity-60">▾</span>
              </Badge>
              {showClassify && (
                <div className="absolute left-0 top-full z-10 mt-1 w-36 rounded-md border bg-popover shadow-md">
                  {CURVE_CLASS_OPTIONS.map((cc) => (
                    <button
                      key={cc}
                      type="button"
                      disabled={isClassifying}
                      className={cn(
                        "flex w-full items-center px-3 py-1.5 text-xs hover:bg-accent transition-colors",
                        curve.curve_class === cc && "font-medium text-primary"
                      )}
                      onClick={() => {
                        onClassify(curve.id, cc);
                        setShowClassify(false);
                      }}
                    >
                      {CURVE_CLASS_LABELS[cc]}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ─── Main component ────────────────────────────────────────────────────────────

export function DoseResponseChart({
  curves,
  className,
  isInteractive = false,
}: DoseResponseChartProps) {
  // ── Interactive state ───────────────────────────────────────────────────────
  const { mutate: refit, isPending: isRefitting } = useRefitDoseResponse();
  const { mutate: classify, isPending: isClassifying } = useClassifyDoseResponse();

  // excluded indices per curve id — tracked separately from curve.excluded_points
  // so local UI state stays until query invalidation refreshes the curve
  const [excludedMap, setExcludedMap] = useState<Record<string, Set<number>>>({});

  // constraints per curve id
  const [constraintsMap, setConstraintsMap] = useState<Record<string, CurveConstraints>>({});

  // debounce refs per curve id
  const debounceRefs = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const getConstraints = useCallback(
    (curve: DoseResponseCurve): CurveConstraints =>
      constraintsMap[curve.id] ?? {
        fixTop: false,
        topValue: curve.top,
        fixBottom: false,
        bottomValue: curve.bottom,
        hillSlope: "unconstrained",
      },
    [constraintsMap]
  );

  const getExcluded = useCallback(
    (curveId: string): Set<number> => excludedMap[curveId] ?? new Set(),
    [excludedMap]
  );

  const callRefit = useCallback(
    (curve: DoseResponseCurve, excluded: Set<number>, constraints: CurveConstraints) => {
      refit({
        curveId: curve.id,
        input: {
          excluded_point_indices: Array.from(excluded),
          hill_slope_constraint:
            constraints.hillSlope !== "unconstrained" ? constraints.hillSlope : null,
          top_constraint: constraints.fixTop ? constraints.topValue : null,
          bottom_constraint: constraints.fixBottom ? constraints.bottomValue : null,
        },
      });
    },
    [refit]
  );

  const handleConstraintChange = useCallback(
    (curve: DoseResponseCurve, patch: Partial<CurveConstraints>) => {
      const current = getConstraints(curve);
      const next = { ...current, ...patch };
      setConstraintsMap((prev) => ({ ...prev, [curve.id]: next }));

      // debounce 500ms
      if (debounceRefs.current[curve.id]) {
        clearTimeout(debounceRefs.current[curve.id]);
      }
      debounceRefs.current[curve.id] = setTimeout(() => {
        callRefit(curve, getExcluded(curve.id), next);
      }, 500);
    },
    [getConstraints, getExcluded, callRefit]
  );

  const handleReset = useCallback(
    (curve: DoseResponseCurve) => {
      const resetConstraints: CurveConstraints = {
        fixTop: false,
        topValue: curve.top,
        fixBottom: false,
        bottomValue: curve.bottom,
        hillSlope: "unconstrained",
      };
      setExcludedMap((prev) => ({ ...prev, [curve.id]: new Set() }));
      setConstraintsMap((prev) => ({ ...prev, [curve.id]: resetConstraints }));
      refit({ curveId: curve.id, input: { excluded_point_indices: [] } });
    },
    [refit]
  );

  const handleClassify = useCallback(
    (curveId: string, curveClass: string) => {
      classify({ curveId, input: { curve_class: curveClass } });
    },
    [classify]
  );

  // ── Early return ────────────────────────────────────────────────────────────
  if (curves.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-lg border border-dashed p-12 text-sm text-muted-foreground">
        No dose-response curves available.
      </div>
    );
  }

  // ── Build Plotly traces ─────────────────────────────────────────────────────
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const traces: any[] = [];

  // Track trace index → (curveId, pointIndex within included array) for click handling
  // Each included-points trace gets a traceIndex so we can map clicks back.
  const traceIndexToCurve: Array<{ curveId: string; type: "included" | "excluded" }> = [];

  for (let i = 0; i < curves.length; i++) {
    const curve = curves[i];
    const color = TRACE_COLORS[i % TRACE_COLORS.length];
    const group = `curve-${curve.id}`;
    const curveTypeLabel = CURVE_TYPE_LABELS[curve.curve_type as CurveType] ?? curve.curve_type;
    const label = curve.molecule_name
      ? `${curve.molecule_name} (${curveTypeLabel})`
      : curveTypeLabel;

    // Merge server excluded_points back into raw_data for interactive mode:
    // In interactive mode we manage exclusions locally.
    // Displayed included = raw_data filtered by local excludedMap
    // Displayed excluded = server excluded_points + locally excluded from raw_data
    const serverIncluded = extractPoints(curve.raw_data);
    const serverExcluded = extractPoints(curve.excluded_points);
    const localExcluded = getExcluded(curve.id);

    let includedX: number[];
    let includedY: number[];
    let excludedX: number[];
    let excludedY: number[];

    if (isInteractive) {
      includedX = serverIncluded.x.filter((_, idx) => !localExcluded.has(idx));
      includedY = serverIncluded.y.filter((_, idx) => !localExcluded.has(idx));
      excludedX = [
        ...serverIncluded.x.filter((_, idx) => localExcluded.has(idx)),
        ...serverExcluded.x,
      ];
      excludedY = [
        ...serverIncluded.y.filter((_, idx) => localExcluded.has(idx)),
        ...serverExcluded.y,
      ];
    } else {
      includedX = serverIncluded.x;
      includedY = serverIncluded.y;
      excludedX = serverExcluded.x;
      excludedY = serverExcluded.y;
    }

    const allX = [...serverIncluded.x, ...serverExcluded.x, curve.fitted_value];
    const xMinRaw = allX.length > 0 ? Math.min(...allX) * 0.1 : curve.fitted_value * 0.01;
    const xMin = Math.max(xMinRaw, 1e-12);
    const xMax = allX.length > 0 ? Math.max(...allX) * 10 : curve.fitted_value * 100;

    // Included data points
    if (includedX.length > 0) {
      const traceIdx = traces.length;
      traceIndexToCurve[traceIdx] = { curveId: curve.id, type: "included" };
      traces.push({
        type: "scatter",
        mode: "markers",
        name: label,
        legendgroup: group,
        x: includedX,
        y: includedY,
        marker: {
          color,
          size: isInteractive ? 9 : 7,
          symbol: "circle",
          line: isInteractive
            ? { color: "rgba(255,255,255,0.3)", width: 1 }
            : undefined,
        },
        showlegend: true,
        hovertemplate: isInteractive
          ? "x: %{x:.4g}<br>y: %{y:.4g}<br><i>click to exclude</i><extra></extra>"
          : undefined,
      });
    }

    // Excluded data points
    if (excludedX.length > 0) {
      const traceIdx = traces.length;
      traceIndexToCurve[traceIdx] = { curveId: curve.id, type: "excluded" };
      traces.push({
        type: "scatter",
        mode: "markers",
        name: `${label} (excluded)`,
        legendgroup: group,
        x: excludedX,
        y: excludedY,
        marker: { color, size: 8, symbol: "x", opacity: 0.5 },
        showlegend: false,
        hovertemplate: isInteractive
          ? "x: %{x:.4g}<br>y: %{y:.4g}<br><i>click to include</i><extra></extra>"
          : undefined,
      });
    }

    // Fitted 4PL sigmoid line (non-clickable)
    const { x: lineX, y: lineY } = generate4PLCurve(curve, xMin, xMax);
    traces.push({
      type: "scatter",
      mode: "lines",
      name: `${label} fit`,
      legendgroup: group,
      x: lineX,
      y: lineY,
      line: { color, width: 2 },
      showlegend: includedX.length === 0,
      hoverinfo: "skip",
    });
  }

  // ── Plotly click handler ────────────────────────────────────────────────────
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handlePlotClick = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (event: any) => {
      if (!isInteractive) return;
      const pt = event?.points?.[0];
      if (!pt) return;

      const traceIdx: number = pt.curveNumber;
      const pointIdx: number = pt.pointIndex;
      const traceInfo = traceIndexToCurve[traceIdx];
      if (!traceInfo) return;

      const { curveId, type } = traceInfo;
      const curve = curves.find((c) => c.id === curveId);
      if (!curve) return;

      const currentExcluded = new Set(getExcluded(curveId));

      if (type === "included") {
        // Find the actual index in the original raw_data array
        // (accounting for already-excluded points shifting display indices)
        const localExcluded = getExcluded(curveId);
        let displayIdx = 0;
        let originalIdx = -1;
        for (let k = 0; k < (curve.raw_data?.length ?? 0); k++) {
          if (!localExcluded.has(k)) {
            if (displayIdx === pointIdx) {
              originalIdx = k;
              break;
            }
            displayIdx++;
          }
        }
        if (originalIdx >= 0) {
          currentExcluded.add(originalIdx);
        }
      } else {
        // excluded trace — find the original index in the raw_data that maps to this display point
        // The excluded trace shows: locally excluded from raw_data first, then server excluded_points.
        // We only support toggling locally excluded points back (server excluded_points are read-only in UI).
        const localExcluded = getExcluded(curveId);
        const locallyExcludedIndices = Array.from(localExcluded);
        if (pointIdx < locallyExcludedIndices.length) {
          const originalIdx = locallyExcludedIndices[pointIdx];
          currentExcluded.delete(originalIdx);
        }
        // If pointIdx >= locallyExcludedIndices.length → server-excluded point, ignore click
      }

      setExcludedMap((prev) => ({ ...prev, [curveId]: currentExcluded }));
      const constraints = getConstraints(curve);
      callRefit(curve, currentExcluded, constraints);
    },
    [isInteractive, curves, getExcluded, getConstraints, callRefit, traceIndexToCurve]
  );

  const layout = {
    height: 350,
    autosize: true,
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: "#a1a1aa" },
    xaxis: {
      title: { text: "Concentration" },
      type: "log" as const,
      gridcolor: "#27272a",
      zerolinecolor: "#27272a",
    },
    yaxis: {
      title: { text: "Response" },
      gridcolor: "#27272a",
      zerolinecolor: "#27272a",
    },
    legend: {
      orientation: "h" as const,
      y: -0.2,
      font: { color: "#a1a1aa" },
    },
    margin: { t: 20, b: 60, l: 60, r: 20 },
    clickmode: isInteractive ? "event" : undefined,
    cursor: isInteractive ? "pointer" : undefined,
  };

  const config = {
    displayModeBar: isInteractive,
    responsive: true,
    modeBarButtonsToRemove: ["lasso2d", "select2d"] as string[],
  };

  return (
    <div className={cn("space-y-4", className)}>
      <Plot
        data={traces}
        layout={layout}
        config={config}
        style={{ width: "100%" }}
        useResizeHandler
        onClick={isInteractive ? handlePlotClick : undefined}
      />

      {/* Per-curve constraint controls (interactive only) */}
      {isInteractive && curves.length > 0 && (
        <div className="space-y-3">
          {curves.map((curve) => (
            <CurveControls
              key={curve.id}
              curve={curve}
              excludedIndices={getExcluded(curve.id)}
              constraints={getConstraints(curve)}
              onConstraintChange={(patch) => handleConstraintChange(curve, patch)}
              onReset={() => handleReset(curve)}
              isPending={isRefitting}
            />
          ))}
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {curves.map((curve) => {
          const totalPoints =
            (curve.raw_data?.length ?? 0) + (curve.excluded_points?.length ?? 0);
          const localExcluded = getExcluded(curve.id);
          return (
            <SummaryCard
              key={curve.id}
              curve={curve}
              excludedCount={localExcluded.size}
              totalPoints={totalPoints}
              isInteractive={isInteractive}
              onClassify={handleClassify}
              isClassifying={isClassifying}
            />
          );
        })}
      </div>
    </div>
  );
}
