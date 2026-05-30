"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { showError, showSuccess } from "@/shared/lib/toast";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useProtocol } from "../hooks/use-protocols";

interface GridImportDialogProps {
  runId: string;
  protocolId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface ImportReadoutsResult {
  matched: number;
  unmatched: number;
  readouts_created: number;
}

/**
 * Import a plate-reader GRID (a value matrix) into one of a run's readouts.
 * Reuses the existing readout-import endpoint via its ``layout=grid`` mode —
 * the server reshapes the matrix to per-well values before importing.
 */
export function GridImportDialog({ runId, protocolId, open, onOpenChange }: GridImportDialogProps) {
  const qc = useQueryClient();
  const { data: protocol } = useProtocol(protocolId);
  const readoutDefs = protocol?.readout_definitions ?? [];

  const [file, setFile] = useState<File | null>(null);
  const [readoutId, setReadoutId] = useState<string>("");
  const [importing, setImporting] = useState(false);

  const reset = () => {
    setFile(null);
    setReadoutId("");
    setImporting(false);
  };

  const handleImport = async () => {
    if (!file || !readoutId) return;
    setImporting(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await customInstance<ImportReadoutsResult>({
        url: `/api/v1/runs/${runId}/import-readouts`,
        method: "POST",
        params: { readout_definition_id: readoutId, layout: "grid" },
        data: form,
      });
      for (const key of [["readout-data"], ["dose-response-curves"], ["plate-map"], ["runs"]]) {
        qc.invalidateQueries({ queryKey: key });
      }
      showSuccess(`Imported ${res.readouts_created} readouts from the plate grid.`);
      onOpenChange(false);
      reset();
    } catch (e) {
      showError(e instanceof Error ? e.message : "Grid import failed");
    } finally {
      setImporting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) reset();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Import plate grid</DialogTitle>
          <DialogDescription>
            Upload a plate-reader matrix (column numbers across the top, well-row letters down the
            side). It is flattened to per-well values and imported into the chosen readout.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label>Readout</Label>
            <Select value={readoutId} onValueChange={setReadoutId}>
              <SelectTrigger>
                <SelectValue placeholder="Which measurement is this grid?" />
              </SelectTrigger>
              <SelectContent>
                {readoutDefs.map((rd) => (
                  <SelectItem key={rd.id} value={rd.id}>
                    {rd.name}
                    {rd.unit ? ` (${rd.unit})` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="grid-file">Grid file (CSV or XLSX)</Label>
            <Input
              id="grid-file"
              type="file"
              accept=".csv,.tsv,.txt,.xlsx,.xlsm"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleImport} disabled={!file || !readoutId || importing}>
            {importing ? "Importing…" : "Import grid"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
