"use client";

import { useEffect, useState } from "react";
import { FlaskRound, Pencil, Plus, Trash2 } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { PageHeader } from "@/shared/components/page-header";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Switch } from "@/shared/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import {
  useCreateSaltEntry,
  useDeleteSaltEntry,
  useSaltCatalog,
  useUpdateSaltEntry,
  type CreateSaltEntryInput,
  type SaltEntry,
  type UpdateSaltEntryInput,
} from "../hooks/use-salt-catalog";

// ---------------------------------------------------------------------------
// Salt dialog (create / edit)
// ---------------------------------------------------------------------------

interface SaltDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: SaltEntry | null;
}

function SaltDialog({ open, onOpenChange, editing }: SaltDialogProps) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [smiles, setSmiles] = useState("");
  const [molecularWeight, setMolecularWeight] = useState("");
  const [isActive, setIsActive] = useState(true);

  const isEdit = editing !== null;
  const create = useCreateSaltEntry();
  const update = useUpdateSaltEntry(editing?.id ?? "");

  useEffect(() => {
    if (editing) {
      setCode(editing.code);
      setName(editing.name);
      setSmiles(editing.smiles);
      setMolecularWeight(String(editing.molecular_weight));
      setIsActive(editing.is_active);
    } else {
      setCode("");
      setName("");
      setSmiles("");
      setMolecularWeight("");
      setIsActive(true);
    }
  }, [editing, open]);

  const handleSubmit = async () => {
    const mw = parseFloat(molecularWeight);
    if (isNaN(mw)) return;

    if (isEdit) {
      const data: UpdateSaltEntryInput = {
        name: name.trim(),
        smiles: smiles.trim(),
        molecular_weight: mw,
        is_active: isActive,
      };
      await update.mutateAsync(data);
    } else {
      const data: CreateSaltEntryInput = {
        code: code.trim(),
        name: name.trim(),
        smiles: smiles.trim(),
        molecular_weight: mw,
      };
      await create.mutateAsync(data);
    }
    onOpenChange(false);
  };

  const isPending = create.isPending || update.isPending;
  const canSubmit =
    name.trim() &&
    smiles.trim() &&
    molecularWeight.trim() &&
    !isNaN(parseFloat(molecularWeight)) &&
    (isEdit || code.trim());

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Salt Entry" : "New Salt Entry"}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          {/* Code — only for create, or read-only for defaults */}
          {!isEdit ? (
            <div className="grid gap-2">
              <Label htmlFor="salt-code">Code</Label>
              <Input
                id="salt-code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="e.g., HCl"
              />
              <p className="text-xs text-muted-foreground">
                Short identifier. Cannot be changed after creation.
              </p>
            </div>
          ) : (
            <div className="grid gap-2">
              <Label>Code</Label>
              <Input
                value={editing?.code ?? ""}
                disabled
                className="font-mono"
              />
            </div>
          )}

          <div className="grid gap-2">
            <Label htmlFor="salt-name">Name</Label>
            <Input
              id="salt-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Hydrochloride"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="salt-smiles">SMILES</Label>
            <Input
              id="salt-smiles"
              value={smiles}
              onChange={(e) => setSmiles(e.target.value)}
              placeholder="e.g., [Cl-]"
              className="font-mono"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="salt-mw">Molecular Weight (Da)</Label>
            <Input
              id="salt-mw"
              type="number"
              value={molecularWeight}
              onChange={(e) => setMolecularWeight(e.target.value)}
              placeholder="e.g., 36.46"
              min={0}
              step="0.01"
            />
          </div>

          {isEdit && (
            <div className="flex items-center justify-between rounded-md border px-3 py-2">
              <Label htmlFor="salt-active" className="cursor-pointer">
                Active
              </Label>
              <Switch
                id="salt-active"
                checked={isActive}
                onCheckedChange={setIsActive}
              />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit || isPending}>
            {isPending ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Delete confirmation dialog
// ---------------------------------------------------------------------------

interface DeleteDialogProps {
  salt: SaltEntry | null;
  onClose: () => void;
}

function DeleteDialog({ salt, onClose }: DeleteDialogProps) {
  const deleteMutation = useDeleteSaltEntry();

  const handleConfirm = async () => {
    if (!salt) return;
    await deleteMutation.mutateAsync(salt.id);
    onClose();
  };

  return (
    <Dialog open={salt !== null} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Delete Salt Entry?</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Permanently delete{" "}
          <span className="font-medium text-foreground">
            {salt?.name} ({salt?.code})
          </span>
          ? This action cannot be undone.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? "Deleting..." : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Active toggle — needs its own component so the hook is called at top level
// ---------------------------------------------------------------------------

function ActiveToggle({ entry }: { entry: SaltEntry }) {
  const update = useUpdateSaltEntry(entry.id);
  return (
    <Switch
      checked={entry.is_active}
      onCheckedChange={(checked) => update.mutate({ is_active: checked })}
      disabled={update.isPending}
      aria-label={`Toggle active for ${entry.name}`}
    />
  );
}

// ---------------------------------------------------------------------------
// Salt table
// ---------------------------------------------------------------------------

interface SaltTableProps {
  entries: SaltEntry[];
  onEdit: (salt: SaltEntry) => void;
  onDelete: (salt: SaltEntry) => void;
}

function SaltTable({ entries, onEdit, onDelete }: SaltTableProps) {
  if (entries.length === 0) {
    return (
      <div className="mt-12 flex flex-col items-center gap-2 text-muted-foreground">
        <FlaskRound className="h-10 w-10" />
        <p>No salt entries defined yet.</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Code</TableHead>
            <TableHead>Name</TableHead>
            <TableHead>SMILES</TableHead>
            <TableHead>MW (Da)</TableHead>
            <TableHead>Default</TableHead>
            <TableHead>Active</TableHead>
            <TableHead className="w-[100px]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.map((entry) => (
            <TableRow key={entry.id}>
              <TableCell className="font-mono font-medium text-sm">
                {entry.code}
              </TableCell>
              <TableCell>{entry.name}</TableCell>
              <TableCell className="font-mono text-xs text-muted-foreground max-w-[200px] truncate">
                {entry.smiles}
              </TableCell>
              <TableCell className="tabular-nums">
                {entry.molecular_weight.toFixed(2)}
              </TableCell>
              <TableCell>
                {entry.is_default ? (
                  <Badge variant="secondary" className="text-xs">
                    Default
                  </Badge>
                ) : (
                  <span className="text-sm text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell>
                <ActiveToggle entry={entry} />
              </TableCell>
              <TableCell>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onEdit(entry)}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  {!entry.is_default && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onDelete(entry)}
                    >
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  )}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SaltCatalogAdmin — main component
// ---------------------------------------------------------------------------

export function SaltCatalogAdmin() {
  const [showAll, setShowAll] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<SaltEntry | null>(null);
  const [deleting, setDeleting] = useState<SaltEntry | null>(null);

  const { data: entries, isLoading } = useSaltCatalog(!showAll);

  const openCreate = () => {
    setEditing(null);
    setDialogOpen(true);
  };

  const openEdit = (salt: SaltEntry) => {
    setEditing(salt);
    setDialogOpen(true);
  };

  return (
    <>
      <PageHeader
        title="Salt Catalog"
        subtitle="Manage the salt forms used during structure standardization and parent extraction."
      >
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Switch
            id="show-all"
            checked={showAll}
            onCheckedChange={setShowAll}
          />
          <label htmlFor="show-all" className="cursor-pointer select-none">
            Show inactive
          </label>
        </div>
        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          Add Salt
        </Button>
      </PageHeader>

      <div className="mt-6">
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : (
          <SaltTable
            entries={entries ?? []}
            onEdit={openEdit}
            onDelete={setDeleting}
          />
        )}
      </div>

      <SaltDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editing={editing}
      />

      <DeleteDialog
        salt={deleting}
        onClose={() => setDeleting(null)}
      />
    </>
  );
}
