"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Plus, RotateCcw, Trash2 } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
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
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/shared/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { PageHeader } from "@/shared/components/page-header";
import {
  useDataSource,
  useUpdateDataSource,
  useDataSourceTemplate,
  type EntityMapping,
  type FieldMapping,
  type IdStorageConfig,
} from "../hooks/use-data-sources";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SOURCE_TYPE_LABELS: Record<string, string> = {
  cdd_vault: "CDD Vault",
  chembl: "ChEMBL",
  pubchem: "PubChem",
  custom: "Custom",
};

const ENTITY_TYPE_LABELS: Record<string, string> = {
  molecule: "Molecules",
  batch: "Batches",
  plate: "Plates",
};

/** Entity types that are shown as sub-sections of their parent tab, not as standalone tabs. */
const CHILD_ENTITY_PARENTS: Record<string, string> = {
  well: "plate",
};

const TARGET_TYPES = [
  { value: "core", label: "Core Field" },
  { value: "custom_field", label: "Custom Field" },
  { value: "identifier", label: "Identifier" },
];

const STORAGE_TYPES = [
  { value: "identifier", label: "Identifier" },
  { value: "custom_field", label: "Custom Field" },
];

// ---------------------------------------------------------------------------
// Entity Mapping Editor
// ---------------------------------------------------------------------------

interface EntityMappingEditorProps {
  mapping: EntityMapping;
  onChange: (updated: EntityMapping) => void;
}

