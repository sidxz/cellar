"use client";

import { Badge } from "@/shared/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { cn } from "@/shared/lib/utils";

import type { DraftExclusion } from "../hooks/use-edit-session";

interface DoseResponsePointInventoryProps {
  // Raw points from the curve (idx-aligned to the original raw_data + excluded array order).
  // For Sprint 2, the consumer passes curve.raw_data — points currently in the fit.
  rawData: { concentration: number; response: number }[];
  // The current DRAFT state of exclusions (from useEditSession).
  // Legacy entries (idx=null) are not toggleable but should appear in the list.
  exclusions: DraftExclusion[];
  // Per-point residual stats (signed σ). Optional — may be undefined if a preview hasn't run yet
  // or there are no residuals available. Used for display only.
  residuals?: (number | null)[];
  // Called when a row is clicked to toggle its exclusion. idx of -1 should be impossible
  // (legacy entries are non-clickable). The parent wires this to useEditSession.toggleExclusion.
  onToggle: (idx: number) => void;
}

type RowStatus = "included" | "excluded_manual" | "suggested_3sigma" | "excluded_3sigma";

interface ResolvedRow {
  idx: number;
  concentration: number;
  response: number;
  residual: number | null;
  status: RowStatus;
  entry: DraftExclusion | null;
}

/** Find the exclusion entry for a given raw-data idx, if any. */
function findExclusionByIdx(exclusions: DraftExclusion[], idx: number): DraftExclusion | undefined {
  return exclusions.find((e) => e.idx === idx);
}

/** Classify a row based on its (optional) exclusion entry. */
function classifyRow(entry: DraftExclusion | undefined): RowStatus {
  if (!entry) return "included";
  if (entry.source === "manual" && entry.excluded) return "excluded_manual";
  if (entry.source === "auto_3sigma" && entry.excluded) return "excluded_3sigma";
  if (entry.source === "auto_3sigma" && !entry.excluded) return "suggested_3sigma";
  // Defensive fallback — a manual entry with excluded=false shouldn't exist
  // but treat as included so we don't gaslight the chemist.
  return "included";
}

/** Format a concentration in molar units. Tiny values use scientific notation. */
function formatConcentration(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value === 0) return "0 M";
  const abs = Math.abs(value);
  // Scientific notation for sub-nanomolar and very large values.
  if (abs < 1e-3 || abs >= 1e3) {
    return `${value.toExponential(2)} M`;
  }
  return `${value.toPrecision(3)} M`;
}

/** Format a residual as signed sigmas, e.g. "+3.5σ" or "-4.1σ". Returns "—" for null. */
function formatResidual(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}σ`;
}

/** Status pill — text + Badge variant + optional class override (for amber suggestion). */
function StatusPill({ status }: { status: RowStatus }) {
  switch (status) {
    case "included":
      return (
        <Badge variant="outline" className="text-xs">
          Included
        </Badge>
      );
    case "excluded_manual":
      return (
        <Badge variant="destructive" className="text-xs">
          Excluded (manual)
        </Badge>
      );
    case "suggested_3sigma":
      return (
        <Badge variant="warning" className="text-xs">
          Suggested (3σ)
        </Badge>
      );
    case "excluded_3sigma":
      return (
        <Badge variant="destructive" className="text-xs">
          Excluded (accepted 3σ)
        </Badge>
      );
  }
}

export function DoseResponsePointInventory({
  rawData,
  exclusions,
  residuals,
  onToggle,
}: DoseResponsePointInventoryProps) {
  const legacyEntries = exclusions.filter((e) => e.idx === null);
  const resolvedRows: ResolvedRow[] = rawData.map((pt, i) => {
    const entry = findExclusionByIdx(exclusions, i) ?? null;
    return {
      idx: i,
      concentration: pt.concentration,
      response: pt.response,
      residual: residuals?.[i] ?? null,
      status: classifyRow(entry ?? undefined),
      entry,
    };
  });

  const isEmpty = resolvedRows.length === 0 && legacyEntries.length === 0;

  if (isEmpty) {
    return (
      <div className="rounded-md border bg-muted/20 p-4 text-center text-sm text-muted-foreground">
        No points to display.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {resolvedRows.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10 text-xs">Pt</TableHead>
              <TableHead className="text-xs">Dose</TableHead>
              <TableHead className="text-xs text-right">Response</TableHead>
              <TableHead className="text-xs text-right">Residual</TableHead>
              <TableHead className="text-xs">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {resolvedRows.map((row) => {
              const isSuggestion = row.status === "suggested_3sigma";
              return (
                <TableRow
                  key={row.idx}
                  onClick={() => onToggle(row.idx)}
                  className={cn("cursor-pointer", isSuggestion && "bg-amber-50 hover:bg-amber-100")}
                >
                  <TableCell className="text-xs font-mono text-muted-foreground">
                    {row.idx + 1}
                  </TableCell>
                  <TableCell className="text-xs font-mono tabular-nums">
                    {formatConcentration(row.concentration)}
                  </TableCell>
                  <TableCell className="text-xs font-mono tabular-nums text-right">
                    {row.response.toFixed(1)}
                  </TableCell>
                  <TableCell className="text-xs font-mono tabular-nums text-right">
                    {formatResidual(row.residual)}
                  </TableCell>
                  <TableCell>
                    <StatusPill status={row.status} />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
      {legacyEntries.length > 0 && (
        <div>
          <div className="text-xs text-muted-foreground mt-3 mb-1">
            Legacy exclusions (read-only)
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-xs">Dose</TableHead>
                <TableHead className="text-xs text-right">Response</TableHead>
                <TableHead className="text-xs">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {legacyEntries.map((entry, i) => (
                <TableRow
                  key={`legacy-${i}`}
                  className="cursor-default opacity-70"
                  // No onClick — legacy entries are read-only.
                >
                  <TableCell className="text-xs font-mono tabular-nums">
                    {entry.concentration !== null && entry.concentration !== undefined
                      ? formatConcentration(entry.concentration)
                      : "—"}
                  </TableCell>
                  <TableCell className="text-xs font-mono tabular-nums text-right">
                    {entry.response !== null && entry.response !== undefined
                      ? entry.response.toFixed(1)
                      : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-xs text-muted-foreground">
                      Legacy
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
