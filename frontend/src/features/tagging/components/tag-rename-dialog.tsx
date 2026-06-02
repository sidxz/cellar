"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { useEffect, useState } from "react";
import { useRenameTag } from "../hooks/use-tags";
import type { Tag } from "../types";

export function TagRenameDialog({
  tag,
  open,
  onOpenChange,
}: {
  tag: Tag | null;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}) {
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const rename = useRenameTag(tag?.id ?? "");

  // biome-ignore lint/correctness/useExhaustiveDependencies: `open` intentionally resets the form when the dialog reopens
  useEffect(() => {
    if (tag) {
      setKey(tag.key);
      setValue(tag.value ?? "");
    }
  }, [tag, open]);

  const submit = async () => {
    await rename.mutateAsync({ key: key.trim(), value: value.trim() || null });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Rename tag</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="tag-key">Key</Label>
            <Input id="tag-key" value={key} onChange={(e) => setKey(e.target.value)} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="tag-value">Value (optional)</Label>
            <Input id="tag-value" value={value} onChange={(e) => setValue(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!key.trim() || rename.isPending}>
            {rename.isPending ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
