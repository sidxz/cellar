"use client";

import { useEffect } from "react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import { AlertCircle, CheckCircle2, XCircle } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { usePreviewBulkIdentifiers } from "../../hooks/use-bulk-identifier-import";
import type {
  BulkIdentifierRowBody,
  BulkAddBatchIdentifiersResponse,
} from "../../types";

interface PreviewStepProps {
  rows: BulkIdentifierRowBody[];
  sourceDefault: string;
  onPreviewReady: (preview: BulkAddBatchIdentifiersResponse) => void;
  onBack: () => void;
  onNext: () => void;
}

const STATUS_BADGE_VARIANT: Record<string, "default" | "destructive" | "secondary" | "outline"> = {
  resolved: "default",
  not_found: "destructive",
  conflict: "destructive",
  already_mapped: "secondary",
  error: "destructive",
};

const STATUS_LABEL: Record<string, string> = {
  resolved: "Ready",
  not_found: "Not found",
  conflict: "Conflict",
  already_mapped: "Already mapped",
  error: "Error",
};

export function PreviewStep({
  rows,
  sourceDefault,
  onPreviewReady,
  onBack,
  onNext,
}: PreviewStepProps) {
  const preview = usePreviewBulkIdentifiers();

  useEffect(() => {
    if (rows.length > 0 && !preview.isPending && !preview.data) {
      preview.mutate(
        { data: { source_default: sourceDefault, rows } },
        { onSuccess: (data) => onPreviewReady(data) },
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows.length, sourceDefault]);

  if (preview.isPending) {
    return <p className="text-sm text-muted-foreground">Resolving rows…</p>;
  }

  if (preview.error) {
    return (
      <Card>
        <CardContent className="p-6">
          <p className="text-sm text-destructive">
            Preview failed:{" "}
            {preview.error instanceof Error
              ? preview.error.message
              : String(preview.error)}
          </p>
          <Button
            variant="outline"
            className="mt-3"
            onClick={() => preview.reset()}
          >
            Try again
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (!preview.data) return null;

  const counts = preview.data.counts;
  const canCommit = (counts.resolved ?? 0) > 0;

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex items-center gap-4 p-4">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            <span className="text-sm">
              <strong>{counts.resolved ?? 0}</strong> ready
            </span>
          </div>
          {(counts.not_found ?? 0) > 0 && (
            <div className="flex items-center gap-2">
              <XCircle className="h-5 w-5 text-destructive" />
              <span className="text-sm">
                <strong>{counts.not_found}</strong> not found
              </span>
            </div>
          )}
          {(counts.conflict ?? 0) > 0 && (
            <div className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-amber-600" />
              <span className="text-sm">
                <strong>{counts.conflict}</strong> conflict
              </span>
            </div>
          )}
          {(counts.already_mapped ?? 0) > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">
                <strong>{counts.already_mapped}</strong> already mapped
              </span>
            </div>
          )}
          {(counts.error ?? 0) > 0 && (
            <div className="flex items-center gap-2">
              <XCircle className="h-5 w-5 text-destructive" />
              <span className="text-sm">
                <strong>{counts.error}</strong> error
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <div className="max-h-[500px] overflow-auto">
            <Table>
              <TableHeader className="sticky top-0 bg-background">
                <TableRow>
                  <TableHead className="w-16">Row</TableHead>
                  <TableHead className="w-32">Status</TableHead>
                  <TableHead>External ID</TableHead>
                  <TableHead>Cellar batch</TableHead>
                  <TableHead>Notes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {preview.data.outcomes.map((o) => (
                  <TableRow key={o.row_index}>
                    <TableCell className="text-xs text-muted-foreground">
                      {o.row_index + 1}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={STATUS_BADGE_VARIANT[o.status] ?? "outline"}
                      >
                        {STATUS_LABEL[o.status] ?? o.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {o.external_identifier}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {o.resolved_batch_number ?? "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {o.status === "conflict" && o.conflict_batch_number
                        ? `Already on ${o.conflict_batch_number}`
                        : (o.message ?? "")}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-between">
        <Button variant="outline" onClick={onBack}>
          Back
        </Button>
        <Button onClick={onNext} disabled={!canCommit}>
          Commit {counts.resolved ?? 0}{" "}
          {counts.resolved === 1 ? "row" : "rows"}
        </Button>
      </div>
    </div>
  );
}
