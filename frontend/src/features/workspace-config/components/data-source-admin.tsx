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
import { Database, Pencil, Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { type ExternalApiKey, useApiKeys } from "../hooks/use-api-keys";
import {
  type CreateDataSourceInput,
  type DataSource,
  useCreateDataSource,
  useDataSources,
  useDeleteDataSource,
  useUpdateDataSource,
} from "../hooks/use-data-sources";

// ---------------------------------------------------------------------------
// Source type definitions
// ---------------------------------------------------------------------------

const SOURCE_TYPES = [
  { value: "cdd_vault", label: "CDD Vault" },
  { value: "chembl", label: "ChEMBL" },
  { value: "pubchem", label: "PubChem" },
  { value: "custom", label: "Custom" },
] as const;

function sourceTypeLabel(type: string): string {
  return SOURCE_TYPES.find((s) => s.value === type)?.label ?? type;
}

// ---------------------------------------------------------------------------
// Create dialog
// ---------------------------------------------------------------------------

interface CreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  apiKeys: ExternalApiKey[];
}

function CreateDialog({ open, onOpenChange, apiKeys }: CreateDialogProps) {
  const [sourceType, setSourceType] = useState("");
  const [name, setName] = useState("");
  const [vaultId, setVaultId] = useState("");
  const [apiKeyName, setApiKeyName] = useState("");

  const create = useCreateDataSource();

  useEffect(() => {
    if (open) {
      setSourceType("");
      setName("");
      setVaultId("");
      setApiKeyName("");
    }
  }, [open]);

  const handleSourceTypeChange = (v: string) => {
    setSourceType(v);
    // Auto-fill name when user picks a source type and the name field is blank
    if (v && !name) {
      setName(sourceTypeLabel(v));
    }
  };

  const handleSubmit = async () => {
    const data: CreateDataSourceInput = {
      name: name.trim(),
      source_type: sourceType,
    };
    if (sourceType === "cdd_vault") {
      data.config = { vault_id: vaultId.trim() };
      data.api_key_name = apiKeyName || undefined;
    } else if (sourceType === "custom") {
      data.api_key_name = apiKeyName || undefined;
    }
    await create.mutateAsync(data);
    onOpenChange(false);
  };

  const canSubmit = (() => {
    if (!sourceType || !name.trim()) return false;
    if (sourceType === "cdd_vault" && (!vaultId.trim() || !apiKeyName)) return false;
    return true;
  })();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Link Data Source</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Source Type</Label>
            <Select value={sourceType} onValueChange={handleSourceTypeChange}>
              <SelectTrigger>
                <SelectValue placeholder="Select source type..." />
              </SelectTrigger>
              <SelectContent>
                {SOURCE_TYPES.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="ds-name">Name</Label>
            <Input
              id="ds-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Production Vault"
            />
          </div>

          {sourceType === "cdd_vault" && (
            <>
              <div className="grid gap-2">
                <Label htmlFor="vault-id">Vault ID</Label>
                <Input
                  id="vault-id"
                  value={vaultId}
                  onChange={(e) => setVaultId(e.target.value)}
                  placeholder="e.g., 12345"
                />
              </div>
              <div className="grid gap-2">
                <Label>API Key</Label>
                <Select value={apiKeyName} onValueChange={setApiKeyName}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select API key..." />
                  </SelectTrigger>
                  <SelectContent>
                    {apiKeys
                      .filter((k) => k.is_active)
                      .map((k) => (
                        <SelectItem key={k.key_name} value={k.key_name}>
                          {k.label}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
                {apiKeys.length === 0 && (
                  <p className="text-xs text-muted-foreground">
                    No API keys configured. Add one in API Keys first.
                  </p>
                )}
              </div>
            </>
          )}

          {sourceType === "custom" && (
            <div className="grid gap-2">
              <Label>API Key (optional)</Label>
              <Select value={apiKeyName} onValueChange={setApiKeyName}>
                <SelectTrigger>
                  <SelectValue placeholder="Select API key..." />
                </SelectTrigger>
                <SelectContent>
                  {apiKeys
                    .filter((k) => k.is_active)
                    .map((k) => (
                      <SelectItem key={k.key_name} value={k.key_name}>
                        {k.label}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {sourceType === "chembl" && (
            <p className="text-sm text-muted-foreground">
              ChEMBL is a public database. No API key or configuration needed.
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit || create.isPending}>
            {create.isPending ? "Linking..." : "Link"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Delete confirmation
// ---------------------------------------------------------------------------

interface DeleteDialogProps {
  dataSource: DataSource | null;
  onOpenChange: (open: boolean) => void;
}

function DeleteDialog({ dataSource, onOpenChange }: DeleteDialogProps) {
  const deleteMutation = useDeleteDataSource();

  const handleConfirm = async () => {
    if (!dataSource) return;
    await deleteMutation.mutateAsync(dataSource.id);
    onOpenChange(false);
  };

  return (
    <Dialog open={dataSource !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Remove Data Source?</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Remove <span className="font-medium text-foreground">{dataSource?.name}</span>? This will
          not delete any imported data.
        </p>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleConfirm} disabled={deleteMutation.isPending}>
            {deleteMutation.isPending ? "Removing..." : "Remove"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Active toggle
// ---------------------------------------------------------------------------

function ActiveToggle({ entry }: { entry: DataSource }) {
  const update = useUpdateDataSource(entry.id);
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
// Data source table
// ---------------------------------------------------------------------------

interface DataSourceTableProps {
  entries: DataSource[];
  onEdit: (ds: DataSource) => void;
  onDelete: (ds: DataSource) => void;
}

function DataSourceTable({ entries, onEdit, onDelete }: DataSourceTableProps) {
  if (entries.length === 0) {
    return <EmptyState variant="inline" icon={Database} title="No data sources linked yet." />;
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>API Key</TableHead>
            <TableHead>Mappings</TableHead>
            <TableHead>Active</TableHead>
            <TableHead className="w-[100px]" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.map((ds) => (
            <TableRow key={ds.id} className="cursor-pointer" onClick={() => onEdit(ds)}>
              <TableCell className="font-medium">{ds.name}</TableCell>
              <TableCell>
                <Badge variant="outline">{sourceTypeLabel(ds.source_type)}</Badge>
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {ds.api_key_name ?? "\u2014"}
              </TableCell>
              <TableCell className="text-sm text-muted-foreground">
                {ds.entity_mappings.length}{" "}
                {ds.entity_mappings.length === 1 ? "entity" : "entities"}
              </TableCell>
              <TableCell onClick={(e) => e.stopPropagation()}>
                <ActiveToggle entry={ds} />
              </TableCell>
              <TableCell onClick={(e) => e.stopPropagation()}>
                <div className="flex gap-1">
                  <Button variant="ghost" size="sm" onClick={() => onEdit(ds)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => onDelete(ds)}>
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
// DataSourceAdmin — main component
// ---------------------------------------------------------------------------

export function DataSourceAdmin() {
  const router = useRouter();
  const [createOpen, setCreateOpen] = useState(false);
  const [deleting, setDeleting] = useState<DataSource | null>(null);

  const { data: sources, isLoading } = useDataSources();
  const { data: apiKeys } = useApiKeys();

  const handleEdit = (ds: DataSource) => {
    router.push(`/admin/data-sources/${ds.id}`);
  };

  return (
    <>
      <PageHeader
        title="Data Sources"
        subtitle="Manage linked external data sources and their field mappings."
      >
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Link Data Source
        </Button>
      </PageHeader>

      <div className="mt-6">
        {isLoading ? (
          <SkeletonList />
        ) : (
          <DataSourceTable entries={sources ?? []} onEdit={handleEdit} onDelete={setDeleting} />
        )}
      </div>

      <CreateDialog open={createOpen} onOpenChange={setCreateOpen} apiKeys={apiKeys ?? []} />

      <DeleteDialog dataSource={deleting} onOpenChange={(open) => !open && setDeleting(null)} />
    </>
  );
}
