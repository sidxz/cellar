"use client";

import { useState } from "react";
import { Button, buttonVariants } from "@/shared/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/components/ui/alert-dialog";
import { Input } from "@/shared/components/ui/input";
import { Textarea } from "@/shared/components/ui/textarea";
import { useCascadePreview } from "@/shared/hooks/use-cascade-preview";
import { useCascadeDelete } from "@/shared/hooks/use-cascade-delete";
import type { CascadeNodeResponse } from "@/shared/lib/api/model";
import { AlertTriangle } from "lucide-react";

export interface CascadeDeleteDialogProps {
  entityType: string;
  entityId: string;
  entityLabel: string;
  onDeleted?: () => void;
}

function NodeView({
  node,
  depth = 0,
}: {
  node: CascadeNodeResponse;
  depth?: number;
}) {
  const indent = depth * 16;
  const actionColor =
    node.action === "block"
      ? "text-destructive font-semibold"
      : node.action === "set_null"
        ? "text-amber-600"
        : node.action === "warn"
          ? "text-muted-foreground"
          : "";

  const sampleLabels = node.samples
    .map((s) => (s as Record<string, unknown>)["label"])
    .filter((l): l is string => typeof l === "string" && l.length > 0);

  return (
    <div style={{ paddingLeft: indent }} className="text-sm">
      <span className={actionColor}>
        [{node.action}] {node.display_label}: {node.count}
      </span>
      {sampleLabels.length > 0 && (
        <span className="text-muted-foreground ml-2 text-xs">
          ({sampleLabels.join(", ")}
          {node.truncated ? ", …" : ""})
        </span>
      )}
      {(node.children ?? []).map((c, i) => (
        <NodeView key={`${c.table}-${i}`} node={c} depth={depth + 1} />
      ))}
    </div>
  );
}

export function CascadeDeleteDialog({
  entityType,
  entityId,
  entityLabel,
  onDeleted,
}: CascadeDeleteDialogProps) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");

  const preview = useCascadePreview(entityType, entityId, open);
  const m = useCascadeDelete({
    onSuccess: () => {
      setOpen(false);
      onDeleted?.();
    },
  });

  const canSubmit = typed === entityLabel && reason.trim().length > 0;

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>
        <Button variant="destructive" size="sm">
          <AlertTriangle className="mr-1 h-4 w-4" />
          Force delete (cascade)
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <AlertDialogHeader>
          <AlertDialogTitle>
            Force delete {entityType}: {entityLabel}
          </AlertDialogTitle>
          <AlertDialogDescription>
            Hard delete. All dependent rows will be removed or unlinked as
            shown. This cannot be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {preview.isLoading && <p>Computing impact…</p>}
        {preview.data && <NodeView node={preview.data} />}

        <div className="space-y-2 pt-2">
          <label className="text-sm font-medium">
            Type{" "}
            <code className="bg-muted px-1 rounded">{entityLabel}</code> to
            confirm:
          </label>
          <Input value={typed} onChange={(e) => setTyped(e.target.value)} />
          <Textarea
            placeholder="Reason for deletion (required)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
          />
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className={buttonVariants({ variant: "destructive" })}
            disabled={!canSubmit || m.isPending}
            onClick={(e) => {
              e.preventDefault();
              m.mutate({
                entityType,
                entityId,
                typedName: typed,
                reason,
              });
            }}
          >
            {m.isPending ? "Deleting…" : "Force delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
