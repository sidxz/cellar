"use client";

import { TestTubes } from "lucide-react";
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
import { useProtocols } from "../hooks/use-protocols";
import {
  PROTOCOL_TYPE_LABELS,
  type Protocol,
  type ProtocolStatus,
  type ProtocolType,
} from "../types";

interface ProtocolListProps {
  onSelect?: (protocolId: string) => void;
}

function statusBadgeVariant(
  status: ProtocolStatus
): "default" | "outline" | "destructive" {
  switch (status) {
    case "active":
      return "default";
    case "draft":
      return "outline";
    case "retired":
      return "destructive";
  }
}

export function ProtocolList({ onSelect }: ProtocolListProps) {
  const { data: protocols, isLoading, error } = useProtocols();

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-dashed border-destructive/50 p-8 text-center">
        <p className="text-sm text-destructive">Failed to load protocols. Is the backend running?</p>
        <p className="mt-1 text-xs text-muted-foreground">{error.message}</p>
      </div>
    );
  }

  if (!protocols?.length) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <TestTubes className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">No protocols</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Create your first screening protocol to get started.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Version</TableHead>
            <TableHead>Readouts</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {protocols.map((protocol: Protocol) => (
            <TableRow
              key={protocol.id}
              className={onSelect ? "cursor-pointer hover:bg-muted/50" : ""}
              onClick={() => onSelect?.(protocol.id)}
            >
              <TableCell className="font-medium">{protocol.name}</TableCell>
              <TableCell>
                {PROTOCOL_TYPE_LABELS[
                  protocol.protocol_type as ProtocolType
                ] ?? protocol.protocol_type}
              </TableCell>
              <TableCell className="font-mono text-sm">
                v{protocol.protocol_version}
              </TableCell>
              <TableCell>{protocol.readout_definitions.length}</TableCell>
              <TableCell>
                <Badge
                  variant={statusBadgeVariant(
                    protocol.status as ProtocolStatus
                  )}
                >
                  {protocol.status}
                </Badge>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
