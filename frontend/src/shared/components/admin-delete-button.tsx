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
import { Textarea } from "@/shared/components/ui/textarea";
import {
  useAdminDelete,
  type AdminDeleteBlocker,
} from "@/shared/hooks/use-admin-delete";
import { Trash2 } from "lucide-react";

export interface AdminDeleteButtonProps {
  entityType: string;
  entityId: string;
  entityLabel: string;
  onDeleted?: () => void;
  triggerLabel?: string;
}

export function AdminDeleteButton({
  entityType,
  entityId,
  entityLabel,
  onDeleted,
  triggerLabel = "Admin: Delete",
}: AdminDeleteButtonProps) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [blockers, setBlockers] = useState<AdminDeleteBlocker[] | null>(null);
  const m = useAdminDelete({
    onSuccess: () => {
      setOpen(false);
      onDeleted?.();
    },
  });

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      setReason("");
      setBlockers(null);
    }
  }

  async function onConfirm() {
    setBlockers(null);
    try {
      await m.mutateAsync({ entityType, entityId, reason });
    } catch (err: unknown) {
      const detail = (err as any)?.response?.data?.detail;
      if (detail?.error === "delete_blocked_by_dependencies") {
        setBlockers(detail.blockers as AdminDeleteBlocker[]);
      }
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={handleOpenChange}>
      <AlertDialogTrigger asChild>
        <Button variant="destructive" size="sm">
          <Trash2 className="mr-1 h-4 w-4" />
          {triggerLabel}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            Delete {entityType}: {entityLabel}
          </AlertDialogTitle>
          <AlertDialogDescription>
            This is a hard delete. Audit-logged.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {blockers ? (
          <div className="space-y-2 text-sm">
            <p className="font-semibold text-destructive">
              Cannot delete — dependencies exist:
            </p>
            <ul className="list-disc pl-5">
              {blockers.map((b) => (
                <li key={b.table}>
                  {b.count} {b.entity_type}
                  {b.count !== 1 ? "s" : ""}
                  {b.samples.length > 0 && (
                    <span className="text-muted-foreground">
                      :{" "}
                      {b.samples
                        .map((s) => {
                          const item = s as Record<string, unknown>;
                          return (item.label as string | null) ?? (item.id as string);
                        })
                        .join(", ")}
                      {b.truncated ? ", …" : ""}
                    </span>
                  )}
                </li>
              ))}
            </ul>
            <p className="text-muted-foreground text-xs pt-2">
              Resolve these references first, then retry.
            </p>
          </div>
        ) : (
          <Textarea
            placeholder="Reason for deletion (required)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
          />
        )}

        <AlertDialogFooter>
          <AlertDialogCancel disabled={m.isPending}>Close</AlertDialogCancel>
          {!blockers && (
            <AlertDialogAction
              className={buttonVariants({ variant: "destructive" })}
              onClick={(e) => {
                e.preventDefault();
                onConfirm();
              }}
              disabled={m.isPending || !reason.trim()}
            >
              {m.isPending ? "Deleting…" : "Delete"}
            </AlertDialogAction>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
