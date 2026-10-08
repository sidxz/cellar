"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import type { NamingChangePreviewResponse } from "@/shared/lib/api/model";

interface NamingChangePreviewProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preview: NamingChangePreviewResponse | undefined;
  isLoading: boolean;
  onApply: () => void;
  isApplying: boolean;
}

/** Before -> after for every protocol an admin naming edit renames. Apply is an explicit gesture
 *  and stays disabled while any two protocols would end up with the same name. */
export function NamingChangePreview({
  open,
  onOpenChange,
  preview,
  isLoading,
  onApply,
  isApplying,
}: NamingChangePreviewProps) {
  const collisions = preview?.collisions ?? [];
  const changes = preview?.changes ?? [];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Protocols this renames</DialogTitle>
          <DialogDescription>
            {isLoading
              ? "Working out the new names..."
              : `${changes.length} protocol${changes.length === 1 ? "" : "s"} will be renamed. Old names stay searchable as former names.`}
          </DialogDescription>
        </DialogHeader>
        {collisions.length > 0 && (
          <div
            role="alert"
            className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
          >
            {collisions.map((c) => (
              <p key={c.name}>
                {c.codes.join(", ")} would all be named "{c.name}". Change a discriminator first.
              </p>
            ))}
          </div>
        )}
        <div className="max-h-96 overflow-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="py-1 pr-3">Code</th>
                <th className="py-1 pr-3">Now</th>
                <th className="py-1">After</th>
              </tr>
            </thead>
            <tbody>
              {changes.map((c) => (
                <tr key={c.protocol_id} className="border-t">
                  <td className="py-1 pr-3 font-mono text-xs">{c.code}</td>
                  <td className="py-1 pr-3 text-muted-foreground">{c.before}</td>
                  <td className="py-1">{c.after}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={onApply} disabled={isLoading || isApplying || collisions.length > 0}>
            {isApplying ? "Applying..." : "Apply"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
