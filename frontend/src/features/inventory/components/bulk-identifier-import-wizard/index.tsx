"use client";

import { useMemo, useState } from "react";
import { Card, CardContent } from "@/shared/components/ui/card";
import { PageHeader } from "@/shared/components/page-header";
import { UploadStep } from "./upload-step";
import { PreviewStep } from "./preview-step";
import { ConfirmStep } from "./confirm-step";
import type {
  BulkIdentifierRowBody,
  BulkAddBatchIdentifiersResponse,
} from "../../types";

type Step = "upload" | "preview" | "confirm";

export function BulkIdentifierImportWizard() {
  const [step, setStep] = useState<Step>("upload");
  const [rows, setRows] = useState<BulkIdentifierRowBody[]>([]);
  const [parseErrors, setParseErrors] = useState<string[]>([]);
  const [, setPreview] = useState<BulkAddBatchIdentifiersResponse | null>(null);

  const sourceDefault = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return `CSV import ${today}`;
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Bulk import batch identifiers"
        subtitle="Map external lot IDs (CDD, partner spreadsheets, paper supplementary) to existing Cellar batches in one upload."
      />

      {step === "upload" && (
        <>
          <UploadStep
            onParsed={(parsedRows, errors) => {
              setRows(parsedRows);
              setParseErrors(errors);
              if (parsedRows.length > 0 && errors.length === 0) {
                setStep("preview");
              }
            }}
          />
          {parseErrors.length > 0 && (
            <Card>
              <CardContent className="space-y-1 p-4">
                <p className="text-sm font-medium text-destructive">
                  CSV issues:
                </p>
                {parseErrors.map((err, i) => (
                  <p key={i} className="text-xs text-destructive">
                    {err}
                  </p>
                ))}
              </CardContent>
            </Card>
          )}
        </>
      )}

      {step === "preview" && (
        <PreviewStep
          rows={rows}
          sourceDefault={sourceDefault}
          onPreviewReady={setPreview}
          onBack={() => {
            setStep("upload");
            setRows([]);
            setPreview(null);
          }}
          onNext={() => setStep("confirm")}
        />
      )}

      {step === "confirm" && (
        <ConfirmStep
          rows={rows}
          sourceDefault={sourceDefault}
          onDone={(data) => setPreview(data)}
        />
      )}
    </div>
  );
}
