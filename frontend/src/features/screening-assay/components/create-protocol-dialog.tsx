"use client";

import { useProjects } from "@/features/research-organization/hooks/use-projects";
import { useOntologySlots } from "@/features/workspace-config/hooks/use-ontology-slots";
import {
  type ProtocolForm,
  useProtocolForms,
} from "@/features/workspace-config/hooks/use-protocol-forms";
import { useVocabularies } from "@/features/workspace-config/hooks/use-vocabularies";
import { OntologySearchInput, type OntologyTerm } from "@/shared/components/ontology-search-input";
import { SearchableSelect } from "@/shared/components/searchable-select";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Separator } from "@/shared/components/ui/separator";
import { Switch } from "@/shared/components/ui/switch";
import { Textarea } from "@/shared/components/ui/textarea";
import { customInstance } from "@/shared/lib/api/custom-instance";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";
import { useCreateProtocol, useProtocols } from "../hooks/use-protocols";
import { useTargets } from "../hooks/use-targets";
import {
  VISIBLE_READOUT_DATA_TYPES,
  WELL_CONC_X,
  isReservedReadoutName,
} from "../lib/readout-constants";
import {
  CURVE_TYPE_LABELS,
  type CreateReadoutDefinitionInput,
  type CurveType,
  DOSE_UNIT_LABELS,
  type DoseUnit,
  HILL_SLOPE_CONSTRAINT_LABELS,
  type InterceptSpec,
  NORMALIZATION_SCOPE_LABELS,
  PROTOCOL_TYPE_LABELS,
  type PickListValue,
  type ProtocolType,
  READOUT_AGGREGATION_LABELS,
  READOUT_DATA_TYPE_LABELS,
  type ReadoutNormalization,
} from "../types";
import { FormulaInput } from "./formula-input";
import { InterceptsEditor } from "./intercepts-editor";
import { PickListEditor } from "./pick-list-editor";
import { NormalizationCheckboxGroup } from "./readout-normalization-checkboxes";

// ---------------------------------------------------------------------------
// Zod schemas
// ---------------------------------------------------------------------------

const readoutSchema = z.object({
  name: z.string(),
  data_type: z.string(),
  unit: z.string(),
  aggregation: z.string(),
  normalizations: z.array(z.string()) as z.ZodArray<z.ZodType<ReadoutNormalization>>,
  is_calculated: z.boolean(),
  calculation_formula: z.string(),
  display_order: z.number(),
  pick_list_values: z.array(
    z.object({ label: z.string(), color: z.string().nullable().optional() }),
  ) as z.ZodArray<z.ZodType<PickListValue>>,
  dr_curve_type: z.string(),
  dr_x_readout: z.string(),
  dr_y_readout: z.string(),
  dr_hill_constraint: z.string(),
  dr_normalization_scope: z.string(),
  dr_activity_threshold: z.string(),
  // Per-spec intercepts derived from the same Hill fit. Empty defaults
  // server-side to a single 50% intercept seeded from `dr_curve_type`.
  dr_intercepts: z.array(
    z.object({
      kind: z.enum(["ic", "ec"]),
      level: z.number(),
      basis: z.enum(["relative_percent", "absolute"]),
      label: z.string().nullable().optional(),
    }),
  ) as z.ZodArray<z.ZodType<InterceptSpec>>,
});

const conditionSchema = z.object({
  name: z.string(),
  data_type: z.string(),
  unit: z.string(),
});

const protocolSchema = z.object({
  name: z.string().min(1, "Protocol name is required"),
  protocol_type: z.string(),
  target_id: z.string(),
  category: z.string(),
  description: z.string(),
  dose_unit: z.string() as z.ZodType<DoseUnit>,
  readouts: z.array(readoutSchema),
  conditions: z.array(conditionSchema),
});

type ProtocolFormValues = z.infer<typeof protocolSchema>;

// ---------------------------------------------------------------------------
// Default factories
// ---------------------------------------------------------------------------

function defaultReadout(order: number): ProtocolFormValues["readouts"][number] {
  return {
    name: "",
    data_type: "numeric",
    unit: "",
    aggregation: "none",
    normalizations: [],
    is_calculated: false,
    calculation_formula: "",
    display_order: order,
    pick_list_values: [],
    dr_curve_type: "ic50",
    dr_x_readout: WELL_CONC_X,
    dr_y_readout: "",
    dr_hill_constraint: "unconstrained",
    dr_normalization_scope: "per_plate",
    dr_activity_threshold: "",
    dr_intercepts: [],
  };
}

