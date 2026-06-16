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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { shortId } from "@/shared/lib/utils";
import { useEffect, useState } from "react";

interface MoleculeLite {
  id: string;
  name?: string | null;
  reg_number?: string | null;
}

interface ProjectOption {
  id: string;
  name: string;
}

interface SaveSelectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (args: { name: string; projectId: string | null }) => Promise<void>;
  count: number;
  preview?: MoleculeLite[];
  defaultName: string;
  projects: ProjectOption[];
  defaultProjectId: string | null;
}

export function SaveSelectionDialog({
  open,
  onOpenChange,
  onSave,
  count,
  preview,
  defaultName,
  projects,
  defaultProjectId,
}: SaveSelectionDialogProps) {
  const [name, setName] = useState(defaultName);
  const [projectId, setProjectId] = useState<string | null>(defaultProjectId);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setName(defaultName);
      setProjectId(defaultProjectId);
    }
  }, [open, defaultName, defaultProjectId]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Save {count} compounds as a new collection</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="save-collection-name">Name</Label>
            <Input
              id="save-collection-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label>Project</Label>
            <Select value={projectId ?? ""} onValueChange={(v) => setProjectId(v || null)}>
              <SelectTrigger>
                <SelectValue placeholder="Workspace-wide" />
              </SelectTrigger>
              <SelectContent>
                {projects.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {preview && preview.length > 0 && (
            <div className="max-h-72 overflow-auto rounded border p-2">
              <ul className="grid grid-cols-3 gap-2 text-xs">
                {preview.map((m) => (
                  <li key={m.id} className="rounded border px-2 py-1">
                    <div className="font-mono">{m.reg_number ?? shortId(m.id)}</div>
                    {m.name && <div className="text-muted-foreground truncate">{m.name}</div>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={saving || !name.trim() || count === 0}
            onClick={async () => {
              setSaving(true);
              try {
                await onSave({ name: name.trim(), projectId });
              } finally {
                setSaving(false);
              }
            }}
          >
            Save &amp; open
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
