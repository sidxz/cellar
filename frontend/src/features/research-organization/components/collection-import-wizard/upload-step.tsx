"use client";

import { Download, Upload } from "lucide-react";
import { useRef, useState } from "react";

import {
  buildCollectionImportTemplate,
  parseCollectionImportFile,
} from "@/features/research-organization/lib/parse-collection-import-csv";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { saveText } from "@/shared/lib/api/download";

export interface UploadStepProps {
  onParsed: (data: { headers: string[]; rows: Record<string, string>[] }) => void;
}

export function UploadStep({ onParsed }: UploadStepProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [parsing, setParsing] = useState(false);
  const [lastFile, setLastFile] = useState<string | null>(null);

  async function handleFile(file: File) {
    setError(null);
    setParsing(true);
    setLastFile(file.name);
    const parsed = await parseCollectionImportFile(file);
    setParsing(false);
    if (parsed.kind === "error") {
      setError(parsed.message);
      return;
    }
    onParsed({ headers: parsed.headers, rows: parsed.rows });
  }

  function handleDownloadTemplate() {
    saveText(buildCollectionImportTemplate(), "collection-import-template.csv");
  }

  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Upload CSV or Excel</h2>
          <Button variant="outline" size="sm" onClick={handleDownloadTemplate}>
            <Download className="mr-2 h-4 w-4" />
            Download Template
          </Button>
        </div>
        <div className="rounded-lg border-2 border-dashed p-8 text-center">
          <Upload className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Upload a CSV or Excel file mapping rows to Cellar molecules.
          </p>
          {lastFile && <p className="mt-2 text-xs text-muted-foreground">Last: {lastFile}</p>}
          <Label htmlFor="csv-file" className="sr-only">
            Upload CSV or Excel
          </Label>
          <Input
            id="csv-file"
            ref={fileRef}
            type="file"
            accept=".csv,.xlsx,.xls,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleFile(f);
              e.target.value = "";
            }}
          />
          <Button className="mt-4" onClick={() => fileRef.current?.click()} disabled={parsing}>
            {parsing ? "Parsing…" : "Choose file"}
          </Button>
        </div>
        <div className="rounded-lg bg-muted/40 p-3 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">CSV columns</p>
          <p className="mt-1">
            Any one of: <code>registration_number</code>, <code>external_id</code>,{" "}
            <code>smiles</code>, <code>inchi_key</code>
          </p>
          <p className="mt-1">
            Optional: <code>name</code>, <code>notes</code>
          </p>
        </div>
        {error && (
          <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-3">
            <p className="text-sm font-medium text-destructive">Parse error</p>
            <p className="mt-1 text-xs text-destructive">{error}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
