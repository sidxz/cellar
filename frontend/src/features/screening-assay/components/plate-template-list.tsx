"use client";

import { useMemo, useState } from "react";
import { Grid3x3, Plus, Trash2 } from "lucide-react";
import type { ColDef } from "ag-grid-community";
import { PageHeader } from "@/shared/components/page-header";
import { ConfirmDeleteDialog } from "@/shared/components/confirm-delete-dialog";
import { Button } from "@/shared/components/ui/button";
import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { MemberName } from "@/shared/components/entity-name";
import { usePlateTemplates, useDeletePlateTemplate } from "../hooks/use-plate-templates";
import { CreatePlateTemplateDialog } from "./create-plate-template-dialog";
import type { PlateTemplate } from "../types";
import { PLATE_FORMAT_LABELS, type PlateFormat } from "../types";

export function PlateTemplateListPage() {
  const { data: templates, isLoading, error } = usePlateTemplates();
  const deleteMutation = useDeletePlateTemplate();
  const [createOpen, setCreateOpen] = useState(false);
  const [editTemplate, setEditTemplate] = useState<PlateTemplate | undefined>();
  const [deleteTarget, setDeleteTarget] = useState<PlateTemplate | null>(null);

  const columnDefs = useMemo<ColDef<PlateTemplate>[]>(
    () => [
      { headerName: "Name", field: "name", flex: 1, minWidth: 180 },
      {
        headerName: "Format",
        field: "format",
        width: 100,
        valueFormatter: (p) =>
          PLATE_FORMAT_LABELS[p.value as PlateFormat] ?? p.value,
      },
      {
        headerName: "Description",
        field: "description",
        flex: 1,
        minWidth: 180,
        valueFormatter: (p) => p.value ?? "\u2014",
      },
      {
        headerName: "Created By",
        field: "created_by",
        width: 160,
        cellRenderer: ({ value }: { value: string | undefined }) =>
          value ? <MemberName id={value} /> : "\u2014",
      },
      {
        headerName: "",
        width: 60,
        sortable: false,
        filter: false,
        cellRenderer: ({ data }: { data: PlateTemplate | undefined }) =>
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
    []
  );

  const handleRowClick = (template: PlateTemplate) => {
    setEditTemplate(template);
    setCreateOpen(true);
  };

  const handleOpenChange = (open: boolean) => {
    setCreateOpen(open);
    if (!open) setEditTemplate(undefined);
  };

  if (error) {
    return (
      <div>
        <PageHeader title="Plate Templates" subtitle="Manage plate layout templates for screening runs.">
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            New Plate Template
          </Button>
        </PageHeader>
        <ErrorState message="Failed to load plate templates. Is the backend running?" details={error.message} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Plate Templates" subtitle="Manage plate layout templates for screening runs.">
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          New Plate Template
        </Button>
      </PageHeader>

      <DataGrid<PlateTemplate>
        rowData={templates}
        columnDefs={columnDefs}
        loading={isLoading}
        height="400px"
        suppressFilters
        onRowClick={handleRowClick}
        emptyState={
          <EmptyState
            icon={Grid3x3}
            title="No plate templates"
            description="Design a plate layout template for your screening runs."
            action={{ label: "New Plate Template", onClick: () => setCreateOpen(true), icon: Plus }}
          />
        }
      />

      <CreatePlateTemplateDialog
        open={createOpen}
        onOpenChange={handleOpenChange}
        plateTemplate={editTemplate}
      />

      <ConfirmDeleteDialog
        open={!!deleteTarget}
        onOpenChange={(open) => { if (!open) setDeleteTarget(null); }}
        title="Delete plate template?"
        description={`This will permanently delete "${deleteTarget?.name ?? ""}". Existing runs using this template will not be affected.`}
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
