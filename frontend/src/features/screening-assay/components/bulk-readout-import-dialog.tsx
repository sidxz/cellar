"use client";

import { useCallback, useRef, useState } from "react";
import { Download, Upload } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { useMolecules } from "@/features/chemical-registration/hooks/use-molecules";
import { useProtocol } from "../hooks/use-protocols";
import { useBulkCreateReadoutData } from "../hooks/use-readout-data";
import type { CreateReadoutDataInput } from "../types";

interface BulkReadoutImportDialogProps {
  runId: string;
  protocolId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface ParseResult {
  rows: CreateReadoutDataInput[];
  headers: string[];
  previewRows: string[][];
}

const REQUIRED_COLUMNS = [
  "compound",
  "batch",
  "readout_definition",
] as const;

function downloadTemplate(
  readoutDefNames: string[],
  moleculeExamples: Array<{ reg: string; batch: string }>,
) {
  const header = "compound,batch,readout_definition,value,qualifier,is_outlier";
  const defName = readoutDefNames[0] ?? "Readout Name";
  const mol1 = moleculeExamples[0] ?? { reg: "CV-00001", batch: "CV-00001-001" };
  const mol2 = moleculeExamples[1] ?? { reg: "CV-00002", batch: "CV-00002-001" };

  const rows = [header];
  for (const def of readoutDefNames.length > 0 ? readoutDefNames : [defName]) {
    rows.push(`${mol1.reg},${mol1.batch},${def},85.2,=,false`);
    rows.push(`${mol2.reg},${mol2.batch},${def},12.7,<,false`);
  }

  const csv = rows.join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "readout_data_template.csv";
  a.click();
  URL.revokeObjectURL(url);
}

interface MoleculeLookup {
  byRegNumber: Map<string, string>;
  byName: Map<string, string>;
}

interface BatchLookup {
  byBatchNumber: Map<string, string>;
}

function buildMoleculeLookup(molecules: Array<{ id: string; registration_number: string; name: string }> | undefined): MoleculeLookup {
  const byRegNumber = new Map<string, string>();
  const byName = new Map<string, string>();
  for (const mol of molecules ?? []) {
    byRegNumber.set(mol.registration_number.toLowerCase(), mol.id);
    if (mol.name) byName.set(mol.name.toLowerCase(), mol.id);
  }
  return { byRegNumber, byName };
}

function resolveMoleculeId(value: string, lookup: MoleculeLookup): string {
  const lower = value.toLowerCase();
  return lookup.byRegNumber.get(lower) ?? lookup.byName.get(lower) ?? value;
}

function parseCsv(text: string, runId: string, moleculeLookup: MoleculeLookup, readoutDefMap: Map<string, string>): ParseResult {
  const lines = text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  if (lines.length < 2) {
    return { rows: [], headers: [], previewRows: [] };
  }

  const headers = lines[0].split(",").map((h) => h.trim().toLowerCase());
  const dataLines = lines.slice(1);
  const previewRows = dataLines.slice(0, 5).map((l) => l.split(",").map((c) => c.trim()));

  const colIndex = (name: string) => headers.indexOf(name);

  const compoundIdx = colIndex("compound");
  const batchIdx = colIndex("batch");
  const readoutDefIdx = colIndex("readout_definition");
  const valueIdx = colIndex("value");
  const qualifierIdx = colIndex("qualifier");
  const outlierIdx = colIndex("is_outlier");

  if (compoundIdx === -1 || batchIdx === -1 || readoutDefIdx === -1) {
    return { rows: [], headers, previewRows };
  }

  const rows: CreateReadoutDataInput[] = dataLines.map((line) => {
    const cols = line.split(",").map((c) => c.trim());
    const compoundValue = cols[compoundIdx] ?? "";
    const readoutDefName = cols[readoutDefIdx] ?? "";
    return {
      run_id: runId,
      molecule_id: resolveMoleculeId(compoundValue, moleculeLookup),
      batch_id: cols[batchIdx] ?? "",
      readout_definition_id: readoutDefMap.get(readoutDefName.toLowerCase()) ?? readoutDefName,
      value_numeric:
        valueIdx !== -1 && cols[valueIdx] ? parseFloat(cols[valueIdx]) : undefined,
      value_qualifier:
        qualifierIdx !== -1 && cols[qualifierIdx] ? cols[qualifierIdx] : undefined,
      is_outlier:
        outlierIdx !== -1 && cols[outlierIdx]
          ? cols[outlierIdx].toLowerCase() === "true"
          : false,
    };
  });

  return { rows, headers, previewRows };
}

export function BulkReadoutImportDialog({
  runId,
  protocolId,
  open,
  onOpenChange,
}: BulkReadoutImportDialogProps) {
  const bulkCreate = useBulkCreateReadoutData();
  const { data: molecules } = useMolecules();
  const { data: protocol } = useProtocol(protocolId);

  const moleculeLookup = buildMoleculeLookup(molecules);
  const readoutDefMap = new Map<string, string>();
  for (const rd of protocol?.readout_definitions ?? []) {
    readoutDefMap.set(rd.name.toLowerCase(), rd.id);
  }
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [submitResult, setSubmitResult] = useState<{
    total_count: number;
    success_count: number;
    error_count: number;
    errors: Array<{ index: number; error: string }>;
  } | null>(null);

  const reset = () => {
    setParseResult(null);
    setFileName(null);
    setSubmitResult(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleFile = useCallback(
    (file: File) => {
      setSubmitResult(null);
      setFileName(file.name);
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target?.result;
        if (typeof text === "string") {
          setParseResult(parseCsv(text, runId, moleculeLookup, readoutDefMap));
        }
      };
      reader.readAsText(file);
    },
    [runId]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file && file.name.endsWith(".csv")) {
        handleFile(file);
      }
    },
    [handleFile]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        handleFile(file);
      }
    },
    [handleFile]
  );

  const handleSubmit = () => {
    if (!parseResult || parseResult.rows.length === 0) return;

    bulkCreate.mutate(
      { items: parseResult.rows },
      {
        onSuccess: (data) => {
          setSubmitResult(data);
          if (data.error_count === 0) {
            setTimeout(() => {
              onOpenChange(false);
              reset();
            }, 1500);
          }
        },
      }
    );
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      reset();
    }
    onOpenChange(nextOpen);
  };

  const missingColumns =
    parseResult && parseResult.headers.length > 0
      ? REQUIRED_COLUMNS.filter(
          (col) => !parseResult.headers.includes(col)
        )
      : [];

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Import Readout Data (CSV)</DialogTitle>
          <DialogDescription>
            Upload a CSV with columns: compound, batch, readout_definition, value, qualifier, is_outlier.
            Use registration numbers (e.g., CV-00001) and batch numbers (e.g., CV-00001-001).
          </DialogDescription>
          <Button
            variant="link"
            size="sm"
            className="mt-1 h-auto p-0 text-xs"
            onClick={() => {
              const rdNames = (protocol?.readout_definitions ?? []).map((rd) => rd.name);
              const molExamples = (molecules ?? []).slice(0, 2).map((m) => ({
                reg: m.registration_number,
                batch: m.registration_number + "-001",
              }));
              downloadTemplate(rdNames, molExamples);
            }}
          >
            <Download className="mr-1 h-3 w-3" />
            Download CSV template
          </Button>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* Drop zone */}
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => fileInputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors ${
              isDragging
                ? "border-primary bg-primary/5"
                : "border-muted-foreground/25 hover:border-muted-foreground/50"
            }`}
          >
            <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              {fileName
                ? fileName
                : "Drop a CSV file here or click to browse"}
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={handleInputChange}
            />
          </div>

          {/* Missing columns warning */}
          {missingColumns.length > 0 && (
            <div className="rounded-md bg-destructive/10 p-3">
              <p className="text-sm text-destructive">
                Missing required columns: {missingColumns.join(", ")}
              </p>
            </div>
          )}

          {/* Preview table */}
          {parseResult && parseResult.rows.length > 0 && (
            <div>
              <p className="mb-2 text-sm font-medium">
                Parsed {parseResult.rows.length} row
                {parseResult.rows.length !== 1 ? "s" : ""} &mdash; preview
                (first 5):
              </p>
              <div className="overflow-x-auto rounded-md border">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      {parseResult.headers.map((h) => (
                        <th
                          key={h}
                          className="whitespace-nowrap px-3 py-2 text-left font-medium"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {parseResult.previewRows.map((row, i) => (
                      <tr key={i} className="border-b last:border-b-0">
                        {row.map((cell, j) => (
                          <td
                            key={j}
                            className="whitespace-nowrap px-3 py-1.5 font-mono"
                          >
                            {cell}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Submit result summary */}
          {submitResult && (
            <div
              className={`rounded-md p-3 ${
                submitResult.error_count > 0
                  ? "bg-destructive/10"
                  : "bg-green-500/10"
              }`}
            >
              <p className="text-sm font-medium">
                {submitResult.success_count}/{submitResult.total_count}{" "}
                imported successfully.
                {submitResult.error_count > 0 &&
                  ` ${submitResult.error_count} error(s).`}
              </p>
              {submitResult.errors.length > 0 && (
                <ul className="mt-2 list-inside list-disc text-xs text-destructive">
                  {submitResult.errors.slice(0, 10).map((err) => (
                    <li key={err.index}>
                      Row {err.index + 1}: {err.error}
                    </li>
                  ))}
                  {submitResult.errors.length > 10 && (
                    <li>...and {submitResult.errors.length - 10} more</li>
                  )}
                </ul>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={
              !parseResult ||
              parseResult.rows.length === 0 ||
              missingColumns.length > 0 ||
              bulkCreate.isPending
            }
          >
            {bulkCreate.isPending
              ? "Importing..."
              : `Import ${parseResult?.rows.length ?? 0} Row${(parseResult?.rows.length ?? 0) !== 1 ? "s" : ""}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
