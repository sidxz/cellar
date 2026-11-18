"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { cn } from "@/shared/lib/utils";
import { AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { usePreviewRegistration } from "../hooks/use-registration-wizard-api";
import { type PreviewCounts, buildPreviewRows } from "../lib/preview-rows";
import type { PreviewItem, PreviewRegistrationItemResponse } from "../types/registration-wizard";

/** Backend caps a forecast request at 500 items; larger files go in chunks. */
const FORECAST_CHUNK = 500;

type Forecast = Map<number, PreviewRegistrationItemResponse>; // row_index → outcome

/** Same shape POST /molecules takes, which is what the forecast classifies. */
function toForecastItem(item: PreviewItem) {
  const storedOnly = (item.external_ids ?? [])
    .filter((e) => e.decides === false)
    .map((e) => e.identifier);
  const storedOnlyBatch = (item.batch_ids ?? [])
    .filter((b) => b.decides === false)
    .map((b) => b.identifier);
  return {
    name: item.name ?? null,
    smiles: item.smiles ?? null,
    molecule_type: item.molecule_type,
    // IDs that don't decide are stored only: they never match or conflict.
    external_ids: (item.external_ids ?? [])
      .filter((e) => e.decides !== false)
      .map((e) => ({ identifier: e.identifier, identifier_type: e.identifier_type })),
    batch_ids: (item.batch_ids ?? []).filter((b) => b.decides !== false).map((b) => b.identifier),
    // sent only when there are some, so a file's request is unchanged
    ...(storedOnly.length > 0 && { stored_only_ids: storedOnly }),
    ...(storedOnlyBatch.length > 0 && { stored_only_batch_ids: storedOnlyBatch }),
  };
}

export interface PreviewTableFooterInfo {
  counts: PreviewCounts;
  /** The forecast has answered (counts of new compounds / batches are real). */
  answered: boolean;
  /** At least one row has no parse error. */
  importable: boolean;
}

/**
 * Tiles + per-row table for parsed rows (a file's or a CDD sample's), with the
 * advisory forecast of what each row would do. ``footer`` renders below the table.
 */
export function PreviewTable({
  items,
  createBatchOnDuplicate,
  footer,
}: {
  items: PreviewItem[];
  createBatchOnDuplicate: boolean;
  footer?: (info: PreviewTableFooterInfo) => ReactNode;
}) {
  // Local state on purpose: revisiting re-asks, which is what you want from a forecast.
  const forecastMutation = usePreviewRegistration();
  // null = waiting, "failed" = could not ask (never rendered as zeros), Map = answer.
  const [forecast, setForecast] = useState<Forecast | "failed" | null>(null);

  // biome-ignore lint/correctness/useExhaustiveDependencies: re-run only when the parse preview changes; mutateAsync is stable and the cancel flag handles overlap (StrictMode double-run included).
  useEffect(() => {
    setForecast(null);
    const rows = items.filter((i) => !i.error);
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
  }, [items]);

  const answered = forecast instanceof Map ? forecast : null;
  const { rows, counts } = buildPreviewRows(items, answered, createBatchOnDuplicate);
  const importable = rows.some((r) => !r.item.error);

  return (
    <>
      {/* Counters */}
      <div className="grid grid-cols-5 gap-3 max-w-4xl">
        <SummaryStat label="Rows" value={counts.rows} tone="default" />
        <SummaryStat
          label="New compounds"
          value={answered ? counts.newCompounds : "\u2014"}
          tone="success"
          icon={<CheckCircle2 className="h-3.5 w-3.5" />}
        />
        <SummaryStat
          label="New batches"
          value={answered ? counts.newBatches : "\u2014"}
          tone="success"
        />
        <SummaryStat
          label="Already in ChemCellar"
          value={answered ? counts.existingBatches : "\u2014"}
          tone="default"
        />
        <SummaryStat
          label="Problems"
          value={counts.problems}
          tone={counts.problems > 0 ? "destructive" : "default"}
          icon={counts.problems > 0 ? <AlertTriangle className="h-3.5 w-3.5" /> : null}
        />
      </div>

      {/* Per-row table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Rows</CardTitle>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          <div className="max-h-[480px] overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-muted/80 backdrop-blur">
                <tr className="border-b">
                  <th className="px-3 py-2 text-left font-medium w-12">#</th>
                  <th className="px-3 py-2 text-left font-medium">Name</th>
                  <th className="px-3 py-2 text-left font-medium">Structure</th>
                  <th className="px-3 py-2 text-left font-medium">Compound</th>
                  <th className="px-3 py-2 text-left font-medium">Batch</th>
                  <th className="px-3 py-2 text-left font-medium">IDs to store</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.item.row_index}
                    className={cn(
                      "border-b last:border-b-0 align-top",
                      r.problem && "bg-destructive/5",
                    )}
                  >
                    <td className="px-3 py-1.5 text-muted-foreground tabular-nums">{r.fileRow}</td>
                    <td className="px-3 py-1.5">{r.item.name ?? "\u2014"}</td>
                    <td className="px-3 py-1.5 font-mono">
                      {r.item.smiles ? (
                        truncate(r.item.smiles, 32)
                      ) : (
                        <span className="font-sans text-muted-foreground">no structure</span>
                      )}
                    </td>
                    <td className="px-3 py-1.5">
                      {r.compound ??
                        (r.problem || forecast === "failed" ? (
                          "\u2014"
                        ) : (
                          <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                        ))}
                    </td>
                    <td className="px-3 py-1.5">
                      {r.problem ? (
                        <span className="text-destructive">{r.problem}</span>
                      ) : (
                        (r.batch ?? "")
                      )}
                    </td>
                    <td className="px-3 py-1.5">
                      <IdChips item={r.item} />
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
          between can change them. A row with a batch problem still registers its compound.
        </p>
      )}

      {footer?.({ counts, answered: answered !== null, importable })}
    </>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}\u2026` : s;
}

/** Every ID the row stores, with its Source, grouped by where it goes. */
function IdChips({ item }: { item: PreviewItem }) {
  const compoundIds = item.external_ids ?? [];
  const batchIds = item.batch_ids ?? [];
  const warnings = item.warnings ?? [];
  if (compoundIds.length === 0 && batchIds.length === 0 && warnings.length === 0) {
    return <span className="text-muted-foreground">{"\u2014"}</span>;
  }
  return (
    <div className="flex flex-col gap-1">
      {compoundIds.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-muted-foreground">Compound:</span>
          {compoundIds.map((e) => (
            <Badge key={`c-${e.identifier}`} variant="outline" className="font-normal">
              {e.source ?? e.identifier_type} · {e.identifier}
            </Badge>
          ))}
        </div>
      )}
      {batchIds.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-muted-foreground">Batch:</span>
          {batchIds.map((b) => (
            <Badge key={`b-${b.identifier}`} variant="outline" className="font-normal">
              {b.source} · {b.identifier}
            </Badge>
          ))}
        </div>
      )}
      {warnings.map((w) => (
        <span key={`w-${w}`} className="text-muted-foreground">
          {w}
        </span>
      ))}
    </div>
  );
}

function SummaryStat({
  label,
  value,
  tone,
  icon,
}: {
  label: string;
  /** A dash while the count isn't known yet (forecast pending or failed). */
  value: number | string;
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
