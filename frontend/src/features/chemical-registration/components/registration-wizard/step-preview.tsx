"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { cn } from "@/shared/lib/utils";
import { AlertTriangle, ArrowLeft, CheckCircle2, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useRegistrationWizard } from "../../hooks/use-registration-wizard";
import {
  usePreviewBulkRegistration,
  usePreviewRegistration,
} from "../../hooks/use-registration-wizard-api";
import type { PreviewItem, PreviewRegistrationItemResponse } from "../../types/registration-wizard";

/** Backend caps a forecast request at 500 items; larger files go in chunks. */
const FORECAST_CHUNK = 500;

type Forecast = Map<number, PreviewRegistrationItemResponse>; // row_index → outcome

/** Same shape POST /molecules takes, which is what the forecast classifies. */
function toForecastItem(item: PreviewItem) {
  return {
    name: item.name ?? null,
    smiles: item.smiles ?? null,
    molecule_type: item.molecule_type,
    external_ids: (item.external_ids ?? []).map((e) => ({
      identifier: e.identifier,
      identifier_type: e.identifier_type,
    })),
  };
}

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

  // Advisory forecast of what each parseable row will do, fetched once the
  // parse preview is in. Local state on purpose: revisiting the step re-asks,
  // which is what you want from a forecast.
  const forecastMutation = usePreviewRegistration();
  // null = waiting, "failed" = could not ask (never rendered as zeros), Map = answer.
  const [forecast, setForecast] = useState<Forecast | "failed" | null>(null);

  // Kick off preview on mount when no data yet
  // biome-ignore lint/correctness/useExhaustiveDependencies: kick off the preview once on mount (guarded by hasRequested ref); the captured bulkInput/previewMutation are intentionally not re-subscribed.
  useEffect(() => {
    if (hasRequested.current || bulkPreview || !bulkInput.file) return;
    hasRequested.current = true;
    previewMutation
      .mutateAsync(bulkInput.file)
      .then((data) => setBulkPreview(data))
      .catch(() => {
        // Error surfaced via mutation state below.
      });
  }, []);

  // biome-ignore lint/correctness/useExhaustiveDependencies: re-run only when the parse preview changes; mutateAsync is stable and the cancel flag handles overlap (StrictMode double-run included).
  useEffect(() => {
    if (!bulkPreview) return;
    const rows = bulkPreview.items.filter((i) => !i.error);
    let cancelled = false;
    (async () => {
      const byRow: Forecast = new Map();
      for (let start = 0; start < rows.length; start += FORECAST_CHUNK) {
        const chunk = rows.slice(start, start + FORECAST_CHUNK);
        const res = await forecastMutation.mutateAsync({ items: chunk.map(toForecastItem) });
        for (const it of res.items) byRow.set(chunk[it.index].row_index, it);
      }
      if (!cancelled) setForecast(byRow);
    })().catch(() => {
      // Error toast comes from the hook; the table must not read as "0 will merge".
      if (!cancelled) setForecast("failed");
    });
    return () => {
      cancelled = true;
    };
  }, [bulkPreview]);

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
  const answered = forecast instanceof Map ? forecast : null;
  const counts = countForecast(answered);

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

      {/* Forecast counters — what confirming would do */}
      {answered && (
        <div className="grid grid-cols-4 gap-3 max-w-3xl">
          <SummaryStat label="Will register" value={counts.registered} tone="success" />
          <SummaryStat label="Duplicates" value={counts.deduplicated} tone="default" />
          <SummaryStat label="Will disclose" value={counts.disclosed} tone="default" />
          <SummaryStat
            label="Conflicts"
            value={counts.conflict}
            tone={counts.conflict > 0 ? "destructive" : "default"}
            icon={counts.conflict > 0 ? <AlertTriangle className="h-3.5 w-3.5" /> : null}
          />
        </div>
      )}

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
                  <th className="px-3 py-2 text-left font-medium">Outcome</th>
                  <th className="px-3 py-2 text-left font-medium">Issue</th>
                </tr>
              </thead>
              <tbody>
                {bulkPreview.items.map((item) => (
                  <tr
                    key={item.row_index}
                    className={cn(
                      "border-b last:border-b-0",
                      item.error && "bg-destructive/5",
                      answered?.get(item.row_index)?.action === "conflict" && "bg-amber-500/5",
                    )}
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
                    <td className="px-3 py-1.5">
                      {item.error || forecast === "failed" ? (
                        "\u2014"
                      ) : answered ? (
                        <OutcomeBadge outcome={answered.get(item.row_index)} />
                      ) : (
                        <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                      )}
                    </td>
                    <td className="px-3 py-1.5 text-destructive">
                      {item.error ??
                        answered?.get(item.row_index)?.conflict_reason ??
                        answered?.get(item.row_index)?.error ??
                        ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {forecast === "failed" && (
        <p className="text-xs text-muted-foreground">
          Forecast unavailable — outcomes will be decided when the job runs.
        </p>
      )}

      {answered && (
        <p className="text-xs text-muted-foreground">
          Forecast only — outcomes are decided when the job runs, and a registration landing in
          between can change them.
        </p>
      )}

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

function countForecast(forecast: Forecast | null) {
  const counts = { registered: 0, deduplicated: 0, disclosed: 0, merge_candidate: 0, conflict: 0 };
  if (!forecast) return counts;
  for (const it of forecast.values()) {
    if (it.action && it.action in counts) counts[it.action as keyof typeof counts] += 1;
  }
  return counts;
}

const OUTCOME_LABELS: Record<
  string,
  { label: string; variant: "success" | "warning" | "secondary" | "destructive" }
> = {
  registered: { label: "New", variant: "success" },
  deduplicated: { label: "Duplicate", variant: "warning" },
  disclosed: { label: "Discloses", variant: "secondary" },
  merge_candidate: { label: "Merge?", variant: "warning" },
  conflict: { label: "Conflict", variant: "destructive" },
};

function OutcomeBadge({ outcome }: { outcome: PreviewRegistrationItemResponse | undefined }) {
  const spec = outcome?.action ? OUTCOME_LABELS[outcome.action] : undefined;
  // The reason / error is printed in the Issue column, so the badge stays a label.
  if (!spec) return <Badge variant="outline">Unknown</Badge>;
  return <Badge variant={spec.variant}>{spec.label}</Badge>;
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
