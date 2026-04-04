"use client";

import { Skeleton } from "@/shared/components/ui/skeleton";
import { Badge } from "@/shared/components/ui/badge";
import { cn } from "@/shared/lib/utils";
import { useReadoutDataByRun } from "../hooks/use-readout-data";

// ─── Types ────────────────────────────────────────────────────────────────────

interface ReadoutDataTableProps {
  runId: string;
  className?: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function truncateId(id: string): string {
  return `${id.slice(0, 8)}...`;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ReadoutDataTable({ runId, className }: ReadoutDataTableProps) {
  const { data, isLoading } = useReadoutDataByRun(runId);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        No readout data recorded for this run.
      </p>
    );
  }

  return (
    <div className={cn("max-h-[500px] overflow-auto rounded-md border", className)}>
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-background">
          <tr className="border-b">
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Molecule</th>
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Batch</th>
            <th className="px-3 py-2 text-right font-medium text-muted-foreground">Value</th>
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Qualifier</th>
            <th className="px-3 py-2 text-left font-medium text-muted-foreground">Text</th>
            <th className="px-3 py-2 text-center font-medium text-muted-foreground">Outlier</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.id} className="border-b last:border-b-0 hover:bg-muted/50">
              <td className="px-3 py-2 font-mono text-xs">{truncateId(row.molecule_id)}</td>
              <td className="px-3 py-2 font-mono text-xs">{truncateId(row.batch_id)}</td>
              <td className="px-3 py-2 text-right tabular-nums">
                {row.value_numeric !== null && row.value_numeric !== undefined
                  ? row.value_numeric.toFixed(3)
                  : "\u2014"}
              </td>
              <td className="px-3 py-2 text-muted-foreground">
                {row.value_qualifier ?? "\u2014"}
              </td>
              <td className="px-3 py-2 text-muted-foreground max-w-[200px] truncate">
                {row.value_text ?? "\u2014"}
              </td>
              <td className="px-3 py-2 text-center">
                {row.is_outlier ? (
                  <Badge variant="destructive" className="text-xs">
                    Outlier
                  </Badge>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
