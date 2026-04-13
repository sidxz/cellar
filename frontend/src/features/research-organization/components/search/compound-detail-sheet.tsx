"use client";

import { memo, useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import {
  X,
  ChevronUp,
  ChevronDown,
  ExternalLink,
} from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetTitle,
  SheetDescription,
} from "@/shared/components/ui/sheet";
import { Button } from "@/shared/components/ui/button";
import { Badge } from "@/shared/components/ui/badge";
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { StructureThumbnail } from "@/shared/components/chemistry";
import type { Molecule } from "@/features/chemical-registration/types";
import {
  LIFECYCLE_LABELS,
  type LifecycleStage,
} from "@/features/chemical-registration/types";
import { useMoleculeActivityDetail } from "../../hooks/use-molecule-activity-detail";
import { generate4PLPoints } from "../../lib/curve-math";
import type { ProtocolCurveGroup, CurveDetail } from "../../types";

// ─── Dynamic Plotly import (must NOT be SSR'd) ────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const Plot = dynamic<any>(
  () => import("react-plotly.js").then((mod) => mod.default as any),
  { ssr: false },
) as React.ComponentType<{
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  layout: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  config?: any;
  style?: React.CSSProperties;
  useResizeHandler?: boolean;
}>;

// ─── Tabs ─────────────────────────────────────────────────────────────────

// Tabs removed — only Activity content shown for now.
// Inventory and History tabs will be added when those APIs are ready.

// ─── Props ────────────────────────────────────────────────────────────────

interface CompoundDetailSheetProps {
  molecule: Molecule | null;
  visibleProtocolIds: string[];
  currentIndex: number;
  totalCount: number;
  onNavigate: (direction: "prev" | "next") => void;
  onClose: () => void;
}

// ─── CurveChart (single interactive Plotly chart) ─────────────────────────

interface CurveChartProps {
  curve: CurveDetail;
}

