"use client";

import { EmptyState } from "@/shared/components/empty-state";
import { PageHeader } from "@/shared/components/page-header";
import { SkeletonList } from "@/shared/components/skeleton-list";
import { Badge } from "@/shared/components/ui/badge";
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
import { Switch } from "@/shared/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Textarea } from "@/shared/components/ui/textarea";
import { formatDate } from "@/shared/lib/format-date";
import { zodResolver } from "@hookform/resolvers/zod";
import { KeyRound, Pencil, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import {
  type CreateApiKeyInput,
  type ExternalApiKey,
  type UpdateApiKeyInput,
  useApiKeys,
  useCreateApiKey,
  useDeleteApiKey,
  useUpdateApiKey,
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
    help: "Find your API key in CDD Vault settings under API Key",
  },
] as const;

// ---------------------------------------------------------------------------
// ApiKey dialog (create / edit)
// ---------------------------------------------------------------------------

// ── Schema ──────────────────────────────────────────────────────────────────

const formSchema = z.object({
  key_name: z.string().min(1, "Service is required"),
  label: z.string().min(1, "Label is required"),
  description: z.string().optional(),
  secret_value: z.string().optional(),
  is_active: z.boolean(),
});

type FormValues = z.infer<typeof formSchema>;

const defaultValues: FormValues = {
  key_name: "",
  label: "",
  description: "",
  secret_value: "",
  is_active: true,
};

function toFormValues(editing: ExternalApiKey): FormValues {
  return {
    key_name: editing.key_name,
    label: editing.label,
    description: editing.description ?? "",
    secret_value: "",
    is_active: editing.is_active,
  };
}

// ── Props ────────────────────────────────────────────────────────────────────

interface ApiKeyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editing: ExternalApiKey | null;
}

// ── Component ────────────────────────────────────────────────────────────────

function ApiKeyDialog({ open, onOpenChange, editing }: ApiKeyDialogProps) {
  const isEdit = editing !== null;
  const create = useCreateApiKey();
  const update = useUpdateApiKey(editing?.id ?? "");

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues,
  });

  useEffect(() => {
    if (open) {
      form.reset(editing ? toFormValues(editing) : defaultValues);
    }
  }, [open, editing, form]);

  const watchedKeyName = form.watch("key_name");

  const onSubmit = async (values: FormValues) => {
    if (isEdit) {
      const data: UpdateApiKeyInput = {
        label: values.label.trim(),
        description: values.description?.trim() || null,
        is_active: values.is_active,
      };
      if (values.secret_value?.trim()) {
        data.secret_value = values.secret_value.trim();
      }
      await update.mutateAsync(data);
    } else {
      const data: CreateApiKeyInput = {
        key_name: values.key_name.trim(),
        label: values.label.trim(),
        description: values.description?.trim() || null,
        secret_value: values.secret_value?.trim() ?? "",
      };
      await create.mutateAsync(data);
    }
    onOpenChange(false);
  };

  const isPending = create.isPending || update.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit API Key" : "New API Key"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)}>
          <div className="grid gap-4 py-4">
            {!isEdit ? (
              <div className="grid gap-2">
                <Label>Service</Label>
                <Controller
                  name="key_name"
                  control={form.control}
                  render={({ field }) => (
                    <Select
                      value={field.value}
                      onValueChange={(v) => {
                        field.onChange(v);
                        const def = KNOWN_API_KEYS.find((k) => k.key_name === v);
                        if (def) {
                          form.setValue("label", def.label);
                          form.setValue("description", def.description);
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
                  )}
                />
                {form.formState.errors.key_name && (
                  <p className="text-xs text-destructive">
                    {form.formState.errors.key_name.message}
                  </p>
                )}
                {watchedKeyName && (
                  <p className="text-xs text-muted-foreground">
                    {KNOWN_API_KEYS.find((k) => k.key_name === watchedKeyName)?.help}
                  </p>
                )}
              </div>
            ) : (
              <div className="grid gap-2">
                <Label>Service</Label>
                <Input
                  value={
                    KNOWN_API_KEYS.find((k) => k.key_name === editing?.key_name)?.label ??
                    editing?.key_name ??
                    ""
                  }
                  disabled
                />
              </div>
            )}

            <div className="grid gap-2">
              <Label htmlFor="key-label">Label</Label>
              <Input
                id="key-label"
                {...form.register("label")}
                placeholder="e.g., BioPortal API Key"
              />
              {form.formState.errors.label && (
                <p className="text-xs text-destructive">{form.formState.errors.label.message}</p>
              )}
            </div>

            <div className="grid gap-2">
              <Label htmlFor="key-description">Description</Label>
              <Textarea
                id="key-description"
                {...form.register("description")}
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
                {...form.register("secret_value")}
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
                <Controller
                  name="is_active"
                  control={form.control}
                  render={({ field }) => (
                    <Switch
                      id="key-active"
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  )}
                />
              </div>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={form.formState.isSubmitting || isPending}>
              {isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Delete confirmation dialog
// ---------------------------------------------------------------------------

interface DeleteDialogProps {
  apiKey: ExternalApiKey | null;
  onOpenChange: (open: boolean) => void;
}

function DeleteDialog({ apiKey, onOpenChange }: DeleteDialogProps) {
  const deleteMutation = useDeleteApiKey();

  const handleConfirm = async () => {
    if (!apiKey) return;
    await deleteMutation.mutateAsync(apiKey.id);
    onOpenChange(false);
  };

  return (
    <Dialog open={apiKey !== null} onOpenChange={onOpenChange}>
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
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleConfirm} disabled={deleteMutation.isPending}>
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
    return <EmptyState variant="inline" icon={KeyRound} title="No API keys configured yet." />;
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
                {entry.key_prefix}
                {"****"}
              </TableCell>
              <TableCell>
                {entry.is_active ? (
                  <Badge variant="default" className="text-xs">
                    Active
                  </Badge>
                ) : (
                  <Badge variant="destructive" className="text-xs">
                    Inactive
                  </Badge>
                )}
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {entry.last_used_at ? formatDate(entry.last_used_at) : "—"}
              </TableCell>
              <TableCell>
                <ActiveToggle entry={entry} />
              </TableCell>
              <TableCell>
                <div className="flex gap-1">
                  <Button variant="ghost" size="sm" onClick={() => onEdit(entry)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => onDelete(entry)}>
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
          <SkeletonList />
        ) : (
          <ApiKeyTable entries={entries ?? []} onEdit={openEdit} onDelete={setDeleting} />
        )}
      </div>

      <ApiKeyDialog open={dialogOpen} onOpenChange={setDialogOpen} editing={editing} />

      <DeleteDialog apiKey={deleting} onOpenChange={(open) => !open && setDeleting(null)} />
    </>
  );
}
