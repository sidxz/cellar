"use client";

import { Boxes } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useBatchesByMolecule } from "../hooks/use-batches";
import { BATCH_SOURCE_LABELS, type Batch, type BatchSource } from "../types";

interface BatchListProps {
  moleculeId?: string;
  onSelectBatch?: (batchId: string | null) => void;
}

export function BatchList({ moleculeId, onSelectBatch }: BatchListProps) {
  const { data: batches, isLoading } = useBatchesByMolecule(moleculeId);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (!moleculeId) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <Boxes className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">Select a compound</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Select a compound from the Compounds page to view its batches.
        </p>
      </div>
    );
  }

  if (!batches?.length) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <Boxes className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">No batches</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          No batches have been created for this compound yet.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Batch #</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>Amount</TableHead>
            <TableHead>Purity</TableHead>
            <TableHead>Salt Form</TableHead>
            <TableHead>Appearance</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {batches.map((batch: Batch) => (
            <TableRow
              key={batch.id}
              className={onSelectBatch ? "cursor-pointer hover:bg-muted/50" : ""}
              onClick={() => onSelectBatch?.(batch.id)}
            >
              <TableCell className="font-mono text-sm">
                {batch.batch_number}
              </TableCell>
              <TableCell>
                <Badge variant="outline">
                  {BATCH_SOURCE_LABELS[batch.source as BatchSource] ??
                    batch.source}
                </Badge>
              </TableCell>
              <TableCell>
                {batch.amount_value} {batch.amount_unit}
              </TableCell>
              <TableCell>
                {batch.purity != null ? `${batch.purity}%` : "—"}
              </TableCell>
              <TableCell>{batch.salt_form ?? "—"}</TableCell>
              <TableCell className="text-muted-foreground">
                {batch.appearance ?? "—"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
