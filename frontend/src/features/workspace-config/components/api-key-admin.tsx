"use client";

import { useEffect, useState } from "react";
import { KeyRound, Pencil, Plus, Trash2 } from "lucide-react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { Switch } from "@/shared/components/ui/switch";
import { Textarea } from "@/shared/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import {
  useApiKeys,
  useCreateApiKey,
  useDeleteApiKey,
  useUpdateApiKey,
  type CreateApiKeyInput,
  type ExternalApiKey,
  type UpdateApiKeyInput,
} from "../hooks/use-api-keys";

// ---------------------------------------------------------------------------
// Known API key definitions — system services that need keys
// ---------------------------------------------------------------------------

const KNOWN_API_KEYS = [
  {
    key_name: "bioportal",
    label: "BioPortal (Ontology Search)",
    description: "Enables ontology term search for protocol annotations (BAO, GO, CLO, etc.)",
    help: "Get a free API key at bioportal.bioontology.org → Account → API Key",
  },
  {
    key_name: "cdd_vault",
    label: "CDD Vault (Protocol Import)",
    description: "Enables importing protocols and data from CDD Vault",
    help: "Find your API key in CDD Vault → Settings → API Key",
  },
] as const;

// ---------------------------------------------------------------------------
// ApiKey dialog (create / edit)
// ---------------------------------------------------------------------------

interface ApiKeyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: ExternalApiKey | null;
}

