"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { AlertTriangle, ArrowLeft, CheckCircle2, Loader2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import { usePreviewBulkRegistration } from "../../hooks/use-registration-wizard-api";

// ---------------------------------------------------------------------------
// StepPreview — parse-only preview between Input and Processing
// ---------------------------------------------------------------------------

export function StepPreview() {
  const bulkInput = useRegistrationWizard((s) => s.bulkInput);
  const bulkPreview = useRegistrationWizard((s) => s.bulkPreview);
  const setBulkPreview = useRegistrationWizard((s) => s.setBulkPreview);
  const nextStep = useRegistrationWizard((s) => s.nextStep);
  const prevStep = useRegistrationWizard((s) => s.prevStep);

  const previewMutation = usePreviewBulkRegistration();
  const hasRequested = useRef(false);

  // Kick off preview on mount when no data yet
  useEffect(() => {
    if (hasRequested.current || bulkPreview || !bulkInput.file) return;
    hasRequested.current = true;
    previewMutation
      .mutateAsync(bulkInput.file)
      .then((data) => setBulkPreview(data))
      .catch(() => {
        // Error surfaced via mutation state below.
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!bulkInput.file) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground text-sm">
          No file selected. Go back and choose one.
        </CardContent>
      </Card>
    );
  }

  if (previewMutation.isPending && !bulkPreview) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-sm text-muted-foreground">Parsing {bulkInput.file.name}…</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (previewMutation.isError) {
    return (
      <Card>
        <CardContent className="py-8">
          <div className="flex flex-col items-center gap-4 text-center">
            <AlertTriangle className="h-8 w-8 text-destructive" />
            <div>
              <p className="text-sm font-medium">Could not parse file</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {previewMutation.error?.message ?? "Parser returned an unknown error."}
              </p>
            </div>
            <Button variant="outline" onClick={prevStep}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!bulkPreview) return null;

  const validCount = bulkPreview.total_count - bulkPreview.error_count;
  const hasErrors = bulkPreview.error_count > 0;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Preview</h2>
          <p className="text-sm text-muted-foreground">
            Review the parsed rows before kicking off the import.
          </p>
        </div>
      </div>

      {/* Counters */}
      <div className="grid grid-cols-3 gap-3 max-w-xl">
        <SummaryStat label="Total" value={bulkPreview.total_count} tone="default" />
        <SummaryStat
          label="Parseable"
          value={validCount}
          tone="success"
          icon={<CheckCircle2 className="h-3.5 w-3.5" />}
        />
        <SummaryStat
          label="Parse errors"
          value={bulkPreview.error_count}
          tone={hasErrors ? "destructive" : "default"}
          icon={hasErrors ? <AlertTriangle className="h-3.5 w-3.5" /> : null}
        />
      </div>

      {/* Per-row table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Parsed rows</CardTitle>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          <div className="max-h-[420px] overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-muted/80 backdrop-blur">
                <tr className="border-b">
                  <th className="px-3 py-2 text-left font-medium w-12">#</th>
                  <th className="px-3 py-2 text-left font-medium">Name</th>
                  <th className="px-3 py-2 text-left font-medium">SMILES</th>
                  <th className="px-3 py-2 text-left font-medium">Identifiers</th>
                  <th className="px-3 py-2 text-left font-medium">Amount</th>
                  <th className="px-3 py-2 text-left font-medium">Salt</th>
                  <th className="px-3 py-2 text-left font-medium">Purity</th>
                  <th className="px-3 py-2 text-left font-medium">Source</th>
                  <th className="px-3 py-2 text-left font-medium">Issue</th>
                </tr>
              </thead>
              <tbody>
                {bulkPreview.items.map((item) => (
                  <tr
                    key={item.row_index}
                    className={`border-b last:border-b-0 ${item.error ? "bg-destructive/5" : ""}`}
                  >
                    <td className="px-3 py-1.5 text-muted-foreground">{item.row_index + 1}</td>
                    <td className="px-3 py-1.5">{item.name ?? "\u2014"}</td>
                    <td className="px-3 py-1.5 font-mono">
                      {item.smiles ? truncate(item.smiles, 40) : "\u2014"}
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">
                      {item.external_ids && item.external_ids.length > 0
                        ? item.external_ids
                            .map((e) => `${e.identifier_type}:${e.identifier}`)
                            .join(", ")
                        : "\u2014"}
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">
                      {item.amount_value != null
                        ? `${item.amount_value} ${item.amount_unit}`
                        : "\u2014"}
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">
                      {item.salt_code ?? "\u2014"}
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">
                      {item.purity != null ? `${item.purity}%` : "\u2014"}
                    </td>
                    <td className="px-3 py-1.5 text-muted-foreground">
                      {item.batch_source ?? "\u2014"}
                    </td>
                    <td className="px-3 py-1.5 text-destructive">{item.error ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {hasErrors && (
        <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
          <p className="text-muted-foreground">
            {bulkPreview.error_count} row{bulkPreview.error_count === 1 ? "" : "s"} failed to parse
            and will be reported as errors. The remaining {validCount} row
            {validCount === 1 ? "" : "s"} will be imported.
          </p>
        </div>
      )}

      <div className="flex justify-between border-t pt-4">
        <Button variant="outline" onClick={prevStep}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back
        </Button>
        <Button onClick={nextStep} disabled={validCount === 0}>
          Confirm &amp; Register {validCount > 0 ? `(${validCount})` : ""}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}\u2026` : s;
}

function SummaryStat({
  label,
  value,
  tone,
  icon,
}: {
  label: string;
  value: number;
  tone: "default" | "success" | "destructive";
  icon?: React.ReactNode;
}) {
  const toneClass =
    tone === "success"
      ? "text-emerald-600 border-emerald-500/30 bg-emerald-500/5"
      : tone === "destructive"
        ? "text-destructive border-destructive/30 bg-destructive/5"
        : "text-foreground border-border bg-muted/30";
  return (
    <Card className={`border ${toneClass}`}>
      <CardContent className="flex flex-col items-center gap-1 py-3 px-2">
        <div className="flex items-center gap-1.5">
          {icon}
          <span className="text-xl font-semibold tabular-nums">{value}</span>
        </div>
        <Badge variant="outline" className="text-[10px] font-normal">
          {label}
        </Badge>
      </CardContent>
    </Card>
  );
}
