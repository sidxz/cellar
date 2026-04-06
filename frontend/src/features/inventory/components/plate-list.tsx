"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { FlaskConical, Plus, Trash2 } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { usePlates, useDeletePlate } from "../hooks/use-plates";
import { RegisterPlateDialog } from "./register-plate-dialog";
import type { RegisteredPlate, PlateStatus, PlateType } from "../types/plates";
import { plateTypeLabels, plateStatusLabels } from "../types/plates";

const PLATE_FORMATS = ["6", "12", "24", "48", "96", "384", "1536"] as const;

function plateStatusVariant(
  status: PlateStatus
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "registered":
      return "outline";
    case "in_use":
      return "default";
    case "stored":
      return "secondary";
    case "depleted":
    case "disposed":
      return "destructive";
    default:
      return "outline";
  }
}

export function PlateList() {
  const router = useRouter();
  const [registerOpen, setRegisterOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<RegisteredPlate | null>(null);
  const [filterType, setFilterType] = useState<string>("__all__");
  const [filterStatus, setFilterStatus] = useState<string>("__all__");
  const [filterFormat, setFilterFormat] = useState<string>("__all__");

  const { data: plates, isLoading, error } = usePlates({
    plate_type: filterType === "__all__" ? undefined : filterType,
    status: filterStatus === "__all__" ? undefined : filterStatus,
    format: filterFormat === "__all__" ? undefined : filterFormat,
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
          params.value ? (
            <Badge variant={plateStatusVariant(params.value as PlateStatus)}>
              {plateStatusLabels[params.value as PlateStatus] ?? params.value}
            </Badge>
          ) : null,
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
    [router]
  );

  if (error) {
    return (
      <div>
        <PageHeader onNew={() => setRegisterOpen(true)} />
        <div className="rounded-lg border border-dashed border-destructive/50 p-8 text-center">
          <p className="text-sm text-destructive">
            Failed to load plates. Is the backend running?
          </p>
          <p className="mt-1 text-xs text-muted-foreground">{error.message}</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader onNew={() => setRegisterOpen(true)} />

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
      </div>

      <DataGrid<RegisteredPlate>
        rowData={plates}
        columnDefs={columnDefs}
        loading={isLoading}
        height="500px"
        suppressFilters
        onRowClick={(plate) => router.push(`/inventory/plates/${plate.id}`)}
        emptyState={
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
            <FlaskConical className="h-12 w-12 text-muted-foreground/40" />
            <h3 className="mt-4 text-lg font-semibold">No plates</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Register a plate to start tracking compound locations.
            </p>
            <Button
              className="mt-4"
              size="sm"
              onClick={() => setRegisterOpen(true)}
            >
              <Plus className="mr-2 h-4 w-4" />
              Register Plate
            </Button>
          </div>
        }
      />

      <RegisterPlateDialog
        open={registerOpen}
        onOpenChange={setRegisterOpen}
      />

      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete plate?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete plate &ldquo;{deleteTarget?.barcode}&rdquo;
              ({deleteTarget?.plate_label}). Well mappings will be lost.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deleteTarget) {
                  deleteMutation.mutate(deleteTarget.id, {
                    onSuccess: () => setDeleteTarget(null),
                  });
                }
              }}
              disabled={deleteMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function PageHeader({ onNew }: { onNew: () => void }) {
  return (
    <div className="mb-6 flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Plates</h1>
        <p className="mt-1 text-muted-foreground">
          Manage registered plates and well mappings.
        </p>
      </div>
      <Button onClick={onNew}>
        <Plus className="mr-2 h-4 w-4" />
        Register Plate
      </Button>
    </div>
  );
}