const CurveChart = memo(function CurveChart({ curve }: CurveChartProps) {
  const rawData = curve.raw_data ?? [];
  if (rawData.length === 0) {
    return (
      <div className="flex h-[260px] items-center justify-center text-xs text-muted-foreground">
        No data points available
      </div>
    );
  }
  const rawX = rawData.map((pt) => pt.x);
  const rawY = rawData.map((pt) => pt.y);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const traces: any[] = [
    {
      x: rawX,
      y: rawY,
      mode: "markers",
      type: "scatter" as const,
      marker: { color: "#a5b4fc", size: 6 },
      name: "Data",
      hovertemplate: "Conc: %{x:.3e}<br>Response: %{y:.1f}<extra></extra>",
    },
  ];

  // Fitted sigmoid + IC50 crosshair
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const shapes: any[] = [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const annotations: any[] = [];

  const hasFit = isFinite(curve.fitted_value) && curve.fitted_value !== 0;
  if (hasFit) {
    const fitted = generate4PLPoints(
      rawData,
      curve.fitted_value,
      curve.hill_slope,
      curve.top,
      curve.bottom,
      { numPoints: 100, rangeExtension: 0.5 },
    );
    if (fitted.x.length > 0) {
      traces.push({
        x: fitted.x,
        y: fitted.y,
        mode: "lines",
        type: "scatter" as const,
        line: { color: "#818cf8", width: 2 },
        name: "Fit",
        hoverinfo: "skip" as const,
      });
    }

    // IC50 crosshair: dotted lines + orange marker + value label
    const midY = (curve.top + curve.bottom) / 2;
    const ec50 = curve.fitted_value;
    const unitLabel = curve.fitted_unit ? ` ${curve.fitted_unit}` : "";

    // Horizontal dotted line at midpoint
    shapes.push({
      type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: midY, y1: midY,
      line: { color: "#71717a", width: 1, dash: "dot" }, opacity: 0.4,
    });
    // Vertical dotted line at IC50
    shapes.push({
      type: "line", xref: "x", x0: ec50, x1: ec50, yref: "paper", y0: 0, y1: 1,
      line: { color: "#71717a", width: 1, dash: "dot" }, opacity: 0.4,
    });
    // Orange marker at intersection
    traces.push({
      type: "scatter", mode: "markers", x: [ec50], y: [midY],
      marker: { color: "#fbbf24", size: 9, line: { color: "#ef4444", width: 2 }, symbol: "circle" },
      showlegend: false,
      hovertemplate: `${curve.curve_type.toUpperCase()} = ${ec50.toPrecision(3)}${unitLabel}<extra></extra>`,
    });
    // Value annotation
    annotations.push({
      x: Math.log10(ec50), y: midY, xref: "x", yref: "y",
      text: `<b>${ec50.toPrecision(3)}${unitLabel}</b>`,
      showarrow: true, arrowhead: 2, arrowsize: 0.8, arrowcolor: "#ef4444",
      ax: 0, ay: -30, font: { color: "#ef4444", size: 11 },
    });
  }

  return (
    <Plot
      data={traces}
      layout={{
        height: 260,
        margin: { l: 50, r: 16, t: 8, b: 40 },
        xaxis: {
          type: "log",
          title: {
            text: `Concentration (${curve.fitted_unit})`,
            font: { size: 10, color: "#a1a1aa" },
          },
          showgrid: true,
          gridcolor: "#1e1e22",
          tickfont: { size: 9, color: "#71717a" },
          zeroline: false,
        },
        yaxis: {
          title: {
            text: "Response (%)",
            font: { size: 10, color: "#a1a1aa" },
          },
          showgrid: true,
          gridcolor: "#1e1e22",
          tickfont: { size: 9, color: "#71717a" },
          zeroline: false,
        },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        showlegend: false,
        shapes,
        annotations,
      }}
      config={{ displayModeBar: false }}
      useResizeHandler
      style={{ width: "100%", height: 260 }}
    />
  );
});

// ─── CurveParamGrid ───────────────────────────────────────────────────────

const CURVE_CLASS_COLORS: Record<string, string> = {
  F: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  P: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  I: "bg-red-500/20 text-red-400 border-red-500/30",
};

function CurveParamGrid({ curve }: { curve: CurveDetail }) {
  const classColor =
    curve.curve_class && CURVE_CLASS_COLORS[curve.curve_class]
      ? CURVE_CLASS_COLORS[curve.curve_class]
      : undefined;

  return (
    <div className="grid grid-cols-4 gap-px rounded-md border border-border bg-border">
      <div className="bg-background px-3 py-2">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Fitted
        </span>
        <p className="mt-0.5 font-mono text-xs tabular-nums">
          {curve.fitted_value.toExponential(2)} {curve.fitted_unit}
        </p>
      </div>
      <div className="bg-background px-3 py-2">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Hill Slope
        </span>
        <p className="mt-0.5 font-mono text-xs tabular-nums">
          {curve.hill_slope.toFixed(2)}
        </p>
      </div>
      <div className="bg-background px-3 py-2">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          R&sup2;
        </span>
        <p className="mt-0.5 font-mono text-xs tabular-nums">
          {curve.r_squared.toFixed(3)}
        </p>
      </div>
      <div className="bg-background px-3 py-2">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Curve Class
        </span>
        <p className="mt-0.5">
          {curve.curve_class ? (
            <span
              className={`inline-flex items-center rounded-sm border px-1.5 py-0.5 text-xs font-semibold ${classColor ?? "bg-muted text-muted-foreground border-border"}`}
            >
              {curve.curve_class}
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">&mdash;</span>
          )}
        </p>
      </div>
    </div>
  );
}

// ─── ProtocolCard ─────────────────────────────────────────────────────────

interface ProtocolCardProps {
  group: ProtocolCurveGroup;
  defaultExpanded?: boolean;
}

function ProtocolCard({ group, defaultExpanded = true }: ProtocolCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  // Pick best curve by R-squared
  const sortedCurves = useMemo(
    () => [...group.curves].sort((a, b) => b.r_squared - a.r_squared),
    [group.curves],
  );
  const bestCurve = sortedCurves[0];

  if (!bestCurve) return null;

  return (
    <div className="rounded-lg border border-border bg-card">
      <button
        type="button"
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-muted/30"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="min-w-0 space-y-0.5">
          <p className="truncate text-sm font-medium">{group.protocol_name}</p>
          <p className="text-xs text-muted-foreground">{bestCurve.curve_type}</p>
        </div>
        {expanded ? (
          <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
      </button>

      {expanded && (
        <div className="space-y-3 border-t border-border px-4 py-3">
          {group.curves.length > 1 && (
            <p className="text-xs text-muted-foreground">
              {group.curves.length} runs &mdash; showing best (R&sup2; ={" "}
              {bestCurve.r_squared.toFixed(3)})
            </p>
          )}
          <CurveChart curve={bestCurve} />
          <CurveParamGrid curve={bestCurve} />
        </div>
      )}
    </div>
  );
}

// ─── Lifecycle badge variant mapping ──────────────────────────────────────

function lifecycleBadgeVariant(
  stage: LifecycleStage,
): "default" | "secondary" | "success" | "warning" | "destructive" | "outline" {
  switch (stage) {
    case "hit":
    case "lead":
      return "success";
    case "preclinical_candidate":
    case "development_candidate":
      return "default";
    case "deprioritized":
      return "warning";
    case "archived":
      return "destructive";
    default:
      return "secondary";
  }
}

// ─── Main Component ───────────────────────────────────────────────────────

export function CompoundDetailSheet({
  molecule,
  visibleProtocolIds,
  currentIndex,
  totalCount,
  onNavigate,
  onClose,
}: CompoundDetailSheetProps) {
  const [othersExpanded, setOthersExpanded] = useState(false);

  const { data: activityDetail, isLoading } = useMoleculeActivityDetail(
    molecule?.id ?? null,
  );

  // Reset expanded state when molecule changes
  useEffect(() => {
    setOthersExpanded(false);
  }, [molecule?.id]);

  // Keyboard navigation: Arrow Up/Down to move between results
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!molecule) return;

      if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        e.preventDefault();
        if (e.key === "ArrowUp" && currentIndex > 0) {
          onNavigate("prev");
        } else if (e.key === "ArrowDown" && currentIndex < totalCount - 1) {
          onNavigate("next");
        }
      }
    },
    [molecule, currentIndex, totalCount, onNavigate],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // Split protocols into selected (visible columns) and others
  const { selected, others } = useMemo(() => {
    if (!activityDetail?.protocols) return { selected: [], others: [] };
    const visibleSet = new Set(visibleProtocolIds);
    const sel: ProtocolCurveGroup[] = [];
    const oth: ProtocolCurveGroup[] = [];
    for (const group of activityDetail.protocols) {
      if (visibleSet.has(group.protocol_id)) {
        sel.push(group);
      } else {
        oth.push(group);
      }
    }
    return { selected: sel, others: oth };
  }, [activityDetail, visibleProtocolIds]);

  const smiles = molecule?.structure?.smiles;
  const descriptors = molecule?.descriptors;

  return (
    <Sheet open={!!molecule} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className="w-[60vw] max-w-[900px] min-w-[500px] gap-0 p-0 sm:max-w-none"
      >
        {/* Accessible title (visually hidden) */}
        <SheetTitle className="sr-only">
          Compound detail: {molecule?.registration_number ?? ""}
        </SheetTitle>
        <SheetDescription className="sr-only">
          Detailed activity data and properties for the selected compound.
        </SheetDescription>

        {molecule && (
          <div className="flex h-full flex-col">
            {/* ── Header ── */}
            <div className="flex items-start gap-4 border-b border-border px-5 py-4">
              {smiles && <StructureThumbnail smiles={smiles} size={80} />}
              <div className="min-w-0 flex-1 space-y-1.5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-base font-semibold">
                      {molecule.registration_number}
                    </p>
                    {molecule.name && (
                      <p className="truncate text-sm text-muted-foreground">
                        {molecule.name}
                      </p>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0"
                    onClick={onClose}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>

                {molecule.molecular_formula && (
                  <p className="text-xs text-muted-foreground">
                    {molecule.molecular_formula}
                  </p>
                )}

                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  {descriptors?.molecular_weight != null && (
                    <span>
                      MW{" "}
                      <span className="font-mono tabular-nums">
                        {descriptors.molecular_weight.toFixed(1)}
                      </span>
                    </span>
                  )}
                  {descriptors?.logp != null && (
                    <span>
                      LogP{" "}
                      <span className="font-mono tabular-nums">
                        {descriptors.logp.toFixed(2)}
                      </span>
                    </span>
                  )}
                </div>

                <Badge variant={lifecycleBadgeVariant(molecule.lifecycle_stage)}>
                  {LIFECYCLE_LABELS[molecule.lifecycle_stage] ??
                    molecule.lifecycle_stage}
                </Badge>
              </div>
            </div>

            {/* ── Navigation bar ── */}
            {totalCount > 1 && (
              <div className="flex items-center justify-between border-b border-border px-5 py-2">
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    disabled={currentIndex === 0}
                    onClick={() => onNavigate("prev")}
                  >
                    <ChevronUp className="h-4 w-4" />
                  </Button>
                  <span className="font-mono text-sm tabular-nums text-muted-foreground">
                    {currentIndex + 1} / {totalCount}
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    disabled={currentIndex === totalCount - 1}
                    onClick={() => onNavigate("next")}
                  >
                    <ChevronDown className="h-4 w-4" />
                  </Button>
                </div>
                <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                  <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono">
                    &uarr;&darr;
                  </kbd>
                  <span>navigate</span>
                  <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono">
                    esc
                  </kbd>
                  <span>close</span>
                </div>
              </div>
            )}

            {/* ── Scrollable content ── */}
            <ScrollArea className="flex-1">
              <div className="space-y-5 px-5 py-4">
                {/* Loading state */}
                {isLoading && (
                  <div className="space-y-4">
                    <Skeleton className="h-[260px] w-full rounded-lg" />
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                  </div>
                )}

                {/* No activity data */}
                {!isLoading &&
                  (!activityDetail ||
                    activityDetail.protocols.length === 0) && (
                    <p className="py-8 text-center text-sm text-muted-foreground">
                      No dose-response data available for this compound.
                    </p>
                  )}

                {/* Selected protocol curves */}
                {!isLoading && selected.length > 0 && (
                  <div className="space-y-3">
                    <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      Selected Protocols
                    </h4>
                    {selected.map((group) => (
                      <ProtocolCard
                        key={group.protocol_id}
                        group={group}
                        defaultExpanded
                      />
                    ))}
                  </div>
                )}

                {/* Other protocols (collapsible) */}
                {!isLoading && others.length > 0 && (
                  <div className="space-y-3">
                    <button
                      type="button"
                      className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left hover:bg-muted/50"
                      onClick={() => setOthersExpanded((v) => !v)}
                    >
                      <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Also tested in {others.length} other protocol
                        {others.length > 1 ? "s" : ""}
                      </span>
                      {othersExpanded ? (
                        <ChevronUp className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      )}
                    </button>

                    {othersExpanded &&
                      others.map((group) => (
                        <ProtocolCard
                          key={group.protocol_id}
                          group={group}
                          defaultExpanded={false}
                        />
                      ))}
                  </div>
                )}
              </div>
            </ScrollArea>

            {/* ── Footer ── */}
            <div className="border-t border-border px-5 py-3">
              <Link
                href={`/compounds/${molecule.id}`}
                target="_blank"
                className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
              >
                Open full detail
                <ExternalLink className="h-3.5 w-3.5" />
              </Link>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
