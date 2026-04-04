"use client";

import { useState } from "react";
import { FlaskConical, Plus, Upload } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useMolecules } from "../hooks/use-molecules";
import {
  LIFECYCLE_LABELS,
  MOLECULE_TYPE_LABELS,
  type LifecycleStage,
  type Molecule,
  type MoleculeType,
} from "../types";
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
  const { data: molecules, isLoading } = useMolecules();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [discloseMol, setDiscloseMol] = useState<Molecule | null>(null);
  const [mergeMol, setMergeMol] = useState<Molecule | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
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

      {!molecules?.length ? (
        <div className="mt-8 flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
          <FlaskConical className="h-12 w-12 text-muted-foreground/40" />
          <h3 className="mt-4 text-lg font-semibold">No compounds registered</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Register your first compound to get started.
          </p>
          <Button className="mt-4" onClick={() => setDialogOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Register Compound
          </Button>
        </div>
      ) : (
        <div className="mt-4 rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Reg #</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Formula</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {molecules.map((mol: Molecule) => (
                <TableRow key={mol.id}>
                  <TableCell className="font-mono text-sm">
                    {mol.registration_number}
                  </TableCell>
                  <TableCell className="font-medium">{mol.name}</TableCell>
                  <TableCell>
                    {MOLECULE_TYPE_LABELS[mol.molecule_type as MoleculeType] ??
                      mol.molecule_type}
                  </TableCell>
                  <TableCell className="font-mono text-sm text-muted-foreground">
                    {mol.molecular_formula ?? "—"}
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={lifecycleBadgeVariant(
                        mol.lifecycle_stage as LifecycleStage
                      )}
                    >
                      {LIFECYCLE_LABELS[mol.lifecycle_stage as LifecycleStage] ??
                        mol.lifecycle_stage}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">
                      {mol.structure_status === "disclosed"
                        ? "Disclosed"
                        : "Undisclosed"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-2">
                      {mol.structure_status === "undisclosed" &&
                        !mol.merged_into_id && (
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
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

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
    </>
  );
}
