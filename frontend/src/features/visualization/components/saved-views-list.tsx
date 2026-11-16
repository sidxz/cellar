"use client";

import { useProjects } from "@/features/research-organization/hooks/use-projects";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { PageHeader } from "@/shared/components/page-header";
import { useMemberNames } from "@/shared/hooks/use-workspace-members";
import { formatRelativeDate } from "@/shared/lib/format-date";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { ChartScatter } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo } from "react";
import { useSavedViews } from "../hooks/use-saved-views";
import { LEVELS } from "../lib/levels";
import type { SavedViewSummary } from "../types";

const viewHref = (v: SavedViewSummary) => `/assays/visualize/${v.id}`;

/** `/assays/visualize` with no source: every saved view the chemist can see, searchable by
 * name; a row opens its view. */
export function SavedViewsListPage() {
  const router = useRouter();
  const { data: views, isLoading, error } = useSavedViews();
  const { data: projects } = useProjects();
  const nameOf = useMemberNames();

  const columnDefs = useMemo<ColDef<SavedViewSummary>[]>(
    () => [
      {
        headerName: "Name",
        field: "name",
        flex: 1,
        minWidth: 200,
        cellRenderer: (p: ICellRendererParams<SavedViewSummary>) =>
          p.data && (
            <Link href={viewHref(p.data)} className="font-medium hover:underline">
              {p.data.name}
            </Link>
          ),
      },
      {
        headerName: "Level",
        width: 120,
        valueGetter: (p) => p.data && LEVELS[p.data.level].label,
      },
      {
        headerName: "Owner",
        width: 170,
        valueGetter: (p) => p.data && (nameOf(p.data.created_by) || "Unknown user"),
      },
      {
        headerName: "Sharing",
        width: 170,
        valueGetter: (p) =>
          p.data &&
          (p.data.visibility === "private"
            ? "Private"
            : (projects?.find((x) => x.id === p.data?.project_id)?.name ?? "Project")),
      },
      {
        headerName: "Last updated",
        field: "updated_at",
        width: 140,
        valueFormatter: (p) => (p.value ? formatRelativeDate(p.value as string) : "—"),
      },
    ],
    [nameOf, projects],
  );

  return (
    <div>
      <PageHeader title="Saved views" subtitle="Plots and filters saved from the workbench." />
      {error ? (
        <ErrorState message="Couldn't load the saved views" details={error.message} />
      ) : (
        <DataGrid<SavedViewSummary>
          rowData={views}
          columnDefs={columnDefs}
          loading={isLoading}
          height="calc(100vh - 200px)"
          suppressFilters
          searchPlaceholder="Search by name…"
          onRowClick={(v) => router.push(viewHref(v))}
          emptyState={
            <EmptyState
              icon={ChartScatter}
              title="No saved views yet"
              description="Open Visualize on a protocol or a run, set up the plots and filters, then click Save view… in the workbench header."
            />
          }
        />
      )}
    </div>
  );
}
