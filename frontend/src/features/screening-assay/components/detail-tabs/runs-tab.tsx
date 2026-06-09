"use client";

import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState } from "@/shared/components/empty-state";
import { StatusBadge } from "@/shared/components/status-badge";
import { Badge } from "@/shared/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useWorkspaceMembers } from "@/shared/hooks/use-workspace-members";
import { shortId } from "@/shared/lib/utils";
import type { ColDef, ColGroupDef, ICellRendererParams } from "ag-grid-community";
import { FlaskConical } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import { useRunsByProtocol } from "../../hooks/use-runs";
import { deriveConditionColumns, readConditionCell } from "../../lib/conditions";
import { worstZPrime } from "../../lib/qc-metrics";
import { type Protocol, RUN_STATUS_LABELS, type Run } from "../../types";
interface RunsTabProps {
  protocol: Protocol;
  protocolId: string;
}

/** Coverage fraction (0–1, or null) → "42%" / "—". */
function coveragePct(fraction: number | null): string {
  return fraction == null ? "—" : `${Math.round(fraction * 100)}%`;
}

function zPrimeBadge(qcMetrics: Record<string, unknown> | null) {
  const zp = worstZPrime(qcMetrics);
  if (zp == null) return <span className="text-muted-foreground">&mdash;</span>;
  if (zp >= 0.5)
    return (
      <Badge variant="outline" className="border-success/40 text-success">
        {zp.toFixed(2)}
      </Badge>
    );
  if (zp >= 0)
    return (
      <Badge variant="outline" className="border-yellow-500/40 text-yellow-400">
        {zp.toFixed(2)}
      </Badge>
    );
  return (
    <Badge variant="outline" className="border-destructive/40 text-destructive">
      {zp.toFixed(2)}
    </Badge>
  );
}

