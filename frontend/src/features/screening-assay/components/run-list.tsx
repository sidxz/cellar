"use client";

import { FlaskConical } from "lucide-react";
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
import { useRunsByProtocol } from "../hooks/use-runs";
import {
  PLATE_FORMAT_LABELS,
  type PlateFormat,
  type Run,
  type RunStatus,
} from "../types";

interface RunListProps {
  protocolId: string;
  onSelect?: (runId: string) => void;
}

function statusBadgeVariant(
  status: RunStatus
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "approved":
      return "default";
    case "completed":
    case "in_progress":
      return "secondary";
    case "rejected":
      return "destructive";
    case "draft":
      return "outline";
  }
}

export function RunList({ protocolId, onSelect }: RunListProps) {
  const { data: runs, isLoading } = useRunsByProtocol(protocolId);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (!runs?.length) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <FlaskConical className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">No runs</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Create a run to start collecting screening data.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Run Date</TableHead>
            <TableHead>Plates</TableHead>
            <TableHead>Format</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Lock</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((run: Run) => (
            <TableRow
              key={run.id}
              className={onSelect ? "cursor-pointer hover:bg-muted/50" : ""}
              onClick={() => onSelect?.(run.id)}
            >
              <TableCell className="font-mono text-sm">
                {run.run_date}
              </TableCell>
              <TableCell>{run.plate_count}</TableCell>
              <TableCell>
                {run.plate_format
                  ? `${PLATE_FORMAT_LABELS[run.plate_format as PlateFormat] ?? run.plate_format}`
                  : "\u2014"}
              </TableCell>
              <TableCell>
                <Badge
                  variant={statusBadgeVariant(run.status as RunStatus)}
                >
                  {run.status}
                </Badge>
              </TableCell>
              <TableCell>
                <Badge variant={run.is_locked ? "destructive" : "outline"}>
                  {run.is_locked ? "Locked" : "Unlocked"}
                </Badge>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