function defaultCondition(): ProtocolFormValues["conditions"][number] {
  return { name: "", data_type: "text", unit: "" };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface CreateProtocolDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pre-select a project (e.g., when creating from project detail). */
  defaultProjectId?: string;
}

export function CreateProtocolDialog({
  open,
  onOpenChange,
  defaultProjectId,
}: CreateProtocolDialogProps) {
  const createMutation = useCreateProtocol();
  const { data: targets } = useTargets();
  const { data: projects } = useProjects();
  const { data: vocabularies } = useVocabularies();
  const { data: protocolForms } = useProtocolForms();
  const { data: ontologySlots } = useOntologySlots();
  // For @-completion in the formula editor.
  const { data: allProtocols } = useProtocols();
  const crossProtocolNames = useMemo(() => (allProtocols ?? []).map((p) => p.name), [allProtocols]);
  const categoryTerms = vocabularies?.find((v) => v.name === "Protocol Categories")?.terms ?? [];

  // Form-template selection and project assignment live outside the zod form:
  // selectedFormId is pure UI state (triggers applyForm); projectId is POSTed
  // separately after protocol creation.
  const [selectedFormId, setSelectedFormId] = useState<string>("");
  const [projectId, setProjectId] = useState<string | null>(defaultProjectId ?? null);

  // Ontology annotations are keyed by slot name and managed by OntologySearchInput;
  // they don't fit naturally into a flat zod array, so we keep them in useState.
  const [ontologyAnnotations, setOntologyAnnotations] = useState<Record<string, OntologyTerm[]>>(
    {},
  );

  // ---- react-hook-form setup ----

  const form = useForm<ProtocolFormValues>({
    resolver: zodResolver(protocolSchema),
    defaultValues: {
      name: "",
      protocol_type: "biochemical",
      target_id: "",
      category: "",
      description: "",
      dose_unit: "uM",
      readouts: [defaultReadout(1)],
      conditions: [],
    },
  });

  const {
    fields: readoutFields,
    append: appendReadout,
    remove: removeReadout,
  } = useFieldArray({
    control: form.control,
    name: "readouts",
  });

  const {
    fields: conditionFields,
    append: appendCondition,
    remove: removeCondition,
  } = useFieldArray({
    control: form.control,
    name: "conditions",
  });

  const readoutValues = form.watch("readouts");

  // ---- form-template application ----

  const resetForm = () => {
    form.reset({
      name: "",
      protocol_type: "biochemical",
      target_id: "",
      category: "",
      description: "",
      dose_unit: "uM",
      readouts: [defaultReadout(1)],
      conditions: [],
    });
    setSelectedFormId("");
    setProjectId(defaultProjectId ?? null);
    setOntologyAnnotations({});
  };

  const applyForm = (template: ProtocolForm) => {
    if (template.protocol_type) {
      form.setValue("protocol_type", template.protocol_type);
    }
    if (template.readout_templates.length > 0) {
      form.setValue(
        "readouts",
        template.readout_templates.map((tpl, i) => {
          const tplNormalizations = tpl.normalizations as ReadoutNormalization[] | undefined;
          const tplLegacy = tpl.normalization as string | undefined;
          const resolvedNormalizations: ReadoutNormalization[] =
            tplNormalizations && tplNormalizations.length > 0
              ? tplNormalizations
              : tplLegacy && tplLegacy !== "none"
                ? [tplLegacy as ReadoutNormalization]
                : [];
          return {
            ...defaultReadout(i + 1),
            name: (tpl.name as string) ?? "",
            data_type: (tpl.data_type as string) ?? "numeric",
            unit: (tpl.unit as string) ?? "",
            aggregation: (tpl.aggregation as string) ?? "none",
            normalizations: resolvedNormalizations,
          };
        }),
      );
    }
    if (template.condition_templates && template.condition_templates.length > 0) {
      form.setValue(
        "conditions",
        template.condition_templates.map((tpl) => ({
          name: (tpl.name as string) ?? "",
          data_type: (tpl.data_type as string) ?? "text",
          unit: (tpl.unit as string) ?? "",
        })),
      );
    }
    if (template.ontology_defaults && template.ontology_defaults.length > 0) {
      const annotations: Record<string, OntologyTerm[]> = {};
      for (const od of template.ontology_defaults) {
        const slotName = od.slot_name as string;
        const terms = od.terms as Array<Record<string, unknown>>;
        if (slotName && Array.isArray(terms)) {
          annotations[slotName] = terms.map((t) => ({
            term_id: (t.term_id as string) ?? "",
            label: (t.label as string) ?? "",
            ontology_source: (t.ontology_source as string) ?? "",
            uri: (t.uri as string) ?? null,
          }));
        }
      }
      setOntologyAnnotations(annotations);
    }
  };

  // ---- derived validation ----

  const validReadouts = readoutValues.filter((rd) => rd.name.trim());
  const hasReservedReadoutName = validReadouts.some((rd) => isReservedReadoutName(rd.name));
  const nameValue = form.watch("name");
  const canSubmit =
    nameValue.trim() &&
    validReadouts.length > 0 &&
    !hasReservedReadoutName &&
    !createMutation.isPending;

  // ---- submit handler ----

  const handleSubmit = form.handleSubmit((values) => {
    const readout_definitions: CreateReadoutDefinitionInput[] = values.readouts
      .filter((rd) => rd.name.trim())
      .map((rd) => {
        const base: CreateReadoutDefinitionInput = {
          name: rd.name.trim(),
          data_type: rd.data_type as CreateReadoutDefinitionInput["data_type"],
          unit: rd.unit || null,
          aggregation: rd.aggregation as CreateReadoutDefinitionInput["aggregation"],
          normalizations: rd.normalizations,
          is_calculated: rd.is_calculated,
          calculation_formula: rd.is_calculated ? rd.calculation_formula || null : null,
          display_order: rd.display_order,
        };
        if (rd.data_type === "pick_list") {
          const cleaned = rd.pick_list_values
            .filter((v) => v.label.trim())
            .map((v) => ({ label: v.label.trim(), color: v.color || null }));
          if (cleaned.length > 0) {
            base.pick_list_values = cleaned;
          }
        }
        if (rd.data_type === "dose_response" && rd.dr_y_readout) {
          base.dose_response_config = {
            curve_type: rd.dr_curve_type,
            x_readout_name:
              rd.dr_x_readout === WELL_CONC_X || !rd.dr_x_readout ? null : rd.dr_x_readout,
            y_readout_name: rd.dr_y_readout,
            hill_slope_constraint: rd.dr_hill_constraint,
            activity_threshold: rd.dr_activity_threshold
              ? Number.parseFloat(rd.dr_activity_threshold)
              : null,
            normalization_scope: rd.dr_normalization_scope,
            top_constraint: null,
            bottom_constraint: null,
            // Empty list -> server seeds a single 50% intercept from
            // curve_type. Send only when the chemist explicitly
            // configured >=1 intercept so we don't drown the create
            // payload in a single-default row.
            ...(rd.dr_intercepts.length > 0 ? { intercepts: rd.dr_intercepts } : {}),
          } as CreateReadoutDefinitionInput["dose_response_config"];
        }
        return base;
      });

    const condition_definitions = values.conditions
      .filter((cd) => cd.name.trim())
      .map((cd) => ({
        name: cd.name.trim(),
        data_type: cd.data_type,
        unit: cd.unit || null,
      }));

    createMutation.mutate(
      {
        name: values.name.trim(),
        protocol_type: values.protocol_type as ProtocolType,
        target_id: values.target_id || null,
        category: values.category || null,
        description: values.description || null,
        dose_unit: values.dose_unit,
        readout_definitions,
        condition_definitions: condition_definitions.length > 0 ? condition_definitions : undefined,
      },
      {
        onSuccess: async (protocol) => {
          if (projectId && protocol?.id) {
            try {
              await customInstance({
                url: `/api/v1/protocols/${protocol.id}/projects/${projectId}`,
                method: "POST",
              });
            } catch {
              // Protocol created but project assignment failed — non-blocking
            }
          }
          onOpenChange(false);
          resetForm();
        },
      },
    );
  });

  // ---- render ----

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[min(95vw,1100px)] max-w-[1100px] sm:max-w-[1100px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New Protocol</DialogTitle>
          <DialogDescription>
            Define a screening protocol with readout definitions.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* Basic info */}
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input placeholder="e.g., EGFR Kinase IC50" {...form.register("name")} />
            {form.formState.errors.name && (
              <p className="text-[11px] text-destructive">{form.formState.errors.name.message}</p>
            )}
          </div>

          {/* Protocol Form Selector */}
          {protocolForms && protocolForms.length > 0 && (
            <div className="grid gap-2">
              <Label>Form Template</Label>
              <Select
                value={selectedFormId}
                onValueChange={(v) => {
                  setSelectedFormId(v);
                  if (v === "__blank__") {
                    resetForm();
                    return;
                  }
                  const template = protocolForms.find((f) => f.id === v);
                  if (template) applyForm(template);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Blank Protocol" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__blank__">Blank Protocol</SelectItem>
                  {protocolForms.map((f) => (
                    <SelectItem key={f.id} value={f.id}>
                      {f.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Pre-fill readouts, conditions, and type from a saved form.
              </p>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Type</Label>
              <Controller
                control={form.control}
                name="protocol_type"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(PROTOCOL_TYPE_LABELS).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>

            <div className="grid gap-2">
              <Label>Target (optional)</Label>
              <Controller
                control={form.control}
                name="target_id"
                render={({ field }) => (
                  <SearchableSelect
                    options={targets?.map((t) => ({ value: t.id, label: t.name })) ?? []}
                    value={field.value || null}
                    onValueChange={(v) => field.onChange(v ?? "")}
                    placeholder="Select target..."
                    searchPlaceholder="Search targets..."
                  />
                )}
              />
            </div>
          </div>

          <div className="grid gap-2">
            <Label>Dose Unit</Label>
            <Controller
              control={form.control}
              name="dose_unit"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger className="w-48">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(DOSE_UNIT_LABELS).map(([value, label]) => (
                      <SelectItem key={value} value={value}>
                        {label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
            <p className="text-xs text-muted-foreground">
              Canonical unit for all wells and IC50 fits of runs of this protocol. Picked once at
              protocol design time.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>Project (optional)</Label>
              <SearchableSelect
                options={projects?.map((p) => ({ value: p.id, label: p.name })) ?? []}
                value={projectId}
                onValueChange={setProjectId}
                placeholder="No project"
                searchPlaceholder="Search projects..."
                emptyMessage="No projects found."
              />
            </div>
            <div className="grid gap-2">
              <Label>Category (optional)</Label>
              {categoryTerms.length > 0 ? (
                <Controller
                  control={form.control}
                  name="category"
                  render={({ field }) => (
                    <SearchableSelect
                      options={categoryTerms.map((t) => ({ value: t, label: t }))}
                      value={field.value || null}
                      onValueChange={(v) => field.onChange(v ?? "")}
                      placeholder="Select category..."
                      searchPlaceholder="Search categories..."
                    />
                  )}
                />
              ) : (
                <Input
                  placeholder="e.g., Primary Screen, Counter Screen"
                  {...form.register("category")}
                />
              )}
            </div>
          </div>

          <div className="grid gap-2">
            <Label>Description</Label>
            <Textarea placeholder="Optional description..." {...form.register("description")} />
          </div>

          {/* Ontology Annotations */}
          {ontologySlots && ontologySlots.length > 0 && (
            <>
              <Separator />
              <Label className="text-base font-semibold">
                Ontology Annotations{" "}
                <span className="text-xs font-normal text-muted-foreground">(optional)</span>
              </Label>
              <div className="space-y-3">
                {ontologySlots.map((slot) => (
                  <div key={slot.id} className="grid gap-1.5">
                    <Label className="text-xs">
                      {slot.label}
                      {slot.is_required && <span className="ml-1 text-destructive">*</span>}
                    </Label>
                    <OntologySearchInput
                      ontologySources={slot.ontology_sources}
                      rootConceptId={slot.root_concept_id}
                      value={ontologyAnnotations[slot.name] ?? []}
                      onChange={(terms) =>
                        setOntologyAnnotations((prev) => ({
                          ...prev,
                          [slot.name]: terms,
                        }))
                      }
                      allowFreeText={slot.allow_free_text}
                      placeholder={`Search ${slot.ontology_sources.join(", ")}...`}
                    />
                  </div>
                ))}
              </div>
            </>
          )}

          <Separator />

          {/* Readout Definitions */}
          <div className="flex items-center justify-between">
            <Label className="text-base font-semibold">Readout Definitions</Label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => appendReadout(defaultReadout(readoutFields.length + 1))}
            >
              <Plus className="mr-2 h-4 w-4" />
              Add Readout
            </Button>
          </div>

          <div className="space-y-3">
            {readoutFields.map((field, index) => {
              const rd = readoutValues[index];
              return (
                <Card key={field.id}>
                  <CardContent className="pt-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="grid flex-1 gap-3">
                        <div className="grid grid-cols-2 gap-3">
                          <div className="grid gap-1">
                            <Label className="text-xs">Name</Label>
                            <Input
                              placeholder="e.g., % Inhibition"
                              {...form.register(`readouts.${index}.name`)}
                            />
                            {rd && isReservedReadoutName(rd.name) && (
                              <p className="text-[11px] text-destructive">
                                Reserved well-metadata name — pick a different readout name (well
                                concentration, batch, and compound are tracked on the well, not as
                                readouts).
                              </p>
                            )}
                          </div>
                          <div className="grid gap-1">
                            <Label className="text-xs">Data Type</Label>
                            <Controller
                              control={form.control}
                              name={`readouts.${index}.data_type`}
                              render={({ field: f }) => (
                                <Select value={f.value} onValueChange={f.onChange}>
                                  <SelectTrigger>
                                    <SelectValue />
                                  </SelectTrigger>
                                  <SelectContent>
                                    {VISIBLE_READOUT_DATA_TYPES.map((value) => (
                                      <SelectItem key={value} value={value}>
                                        {
                                          READOUT_DATA_TYPE_LABELS[
                                            value as keyof typeof READOUT_DATA_TYPE_LABELS
                                          ]
                                        }
                                      </SelectItem>
                                    ))}
                                  </SelectContent>
                                </Select>
                              )}
                            />
                          </div>
                        </div>

                        {/* Pick List Values */}
                        {rd?.data_type === "pick_list" && (
                          <div className="grid gap-1">
                            <Label className="text-xs">Allowed Values</Label>
                            <Controller
                              control={form.control}
                              name={`readouts.${index}.pick_list_values`}
                              render={({ field: f }) => (
                                <PickListEditor value={f.value} onChange={f.onChange} />
                              )}
                            />
                          </div>
                        )}

                        {/* Numeric measurement attributes */}
                        {rd?.data_type !== "pick_list" && (
                          <div className="grid grid-cols-3 gap-3">
                            <div className="grid gap-1">
                              <Label className="text-xs">Unit</Label>
                              <Input
                                placeholder="e.g., nM"
                                {...form.register(`readouts.${index}.unit`)}
                              />
                            </div>
                            <div className="grid gap-1">
                              <Label className="text-xs">Aggregation</Label>
                              <Controller
                                control={form.control}
                                name={`readouts.${index}.aggregation`}
                                render={({ field: f }) => (
                                  <Select value={f.value} onValueChange={f.onChange}>
                                    <SelectTrigger>
                                      <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                      {Object.entries(READOUT_AGGREGATION_LABELS).map(
                                        ([value, label]) => (
                                          <SelectItem key={value} value={value}>
                                            {label}
                                          </SelectItem>
                                        ),
                                      )}
                                    </SelectContent>
                                  </Select>
                                )}
                              />
                            </div>
                            <div className="grid gap-1">
                              <Label className="text-xs">Normalization</Label>
                              <Controller
                                control={form.control}
                                name={`readouts.${index}.normalizations`}
                                render={({ field: f }) => (
                                  <NormalizationCheckboxGroup
                                    value={f.value}
                                    onChange={f.onChange}
                                  />
                                )}
                              />
                            </div>
                          </div>
                        )}

                        {/* Calculated readout toggle */}
                        <div className="flex items-center gap-3">
                          <Controller
                            control={form.control}
                            name={`readouts.${index}.is_calculated`}
                            render={({ field: f }) => (
                              <Switch checked={f.value} onCheckedChange={f.onChange} size="sm" />
                            )}
                          />
                          <Label className="text-xs">Calculated</Label>
                        </div>
                        {rd?.is_calculated && (
                          <div className="grid gap-1">
                            <Label className="text-xs">Formula</Label>
                            <Controller
                              control={form.control}
                              name={`readouts.${index}.calculation_formula`}
                              render={({ field: f }) => (
                                <FormulaInput
                                  value={f.value}
                                  onChange={f.onChange}
                                  availableReadoutNames={readoutValues
                                    .filter((other, i) => i !== index && other.name.trim())
                                    .map((r) => r.name.trim())}
                                  protocolNames={crossProtocolNames}
                                />
                              )}
                            />
                            <p className="text-[11px] text-muted-foreground">
                              Use other readout names as variables. Type <code>@</code> for
                              cross-protocol.
                            </p>
                          </div>
                        )}

                        {/* Dose-Response Config */}
                        {rd?.data_type === "dose_response" && (
                          <div className="space-y-3 rounded-lg border bg-muted/30 p-3">
                            <p className="text-xs font-medium">Dose-Response Configuration</p>
                            <div className="grid grid-cols-3 gap-3">
                              <div className="grid gap-1">
                                <Label className="text-xs">Curve Type</Label>
                                <Controller
                                  control={form.control}
                                  name={`readouts.${index}.dr_curve_type`}
                                  render={({ field: f }) => (
                                    <Select value={f.value} onValueChange={f.onChange}>
                                      <SelectTrigger>
                                        <SelectValue />
                                      </SelectTrigger>
                                      <SelectContent>
                                        {Object.entries(CURVE_TYPE_LABELS).map(([v, l]) => (
                                          <SelectItem key={v} value={v}>
                                            {l}
                                          </SelectItem>
                                        ))}
                                      </SelectContent>
                                    </Select>
                                  )}
                                />
                              </div>
                              <div className="grid gap-1">
                                <Label className="text-xs">X-Axis Readout</Label>
                                <Controller
                                  control={form.control}
                                  name={`readouts.${index}.dr_x_readout`}
                                  render={({ field: f }) => (
                                    <Select value={f.value} onValueChange={f.onChange}>
                                      <SelectTrigger>
                                        <SelectValue />
                                      </SelectTrigger>
                                      <SelectContent>
                                        <SelectItem value={WELL_CONC_X}>
                                          (use well concentration)
                                        </SelectItem>
                                        {readoutValues
                                          .filter(
                                            (other, i) =>
                                              i !== index &&
                                              other.name.trim() &&
                                              other.data_type === "numeric",
                                          )
                                          .map((other) => (
                                            <SelectItem key={other.name} value={other.name.trim()}>
                                              {other.name}
                                            </SelectItem>
                                          ))}
                                      </SelectContent>
                                    </Select>
                                  )}
                                />
                              </div>
                              <div className="grid gap-1">
                                <Label className="text-xs">Y-Axis Readout</Label>
                                <Controller
                                  control={form.control}
                                  name={`readouts.${index}.dr_y_readout`}
                                  render={({ field: f }) => (
                                    <Select value={f.value} onValueChange={f.onChange}>
                                      <SelectTrigger>
                                        <SelectValue placeholder="Select..." />
                                      </SelectTrigger>
                                      <SelectContent>
                                        {readoutValues
                                          .filter(
                                            (other, i) =>
                                              i !== index &&
                                              other.name.trim() &&
                                              other.data_type === "numeric",
                                          )
                                          .map((other) => (
                                            <SelectItem key={other.name} value={other.name.trim()}>
                                              {other.name}
                                            </SelectItem>
                                          ))}
                                      </SelectContent>
                                    </Select>
                                  )}
                                />
                              </div>
                            </div>

                            {/* Intercepts — chemist declares which intercepts
                                the fit emits (EC50, EC90, IC10, …). Empty list
                                = single implicit 50% intercept seeded from the
                                Curve Type. Every downstream surface emits one
                                column per row. */}
                            <Controller
                              control={form.control}
                              name={`readouts.${index}.dr_intercepts`}
                              render={({ field: f }) => (
                                <div className="grid gap-2 rounded-md border bg-background p-3">
                                  <div className="flex items-baseline justify-between">
                                    <Label className="text-xs font-medium">Intercepts</Label>
                                    <span className="text-[11px] text-muted-foreground">
                                      One row per intercept (EC50, EC90, IC10, …) — all derived from
                                      the same Hill fit
                                    </span>
                                  </div>
                                  <InterceptsEditor
                                    value={f.value as InterceptSpec[]}
                                    onChange={f.onChange}
                                    curveType={
                                      (form.watch(
                                        `readouts.${index}.dr_curve_type`,
                                      ) as CurveType) ?? "ic50"
                                    }
                                  />
                                </div>
                              )}
                            />

                            <div className="grid grid-cols-3 gap-3">
                              <div className="grid gap-1">
                                <Label className="text-xs">Hill Slope</Label>
                                <Controller
                                  control={form.control}
                                  name={`readouts.${index}.dr_hill_constraint`}
                                  render={({ field: f }) => (
                                    <Select value={f.value} onValueChange={f.onChange}>
                                      <SelectTrigger>
                                        <SelectValue />
                                      </SelectTrigger>
                                      <SelectContent>
                                        {Object.entries(HILL_SLOPE_CONSTRAINT_LABELS).map(
                                          ([v, l]) => (
                                            <SelectItem key={v} value={v}>
                                              {l}
                                            </SelectItem>
                                          ),
                                        )}
                                      </SelectContent>
                                    </Select>
                                  )}
                                />
                              </div>
                              <div className="grid gap-1">
                                <Label className="text-xs">Normalization</Label>
                                <Controller
                                  control={form.control}
                                  name={`readouts.${index}.dr_normalization_scope`}
                                  render={({ field: f }) => (
                                    <Select value={f.value} onValueChange={f.onChange}>
                                      <SelectTrigger>
                                        <SelectValue />
                                      </SelectTrigger>
                                      <SelectContent>
                                        {Object.entries(NORMALIZATION_SCOPE_LABELS).map(
                                          ([v, l]) => (
                                            <SelectItem key={v} value={v}>
                                              {l}
                                            </SelectItem>
                                          ),
                                        )}
                                      </SelectContent>
                                    </Select>
                                  )}
                                />
                              </div>
                              <div className="grid gap-1">
                                <Label className="text-xs">Activity Threshold (%)</Label>
                                <Input
                                  type="number"
                                  min="0"
                                  max="100"
                                  placeholder="e.g., 30"
                                  {...form.register(`readouts.${index}.dr_activity_threshold`)}
                                />
                              </div>
                            </div>
                          </div>
                        )}
                      </div>

                      {readoutFields.length > 1 && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="mt-5 shrink-0"
                          onClick={() => removeReadout(index)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          <Separator />

          {/* Condition Definitions */}
          <div className="flex items-center justify-between">
            <Label className="text-base font-semibold">
              Conditions{" "}
              <span className="text-xs font-normal text-muted-foreground">(optional)</span>
            </Label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => appendCondition(defaultCondition())}
            >
              <Plus className="mr-2 h-4 w-4" />
              Add Condition
            </Button>
          </div>

          {conditionFields.length > 0 && (
            <div className="space-y-2">
              {conditionFields.map((field, index) => (
                <div key={field.id} className="flex items-end gap-2">
                  <div className="grid gap-1 flex-1">
                    <Label className="text-xs">Name</Label>
                    <Input
                      placeholder="e.g., Cell Line"
                      {...form.register(`conditions.${index}.name`)}
                    />
                  </div>
                  <div className="grid gap-1 w-[130px]">
                    <Label className="text-xs">Type</Label>
                    <Controller
                      control={form.control}
                      name={`conditions.${index}.data_type`}
                      render={({ field: f }) => (
                        <Select value={f.value} onValueChange={f.onChange}>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="text">Text</SelectItem>
                            <SelectItem value="numeric">Numeric</SelectItem>
                            <SelectItem value="pick_list">Pick List</SelectItem>
                          </SelectContent>
                        </Select>
                      )}
                    />
                  </div>
                  <div className="grid gap-1 w-[100px]">
                    <Label className="text-xs">Unit</Label>
                    <Input placeholder="optional" {...form.register(`conditions.${index}.unit`)} />
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="shrink-0"
                    onClick={() => removeCondition(index)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {createMutation.isPending ? "Creating..." : "Create Protocol"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
