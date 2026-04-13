"use client";

import { memo, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import {
  X,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  ExternalLink,
} from "lucide-react";
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
import type { ProtocolCurveGroup, CurveDetail } from "../../types";

// ─── Dynamic Plotly import (must NOT be SSR'd) ────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const Plot = dynamic<any>(
  () => import("react-plotly.js").then((mod) => mod.default as any),
  { ssr: false }
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

// ─── Props ─────────────────────────────────────────────────────────────────

interface CompoundDetailPanelProps {
  molecule: Molecule | null;
  visibleProtocolIds: string[];
  currentIndex: number;
  totalCount: number;
  onNavigate: (direction: "prev" | "next") => void;
  onClose: () => void;
}

// ─── 4PL sigmoid curve generator ───────────────────────────────────────────

function generate4PLPoints(
  ic50: number,
  hillSlope: number,
  top: number,
  bottom: number,
  xMin: number,
  xMax: number,
): { x: number[]; y: number[] } {
  const logMin = Math.log10(xMin);
  const logMax = Math.log10(xMax);
  const xs: number[] = [];
  const ys: number[] = [];

  for (let i = 0; i <= 100; i++) {
    const logX = logMin + (logMax - logMin) * (i / 100);
    const x = Math.pow(10, logX);
    const y = bottom + (top - bottom) / (1 + Math.pow(x / ic50, hillSlope));
    xs.push(x);
    ys.push(y);
  }
  return { x: xs, y: ys };
}

// ─── CurveChart (single interactive Plotly chart) ──────────────────────────

interface CurveChartProps {
  curve: CurveDetail;
}

const CurveChart = memo(function CurveChart({ curve }: CurveChartProps) {
  const rawX = curve.raw_data.map((pt) => pt.x);
  const rawY = curve.raw_data.map((pt) => pt.y);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const traces: any[] = [
    {
      x: rawX,
      y: rawY,
      mode: "markers",
      type: "scatter" as const,
      marker: { color: "#a78bfa", size: 6 },
      name: "Data",
      hovertemplate: "Conc: %{x:.3e}<br>Response: %{y:.1f}<extra></extra>",
    },
  ];

  // Fitted sigmoid
  if (curve.fitted_value > 0) {
    const xMin = Math.min(...rawX);
    const xMax = Math.max(...rawX);
    if (xMin > 0 && xMax > xMin) {
      const fitted = generate4PLPoints(
        curve.fitted_value,
        curve.hill_slope,
        curve.top,
        curve.bottom,
        xMin * 0.3,
        xMax * 3,
      );
      traces.push({
        x: fitted.x,
        y: fitted.y,
        mode: "lines",
        type: "scatter" as const,
        line: { color: "#60a5fa", width: 2 },
        name: "Fit",
        hoverinfo: "skip" as const,
      });
    }
  }

  return (
    <Plot
      data={traces}
      layout={{
        height: 250,
        margin: { l: 50, r: 16, t: 8, b: 40 },
        xaxis: {
          type: "log",
          title: { text: `Concentration (${curve.fitted_unit})`, font: { size: 10, color: "#a1a1aa" } },
          showgrid: true,
          gridcolor: "rgba(63,63,70,0.3)",
          tickfont: { size: 9, color: "#71717a" },
          zeroline: false,
        },
        yaxis: {
          title: { text: "Response (%)", font: { size: 10, color: "#a1a1aa" } },
          showgrid: true,
          gridcolor: "rgba(63,63,70,0.3)",
          tickfont: { size: 9, color: "#71717a" },
          zeroline: false,
        },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        showlegend: false,
      }}
      config={{ displayModeBar: false }}
      useResizeHandler
      style={{ width: "100%", height: 250 }}
    />
  );
});

// ─── Curve param grid ──────────────────────────────────────────────────────

function CurveParamGrid({ curve }: { curve: CurveDetail }) {
  return (
    <div className="grid grid-cols-4 gap-x-3 gap-y-1 text-xs">
      <div>
        <span className="text-muted-foreground">Fitted</span>
        <p className="font-mono tabular-nums">
          {curve.fitted_value.toExponential(2)} {curve.fitted_unit}
        </p>
      </div>
      <div>
        <span className="text-muted-foreground">Hill</span>
        <p className="font-mono tabular-nums">{curve.hill_slope.toFixed(2)}</p>
      </div>
      <div>
        <span className="text-muted-foreground">R&sup2;</span>
        <p className="font-mono tabular-nums">{curve.r_squared.toFixed(3)}</p>
      </div>
      <div>
        <span className="text-muted-foreground">Class</span>
        <p>{curve.curve_class ?? "\u2014"}</p>
      </div>
    </div>
  );
}

// ─── ProtocolCurveSection ──────────────────────────────────────────────────

interface ProtocolCurveSectionProps {
  group: ProtocolCurveGroup;
  defaultExpanded?: boolean;
}

function ProtocolCurveSection({ group, defaultExpanded = true }: ProtocolCurveSectionProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  // Pick best curve by R-squared
  const sortedCurves = useMemo(
    () => [...group.curves].sort((a, b) => b.r_squared - a.r_squared),
    [group.curves],
  );
  const bestCurve = sortedCurves[0];

  if (!bestCurve) return null;

  return (
    <div className="space-y-2">
      <button
        type="button"
        className="flex w-full items-center justify-between text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="space-y-0.5">
          <p className="text-sm font-medium">{group.protocol_name}</p>
          <p className="text-xs text-muted-foreground">{bestCurve.curve_type}</p>
        </div>
        {expanded ? (
          <ChevronUp className="h-4 w-4 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        )}
      </button>

      {expanded && (
        <div className="space-y-3">
          {group.curves.length > 1 && (
            <p className="text-xs text-muted-foreground">
              {group.curves.length} runs &mdash; showing best (R&sup2; = {bestCurve.r_squared.toFixed(3)})
            </p>
          )}
          <CurveChart curve={bestCurve} />
          <CurveParamGrid curve={bestCurve} />
        </div>
      )}
    </div>
  );
}

// ─── Lifecycle badge variant mapping ───────────────────────────────────────

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

// ─── Main panel ────────────────────────────────────────────────────────────

export function CompoundDetailPanel({
  molecule,
  visibleProtocolIds,
  currentIndex,
  totalCount,
  onNavigate,
  onClose,
}: CompoundDetailPanelProps) {
  const { data: activityDetail, isLoading } = useMoleculeActivityDetail(
    molecule?.id ?? null,
  );

  const [othersExpanded, setOthersExpanded] = useState(false);

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

  if (!molecule) return null;

  const smiles = molecule.structure?.smiles;
  const descriptors = molecule.descriptors;

  return (
    <div className="flex h-full flex-col border-l border-border bg-background">
      {/* ── Header ── */}
      <div className="flex items-start gap-3 border-b border-border px-4 py-3">
        {smiles && <StructureThumbnail smiles={smiles} size={80} />}
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">
                {molecule.registration_number}
              </p>
              {molecule.name && (
                <p className="truncate text-xs text-muted-foreground">
                  {molecule.name}
                </p>
              )}
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 shrink-0"
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

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            {descriptors?.molecular_weight != null && (
              <span>
                MW <span className="font-mono tabular-nums">{descriptors.molecular_weight.toFixed(1)}</span>
              </span>
            )}
            {descriptors?.logp != null && (
              <span>
                LogP <span className="font-mono tabular-nums">{descriptors.logp.toFixed(2)}</span>
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <Badge variant={lifecycleBadgeVariant(molecule.lifecycle_stage)}>
              {LIFECYCLE_LABELS[molecule.lifecycle_stage] ?? molecule.lifecycle_stage}
            </Badge>
            <Link
              href={`/compounds/${molecule.id}`}
              className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
            >
              Open full detail
              <ExternalLink className="h-3 w-3" />
            </Link>
          </div>
        </div>
      </div>

      {/* ── Navigation bar ── */}
      {totalCount > 1 && (
        <div className="flex items-center justify-center gap-2 border-b border-border px-4 py-2">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            disabled={currentIndex === 0}
            onClick={() => onNavigate("prev")}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm font-mono tabular-nums text-muted-foreground">
            {currentIndex + 1} / {totalCount}
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            disabled={currentIndex === totalCount - 1}
            onClick={() => onNavigate("next")}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}

      {/* ── Scrollable content ── */}
      <ScrollArea className="flex-1">
        <div className="space-y-6 px-4 py-4">
          {/* Loading state */}
          {isLoading && (
            <div className="space-y-4">
              <Skeleton className="h-[250px] w-full" />
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
            </div>
          )}

          {/* No activity data */}
          {!isLoading && (!activityDetail || activityDetail.protocols.length === 0) && (
            <p className="text-sm text-muted-foreground">
              No dose-response data available for this compound.
            </p>
          )}

          {/* Selected protocol curves */}
          {!isLoading && selected.length > 0 && (
            <div className="space-y-4">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Selected Protocols
              </h4>
              {selected.map((group) => (
                <ProtocolCurveSection
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
                  Also tested in {others.length} other protocol{others.length > 1 ? "s" : ""}
                </span>
                {othersExpanded ? (
                  <ChevronUp className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                )}
              </button>

              {othersExpanded &&
                others.map((group) => (
                  <ProtocolCurveSection
                    key={group.protocol_id}
                    group={group}
                    defaultExpanded={false}
                  />
                ))}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