function EntityMappingEditor({ mapping, onChange }: EntityMappingEditorProps) {
  const updateIdStorage = (partial: Partial<IdStorageConfig>) => {
    onChange({
      ...mapping,
      id_storage: { ...mapping.id_storage, ...partial },
    });
  };

  const updateFieldMapping = (index: number, partial: Partial<FieldMapping>) => {
    const updated = [...mapping.field_mappings];
    updated[index] = { ...updated[index], ...partial };
    onChange({ ...mapping, field_mappings: updated });
  };

  const removeFieldMapping = (index: number) => {
    onChange({
      ...mapping,
      field_mappings: mapping.field_mappings.filter((_, i) => i !== index),
    });
  };

  const addFieldMapping = () => {
    onChange({
      ...mapping,
      field_mappings: [
        ...mapping.field_mappings,
        { source_field: "", target_field: "", target_type: "core" },
      ],
    });
  };

  return (
    <div className="space-y-6">
      {/* ID field config */}
      <div className="rounded-md border p-4 space-y-4">
        <h4 className="text-sm font-medium">ID Mapping</h4>
        <div className="grid grid-cols-4 gap-4">
          <div className="grid gap-1.5">
            <Label className="text-xs">Source ID Field</Label>
            <Input
              value={mapping.id_field}
              onChange={(e) =>
                onChange({ ...mapping, id_field: e.target.value })
              }
              placeholder="e.g., id"
            />
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Parent Path</Label>
            <Input
              value={mapping.parent_path ?? ""}
              onChange={(e) =>
                onChange({
                  ...mapping,
                  parent_path: e.target.value || null,
                })
              }
              placeholder="e.g., batches"
            />
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Storage Type</Label>
            <Select
              value={mapping.id_storage.storage_type}
              onValueChange={(v) =>
                updateIdStorage({
                  storage_type: v as "identifier" | "custom_field",
                  identifier_type:
                    v === "identifier"
                      ? mapping.id_storage.identifier_type
                      : null,
                  custom_field_name:
                    v === "custom_field"
                      ? mapping.id_storage.custom_field_name
                      : null,
                })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STORAGE_TYPES.map((st) => (
                  <SelectItem key={st.value} value={st.value}>
                    {st.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">
              {mapping.id_storage.storage_type === "identifier"
                ? "Identifier Type"
                : "Custom Field Name"}
            </Label>
            <Input
              value={
                mapping.id_storage.storage_type === "identifier"
                  ? mapping.id_storage.identifier_type ?? ""
                  : mapping.id_storage.custom_field_name ?? ""
              }
              onChange={(e) => {
                if (mapping.id_storage.storage_type === "identifier") {
                  updateIdStorage({ identifier_type: e.target.value || null });
                } else {
                  updateIdStorage({
                    custom_field_name: e.target.value || null,
                  });
                }
              }}
              placeholder={
                mapping.id_storage.storage_type === "identifier"
                  ? "e.g., cdd_molecule_id"
                  : "e.g., cdd_batch_id"
              }
            />
          </div>
        </div>
      </div>

      {/* Field mappings table */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-medium">Field Mappings</h4>
          <Button variant="outline" size="sm" onClick={addFieldMapping}>
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            Add Mapping
          </Button>
        </div>

        {mapping.field_mappings.length === 0 ? (
          <div className="rounded-md border p-6 text-center text-sm text-muted-foreground">
            No field mappings configured.
          </div>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Source Field</TableHead>
                  <TableHead className="w-10 text-center">&rarr;</TableHead>
                  <TableHead>Target Field</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {mapping.field_mappings.map((fm, i) => (
                  <TableRow key={i}>
                    <TableCell>
                      <Input
                        value={fm.source_field}
                        onChange={(e) =>
                          updateFieldMapping(i, {
                            source_field: e.target.value,
                          })
                        }
                        placeholder="e.g., name"
                        className="h-8"
                      />
                    </TableCell>
                    <TableCell className="text-center text-muted-foreground">
                      &rarr;
                    </TableCell>
                    <TableCell>
                      <Input
                        value={fm.target_field}
                        onChange={(e) =>
                          updateFieldMapping(i, {
                            target_field: e.target.value,
                          })
                        }
                        placeholder="e.g., name"
                        className="h-8"
                      />
                    </TableCell>
                    <TableCell>
                      <Select
                        value={fm.target_type}
                        onValueChange={(v) =>
                          updateFieldMapping(i, { target_type: v as FieldMapping["target_type"] })
                        }
                      >
                        <SelectTrigger className="h-8">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {TARGET_TYPES.map((tt) => (
                            <SelectItem key={tt.value} value={tt.value}>
                              {tt.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeFieldMapping(i)}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DataSourceDetail — main component
// ---------------------------------------------------------------------------

interface DataSourceDetailProps {
  dataSourceId: string;
}

export function DataSourceDetail({ dataSourceId }: DataSourceDetailProps) {
  const router = useRouter();
  const { data: ds, isLoading } = useDataSource(dataSourceId);
  const update = useUpdateDataSource(dataSourceId);

  // Local edit state
  const [name, setName] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [mappings, setMappings] = useState<EntityMapping[]>([]);
  const [dirty, setDirty] = useState(false);

  // Active tab for entity type
  const entityTypes = mappings.map((m) => m.entity_type);
  const [activeTab, setActiveTab] = useState(entityTypes[0] ?? "molecule");

  // Template for reset
  const { data: template } = useDataSourceTemplate(ds?.source_type ?? null);

  // Sync from server
  useEffect(() => {
    if (ds) {
      setName(ds.name);
      setIsActive(ds.is_active);
      setMappings(structuredClone(ds.entity_mappings));
      setDirty(false);
      if (ds.entity_mappings.length > 0) {
        setActiveTab(ds.entity_mappings[0].entity_type);
      }
    }
  }, [ds]);

  const handleMappingChange = (entityType: string, updated: EntityMapping) => {
    setMappings((prev) =>
      prev.map((m) => (m.entity_type === entityType ? updated : m))
    );
    setDirty(true);
  };

  const handleSave = async () => {
    await update.mutateAsync({
      name: name.trim(),
      is_active: isActive,
      entity_mappings: mappings,
    });
    setDirty(false);
  };

  const handleReset = () => {
    if (template) {
      setMappings(structuredClone(template));
      setDirty(true);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!ds) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        Data source not found.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push("/admin/data-sources")}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <PageHeader
          title={ds.name}
          subtitle={`${SOURCE_TYPE_LABELS[ds.source_type] ?? ds.source_type} data source`}
        />
      </div>

      {/* Header section */}
      <div className="rounded-md border p-4 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="grid gap-1.5">
            <Label>Name</Label>
            <Input
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setDirty(true);
              }}
            />
          </div>
          <div className="grid gap-1.5">
            <Label>Source Type</Label>
            <div className="flex items-center h-9">
              <Badge variant="outline">
                {SOURCE_TYPE_LABELS[ds.source_type] ?? ds.source_type}
              </Badge>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          {"vault_id" in ds.config && (
            <div className="grid gap-1.5">
              <Label>Vault ID</Label>
              <Input value={String(ds.config.vault_id)} disabled />
            </div>
          )}
          {ds.api_key_name && (
            <div className="grid gap-1.5">
              <Label>API Key</Label>
              <Input value={ds.api_key_name} disabled />
            </div>
          )}
        </div>

        <div className="flex items-center gap-3">
          <Switch
            id="ds-active"
            checked={isActive}
            onCheckedChange={(checked) => {
              setIsActive(checked);
              setDirty(true);
            }}
          />
          <Label htmlFor="ds-active" className="cursor-pointer">
            Active
          </Label>
        </div>
      </div>

      {/* Entity Mappings */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold">Entity Mappings</h3>
          {template && (
            <Button variant="outline" size="sm" onClick={handleReset}>
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
              Reset to Defaults
            </Button>
          )}
        </div>

        {mappings.length === 0 ? (
          <div className="rounded-md border p-8 text-center text-sm text-muted-foreground">
            No entity mappings configured for this source type.
          </div>
        ) : (
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList>
              {mappings
                .filter((m) => !CHILD_ENTITY_PARENTS[m.entity_type])
                .map((m) => (
                  <TabsTrigger key={m.entity_type} value={m.entity_type}>
                    {ENTITY_TYPE_LABELS[m.entity_type] ?? m.entity_type}
                  </TabsTrigger>
                ))}
            </TabsList>
            {mappings
              .filter((m) => !CHILD_ENTITY_PARENTS[m.entity_type])
              .map((m) => {
                const children = mappings.filter(
                  (c) => CHILD_ENTITY_PARENTS[c.entity_type] === m.entity_type
                );
                return (
                  <TabsContent key={m.entity_type} value={m.entity_type}>
                    <EntityMappingEditor
                      mapping={m}
                      onChange={(updated) =>
                        handleMappingChange(m.entity_type, updated)
                      }
                    />
                    {children.map((child) => (
                      <div key={child.entity_type} className="mt-6">
                        <h4 className="text-sm font-semibold mb-3 capitalize">
                          {child.entity_type} Mapping
                        </h4>
                        <EntityMappingEditor
                          mapping={child}
                          onChange={(updated) =>
                            handleMappingChange(child.entity_type, updated)
                          }
                        />
                      </div>
                    ))}
                  </TabsContent>
                );
              })}
          </Tabs>
        )}
      </div>

      {/* Save / Cancel */}
      <div className="flex gap-3 border-t pt-4">
        <Button onClick={handleSave} disabled={!dirty || update.isPending}>
          {update.isPending ? "Saving..." : "Save Changes"}
        </Button>
        <Button
          variant="outline"
          onClick={() => router.push("/admin/data-sources")}
        >
          {dirty ? "Discard" : "Back"}
        </Button>
      </div>
    </div>
  );
}
