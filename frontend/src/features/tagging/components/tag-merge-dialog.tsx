"use client";

import { TagChip } from "@/shared/components/tag-chip";
import { Button } from "@/shared/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/shared/components/ui/command";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { useState } from "react";
import { useMergeTags, useTags } from "../hooks/use-tags";
import type { Tag } from "../types";

export function TagMergeDialog({
  tag,
  open,
  onOpenChange,
}: {
  tag: Tag | null;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const [q, setQ] = useState("");
  const [target, setTarget] = useState<Tag | null>(null);
  const { data: tags } = useTags({ q: q || undefined, limit: 50 });
  const merge = useMergeTags();
  const candidates = (tags ?? []).filter((t) => t.id !== tag?.id);

  const close = (o: boolean) => {
    if (!o) {
      setTarget(null);
      setQ("");
    }
    onOpenChange(o);
  };

  const submit = () => {
    if (!tag || !target) return;
    merge.mutate(
      { id: tag.id, data: { target_tag_id: target.id } },
      { onSuccess: () => close(false) },
    );
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Merge tag</DialogTitle>
          <DialogDescription>
            Move every assignment of {tag && <TagChip tagKey={tag.key} value={tag.value} />} onto
            another tag, then delete it. This cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <div className="py-2">
          <div className="mb-2 text-sm text-muted-foreground">Merge into:</div>
          {target ? (
            <div className="flex items-center gap-2">
              <TagChip tagKey={target.key} value={target.value} />
              <Button variant="ghost" size="sm" onClick={() => setTarget(null)}>
                Change
              </Button>
            </div>
          ) : (
            <Command shouldFilter={false} className="rounded-md border">
              <CommandInput
                value={q}
                onValueChange={setQ}
                placeholder="Search target tag…"
                className="h-8 text-sm"
              />
              <CommandList>
                <CommandEmpty className="px-3 py-2 text-xs text-muted-foreground">
                  No tags.
                </CommandEmpty>
                <CommandGroup>
                  {candidates.map((t) => (
                    <CommandItem
                      key={t.id}
                      value={`${t.key}=${t.value ?? ""}`}
                      onSelect={() => setTarget(t)}
                      className="text-sm"
                    >
                      <TagChip tagKey={t.key} value={t.value} />
                    </CommandItem>
                  ))}
                </CommandGroup>
              </CommandList>
            </Command>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => close(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!target || merge.isPending}>
            {merge.isPending ? "Merging…" : "Merge"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