export function RunsTab({ protocol, protocolId }: RunsTabProps) {
  const router = useRouter();
  const { data: runs, isLoading } = useRunsByProtocol(protocolId);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const { data: members } = useWorkspaceMembers();
  const { data: orgs } = useOrganizations();

  const memberName = useCallback(
    (userId: string) => members?.find((m) => m.user_id === userId)?.name ?? null,
    [members],
  );
  const orgName = useCallback(
    (orgId: string) => orgs?.find((o) => o.id === orgId)?.name ?? null,
    [orgs],
  );

  const filteredRuns = useMemo(() => {
    if (!runs) return [];
    if (statusFilter === "all") return runs;
    return runs.filter((r) => r.status === statusFilter);
  }, [runs, statusFilter]);

  // One column per condition variable any run records, typed from the protocol's
  // definitions. Derived from all runs (not the status-filtered subset) so the
  // column set is stable as the status filter changes.
  const conditionGroup = useMemo<ColGroupDef<Run> | null>(() => {
    const specs = deriveConditionColumns(runs, protocol.condition_definitions ?? []);
    if (specs.length === 0) return null;
    return {
      headerName: "Conditions",
      children: specs.map((spec) => ({
        colId: `cond:${spec.key}`,
        headerName:
          spec.type === "numeric" && spec.unit ? `${spec.label} (${spec.unit})` : spec.label,
        headerTooltip: spec.unit ? `${spec.label} (${spec.unit})` : spec.label,
        width: 140,
        minWidth: 110,
        // Per-column override: the grid sets suppressFilters, but condition
        // columns are sortable + filterable via the header menu.
        sortable: true,
        filter: spec.type === "numeric" ? "agNumberColumnFilter" : "agTextColumnFilter",
        valueGetter: (p) => readConditionCell(p.data?.conditions, spec),
        valueFormatter: (p) => (p.value == null || p.value === "" ? "—" : String(p.value)),
      })),
    };
  }, [runs, protocol.condition_definitions]);

  // Targets / collections are run associations — show each column only when at
  // least one run carries the data (mirrors the conditions rule). Derived from
  // all runs so the column set is stable across the status filter.
  const hasTargets = useMemo(() => (runs ?? []).some((r) => (r.targets?.length ?? 0) > 0), [runs]);
  const hasCollections = useMemo(
    () => (runs ?? []).some((r) => (r.collections?.length ?? 0) > 0),
    [runs],
  );

  const associationColumns = useMemo<ColDef<Run>[]>(() => {
    const cols: ColDef<Run>[] = [];
    if (hasTargets) {
      cols.push({
        colId: "targets",
        headerName: "Target",
        flex: 1,
        minWidth: 140,
        cellClass: "text-sm",
        filter: "agTextColumnFilter",
        // Plain text (with native ellipsis) reads cleaner in a dense grid than
        // pills; chips stay on the run-detail header.
        valueGetter: (p) => (p.data?.targets ?? []).map((t) => t.name).join(", "),
        valueFormatter: (p) => p.value || "—",
        tooltipValueGetter: (p) => (p.value as string) || null,
      });
    }
    if (hasCollections) {
      cols.push({
        colId: "collections",
        headerName: "Collection",
        flex: 1,
        minWidth: 150,
        cellClass: "text-sm",
        filter: "agTextColumnFilter",
        // "<library> (<coverage>%)" — names the library and keeps the coverage
        // number; full covered/total rides in the tooltip.
        valueGetter: (p) =>
          (p.data?.collections ?? [])
            .map((c) => `${c.name} (${coveragePct(c.fraction)})`)
            .join(", "),
        valueFormatter: (p) => p.value || "—",
        tooltipValueGetter: (p) => {
          const runCols = p.data?.collections ?? [];
          if (runCols.length === 0) return null;
          return runCols
            .map((c) => `${c.name}: ${c.covered}/${c.total} (${coveragePct(c.fraction)})`)
            .join(", ");
        },
      });
    }
    return cols;
  }, [hasTargets, hasCollections]);

  const columnDefs = useMemo<(ColDef<Run> | ColGroupDef<Run>)[]>(
    () => [
      {
        headerName: "Run Date",
        field: "run_date",
        width: 110,
        cellClass: "font-mono text-sm",
      },
      {
        headerName: "Scientist",
        field: "operator",
        width: 130,
        filter: "agTextColumnFilter",
        valueGetter: (p) =>
          p.data ? (memberName(p.data.operator) ?? shortId(p.data.operator)) : null,
      },
      ...associationColumns,
      ...(conditionGroup ? [conditionGroup] : []),
      {
        headerName: "Lab",
        field: "performed_at_org_id",
        width: 100,
        valueGetter: (p) =>
          p.data?.performed_at_org_id ? (orgName(p.data.performed_at_org_id) ?? null) : null,
        valueFormatter: (p) => p.value ?? "\u2014",
      },
      {
        headerName: "Molecules",
        field: "molecule_count",
        width: 90,
        valueFormatter: (p) => (p.value != null && p.value > 0 ? String(p.value) : "\u2014"),
      },
      { headerName: "Plates", field: "plate_count", width: 80 },
      {
        headerName: "Z\u2032",
        field: "qc_metrics",
        width: 90,
        cellRenderer: (params: ICellRendererParams<Run>) => zPrimeBadge(params.value),
      },
      {
        headerName: "Status",
        field: "status",
        width: 110,
        cellRenderer: (params: ICellRendererParams<Run>) => <StatusBadge status={params.value} />,
      },
      {
        headerName: "Notes",
        field: "notes",
        flex: 1,
        minWidth: 160,
        cellRenderer: (params: ICellRendererParams<Run>) => {
          const text = params.value as string | null;
          if (!text) return <span className="text-muted-foreground">&mdash;</span>;
          return (
            <span className="text-sm" title={text}>
              {text.length > 80 ? `${text.slice(0, 80)}...` : text}
            </span>
          );
        },
      },
    ],
    [memberName, orgName, conditionGroup, associationColumns],
  );

  return (
    <DataGrid<Run>
      rowData={filteredRuns}
      columnDefs={columnDefs}
      loading={isLoading}
      height="500px"
      suppressFilters
      // Status filter shares the grid's toolbar row, right of the quick filter.
      toolbarActions={
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="Filter by status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            {Object.entries(RUN_STATUS_LABELS).map(([v, l]) => (
              <SelectItem key={v} value={v}>
                {l}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
      onRowClick={(run) => router.push(`/assays/runs/${run.id}`)}
      emptyState={
        <EmptyState
          icon={FlaskConical}
          title="No runs"
          description="Create a run to start collecting screening data."
        />
      }
    />
  );
}
