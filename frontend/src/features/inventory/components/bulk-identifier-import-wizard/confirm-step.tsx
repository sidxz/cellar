"use client";

import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import { CheckCircle2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useCommitBulkIdentifiers } from "../../hooks/use-bulk-identifier-import";
import type { BulkAddBatchIdentifiersResponse, BulkIdentifierRowBody } from "../../types";

interface ConfirmStepProps {
  rows: BulkIdentifierRowBody[];
  sourceDefault: string;
  onDone: (result: BulkAddBatchIdentifiersResponse) => void;
}

export function ConfirmStep({ rows, sourceDefault, onDone }: ConfirmStepProps) {
  const router = useRouter();
  const commit = useCommitBulkIdentifiers();

  // biome-ignore lint/correctness/useExhaustiveDependencies: run once on mount to commit the rows; re-running on commit/rows/sourceDefault changes would re-submit the import.
  useEffect(() => {
    if (!commit.isPending && !commit.data) {
      commit.mutate(
        { data: { source_default: sourceDefault, rows } },
        { onSuccess: (data) => onDone(data) },
      );
    }
  }, []);

  if (commit.isPending) {
    return <p className="text-sm text-muted-foreground">Committing…</p>;
  }
  if (commit.error) {
    return (
      <Card>
        <CardContent className="p-6">
          <p className="text-sm text-destructive">
            Commit failed:{" "}
            {commit.error instanceof Error ? commit.error.message : String(commit.error)}
          </p>
        </CardContent>
      </Card>
    );
  }
  if (!commit.data) return null;

  const counts = commit.data.counts;
  const skipped = (counts.not_found ?? 0) + (counts.conflict ?? 0) + (counts.error ?? 0);

  return (
    <Card>
      <CardContent className="space-y-3 p-6">
        <div className="flex items-center gap-3">
          <CheckCircle2 className="h-6 w-6 text-emerald-600" />
          <p className="text-lg font-medium">
            {counts.resolved ?? 0} batch{" "}
            {(counts.resolved ?? 0) === 1 ? "identifier" : "identifiers"} added
          </p>
        </div>
        <p className="text-sm text-muted-foreground">
          {skipped > 0
            ? `${skipped} rows skipped (not_found / conflict / error).`
            : "All rows committed successfully."}
        </p>
        <div className="flex gap-2 pt-2">
          <Button onClick={() => router.push("/inventory#batches")}>Back to Batches</Button>
          <Button variant="outline" onClick={() => router.refresh()}>
            Import another file
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
