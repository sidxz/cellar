"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";

interface Outcome {
  row_index: number;
  status:
    | "resolved"
    | "already_present"
    | "unregistered"
    | "ambiguous"
    | "error";
  molecule_id?: string | null;
  molecule_name?: string | null;
  candidates?: string[];
  message?: string | null;
}

export interface PreviewResult {
  outcomes: Outcome[];
  resolved_count: number;
  already_present_count: number;
  unregistered_count: number;
  ambiguous_count: number;
  error_count: number;
  preview_id: string | null;
}

export interface PreviewStepProps {
  result: PreviewResult;
  collectionId: string;
  onCommit: () => void;
  rows?: Record<string, string>[];
  mapping?: Record<string, string>;
  submitting?: boolean;
}

const STATUS_VARIANT: Record<
  Outcome["status"],
  "default" | "secondary" | "destructive" | "outline"
> = {
  resolved: "default",
  already_present: "secondary",
  unregistered: "outline",
  ambiguous: "outline",
  error: "destructive",
};

// Priority order of roles to surface as "what was the chemist's input on this row?"
const INPUT_PRIORITY = [
  "registration_number",
  "inchi_key",
  "smiles",
  "external_id",
  "name",
] as const;

function truncate(s: string, max = 40): string {
  return s.length > max ? s.slice(0, max) + "…" : s;
}

export function PreviewStep({
  result,
  collectionId,
  onCommit,
  rows,
  mapping,
  submitting = false,
}: PreviewStepProps) {
  const canCommit = result.resolved_count > 0;
  const handoffHref = result.preview_id
    ? `/compounds/bulk-register?from_collection_import=${result.preview_id}&return_to_collection=${collectionId}`
    : null;

  function getRowInput(rowIndex: number): string {
    if (!rows || !mapping) return "";
    const row = rows[rowIndex];
    if (!row) return "";
    for (const role of INPUT_PRIORITY) {
      const header = mapping[role];
      if (!header) continue;
      const v = row[header];
      if (v && v.trim()) return truncate(v.trim());
    }
    return "";
  }

  const commitLabel = submitting
    ? "Adding…"
    : `Add ${result.resolved_count} to collection`;
  const bottomAriaLabel = `Add ${result.resolved_count} resolved ${
    result.resolved_count === 1 ? "row" : "rows"
  } to the collection`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        <Badge className="bg-emerald-100 text-emerald-900">
          {result.resolved_count} resolved
        </Badge>
        <Badge variant="secondary">
          {result.already_present_count} already present
        </Badge>
        <Badge variant="outline" className="border-amber-500 text-amber-700">
          {result.unregistered_count} unregistered
        </Badge>
        <Badge variant="outline" className="border-amber-500 text-amber-700">
          {result.ambiguous_count} ambiguous
        </Badge>
        <Badge variant="destructive">{result.error_count} error</Badge>
      </div>
      {handoffHref && result.unregistered_count > 0 && (
        <div className="rounded border border-amber-300 bg-amber-50 p-3">
          <p className="text-sm text-amber-900">
            {result.unregistered_count} rows reference molecules not yet
            registered. They will be skipped by this import.
          </p>
          <Link
            href={handoffHref}
            className="mt-2 inline-block text-sm font-medium underline"
          >
            Register them →
          </Link>
        </div>
      )}
      {canCommit && (
        <div className="flex justify-end">
          <Button
            disabled={submitting}
            onClick={onCommit}
            aria-label={`Add ${result.resolved_count} resolved ${
              result.resolved_count === 1 ? "row" : "rows"
            } to the collection (top)`}
          >
            {submitting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Adding…
              </>
            ) : (
              `Add ${result.resolved_count} to collection`
            )}
          </Button>
        </div>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Input</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Molecule</TableHead>
            <TableHead>Diagnostic</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {result.outcomes.map((o) => {
            const input = getRowInput(o.row_index);
            return (
              <TableRow key={o.row_index}>
                <TableCell className="font-mono text-sm">
                  {input || `#${o.row_index + 1}`}
                </TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANT[o.status]}>{o.status}</Badge>
                </TableCell>
                <TableCell>{o.molecule_name ?? "—"}</TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {o.message ?? ""}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      <Button
        disabled={!canCommit || submitting}
        onClick={onCommit}
        aria-label={bottomAriaLabel}
      >
        {submitting ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Adding…
          </>
        ) : (
          commitLabel
        )}
      </Button>
    </div>
  );
}
