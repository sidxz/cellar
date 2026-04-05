"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Clock, FileSignature } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader } from "@/shared/components/ui/card";
import { Separator } from "@/shared/components/ui/separator";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useAuditOperations, useAuditByEntity } from "../hooks/use-audit";
import type { AuditOperation } from "../types";

// ─── Operation type → badge variant mapping ──────────────────────────────────

const OPERATION_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  create: "default",
  update: "secondary",
  delete: "destructive",
  state_change: "outline",
};

function operationVariant(op: string) {
  return OPERATION_VARIANT[op] ?? "outline";
}

// ─── Entry diff row ──────────────────────────────────────────────────────────

function EntryRow({ fieldName, oldValue, newValue }: {
  fieldName: string;
  oldValue: string | null;
  newValue: string | null;
}) {
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-sm">
      <div className="text-right">
        <span className="font-medium text-muted-foreground">{fieldName}</span>
      </div>
      <span className="text-muted-foreground">:</span>
      <div className="flex items-center gap-1.5 min-w-0">
        {oldValue !== null && (
          <span className="text-red-400 line-through truncate max-w-[140px]" title={oldValue}>
            {oldValue}
          </span>
        )}
        {oldValue !== null && newValue !== null && (
          <span className="text-muted-foreground shrink-0">-&gt;</span>
        )}
        {newValue !== null && (
          <span className="text-green-400 truncate max-w-[140px]" title={newValue}>
            {newValue}
          </span>
        )}
      </div>
    </div>
  );
}

// ─── Single operation card ───────────────────────────────────────────────────

function OperationCard({ operation }: { operation: AuditOperation }) {
  const [expanded, setExpanded] = useState(false);
  const hasEntries = operation.entries.length > 0;
  const hasSignature = operation.signature !== null;

  return (
    <Card className="relative">
      <CardHeader className="p-4 pb-2">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={operationVariant(operation.operation_type)}>
              {operation.operation_type}
            </Badge>
            <span className="text-sm font-medium">
              {operation.entity_type}
            </span>
            <span className="text-xs text-muted-foreground font-mono truncate max-w-[120px]" title={operation.entity_id}>
              {operation.entity_id.slice(0, 8)}
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground shrink-0">
            <Clock className="size-3" />
            {new Date(operation.performed_at).toLocaleString()}
          </div>
        </div>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-xs text-muted-foreground">
            by <span className="font-mono">{operation.performed_by.slice(0, 8)}</span>
          </span>
          {operation.reason && (
            <>
              <Separator orientation="vertical" className="h-3" />
              <span className="text-xs text-muted-foreground italic truncate max-w-[200px]" title={operation.reason}>
                {operation.reason}
              </span>
            </>
          )}
        </div>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        {(hasEntries || hasSignature) && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? <ChevronDown className="size-3 mr-1" /> : <ChevronRight className="size-3 mr-1" />}
            {hasEntries ? `${operation.entries.length} change${operation.entries.length !== 1 ? "s" : ""}` : ""}
            {hasEntries && hasSignature ? " + signature" : ""}
            {!hasEntries && hasSignature ? "Signature" : ""}
          </Button>
        )}
        {expanded && (
          <div className="mt-3 space-y-3">
            {hasEntries && (
              <div className="space-y-1.5 rounded-md border p-3">
                {operation.entries.map((entry) => (
                  <EntryRow
                    key={entry.id}
                    fieldName={entry.field_name}
                    oldValue={entry.old_value}
                    newValue={entry.new_value}
                  />
                ))}
              </div>
            )}
            {hasSignature && operation.signature && (
              <div className="flex items-center gap-2 rounded-md border p-3 text-sm">
                <FileSignature className="size-4 text-muted-foreground shrink-0" />
                <span className="text-muted-foreground">Signed by</span>
                <span className="font-mono text-xs">{operation.signature.signer_id.slice(0, 8)}</span>
                <Separator orientation="vertical" className="h-3" />
                <span className="italic text-muted-foreground truncate" title={operation.signature.reason}>
                  {operation.signature.reason}
                </span>
                <span className="ml-auto text-xs text-muted-foreground shrink-0">
                  {new Date(operation.signature.signed_at).toLocaleString()}
                </span>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Loading skeleton ────────────────────────────────────────────────────────

function TimelineSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <Card key={i}>
          <CardHeader className="p-4 pb-2">
            <div className="flex items-center gap-2">
              <Skeleton className="h-5 w-16" />
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-16" />
            </div>
            <Skeleton className="h-3 w-32 mt-1" />
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <Skeleton className="h-7 w-24" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ─── Empty state ─────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <Clock className="size-10 text-muted-foreground/50 mb-3" />
      <p className="text-sm text-muted-foreground">No audit operations found.</p>
    </div>
  );
}

// ─── Timeline (data-driven) ─────────────────────────────────────────────────

function TimelineContent({
  operations,
  isLoading,
}: {
  operations: AuditOperation[] | undefined;
  isLoading: boolean;
}) {
  if (isLoading) return <TimelineSkeleton />;
  if (!operations || operations.length === 0) return <EmptyState />;

  return (
    <div className="space-y-3">
      {operations.map((op) => (
        <OperationCard key={op.id} operation={op} />
      ))}
    </div>
  );
}

// ─── Public components ───────────────────────────────────────────────────────

/** Standalone timeline that fetches its own data with optional filters. */
export function AuditTimeline(props: {
  entityType?: string;
  entityId?: string;
}) {
  // If both entityType and entityId are provided, use the entity-specific hook
  const entityQuery = useAuditByEntity(
    props.entityType ?? "",
    props.entityType && props.entityId ? props.entityId : undefined,
  );

  // Otherwise, fetch all operations (optionally filtered by entity_type)
  const listQuery = useAuditOperations(
    !props.entityId
      ? { entity_type: props.entityType || undefined }
      : undefined,
  );

  // Pick the active query
  const isEntityMode = !!(props.entityType && props.entityId);
  const { data, isLoading } = isEntityMode ? entityQuery : listQuery;

  return <TimelineContent operations={data} isLoading={isLoading} />;
}

/** Data-only timeline that receives pre-fetched operations. */
export function AuditTimelineView({
  operations,
  isLoading,
}: {
  operations: AuditOperation[] | undefined;
  isLoading: boolean;
}) {
  return <TimelineContent operations={operations} isLoading={isLoading} />;
}
