"use client";

import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Download, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { generateCsvTemplate, parseBulkIdentifierCsv } from "../../lib/parse-bulk-identifier-csv";
import type { BulkIdentifierRowBody } from "../../types";

interface UploadStepProps {
  onParsed: (rows: BulkIdentifierRowBody[], errors: string[]) => void;
}

export function UploadStep({ onParsed }: UploadStepProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [parsing, setParsing] = useState(false);
  const [lastFile, setLastFile] = useState<string | null>(null);

  const handleFile = async (file: File) => {
    setParsing(true);
    setLastFile(file.name);
    const { rows, errors } = await parseBulkIdentifierCsv(file);
    setParsing(false);
    onParsed(rows, errors);
  };

  const handleDownloadTemplate = () => {
    const csv = generateCsvTemplate();
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "batch-identifiers-template.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Upload CSV</h2>
          <Button variant="outline" size="sm" onClick={handleDownloadTemplate}>
            <Download className="mr-2 h-4 w-4" />
            Download template
          </Button>
        </div>
        <div className="rounded-lg border-2 border-dashed p-8 text-center">
          <Upload className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">
            Upload a CSV file mapping external lot IDs to Cellar batches.
          </p>
          {lastFile && <p className="mt-2 text-xs text-muted-foreground">Last: {lastFile}</p>}
          <Button className="mt-4" onClick={() => fileRef.current?.click()} disabled={parsing}>
            {parsing ? "Parsing…" : "Choose file"}
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
              e.target.value = ""; // allow re-upload of same file
            }}
          />
        </div>
        <div className="rounded-lg bg-muted/40 p-3 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">CSV columns</p>
          <p className="mt-1">
            Required: <code>external_identifier</code>
          </p>
          <p className="mt-1">
            Locator (either): <code>cellar_batch_number</code> OR (
            <code>cellar_molecule_reg_number</code> + <code>cellar_batch_sequence</code>)
          </p>
          <p className="mt-1">
            Optional: <code>identifier_type</code> (default <code>external_lot</code>),{" "}
            <code>source</code> (default &quot;CSV import &lt;date&gt;&quot;)
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
