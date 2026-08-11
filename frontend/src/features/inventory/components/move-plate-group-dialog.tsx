"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useEffect, useMemo, useState } from "react";
import type { PlateGroupNode, PlateGroupTree } from "../hooks/use-plate-groups";
import { useMovePlateGroup } from "../hooks/use-plate-groups";

const ROOT = "__root__";

interface Option {
  id: string;
  label: string;
}

function collectOptions(
  nodes: PlateGroupNode[],
  excludeId: string,
  depth: number,
  out: Option[],
): void {
  for (const n of nodes) {
    if (n.id === excludeId) continue; // prunes the whole subtree
    out.push({ id: n.id, label: `${" ".repeat(depth * 3)}${n.name}` });
    collectOptions(n.children ?? [], excludeId, depth + 1, out);
  }
}

export interface MovePlateGroupDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  group: PlateGroupNode;
  tree: PlateGroupTree;
}

export function MovePlateGroupDialog({
  open,
  onOpenChange,
  group,
  tree,
}: MovePlateGroupDialogProps) {
  const [target, setTarget] = useState<string>(ROOT);
  const move = useMovePlateGroup();

  useEffect(() => {
    if (open) setTarget(group.parent_group_id ?? ROOT);
  }, [open, group]);

  const options = useMemo(() => {
    const out: Option[] = [];
    collectOptions(tree.roots, group.id, 0, out);
    return out;
  }, [tree, group.id]);

  const handleMove = () => {
    move.mutate(
      { groupId: group.id, parentGroupId: target === ROOT ? null : target },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Move &ldquo;{group.name}&rdquo;</DialogTitle>
        </DialogHeader>
        <Select value={target} onValueChange={setTarget}>
          <SelectTrigger aria-label="New parent">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ROOT}>(top level)</SelectItem>
            {options.map((o) => (
              <SelectItem key={o.id} value={o.id}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={move.isPending}>
            Cancel
          </Button>
          <Button
            onClick={handleMove}
            disabled={move.isPending || target === (group.parent_group_id ?? ROOT)}
          >
            Move
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
