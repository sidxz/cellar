"use client";

import { PageHeader } from "@/shared/components/page-header";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Controller, useFieldArray, useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import {
  type EntityMapping,
  type FieldMapping,
  type IdStorageConfig,
  useDataSource,
  useDataSourceTemplate,
  useUpdateDataSource,
} from "../hooks/use-data-sources";

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

const idStorageSchema = z.object({
  storage_type: z.enum(["identifier", "custom_field"]),
  identifier_type: z.string().nullable(),
  custom_field_name: z.string().nullable(),
});

const fieldMappingSchema = z.object({
  source_field: z.string(),
  target_field: z.string(),
  target_type: z.enum(["core", "custom_field", "identifier"]),
});

const entityMappingSchema = z.object({
  entity_type: z.string(),
  id_field: z.string(),
  id_storage: idStorageSchema,
  field_mappings: z.array(fieldMappingSchema),
  parent_path: z.string().nullable().optional(),
});

const schema = z.object({
  name: z.string().min(1, "Name is required"),
  isActive: z.boolean(),
  createBatchOnDup: z.boolean(),
  mappings: z.array(entityMappingSchema),
});

type FormValues = z.infer<typeof schema>;

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
// EntityMappingEditor — receives mapping + onChange (unchanged API)
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
              onChange={(e) => onChange({ ...mapping, id_field: e.target.value })}
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
                  identifier_type: v === "identifier" ? mapping.id_storage.identifier_type : null,
                  custom_field_name:
                    v === "custom_field" ? mapping.id_storage.custom_field_name : null,
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
                  ? (mapping.id_storage.identifier_type ?? "")
                  : (mapping.id_storage.custom_field_name ?? "")
              }
              onChange={(e) => {
                if (mapping.id_storage.storage_type === "identifier") {
                  updateIdStorage({ identifier_type: e.target.value || null });
                } else {
                  updateIdStorage({ custom_field_name: e.target.value || null });
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
                  // biome-ignore lint/suspicious/noArrayIndexKey: field mappings have no stable id
                  <TableRow key={i}>
                    <TableCell>
                      <Input
                        value={fm.source_field}
                        onChange={(e) => updateFieldMapping(i, { source_field: e.target.value })}
                        placeholder="e.g., name"
                        className="h-8"
                      />
                    </TableCell>
                    <TableCell className="text-center text-muted-foreground">&rarr;</TableCell>
                    <TableCell>
                      <Input
                        value={fm.target_field}
                        onChange={(e) => updateFieldMapping(i, { target_field: e.target.value })}
                        placeholder="e.g., name"
                        className="h-8"
                      />
                    </TableCell>
                    <TableCell>
                      <Select
                        value={fm.target_type}
                        onValueChange={(v) =>
                          updateFieldMapping(i, {
                            target_type: v as FieldMapping["target_type"],
                          })
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
                      <Button variant="ghost" size="sm" onClick={() => removeFieldMapping(i)}>
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

  // Template for reset
  const { data: template } = useDataSourceTemplate(ds?.source_type ?? null);

  const {
    register,
    handleSubmit,
    control,
    reset,
    setValue,
    formState: { isDirty, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      isActive: true,
      createBatchOnDup: false,
      mappings: [],
    },
  });

  // useFieldArray for the mappings list (supports reset-to-template)
  const { fields: mappingFields, replace: replaceMappings } = useFieldArray({
    control,
    name: "mappings",
  });

  // Track active tab for entity type separately — not part of submission payload
  const mappings = useWatch({ control, name: "mappings" });
  const entityTypes = mappings.map((m) => m.entity_type);

  // Sync from server data on load
  useEffect(() => {
    if (ds) {
      reset({
        name: ds.name,
        isActive: ds.is_active,
        createBatchOnDup: ds.create_batch_on_duplicate ?? false,
        // Backend types `target_type` / `storage_type` as bare `str`; the editor
        // narrows them to its allowed values (enforced by the form's zod schema).
        mappings: structuredClone(ds.entity_mappings) as EntityMapping[],
      });
    }
  }, [ds, reset]);

  const handleMappingChange = (entityType: string, updated: EntityMapping) => {
    const idx = mappings.findIndex((m) => m.entity_type === entityType);
    if (idx !== -1) {
      setValue(`mappings.${idx}`, updated, { shouldDirty: true });
    }
  };

  const handleReset = () => {
    if (template) {
      // Same narrowing as the seed effect: the template endpoint returns the
      // widened EntityMappingResponse; the form constrains the union values.
      replaceMappings(structuredClone(template) as EntityMapping[]);
    }
  };

  const onSubmit = async (values: FormValues) => {
    await update.mutateAsync({
      name: values.name.trim(),
      is_active: values.isActive,
      create_batch_on_duplicate: values.createBatchOnDup,
      entity_mappings: values.mappings,
    });
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
    return <div className="py-12 text-center text-muted-foreground">Data source not found.</div>;
  }

  // Active tab state is derived — default to first mapping's entity_type
  const defaultTab = entityTypes[0] ?? "molecule";

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => router.push("/admin/data-sources")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <PageHeader
          title={ds.name}
          subtitle={`${SOURCE_TYPE_LABELS[ds.source_type] ?? ds.source_type} data source`}
        />
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        {/* Header section */}
        <div className="rounded-md border p-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-1.5">
              <Label>Name</Label>
              <Input {...register("name")} />
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
            <Controller
              name="isActive"
              control={control}
              render={({ field }) => (
                <Switch id="ds-active" checked={field.value} onCheckedChange={field.onChange} />
              )}
            />
            <Label htmlFor="ds-active" className="cursor-pointer">
              Active
            </Label>
          </div>

          <div className="flex items-start justify-between gap-4 rounded-md border p-3">
            <div>
              <Label htmlFor="ds-cbod" className="text-sm font-medium">
                Create batch on re-import
              </Label>
              <p className="text-xs text-muted-foreground mt-1">
                When off, scheduled syncs from this source only update existing molecules with new
                metadata; they do not create duplicate batches.
              </p>
            </div>
            <Controller
              name="createBatchOnDup"
              control={control}
              render={({ field }) => (
                <Switch id="ds-cbod" checked={field.value} onCheckedChange={field.onChange} />
              )}
            />
          </div>
        </div>

        {/* Entity Mappings */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-semibold">Entity Mappings</h3>
            {template && (
              <Button type="button" variant="outline" size="sm" onClick={handleReset}>
                <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                Reset to Defaults
              </Button>
            )}
          </div>

          {mappingFields.length === 0 ? (
            <div className="rounded-md border p-8 text-center text-sm text-muted-foreground">
              No entity mappings configured for this source type.
            </div>
          ) : (
            <Tabs defaultValue={defaultTab}>
              <TabsList>
                {mappingFields
                  .filter((m) => !CHILD_ENTITY_PARENTS[m.entity_type])
                  .map((m) => (
                    <TabsTrigger key={m.entity_type} value={m.entity_type}>
                      {ENTITY_TYPE_LABELS[m.entity_type] ?? m.entity_type}
                    </TabsTrigger>
                  ))}
              </TabsList>
              {mappingFields
                .filter((m) => !CHILD_ENTITY_PARENTS[m.entity_type])
                .map((m) => {
                  const children = mappingFields.filter(
                    (c) => CHILD_ENTITY_PARENTS[c.entity_type] === m.entity_type,
                  );
                  // Find the live watched value for this entity type
                  const liveMapping = mappings.find((lm) => lm.entity_type === m.entity_type) as
                    | EntityMapping
                    | undefined;
                  return (
                    <TabsContent key={m.entity_type} value={m.entity_type}>
                      {liveMapping && (
                        <EntityMappingEditor
                          mapping={liveMapping}
                          onChange={(updated) => handleMappingChange(m.entity_type, updated)}
                        />
                      )}
                      {children.map((child) => {
                        const liveChild = mappings.find(
                          (lm) => lm.entity_type === child.entity_type,
                        ) as EntityMapping | undefined;
                        return (
                          <div key={child.entity_type} className="mt-6">
                            <h4 className="text-sm font-semibold mb-3 capitalize">
                              {child.entity_type} Mapping
                            </h4>
                            {liveChild && (
                              <EntityMappingEditor
                                mapping={liveChild}
                                onChange={(updated) =>
                                  handleMappingChange(child.entity_type, updated)
                                }
                              />
                            )}
                          </div>
                        );
                      })}
                    </TabsContent>
                  );
                })}
            </Tabs>
          )}
        </div>

        {/* Save / Cancel */}
        <div className="flex gap-3 border-t pt-4">
          <Button type="submit" disabled={!isDirty || isSubmitting || update.isPending}>
            {update.isPending ? "Saving..." : "Save Changes"}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => router.push("/admin/data-sources")}
          >
            {isDirty ? "Discard" : "Back"}
          </Button>
        </div>
      </form>
    </div>
  );
}
