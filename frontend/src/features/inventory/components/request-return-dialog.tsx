"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { ChevronDown } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { PlateLoan } from "../hooks/use-plate-loans";
import { useLoanItemsAction } from "../hooks/use-plate-loans";

export interface RequestReturnDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  loan: PlateLoan;
  /** Items being returned — the checked/eligible checked-out items from the loan card. */
  itemIds: string[];
}

interface ReturningGroup {
  id: string;
  label: string;
}

/** Distinct groups among the returning items, in first-seen order. Items with
 * no group_id are excluded — the backend doesn't require a note for them. */
function deriveGroups(items: PlateLoan["items"]): ReturningGroup[] {
  const byId = new Map<string, { name: string; barcodes: string[] }>();
  for (const item of items) {
    if (!item.group_id) continue;
    const existing = byId.get(item.group_id);
    if (existing) existing.barcodes.push(item.barcode);
    else
      byId.set(item.group_id, { name: item.group_name ?? "Ungrouped", barcodes: [item.barcode] });
  }
  return [...byId.entries()].map(([id, { name, barcodes }]) => ({
    id,
    label: `${name} (${barcodes.join(", ")})`,
  }));
}

export function RequestReturnDialog({
  open,
  onOpenChange,
  loan,
  itemIds,
}: RequestReturnDialogProps) {
  const action = useLoanItemsAction();
  const returningItems = useMemo(
    () => loan.items.filter((i) => itemIds.includes(i.id)),
    [loan.items, itemIds],
  );
  const groups = useMemo(() => deriveGroups(returningItems), [returningItems]);

  const [groupNotes, setGroupNotes] = useState<Record<string, string>>({});
  const [plateNotes, setPlateNotes] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!open) return;
    setGroupNotes({});
    setPlateNotes({});
  }, [open]);

  const canSubmit = groups.every((g) => (groupNotes[g.id] ?? "").trim() !== "");

  const handleSubmit = () => {
    const comments = groups.map((g) => ({ group_id: g.id, body: groupNotes[g.id].trim() }));
    const plateComments = returningItems
      .map((item) => ({ plate_id: item.plate_id, body: (plateNotes[item.id] ?? "").trim() }))
      .filter((c) => c.body !== "");
    action.mutate(
      { loanId: loan.id, verb: "request-return", itemIds, comments, plateComments },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Request return</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          {groups.map((g) => (
            <div key={g.id} className="flex flex-col gap-2">
              <Label htmlFor={`group-note-${g.id}`}>{g.label}</Label>
              <Textarea
                id={`group-note-${g.id}`}
                rows={2}
                value={groupNotes[g.id] ?? ""}
                onChange={(e) => setGroupNotes((prev) => ({ ...prev, [g.id]: e.target.value }))}
              />
            </div>
          ))}

          <Collapsible>
            <CollapsibleTrigger className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
              <ChevronDown className="h-4 w-4" />
              Per-plate notes (optional)
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2 flex flex-col gap-3">
              {returningItems.map((item) => (
                <div key={item.id} className="flex flex-col gap-2">
                  <Label htmlFor={`plate-note-${item.id}`}>{item.barcode}</Label>
                  <Textarea
                    id={`plate-note-${item.id}`}
                    rows={2}
                    value={plateNotes[item.id] ?? ""}
                    onChange={(e) =>
                      setPlateNotes((prev) => ({ ...prev, [item.id]: e.target.value }))
                    }
                  />
                </div>
              ))}
            </CollapsibleContent>
          </Collapsible>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={action.isPending}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={action.isPending || !canSubmit}>
            Request return
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
