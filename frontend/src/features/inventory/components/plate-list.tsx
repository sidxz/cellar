"use client";

import { TagFilter, type TagFilterValue } from "@/features/tagging/components/tag-filter";
import { ConfirmDeleteDialog } from "@/shared/components/confirm-delete-dialog";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { PageHeader } from "@/shared/components/page-header";
import { StatusBadge } from "@/shared/components/status-badge";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { FileUp, FlaskConical, Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useDeletePlate, usePlates } from "../hooks/use-plates";
import type { PlateStatus, PlateType, RegisteredPlate } from "../types/plates";
import { plateStatusLabels, plateTypeLabels } from "../types/plates";
import { RegisterPlateDialog } from "./register-plate-dialog";

const PLATE_FORMATS = ["6", "12", "24", "48", "96", "384", "1536"] as const;

export function PlateList() {
  const router = useRouter();
  const [registerOpen, setRegisterOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<RegisteredPlate | null>(null);
  const [filterType, setFilterType] = useState<string>("__all__");
  const [filterStatus, setFilterStatus] = useState<string>("__all__");
  const [filterFormat, setFilterFormat] = useState<string>("__all__");
  const [tagFilter, setTagFilter] = useState<TagFilterValue>({ tagIds: [], tagLogic: "any" });

  const {
    data: plates,
    isLoading,
    error,
  } = usePlates({
    plate_type: filterType === "__all__" ? undefined : filterType,
    status: filterStatus === "__all__" ? undefined : filterStatus,
    format: filterFormat === "__all__" ? undefined : filterFormat,
    tags: tagFilter.tagIds,
    tagLogic: tagFilter.tagLogic,
  });
  const deleteMutation = useDeletePlate();

  const columnDefs = useMemo<ColDef<RegisteredPlate>[]>(
    () => [
      {
        headerName: "Barcode",
        field: "barcode",
        flex: 1,
        minWidth: 140,
        cellClass: "font-mono text-sm",
        cellRenderer: ({ data }: { data: RegisteredPlate | undefined }) =>
          data ? (
            <button
              className="text-primary hover:underline font-mono text-sm"
              onClick={(e) => {
                e.stopPropagation();
                router.push(`/inventory/plates/${data.id}`);
              }}
            >
              {data.barcode}
            </button>
          ) : null,
      },
      {
        headerName: "Label",
        field: "plate_label",
        flex: 1,
        minWidth: 160,
      },
      {
        headerName: "Format",
        field: "format",
        width: 90,
        valueFormatter: (p) => (p.value ? `${p.value}-well` : "\u2014"),
      },
      {
        headerName: "Type",
        field: "plate_type",
        width: 150,
        cellRenderer: (params: ICellRendererParams<RegisteredPlate>) =>
          params.value ? (
            <Badge variant="outline">
              {plateTypeLabels[params.value as PlateType] ?? params.value}
            </Badge>
          ) : null,
      },
      {
        headerName: "Status",
        field: "status",
        width: 120,
        cellRenderer: (params: ICellRendererParams<RegisteredPlate>) =>
          params.value ? <StatusBadge status={params.value as PlateStatus} /> : null,
      },
      {
        headerName: "Wells Mapped",
        width: 130,
        valueGetter: (p) => {
          if (!p.data?.well_map) return "0";
          return String(Object.keys(p.data.well_map).length);
        },
      },
      {
        headerName: "",
        width: 60,
        sortable: false,
        filter: false,
        cellRenderer: ({ data }: { data: RegisteredPlate | undefined }) =>
          data ? (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-destructive"
              onClick={(e) => {
                e.stopPropagation();
                setDeleteTarget(data);
              }}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          ) : null,
      },
    ],
    [router],
  );

  if (error) {
    return (
      <div>
        <PageHeader title="Plates" subtitle="Manage registered plates and well mappings.">
          <Button variant="outline" onClick={() => router.push("/inventory/plates/import")}>
            <FileUp className="mr-2 h-4 w-4" />
            Import Data
          </Button>
          <Button onClick={() => setRegisterOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Register Plate
          </Button>
        </PageHeader>
        <ErrorState
          message="Failed to load plates. Is the backend running?"
          details={error.message}
        />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Plates" subtitle="Manage registered plates and well mappings.">
        <Button variant="outline" onClick={() => router.push("/inventory/plates/import")}>
          <FileUp className="mr-2 h-4 w-4" />
          Import Data
        </Button>
        <Button onClick={() => setRegisterOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Register Plate
        </Button>
      </PageHeader>

      {/* Filter bar */}
      <div className="mb-4 flex flex-wrap gap-2">
        <Select value={filterType} onValueChange={setFilterType}>
          <SelectTrigger className="w-[170px]">
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All types</SelectItem>
            {(Object.keys(plateTypeLabels) as PlateType[]).map((t) => (
              <SelectItem key={t} value={t}>
                {plateTypeLabels[t]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="w-[150px]">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All statuses</SelectItem>
            {(Object.keys(plateStatusLabels) as PlateStatus[]).map((s) => (
              <SelectItem key={s} value={s}>
                {plateStatusLabels[s]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filterFormat} onValueChange={setFilterFormat}>
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="All formats" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All formats</SelectItem>
            {PLATE_FORMATS.map((f) => (
              <SelectItem key={f} value={f}>
                {f}-well
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <TagFilter value={tagFilter} onChange={setTagFilter} />
      </div>

      <DataGrid<RegisteredPlate>
        rowData={plates}
        columnDefs={columnDefs}
        loading={isLoading}
        height="500px"
        suppressFilters
        onRowClick={(plate) => router.push(`/inventory/plates/${plate.id}`)}
        emptyState={
          <EmptyState
            icon={FlaskConical}
            title="No plates"
            description="Register a plate to start tracking compound locations."
            action={{ label: "Register Plate", onClick: () => setRegisterOpen(true), icon: Plus }}
          />
        }
      />

      <RegisterPlateDialog open={registerOpen} onOpenChange={setRegisterOpen} />

      <ConfirmDeleteDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title="Delete plate?"
        description={`This will permanently delete plate "${deleteTarget?.barcode ?? ""}" (${deleteTarget?.plate_label ?? ""}). Well mappings will be lost.`}
        onConfirm={() => {
          if (deleteTarget) {
            deleteMutation.mutate(deleteTarget.id, {
              onSuccess: () => setDeleteTarget(null),
            });
          }
        }}
        isPending={deleteMutation.isPending}
      />
    </div>
  );
}
