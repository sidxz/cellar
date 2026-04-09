"use client";

import { useCallback, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Upload } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { useImportReadouts } from "../hooks/use-plate-setup";
import type { ImportReadoutsResult } from "../types";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function parseCsvPreview(text: string): { headers: string[]; rows: string[][] } {
  const lines = text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  if (lines.length === 0) return { headers: [], rows: [] };

  const headers = lines[0].split(",").map((h) => h.trim());
  const rows = lines
    .slice(1, 6)
    .map((l) => l.split(",").map((c) => c.trim()));

  return { headers, rows };
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface SimplifiedImportDialogProps {
  runId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ─── Component ───────────────────────────────────────────────────────────────

export function SimplifiedImportDialog({
  runId,
  open,
  onOpenChange,
}: SimplifiedImportDialogProps) {
  const importReadouts = useImportReadouts(runId);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<{ headers: string[]; rows: string[][] } | null>(
    null
  );
  const [isDragging, setIsDragging] = useState(false);
  const [result, setResult] = useState<ImportReadoutsResult | null>(null);

  const reset = () => {
    setFile(null);
    setPreview(null);
    setResult(null);
    importReadouts.reset();
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) reset();
    onOpenChange(nextOpen);
  };

  const handleFile = useCallback((f: File) => {
    setFile(f);
    setResult(null);
    importReadouts.reset();
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result;
      if (typeof text === "string") {
        setPreview(parseCsvPreview(text));
      }
    };
    reader.readAsText(f);
  }, [importReadouts]);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const f = e.dataTransfer.files[0];
      if (f && f.name.endsWith(".csv")) handleFile(f);
    },
    [handleFile]
  );

  const handleImport = () => {
    if (!file) return;
    importReadouts.mutate(
      { file },
      {
        onSuccess: (data) => {
          setResult(data);
          if (data.unmatched === 0) {
            setTimeout(() => handleOpenChange(false), 1800);
          }
        },
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Import Readout Data</DialogTitle>
          <DialogDescription>
            Upload a CSV file with readout values. The server will match rows to
            existing well assignments by compound or well position.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Drop zone */}
          <div
            onDrop={handleDrop}
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
            onClick={() => fileInputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors ${
              isDragging
                ? "border-primary bg-primary/5"
                : "border-muted-foreground/25 hover:border-muted-foreground/50"
            }`}
          >
            <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              {file ? file.name : "Drop a CSV here or click to browse"}
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFile(f);
              }}
            />
          </div>

          {/* Preview table */}
          {preview && preview.headers.length > 0 && !result && (
            <div>
              <p className="mb-2 text-xs text-muted-foreground font-medium">
                Preview (first 5 rows):
              </p>
              <div className="overflow-x-auto rounded-md border">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b bg-muted/50">
                      {preview.headers.map((h) => (
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
                    {preview.rows.map((row, i) => (
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

          {/* Import result */}
          {result && (
            <div
              className={`flex items-start gap-2 rounded-md p-3 text-sm ${
                result.unmatched > 0 ? "bg-yellow-500/10" : "bg-green-500/10"
              }`}
            >
              {result.unmatched === 0 ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-green-400" />
              ) : (
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-yellow-400" />
              )}
              <div className={result.unmatched === 0 ? "text-green-400" : "text-yellow-400"}>
                <p>
                  <span className="font-medium">{result.readouts_created}</span> readouts
                  created from{" "}
                  <span className="font-medium">{result.total_rows}</span> rows.
                </p>
                <p className="text-xs mt-0.5">
                  Matched: {result.matched} / Unmatched: {result.unmatched}
                </p>
              </div>
            </div>
          )}

          {/* Error */}
          {importReadouts.isError && (
            <div className="flex items-start gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>Import failed. Please check your file format and try again.</span>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            onClick={handleImport}
            disabled={!file || importReadouts.isPending || !!result}
          >
            {importReadouts.isPending ? "Importing..." : "Import"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
