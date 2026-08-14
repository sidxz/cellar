"use client";

import { SkeletonList } from "@/shared/components/skeleton-list";
import { CHART_AXIS, CHART_COLORS } from "@/shared/lib/chart-colors";
import { Plot } from "@/shared/lib/plotly";
import { cn } from "@/shared/lib/utils";
import { usePlateInsights } from "../hooks/use-plate-insights";
import { truncateLabel } from "./plate-group-tree-utils";

/** Horizontal-bar y-axis categories get a shorter cap than the tree's node
 * labels — the fixed 140px margin (below) has less room than the tree canvas. */
const CHART_LABEL_MAX = 24;

const plotConfig = { displayModeBar: false, responsive: true };
const plotStyle = { width: "100%", height: "350px" };

/** Categorical axes overflow once labels run long; angle them only then. */
function tickAngle(labels: string[]): number | undefined {
  return labels.some((label) => label.length > 8) ? -45 : undefined;
}

/** Shared Plotly layout conventions (house style, see activity-tab.tsx). */
function baseLayout(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    height: 350,
    autosize: true,
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: CHART_AXIS.label },
    margin: { l: 60, r: 20, t: 20, b: 60 },
    bargap: 0.3,
    ...overrides,
  };
}

interface PlateInsightsPanelProps {
  orgId: string | undefined;
}

export function PlateInsightsPanel({ orgId }: PlateInsightsPanelProps) {
  const { data, isLoading, error } = usePlateInsights(orgId);

  if (error) {
    return (
      <p className="text-sm text-destructive">
        {error instanceof Error ? error.message : "Failed to load insights"}
      </p>
    );
  }

  if (isLoading || !data) {
    return <SkeletonList rows={4} />;
  }

  if (data.total_plates === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-3 rounded-md border border-dashed">
        <p className="text-sm text-muted-foreground">No plates for this organization yet.</p>
      </div>
    );
  }

  const statusLabels = data.by_status.map((b) => b.key);
  const typeLabels = data.by_type.map((b) => b.key);
  const weekLabels = data.loan_activity_weekly.map((w) => w.week_start);
  // Top 10 by count, then reversed: Plotly renders horizontal-bar categories
  // bottom-to-top in array order, so the largest must be last to land on top.
  const topLocations = [...data.by_location]
    .sort((a, b) => b.count - a.count)
    .slice(0, 10)
    .reverse();
  const topGroups = [...data.group_sizes]
    .sort((a, b) => b.count - a.count)
    .slice(0, 10)
    .reverse();

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-md border bg-card p-4">
          <div className="text-2xl font-semibold">{data.total_plates}</div>
          <div className="text-sm text-muted-foreground">Total plates</div>
        </div>
        <div className="rounded-md border bg-card p-4">
          <div className="text-2xl font-semibold">{data.open_loans}</div>
          <div className="text-sm text-muted-foreground">Open loans</div>
        </div>
        <div className="rounded-md border bg-card p-4">
          <div
            className={cn("text-2xl font-semibold", data.overdue_count > 0 && "text-destructive")}
          >
            {data.overdue_count}
          </div>
          <div className="text-sm text-muted-foreground">Overdue</div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-md border bg-card p-4">
          <p className="text-sm font-medium">Plates by status</p>
          <Plot
            data={[
              {
                type: "bar",
                x: statusLabels,
                y: data.by_status.map((b) => b.count),
                marker: { color: CHART_COLORS.primary },
                hoverinfo: "x+y",
              },
            ]}
            layout={baseLayout({
              xaxis: { gridcolor: CHART_AXIS.grid, tickangle: tickAngle(statusLabels) },
              yaxis: { gridcolor: CHART_AXIS.grid, tickformat: ",d" },
            })}
            config={plotConfig}
            useResizeHandler
            style={plotStyle}
          />
        </div>

        <div className="rounded-md border bg-card p-4">
          <p className="text-sm font-medium">Plates by type</p>
          <Plot
            data={[
              {
                type: "bar",
                x: typeLabels,
                y: data.by_type.map((b) => b.count),
                marker: { color: CHART_COLORS.purple },
                hoverinfo: "x+y",
              },
            ]}
            layout={baseLayout({
              xaxis: { gridcolor: CHART_AXIS.grid, tickangle: tickAngle(typeLabels) },
              yaxis: { gridcolor: CHART_AXIS.grid, tickformat: ",d" },
            })}
            config={plotConfig}
            useResizeHandler
            style={plotStyle}
          />
        </div>

        <div className="rounded-md border bg-card p-4">
          <p className="text-sm font-medium">Loan activity (12 weeks)</p>
          <Plot
            data={[
              {
                type: "bar",
                name: "Requested",
                x: weekLabels,
                y: data.loan_activity_weekly.map((w) => w.requested),
                marker: { color: CHART_COLORS.primary },
                hoverinfo: "x+y",
              },
              {
                type: "bar",
                name: "Returned",
                x: weekLabels,
                y: data.loan_activity_weekly.map((w) => w.returned),
                marker: { color: CHART_COLORS.success },
                hoverinfo: "x+y",
              },
            ]}
            layout={baseLayout({
              barmode: "group",
              xaxis: { gridcolor: CHART_AXIS.grid, tickangle: tickAngle(weekLabels) },
              yaxis: { gridcolor: CHART_AXIS.grid, tickformat: ",d" },
              legend: { orientation: "h", y: -0.25, font: { color: CHART_AXIS.label } },
              margin: { l: 60, r: 20, t: 20, b: 80 },
            })}
            config={plotConfig}
            useResizeHandler
            style={plotStyle}
          />
        </div>

        <div className="rounded-md border bg-card p-4">
          <p className="text-sm font-medium">Storage occupancy (top 10)</p>
          <Plot
            data={[
              {
                type: "bar",
                orientation: "h",
                x: topLocations.map((l) => l.count),
                y: topLocations.map((l) => truncateLabel(l.name, CHART_LABEL_MAX)),
                customdata: topLocations.map((l) => l.name),
                hovertemplate: "%{customdata}: %{x}<extra></extra>",
                marker: { color: CHART_COLORS.neutral },
              },
            ]}
            layout={baseLayout({
              xaxis: { gridcolor: CHART_AXIS.grid, tickformat: ",d" },
              yaxis: { gridcolor: CHART_AXIS.grid },
              margin: { l: 140, r: 20, t: 20, b: 40 },
            })}
            config={plotConfig}
            useResizeHandler
            style={plotStyle}
          />
        </div>

        <div className="rounded-md border bg-card p-4">
          <p className="text-sm font-medium">Top groups (top 10)</p>
          <Plot
            data={[
              {
                type: "bar",
                orientation: "h",
                x: topGroups.map((g) => g.count),
                y: topGroups.map((g) => truncateLabel(g.name, CHART_LABEL_MAX)),
                customdata: topGroups.map((g) => g.name),
                hovertemplate: "%{customdata}: %{x}<extra></extra>",
                marker: { color: CHART_COLORS.primaryLight },
              },
            ]}
            layout={baseLayout({
              xaxis: { gridcolor: CHART_AXIS.grid, tickformat: ",d" },
              yaxis: { gridcolor: CHART_AXIS.grid },
              margin: { l: 140, r: 20, t: 20, b: 40 },
            })}
            config={plotConfig}
            useResizeHandler
            style={plotStyle}
          />
        </div>
      </div>
    </div>
  );
}
