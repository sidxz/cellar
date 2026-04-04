"use client";

import { useCallback, useRef, useState } from "react";
import { Upload } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { useBulkCreateReadoutData } from "../hooks/use-readout-data";
import type { CreateReadoutDataInput } from "../types";

interface BulkReadoutImportDialogProps {
  runId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface ParseResult {
  rows: CreateReadoutDataInput[];
  headers: string[];
  previewRows: string[][];
}

const EXPECTED_COLUMNS = [
  "molecule_id",
  "batch_id",
  "readout_definition_id",
  "value_numeric",
  "value_qualifier",
  "is_outlier",
] as const;

function parseCsv(text: string, runId: string): ParseResult {
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

  const moleculeIdx = colIndex("molecule_id");
  const batchIdx = colIndex("batch_id");
  const readoutDefIdx = colIndex("readout_definition_id");
  const valueIdx = colIndex("value_numeric");
  const qualifierIdx = colIndex("value_qualifier");
  const outlierIdx = colIndex("is_outlier");

  if (moleculeIdx === -1 || batchIdx === -1 || readoutDefIdx === -1) {
    return { rows: [], headers, previewRows };
  }

  const rows: CreateReadoutDataInput[] = dataLines.map((line) => {
    const cols = line.split(",").map((c) => c.trim());
    return {
      run_id: runId,
      molecule_id: cols[moleculeIdx] ?? "",
      batch_id: cols[batchIdx] ?? "",
      readout_definition_id: cols[readoutDefIdx] ?? "",
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
  open,
  onOpenChange,
}: BulkReadoutImportDialogProps) {
  const bulkCreate = useBulkCreateReadoutData();
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
          setParseResult(parseCsv(text, runId));
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
      ? EXPECTED_COLUMNS.filter(
          (col) => ["molecule_id", "batch_id", "readout_definition_id"].includes(col) && !parseResult.headers.includes(col)
        )
      : [];

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Import Readout Data (CSV)</DialogTitle>
          <DialogDescription>
            Upload a CSV file with columns: molecule_id, batch_id,
            readout_definition_id, value_numeric, value_qualifier, is_outlier
          </DialogDescription>
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