function ApiKeyDialog({ open, onOpenChange, editing }: ApiKeyDialogProps) {
  const [keyName, setKeyName] = useState("");
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [secretValue, setSecretValue] = useState("");
  const [isActive, setIsActive] = useState(true);

  const isEdit = editing !== null;
  const create = useCreateApiKey();
  const update = useUpdateApiKey(editing?.id ?? "");

  useEffect(() => {
    if (editing) {
      setKeyName(editing.key_name);
      setLabel(editing.label);
      setDescription(editing.description ?? "");
      setSecretValue("");
      setIsActive(editing.is_active);
    } else {
      setKeyName("");
      setLabel("");
      setDescription("");
      setSecretValue("");
      setIsActive(true);
    }
  }, [editing, open]);

  const handleSubmit = async () => {
    if (isEdit) {
      const data: UpdateApiKeyInput = {
        label: label.trim(),
        description: description.trim() || null,
        is_active: isActive,
      };
      if (secretValue.trim()) {
        data.secret_value = secretValue.trim();
      }
      await update.mutateAsync(data);
    } else {
      const data: CreateApiKeyInput = {
        key_name: keyName.trim(),
        label: label.trim(),
        description: description.trim() || null,
        secret_value: secretValue.trim(),
      };
      await create.mutateAsync(data);
    }
    onOpenChange(false);
  };

  const isPending = create.isPending || update.isPending;
  const canSubmit = isEdit
    ? label.trim()
    : keyName.trim() && label.trim() && secretValue.trim();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit API Key" : "New API Key"}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          {!isEdit ? (
            <div className="grid gap-2">
              <Label>Service</Label>
              <Select
                value={keyName}
                onValueChange={(v) => {
                  setKeyName(v);
                  const def = KNOWN_API_KEYS.find((k) => k.key_name === v);
                  if (def) {
                    setLabel(def.label);
                    setDescription(def.description);
                  }
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select service..." />
                </SelectTrigger>
                <SelectContent>
                  {KNOWN_API_KEYS.map((k) => (
                    <SelectItem key={k.key_name} value={k.key_name}>
                      {k.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {keyName && (
                <p className="text-xs text-muted-foreground">
                  {KNOWN_API_KEYS.find((k) => k.key_name === keyName)?.help}
                </p>
              )}
            </div>
          ) : (
            <div className="grid gap-2">
              <Label>Service</Label>
              <Input
                value={KNOWN_API_KEYS.find((k) => k.key_name === editing?.key_name)?.label ?? editing?.key_name ?? ""}
                disabled
              />
            </div>
          )}

          <div className="grid gap-2">
            <Label htmlFor="key-label">Label</Label>
            <Input
              id="key-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g., BioPortal API Key"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="key-description">Description</Label>
            <Textarea
              id="key-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional notes about this key"
              rows={2}
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="key-secret">
              {isEdit ? "New Secret Value (optional)" : "Secret Value"}
            </Label>
            <Input
              id="key-secret"
              type="password"
              value={secretValue}
              onChange={(e) => setSecretValue(e.target.value)}
              placeholder={isEdit ? "Leave blank to keep current value" : "Paste your API key"}
            />
            {isEdit && (
              <p className="text-xs text-muted-foreground">
                Only provide if rotating the secret.
              </p>
            )}
          </div>

          {isEdit && (
            <div className="flex items-center justify-between rounded-md border px-3 py-2">
              <Label htmlFor="key-active" className="cursor-pointer">
                Active
              </Label>
              <Switch
                id="key-active"
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
  apiKey: ExternalApiKey | null;
  onClose: () => void;
}

function DeleteDialog({ apiKey, onClose }: DeleteDialogProps) {
  const deleteMutation = useDeleteApiKey();

  const handleConfirm = async () => {
    if (!apiKey) return;
    await deleteMutation.mutateAsync(apiKey.id);
    onClose();
  };

  return (
    <Dialog open={apiKey !== null} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Delete API Key?</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Permanently delete{" "}
          <span className="font-medium text-foreground">
            {apiKey?.label} ({apiKey?.key_name})
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
// Active toggle
// ---------------------------------------------------------------------------

function ActiveToggle({ entry }: { entry: ExternalApiKey }) {
  const update = useUpdateApiKey(entry.id);
  return (
    <Switch
      checked={entry.is_active}
      onCheckedChange={(checked) => update.mutate({ is_active: checked })}
      disabled={update.isPending}
      aria-label={`Toggle active for ${entry.label}`}
    />
  );
}

// ---------------------------------------------------------------------------
// API Key table
// ---------------------------------------------------------------------------

interface ApiKeyTableProps {
  entries: ExternalApiKey[];
  onEdit: (key: ExternalApiKey) => void;
  onDelete: (key: ExternalApiKey) => void;
}

function ApiKeyTable({ entries, onEdit, onDelete }: ApiKeyTableProps) {
  if (entries.length === 0) {
    return (
      <div className="mt-12 flex flex-col items-center gap-2 text-muted-foreground">
        <KeyRound className="h-10 w-10" />
        <p>No API keys configured yet.</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Label</TableHead>
            <TableHead>Key Name</TableHead>
            <TableHead>Prefix</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Last Used</TableHead>
            <TableHead>Active</TableHead>
            <TableHead className="w-[100px]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.map((entry) => (
            <TableRow key={entry.id}>
              <TableCell className="font-medium">{entry.label}</TableCell>
              <TableCell className="font-mono text-sm text-muted-foreground">
                {entry.key_name}
              </TableCell>
              <TableCell className="font-mono text-sm">
                {entry.key_prefix}{"****"}
              </TableCell>
              <TableCell>
                {entry.is_active ? (
                  <Badge variant="default" className="text-xs">Active</Badge>
                ) : (
                  <Badge variant="destructive" className="text-xs">Inactive</Badge>
                )}
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {entry.last_used_at
                  ? new Date(entry.last_used_at).toLocaleDateString()
                  : "\u2014"}
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
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onDelete(entry)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
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
// ApiKeyAdmin — main component
// ---------------------------------------------------------------------------

export function ApiKeyAdmin() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ExternalApiKey | null>(null);
  const [deleting, setDeleting] = useState<ExternalApiKey | null>(null);

  const { data: entries, isLoading } = useApiKeys();

  const openCreate = () => {
    setEditing(null);
    setDialogOpen(true);
  };

  const openEdit = (key: ExternalApiKey) => {
    setEditing(key);
    setDialogOpen(true);
  };

  return (
    <>
      <PageHeader
        title="API Keys"
        subtitle="Manage external API keys used by integrations (e.g., BioPortal, PubChem)."
      >
        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          Add API Key
        </Button>
      </PageHeader>

      <div className="mt-6">
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : (
          <ApiKeyTable
            entries={entries ?? []}
            onEdit={openEdit}
            onDelete={setDeleting}
          />
        )}
      </div>

      <ApiKeyDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editing={editing}
      />

      <DeleteDialog apiKey={deleting} onClose={() => setDeleting(null)} />
    </>
  );
}
