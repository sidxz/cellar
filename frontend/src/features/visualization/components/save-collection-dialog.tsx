"use client";

import { useCreateCollection } from "@/features/research-organization/hooks/use-collections";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { useCanEdit } from "@/shared/hooks/use-current-user";
import { useRouter } from "next/navigation";
import { type FormEvent, useMemo, useState } from "react";
import { usePassMask } from "../hooks/use-pass-mask";
import { actionSet } from "../lib/action-set";
import { uniqueCompounds } from "../lib/dataset";
import { useWorkbench } from "../store/workbench-context";
import type { Dataset } from "../types";

const NO_COMPOUNDS = "No compounds in the current rows (controls and DMSO are excluded)";
const fmt = (n: number) => n.toLocaleString();
const compounds = (n: number) => `${fmt(n)} ${n === 1 ? "compound" : "compounds"}`;

/** Compounds of the sample rows Save acts on (selected ∩ passing, else all passing). */
function useSaveCompounds(ds: Dataset) {
  const selection = useWorkbench((s) => s.selection);
  const mask = usePassMask(ds);
  return useMemo(() => {
    const set = actionSet(ds, selection, mask);
    return { mode: set.mode, ids: uniqueCompounds(ds, set.rows) };
  }, [ds, selection, mask]);
}

/** Table-toolbar "Save N compounds…"; hidden for viewers, disabled with the reason at 0. */
export function SaveCollectionButton({ ds }: { ds: Dataset }) {
  const canEdit = useCanEdit();
  const { ids } = useSaveCompounds(ds);
  const [open, setOpen] = useState(false);
  if (!canEdit) return null;
  return (
    <>
      {/* Disabled buttons show no tooltip, so the reason sits on a wrapper. */}
      <span title={ids.length === 0 ? NO_COMPOUNDS : undefined}>
        <Button
          size="sm"
          variant="outline"
          className="h-7"
          disabled={ids.length === 0}
          onClick={() => setOpen(true)}
        >
          Save {compounds(ids.length)}…
        </Button>
      </span>
      {open && <SaveCollectionDialog ds={ds} open onOpenChange={setOpen} />}
    </>
  );
}

/** Explicit name dialog; creates the collection and its members in one call. */
export function SaveCollectionDialog({
  ds,
  open,
  onOpenChange,
}: {
  ds: Dataset;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { mode, ids } = useSaveCompounds(ds);
  const router = useRouter();
  const create = useCreateCollection((c) => ({
    description: `${c.name} · ${compounds(ids.length)}`,
    action: { label: "Open collection", onClick: () => router.push(`/collections/${c.id}`) },
  }));
  const [name, setName] = useState("");

  const save = (e: FormEvent) => {
    e.preventDefault();
    create.mutate(
      { name: name.trim(), molecule_ids: ids },
      { onSuccess: () => onOpenChange(false) },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={save} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Save as collection</DialogTitle>
            <DialogDescription>
              {compounds(ids.length)} from{" "}
              {mode === "selected" ? "your selection" : "the filtered rows"} · controls and DMSO
              wells are never included
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1">
            <Label htmlFor="workbench-collection-name">Name</Label>
            <Input
              id="workbench-collection-name"
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || ids.length === 0 || create.isPending}>
              Save collection
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
