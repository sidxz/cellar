"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Download, FlaskConical, ListPlus, Plus, Upload } from "lucide-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { downloadFile } from "@/shared/lib/api/download";
import { useMolecules } from "../hooks/use-molecules";
import {
  LIFECYCLE_LABELS,
  MOLECULE_TYPE_LABELS,
  type LifecycleStage,
  type Molecule,
  type MoleculeType,
} from "../types";
import { CollectionPickerDialog } from "@/features/research-organization/components/collection-picker-dialog";
import { MoleculeRegistrationDialog } from "./molecule-registration-dialog";
import { BulkRegistrationDialog } from "./bulk-registration-dialog";
import { CompoundSearchBar } from "./compound-search-bar";
import { DisclosureDialog } from "./disclosure-dialog";
import { MergeConfirmationDialog } from "./merge-confirmation-dialog";

function lifecycleBadgeVariant(
  stage: LifecycleStage
): "default" | "secondary" | "destructive" | "outline" {
  switch (stage) {
    case "active":
    case "hit":
    case "lead":
      return "default";
    case "preclinical_candidate":
    case "development_candidate":
      return "secondary";
    case "deprioritized":
    case "archived":
      return "destructive";
    default:
      return "outline";
  }
}

export function MoleculeList() {
  const router = useRouter();
  const { data: molecules, isLoading, error } = useMolecules();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [discloseMol, setDiscloseMol] = useState<Molecule | null>(null);
  const [mergeMol, setMergeMol] = useState<Molecule | null>(null);
  const [pickerMolIds, setPickerMolIds] = useState<string[]>([]);

  const handleSdfExport = useCallback(() => {
    if (!molecules?.length) return;
    downloadFile({
      url: "/api/v1/molecules/export/sdf",
      data: { molecule_ids: molecules.map((m) => m.id) },
      filename: "compounds.sdf",
    });
  }, [molecules]);

  const columnDefs = useMemo<ColDef<Molecule>[]>(
    () => [
      {
        headerName: "Structure",
        field: "structure",
        width: 120,
        sortable: false,
        filter: false,
        resizable: false,
        autoHeight: true,
        cellRenderer: (params: ICellRendererParams<Molecule>) => {
          const mol = params.data;
          if (!mol) return null;
          if (mol.structure_status === "disclosed" && mol.structure?.smiles) {
            return (
              <div className="py-1">
                <StructureThumbnail smiles={mol.structure.smiles} size={80} />
              </div>
            );
          }
          return (
            <div className="flex h-[80px] w-[80px] items-center justify-center rounded bg-muted text-xs text-muted-foreground">
              N/A
            </div>
          );
        },
      },
      {
        headerName: "Reg #",
        field: "registration_number",
        width: 120,
        cellClass: "font-mono text-sm",
      },
      { headerName: "Name", field: "name", flex: 1, minWidth: 150 },
      {
        headerName: "Type",
        field: "molecule_type",
        width: 130,
        valueFormatter: (p) =>
          MOLECULE_TYPE_LABELS[p.value as MoleculeType] ?? p.value,
      },
      {
        headerName: "Formula",
        field: "molecular_formula",
        width: 140,
        cellClass: "font-mono text-sm text-muted-foreground",
        valueFormatter: (p) => p.value ?? "\u2014",
      },
      {
        headerName: "Stage",
        field: "lifecycle_stage",
        width: 130,
        cellRenderer: (params: ICellRendererParams<Molecule>) => {
          const stage = params.value as LifecycleStage;
          return (
            <Badge variant={lifecycleBadgeVariant(stage)}>
              {LIFECYCLE_LABELS[stage] ?? stage}
            </Badge>
          );
        },
      },
      {
        headerName: "Status",
        field: "structure_status",
        width: 110,
        cellRenderer: (params: ICellRendererParams<Molecule>) => (
          <Badge variant="outline">
            {params.value === "disclosed" ? "Disclosed" : "Undisclosed"}
          </Badge>
        ),
      },
      {
        headerName: "",
        field: "id",
        width: 160,
        sortable: false,
        filter: false,
        resizable: false,
        cellRenderer: (params: ICellRendererParams<Molecule>) => {
          const mol = params.data;
          if (!mol) return null;
          return (
            <div className="flex justify-end gap-2">
              {mol.structure_status === "undisclosed" && !mol.merged_into_id && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setDiscloseMol(mol)}
                >
                  Disclose
                </Button>
              )}
              {!mol.merged_into_id && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setMergeMol(mol)}
                >
                  Merge
                </Button>
              )}
            </div>
          );
        },
      },
    ],
    []
  );

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-destructive/50 p-12 text-center">
        <p className="text-sm text-destructive">
          Failed to load compounds. Is the backend running?
        </p>
        <p className="mt-1 text-xs text-muted-foreground">{error.message}</p>
      </div>
    );
  }

  return (
    <>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Compounds</h1>
          <p className="mt-1 text-muted-foreground">
            Search, register, and manage chemical compounds.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleSdfExport} disabled={!molecules?.length}>
            <Download className="h-4 w-4" />
            Export SDF
          </Button>
          <Button variant="outline" onClick={() => setBulkOpen(true)}>
            <Upload className="mr-2 h-4 w-4" />
            Bulk Upload
          </Button>
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Register Compound
          </Button>
        </div>
      </div>

      <div className="mt-4">
        <CompoundSearchBar />
      </div>

      <div className="mt-4">
        <DataGrid<Molecule>
          rowData={molecules}
          columnDefs={columnDefs}
          loading={isLoading}
          height="calc(100vh - 280px)"
          exportFilename="compounds"
          onRowClick={(mol) => {
            router.push(`/compounds/${mol.id}`);
          }}
          selectionToolbar={(selected) => (
            <>
              <span className="text-sm text-muted-foreground">
                {selected.length} selected
              </span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setPickerMolIds(selected.map((m) => m.id))}
              >
                <ListPlus className="mr-1 h-4 w-4" />
                Add to Collection
              </Button>
            </>
          )}
          emptyState={
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
              <FlaskConical className="h-12 w-12 text-muted-foreground/40" />
              <h3 className="mt-4 text-lg font-semibold">
                No compounds registered
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Register your first compound to get started.
              </p>
              <Button className="mt-4" onClick={() => setDialogOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Register Compound
              </Button>
            </div>
          }
        />
      </div>

      <MoleculeRegistrationDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
      />
      <BulkRegistrationDialog open={bulkOpen} onOpenChange={setBulkOpen} />
      {discloseMol && (
        <DisclosureDialog
          molecule={discloseMol}
          open={!!discloseMol}
          onOpenChange={(open) => !open && setDiscloseMol(null)}
        />
      )}
      {mergeMol && (
        <MergeConfirmationDialog
          sourceMolecule={mergeMol}
          open={!!mergeMol}
          onOpenChange={(open) => !open && setMergeMol(null)}
        />
      )}
      <CollectionPickerDialog
        open={pickerMolIds.length > 0}
        onOpenChange={(open) => {
          if (!open) setPickerMolIds([]);
        }}
        moleculeIds={pickerMolIds}
        onComplete={() => setPickerMolIds([])}
      />
    </>
  );
}
