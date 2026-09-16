"use client";

import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { useEffect, useMemo, useState } from "react";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { useAssignPlatesToGroup } from "../hooks/use-plate-groups";
import { usePlates } from "../hooks/use-plates";

export interface AssignPlatesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  group: PlateGroupNode;
}

export function AssignPlatesDialog({ open, onOpenChange, group }: AssignPlatesDialogProps) {
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const assign = useAssignPlatesToGroup();
  // Org invariant: only same-org plates are assignable — filter server-side.
  const { data: plates, isLoading } = usePlates(
    { owner_org_id: group.owner_org_id },
    { enabled: open },
  );

  useEffect(() => {
    if (open) {
      setSearch("");
      setSelected(new Set());
    }
  }, [open]);

  const candidates = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (plates ?? [])
      .filter((p) => p.group_id !== group.id)
      .filter(
        (p) =>
          q === "" ||
          p.barcode.toLowerCase().includes(q) ||
          p.plate_label.toLowerCase().includes(q),
      );
  }, [plates, search, group.id]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleAssign = () => {
    assign.mutate(
      { groupId: group.id, plateIds: [...selected] },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add plates to &ldquo;{group.name}&rdquo;</DialogTitle>
        </DialogHeader>
        <Input
          placeholder="Search barcode or label…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="max-h-72 overflow-y-auto rounded-md border">
          {isLoading ? (
            <p className="p-3 text-sm text-muted-foreground">Loading…</p>
          ) : candidates.length === 0 ? (
            <p className="p-3 text-sm text-muted-foreground">
              No assignable plates in this organization.
            </p>
          ) : (
            <ul className="divide-y">
              {candidates.map((p) => (
                <li key={p.id} className="flex items-center gap-3 px-3 py-2 text-sm">
                  <Checkbox
                    id={`assign-${p.id}`}
                    checked={selected.has(p.id)}
                    onCheckedChange={() => toggle(p.id)}
                  />
                  <label htmlFor={`assign-${p.id}`} className="flex-1 cursor-pointer">
                    <span className="font-mono">{p.barcode}</span>
                    <span className="ml-2 text-muted-foreground">{p.plate_label}</span>
                    {p.group_id ? (
                      <span className="ml-2 text-xs text-amber-600">
                        will move from its current group
                      </span>
                    ) : null}
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={assign.isPending}>
            Cancel
          </Button>
          <Button onClick={handleAssign} disabled={assign.isPending || selected.size === 0}>
            Add {selected.size > 0 ? `(${selected.size})` : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
