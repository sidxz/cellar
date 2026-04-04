"use client";

import { Package } from "lucide-react";
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
import { useSamplesByBatch } from "../hooks/use-samples";
import {
  CONTAINER_TYPE_LABELS,
  SAMPLE_STATUS_LABELS,
  type ContainerType,
  type Sample,
  type SampleStatus,
} from "../types";

interface SampleListProps {
  batchId?: string;
}

function statusBadgeVariant(
  status: SampleStatus
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "available":
      return "default";
    case "quarantined":
      return "secondary";
    case "depleted":
    case "expired":
    case "disposed":
      return "destructive";
    default:
      return "outline";
  }
}

export function SampleList({ batchId }: SampleListProps) {
  const { data: samples, isLoading } = useSamplesByBatch(batchId);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (!batchId) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <Package className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">Select a batch</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Select a batch to view its samples.
        </p>
      </div>
    );
  }

  if (!samples?.length) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <Package className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">No samples</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          No samples have been created for this batch yet.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Barcode</TableHead>
            <TableHead>Container</TableHead>
            <TableHead>Amount</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Solvent</TableHead>
            <TableHead>Freeze/Thaw</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {samples.map((sample: Sample) => (
            <TableRow key={sample.id}>
              <TableCell className="font-mono text-sm">
                {sample.barcode}
              </TableCell>
              <TableCell>
                {CONTAINER_TYPE_LABELS[
                  sample.container_type as ContainerType
                ] ?? sample.container_type}
              </TableCell>
              <TableCell>
                {sample.amount_value} {sample.amount_unit}
              </TableCell>
              <TableCell>
                <Badge
                  variant={statusBadgeVariant(sample.status as SampleStatus)}
                >
                  {SAMPLE_STATUS_LABELS[sample.status as SampleStatus] ??
                    sample.status}
                </Badge>
              </TableCell>
              <TableCell>{sample.solvent ?? "—"}</TableCell>
              <TableCell>{sample.freeze_thaw_count}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
