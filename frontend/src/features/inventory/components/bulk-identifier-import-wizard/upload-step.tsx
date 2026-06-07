"use client";

import { CsvDropzone } from "@/shared/components/csv-dropzone";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import { saveText } from "@/shared/lib/api/download";
import { Download } from "lucide-react";
import { useState } from "react";
import { generateCsvTemplate, parseBulkIdentifierCsv } from "../../lib/parse-bulk-identifier-csv";
import type { BulkIdentifierRowBody } from "../../types";

interface UploadStepProps {
  onParsed: (rows: BulkIdentifierRowBody[], errors: string[]) => void;
}

export function UploadStep({ onParsed }: UploadStepProps) {
  const [parsing, setParsing] = useState(false);
  const [file, setFile] = useState<File | null>(null);

  const handleFile = async (f: File) => {
    setParsing(true);
    setFile(f);
    const { rows, errors } = await parseBulkIdentifierCsv(f);
    setParsing(false);
    onParsed(rows, errors);
  };

  const handleDownloadTemplate = () => {
    saveText(generateCsvTemplate(), "batch-identifiers-template.csv");
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
        <CsvDropzone
          file={file}
          onFile={handleFile}
          isPending={parsing}
          accept={{ "text/csv": [".csv"] }}
          prompt="Drop a CSV here, or click to browse"
          hint="CSV mapping external lot IDs to Cellar batches"
        />
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
