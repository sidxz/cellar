"use client";

import { DeleteBlockerList } from "@/shared/components/delete-blocker-list";
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
import { Button, buttonVariants } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { Textarea } from "@/shared/components/ui/textarea";
import { getDeleteBlockedError } from "@/shared/hooks/use-admin-delete";
import { useCascadeDelete } from "@/shared/hooks/use-cascade-delete";
import { useCascadePreview } from "@/shared/hooks/use-cascade-preview";
import type { BlockerPayload, CascadeNodeResponse } from "@/shared/lib/api/model";
import { AlertTriangle } from "lucide-react";
import { useId, useState } from "react";

export interface CascadeDeleteDialogProps {
  entityType: string;
  entityId: string;
  entityLabel: string;
  onDeleted?: () => void;
  /** Controlled open state. When provided, the built-in red trigger button is
   *  NOT rendered — drive the dialog from your own control (e.g. a menu item).
   *  Omit both for the default self-triggering button behavior. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

function NodeView({
  node,
  depth = 0,
}: {
  node: CascadeNodeResponse;
  depth?: number;
}) {
  const indent = depth * 16;
  const actionColor = node.action === "set_null" ? "text-amber-600" : "";

  const sampleLabels = node.samples
    .map((s) => (s as Record<string, unknown>).label)
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
  open: controlledOpen,
  onOpenChange,
}: CascadeDeleteDialogProps) {
  const typedNameId = useId();
  const reasonId = useId();
  const blockersId = useId();
  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : internalOpen;
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");
  // Blockers returned by a delete that a new reference beat after the preview.
  const [refused, setRefused] = useState<BlockerPayload[] | null>(null);
  const setOpen = (next: boolean) => {
    if (!isControlled) setInternalOpen(next);
    if (!next) setRefused(null);
    onOpenChange?.(next);
  };

  const preview = useCascadePreview(entityType, entityId, open);
  const m = useCascadeDelete({
    onSuccess: () => {
      setOpen(false);
      onDeleted?.();
    },
  });

  const blockers = refused ?? preview.data?.blockers ?? [];
  const warnings = preview.data?.warnings ?? [];
  const canSubmit =
    preview.isSuccess && blockers.length === 0 && typed === entityLabel && reason.trim().length > 0;

  async function onConfirm() {
    setRefused(null);
    try {
      await m.mutateAsync({ entityType, entityId, typedName: typed, reason });
    } catch (err: unknown) {
      const blocked = getDeleteBlockedError(err);
      if (blocked) {
        setRefused(blocked.blockers);
        void preview.refetch();
      }
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      {!isControlled && (
        <AlertDialogTrigger asChild>
          <Button variant="destructive" size="sm">
            <AlertTriangle className="mr-1 h-4 w-4" />
            Force delete (cascade)
          </Button>
        </AlertDialogTrigger>
      )}
      <AlertDialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <AlertDialogHeader>
          <AlertDialogTitle>
            Force delete {entityType}: {entityLabel}
          </AlertDialogTitle>
          <AlertDialogDescription>
            Hard delete. All dependent rows will be removed or unlinked as shown. This cannot be
            undone.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {preview.isLoading && <p>Computing impact…</p>}
        {preview.isError && (
          <p className="text-sm text-destructive">
            Couldn't compute what this delete affects. Close the dialog and try again.
          </p>
        )}

        {blockers.length > 0 && (
          <div id={blockersId} role="alert" className="space-y-1 text-sm">
            <p className="font-semibold text-destructive">
              Can't force delete while these still use it:
            </p>
            <DeleteBlockerList items={blockers} />
            <p className="text-muted-foreground text-xs">
              Resolve them first, then open this dialog again.
            </p>
          </div>
        )}

        {warnings.length > 0 && (
          <div className="space-y-1 text-sm">
            <p className="font-medium">Also affected, not blocking:</p>
            <DeleteBlockerList items={warnings} />
          </div>
        )}

        {preview.data && <NodeView node={preview.data} />}

        <div className="space-y-2 pt-2">
          <label htmlFor={typedNameId} className="text-sm font-medium">
            Type <code className="bg-muted px-1 rounded">{entityLabel}</code> to confirm:
          </label>
          <Input id={typedNameId} value={typed} onChange={(e) => setTyped(e.target.value)} />
          <label htmlFor={reasonId} className="text-sm font-medium">
            Reason
          </label>
          <Textarea
            id={reasonId}
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
            aria-describedby={blockers.length > 0 ? blockersId : undefined}
            onClick={(e) => {
              e.preventDefault();
              void onConfirm();
            }}
          >
            {m.isPending ? "Deleting…" : "Force delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
