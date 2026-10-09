"use client";

import { useProjects } from "@/features/research-organization/hooks/use-projects";
import { useProtocolCategories } from "@/features/workspace-config/hooks/use-protocol-categories";
import {
  type ProtocolForm,
  useProtocolForms,
} from "@/features/workspace-config/hooks/use-protocol-forms";
import type { OntologyTerm } from "@/shared/components/ontology-search-input";
import { PickListValuesInput } from "@/shared/components/pick-list-values-input";
import { SearchableSelect } from "@/shared/components/searchable-select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
import { Button } from "@/shared/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible";
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
import { Textarea } from "@/shared/components/ui/textarea";
import { UnitPicker } from "@/shared/components/unit-picker";
import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronDown, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { useProtocolFacetSlots } from "../hooks/use-protocol-facet-slots";
import { useProtocolNamePreview } from "../hooks/use-protocol-name-preview";
import { useAssignProtocolToProject } from "../hooks/use-protocol-projects";
import { useCreateProtocol, useProtocols } from "../hooks/use-protocols";
import { isFixedValueValid } from "../lib/conditions";
import { ontologyAnnotationsPayload } from "../lib/ontology-annotations-payload";
import {
  applyFormFacets,
  conditionsFromForm,
  formsForCategory,
  pickFormForCategory,
  readoutsFromForm,
} from "../lib/protocol-form-apply";
import { WELL_CONC_X, isReservedReadoutName } from "../lib/readout-constants";
import {
  type CreateReadoutDefinitionInput,
  DOSE_UNIT_LABELS,
  PROTOCOL_TYPE_LABELS,
  type Protocol,
  type ProtocolType,
} from "../types";
import { ConditionValueInput } from "./condition-fields";
import {
  DEFAULT_VALUES,
  type ProtocolFormValues,
  defaultCondition,
  defaultReadout,
  protocolSchema,
} from "./create-protocol/form-values";
import { NicknameInput } from "./create-protocol/nickname-input";
import { ReadoutRow } from "./create-protocol/readout-row";
import { FacetField, NameFacts, factSlots } from "./create-protocol/required-facts";
import {
  SiblingDiscriminators,
  type SiblingValues,
  siblingDiscriminatorsPayload,
} from "./create-protocol/sibling-discriminators";
import { StartsFrom } from "./create-protocol/starts-from";
import { DiscriminatorInput } from "./discriminator-input";
import { ProtocolCategoryInput } from "./protocol-category-input";
import { ProtocolNamePreview, isPreviewSavable, useNameSlots } from "./protocol-name-preview";
import { SimilarProtocolsPanel } from "./similar-protocols-panel";
import { TargetMultiSelect } from "./target-multi-select";

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface CreateProtocolDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pre-select a project (e.g., when creating from project detail). */
  defaultProjectId?: string;
  /** Called when the user clicks "Log a run of this" on a suggestion.
   *  The dialog closes itself before calling this. */
  onLogRun?: (protocolId: string) => void;
  /** Start from an existing protocol (a new assay): copies its facts, not its
   *  discriminator, code or name. */
  prefill?: Protocol;
}

const DEFAULT_READOUTS_JSON = JSON.stringify(DEFAULT_VALUES.readouts);
const DEFAULT_CONDITIONS_JSON = JSON.stringify(DEFAULT_VALUES.conditions);

export function CreateProtocolDialog({
  open,
  onOpenChange,
  defaultProjectId,
  onLogRun,
  prefill,
}: CreateProtocolDialogProps) {
  const createMutation = useCreateProtocol();
  const assignToProject = useAssignProtocolToProject();
  const { data: projects } = useProjects();
  const { data: protocolForms } = useProtocolForms();
  const { data: categories } = useProtocolCategories();
  const facetSlots = useProtocolFacetSlots();
  // For @-completion in the formula editor.
  const { data: allProtocols } = useProtocols();
  const crossProtocols = useMemo(
    () =>
      (allProtocols ?? [])
        .filter((p) => p.code)
        .map((p) => ({ code: p.code as string, name: p.name })),
    [allProtocols],
  );

  // Project assignment is POSTed separately after protocol creation.
  const [projectId, setProjectId] = useState<string | null>(defaultProjectId ?? null);

  // Ontology annotations are keyed by slot name and managed by OntologySearchInput;
  // they don't fit naturally into a flat zod array, so we keep them in useState.
  const [ontologyAnnotations, setOntologyAnnotations] = useState<Record<string, OntologyTerm[]>>(
    {},
  );
  const setAnnotation = (slot: string, terms: OntologyTerm[]) =>
    setOntologyAnnotations((prev) => ({ ...prev, [slot]: terms }));

  // The form the protocol starts from. What a form last applied (readouts, conditions, facet
  // slot → terms, as JSON) tells the chemist's edits apart: only those survive a re-apply.
  const [selectedForm, setSelectedForm] = useState<ProtocolForm | null>(null);
  const [appliedReadouts, setAppliedReadouts] = useState(DEFAULT_READOUTS_JSON);
  const [appliedConditions, setAppliedConditions] = useState(DEFAULT_CONDITIONS_JSON);
  const [appliedFacets, setAppliedFacets] = useState<Record<string, string>>({});
  const [pendingForm, setPendingForm] = useState<ProtocolForm | null>(null);
  const [nicknames, setNicknames] = useState<string[]>([]);
  const [siblingValues, setSiblingValues] = useState<SiblingValues>({});
  const [showDiscriminator, setShowDiscriminator] = useState(false);

  // ---- react-hook-form setup ----

  const form = useForm<ProtocolFormValues>({
    resolver: zodResolver(protocolSchema),
    defaultValues: DEFAULT_VALUES,
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

  // ---- draft retention: the dialog stays mounted, so entries survive a close ----

  const isDirty = form.formState.isDirty;
  const [draftKept, setDraftKept] = useState(false);
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) setDraftKept(isDirty && !prefill);
  }

  const resetForm = () => {
    form.reset(DEFAULT_VALUES);
    setProjectId(defaultProjectId ?? null);
    setOntologyAnnotations({});
    setSelectedForm(null);
    setAppliedReadouts(DEFAULT_READOUTS_JSON);
    setAppliedConditions(DEFAULT_CONDITIONS_JSON);
    setAppliedFacets({});
    setNicknames([]);
    setSiblingValues({});
    setShowDiscriminator(false);
    setDraftKept(false);
  };

  // A new assay starts from the protocol it replaces: same facts, its own discriminator.
  useEffect(() => {
    if (!open || !prefill) return;
    form.reset({
      protocol_type: prefill.protocol_type,
      discriminator: "",
      target_ids: (prefill.targets ?? []).map((t) => t.id),
      category: prefill.category ?? "",
      description: prefill.description ?? "",
      dose_unit: prefill.dose_unit,
      readouts: prefill.readout_definitions.map((rd, i) => {
        const dr = rd.dose_response_config;
        return {
          ...defaultReadout(i + 1),
          name: rd.name,
          data_type: rd.data_type,
          unit: rd.unit ?? "",
          aggregation: rd.aggregation ?? "none",
          normalizations: rd.normalizations ?? [],
          is_calculated: rd.is_calculated,
          calculation_formula: rd.calculation_formula ?? "",
          display_order: rd.display_order ?? i + 1,
          pick_list_values: rd.pick_list_values ?? [],
          ...(dr
            ? {
                dr_curve_type: dr.curve_type,
                dr_x_readout: dr.x_readout_name ?? WELL_CONC_X,
                dr_y_readout: dr.y_readout_name,
                dr_hill_constraint: dr.hill_slope_constraint,
                dr_normalization_scope: dr.normalization_scope,
                dr_activity_threshold:
                  dr.activity_threshold != null ? String(dr.activity_threshold) : "",
                dr_intercepts: dr.intercepts ?? [],
              }
            : {}),
        };
      }),
      conditions: prefill.condition_definitions.map((cd) => ({
        name: cd.name,
        data_type: cd.data_type,
        unit: cd.unit ?? "",
        pick_list_values: cd.pick_list_values ?? [],
        fixed_value: cd.fixed_value ?? "",
      })),
    });
    setAppliedReadouts(JSON.stringify(form.getValues("readouts")));
    setOntologyAnnotations(prefill.ontology_annotations ?? {});
  }, [open, prefill, form]);

  // ---- forms: picking a category applies its form ----

  const applyReadouts = (f: ProtocolForm) => {
    const readouts = readoutsFromForm(f);
    form.setValue("readouts", readouts);
    setAppliedReadouts(JSON.stringify(readouts));
  };

  /** Type, conditions and facet defaults apply at once, replacing what the last form applied
   *  (null: no form, so those are cleared); readouts the chemist edited are asked about. */
  const applyPickedForm = (f: ProtocolForm | null) => {
    setSelectedForm(f);
    const conditionsNow = JSON.stringify(form.getValues("conditions"));
    if (conditionsNow === DEFAULT_CONDITIONS_JSON || conditionsNow === appliedConditions) {
      const conditions = f ? conditionsFromForm(f) : [];
      form.setValue("conditions", conditions);
      setAppliedConditions(JSON.stringify(conditions));
    }
    const facets = applyFormFacets(ontologyAnnotations, appliedFacets, f);
    setOntologyAnnotations(facets.annotations);
    setAppliedFacets(facets.applied);
    if (!f) return;
    if (f.protocol_type) form.setValue("protocol_type", f.protocol_type);
    if (f.readout_templates.length === 0) return;
    if (JSON.stringify(form.getValues("readouts")) !== appliedReadouts) setPendingForm(f);
    else applyReadouts(f);
  };

  const categoryValue = form.watch("category") || null;
  const categoryId = categories?.find((c) => c.label === categoryValue)?.id ?? null;
  const onCategoryPicked = (label: string) => {
    // A new assay from an existing protocol keeps that protocol's readouts.
    if (prefill) return;
    const id = categories?.find((c) => c.label === label)?.id;
    applyPickedForm(id ? pickFormForCategory(protocolForms ?? [], id) : null);
  };
  const { own: ownForms, generic: genericForms } = formsForCategory(
    protocolForms ?? [],
    categoryId,
  );

  // ---- derived validation ----

  const { required: needs, optional: mayName } = useNameSlots(categoryValue);
  const followsTarget = selectedForm?.assay_format_from_target ?? false;
  // The pattern's facts sit under the category, the optional ones too: they change the name.
  const requiredSlots = factSlots(needs, followsTarget);
  const optionalSlots = factSlots(mayName, followsTarget).filter((s) => !requiredSlots.includes(s));
  const nameFactSlots = [...requiredSlots, ...optionalSlots];
  const assayFormatHint =
    followsTarget && !ontologyAnnotations.assay_format?.length ? "Follows the target" : undefined;
  const targetIds = form.watch("target_ids") ?? [];
  const discriminatorValue = form.watch("discriminator");
  const preview = useProtocolNamePreview(
    categoryValue
      ? {
          category: categoryValue,
          target_ids: targetIds,
          ontology_annotations: ontologyAnnotations,
          discriminator: discriminatorValue.trim() || null,
          // A form that follows the target gives {matrix} its assay format.
          form_id: selectedForm?.id ?? null,
          sibling_discriminators: Object.entries(siblingValues)
            .filter(([, v]) => v.discriminator.trim())
            .map(([protocol_id, v]) => ({ protocol_id, discriminator: v.discriminator.trim() })),
        }
      : null,
  );
  const siblings = preview.data?.siblings ?? [];
  // The pattern places it: then it is part of every name in the category, not a tie-breaker.
  const discriminatorInName = needs.has("discriminator");
  const showDiscriminatorField =
    discriminatorInName ||
    siblings.length > 0 ||
    showDiscriminator ||
    discriminatorValue.trim() !== "";

  // Facts the pattern does not place, assay format first.
  const moreSlots = facetSlots
    .filter((s) => !nameFactSlots.includes(s.name))
    .sort((a, b) => Number(b.name === "assay_format") - Number(a.name === "assay_format"));

  const validReadouts = readoutValues.filter((rd) => rd.name.trim());
  const hasReservedReadoutName = validReadouts.some((rd) => isReservedReadoutName(rd.name));
  const conditionValues = form.watch("conditions");
  // The backend refuses a pick list with no values.
  const hasEmptyPickList = conditionValues.some(
    (cd) => cd.name.trim() && cd.data_type === "pick_list" && cd.pick_list_values.length === 0,
  );
  const hasInvalidFixedValue = conditionValues.some(
    (cd) => cd.name.trim() && !isFixedValueValid(cd),
  );
  const canSubmit =
    validReadouts.length > 0 &&
    !hasEmptyPickList &&
    !hasInvalidFixedValue &&
    !hasReservedReadoutName &&
    isPreviewSavable(preview.data) &&
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
        ...(cd.data_type === "pick_list" ? { pick_list_values: cd.pick_list_values } : {}),
        ...(cd.fixed_value.trim() ? { fixed_value: cd.fixed_value.trim() } : {}),
      }));

    createMutation.mutate(
      {
        protocol_type: values.protocol_type as ProtocolType,
        discriminator: values.discriminator.trim() || null,
        target_ids: values.target_ids,
        category: values.category || null,
        description: values.description || null,
        dose_unit: values.dose_unit,
        readout_definitions,
        condition_definitions: condition_definitions.length > 0 ? condition_definitions : undefined,
        // Facets persisted atomically with the protocol — one transaction, so a
        // multi-slot set can't race/drop the way separate post-create PUTs did.
        ontology_annotations: ontologyAnnotationsPayload(ontologyAnnotations),
        form_id: selectedForm?.id ?? null,
        nicknames,
        sibling_discriminators: siblingDiscriminatorsPayload(
          siblings,
          siblingValues,
          preview.data?.name ?? "",
        ),
      },
      {
        onSuccess: async (protocol) => {
          if (projectId && protocol?.id) {
            // Non-blocking: the protocol is already created. A failed assignment
            // is surfaced by the mutation's onError toast (recovery hint) rather
            // than vanishing; the catch only prevents an unhandled rejection.
            try {
              await assignToProject.mutateAsync({ protocolId: protocol.id, projectId });
            } catch {
              // Error already surfaced by useAssignProtocolToProject.onError.
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
          <DialogTitle>
            {prefill ? `New protocol from ${prefill.code ?? prefill.name}` : "New Protocol"}
          </DialogTitle>
          <DialogDescription>
            Pick a category; the name, its facts and the readouts follow from it.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          {/* First, and focused on open as the first control in the dialog. */}
          <div className="grid gap-2">
            <Label>Category</Label>
            <Controller
              control={form.control}
              name="category"
              render={({ field }) => (
                <ProtocolCategoryInput
                  value={field.value ?? ""}
                  onChange={(v) => {
                    field.onChange(v);
                    onCategoryPicked(v);
                  }}
                />
              )}
            />
          </div>

          <NameFacts
            required={requiredSlots}
            optional={optionalSlots}
            assayFormatHint={assayFormatHint}
            facetSlots={facetSlots}
            annotations={ontologyAnnotations}
            onAnnotations={setAnnotation}
            targetIds={targetIds}
            onTargetIds={(ids) => form.setValue("target_ids", ids, { shouldDirty: true })}
          />

          <ProtocolNamePreview preview={preview.data} isFetching={preview.isFetching} />

          {showDiscriminatorField ? (
            <div className="grid gap-2">
              <Label htmlFor="protocol-discriminator">
                Discriminator{discriminatorInName ? "" : " (optional)"}
              </Label>
              <Controller
                control={form.control}
                name="discriminator"
                render={({ field }) => (
                  <DiscriminatorInput
                    id="protocol-discriminator"
                    value={field.value}
                    onChange={field.onChange}
                    base={preview.data?.base ?? null}
                    placeholder={discriminatorInName ? "Part of this category's name" : undefined}
                  />
                )}
              />
              <p className="text-xs text-muted-foreground">
                {discriminatorInName
                  ? "Part of this category's name, so every protocol in it needs one."
                  : "Only needed when another protocol would get the same name. A method or a fixed condition, never a stage, library or date."}
              </p>
            </div>
          ) : (
            <Button
              type="button"
              variant="link"
              size="sm"
              className="h-auto justify-self-start p-0"
              onClick={() => setShowDiscriminator(true)}
            >
              + method or condition
            </Button>
          )}

          <SiblingDiscriminators
            siblings={siblings}
            renames={preview.data?.sibling_renames ?? []}
            values={siblingValues}
            newName={preview.data?.name ?? ""}
            onChange={setSiblingValues}
          />

          <StartsFrom
            forms={ownForms.length > 0 ? ownForms : genericForms}
            selectedId={selectedForm?.id ?? null}
            onPick={applyPickedForm}
          />

          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <Label>Readouts</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => appendReadout(defaultReadout(readoutFields.length + 1))}
              >
                <Plus className="mr-2 h-4 w-4" />
                Add readout
              </Button>
            </div>
            {readoutFields.map((field, index) => (
              <ReadoutRow
                key={field.id}
                form={form}
                index={index}
                readouts={readoutValues}
                crossProtocols={crossProtocols}
                canRemove={readoutFields.length > 1}
                onRemove={() => removeReadout(index)}
              />
            ))}
          </div>

          <NicknameInput value={nicknames} onChange={setNicknames} name={preview.data?.name} />

          <Collapsible>
            <CollapsibleTrigger asChild>
              <Button type="button" variant="ghost" size="sm" className="group -ml-2">
                <ChevronDown className="mr-1 h-4 w-4 -rotate-90 transition-transform group-data-[state=open]:rotate-0" />
                More details
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="grid gap-4 pt-2">
              <div className="grid w-64 gap-2">
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

              {moreSlots.map((slot) => (
                <FacetField
                  key={slot.id}
                  slot={slot}
                  value={ontologyAnnotations[slot.name] ?? []}
                  onChange={(terms) => setAnnotation(slot.name, terms)}
                  hint={slot.name === "assay_format" ? assayFormatHint : undefined}
                />
              ))}

              {!nameFactSlots.includes("target") && (
                <div className="grid gap-2">
                  <Label>Targets</Label>
                  <Controller
                    control={form.control}
                    name="target_ids"
                    render={({ field }) => (
                      <TargetMultiSelect value={field.value} onChange={field.onChange} />
                    )}
                  />
                </div>
              )}

              <div className="grid gap-2">
                <Label>Description</Label>
                <Textarea placeholder="Optional description..." {...form.register("description")} />
              </div>

              <div className="grid gap-2">
                <Label>Project</Label>
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
                <div className="flex items-center justify-between">
                  <Label>Conditions</Label>
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
                {conditionFields.map((field, index) => (
                  <div key={field.id} className="grid gap-2">
                    <div className="flex items-end gap-2">
                      <div className="grid flex-1 gap-1">
                        <Label className="text-xs">Name</Label>
                        <Input
                          placeholder="e.g., Incubation time"
                          {...form.register(`conditions.${index}.name`)}
                        />
                      </div>
                      <div className="grid w-[130px] gap-1">
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
                      <div className="grid w-40 gap-1">
                        <Label className="text-xs">Unit</Label>
                        <Controller
                          control={form.control}
                          name={`conditions.${index}.unit`}
                          render={({ field: f }) => (
                            <UnitPicker value={f.value} onChange={f.onChange} />
                          )}
                        />
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        aria-label="Remove condition"
                        className="shrink-0"
                        onClick={() => removeCondition(index)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                    {conditionValues[index]?.data_type === "pick_list" && (
                      <Controller
                        control={form.control}
                        name={`conditions.${index}.pick_list_values`}
                        render={({ field: f }) => (
                          <PickListValuesInput values={f.value} onChange={f.onChange} />
                        )}
                      />
                    )}
                    <div className="grid gap-1">
                      <Label className="text-xs">Fixed for this protocol (optional)</Label>
                      <Controller
                        control={form.control}
                        name={`conditions.${index}.fixed_value`}
                        render={({ field: f }) => (
                          <ConditionValueInput
                            def={conditionValues[index] ?? defaultCondition()}
                            value={f.value}
                            onChange={f.onChange}
                            noneLabel="(varies per run)"
                            aria-label="Fixed for this protocol"
                          />
                        )}
                      />
                      {conditionValues[index] && !isFixedValueValid(conditionValues[index]) && (
                        <p className="text-xs text-destructive">
                          {conditionValues[index].data_type === "numeric"
                            ? "Must be a number."
                            : "Must be one of the values."}
                        </p>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {readoutValues.some((r) => r.data_type === "dose_response") && (
                <div className="grid gap-2">
                  <Label>Dose unit</Label>
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
                    Canonical unit for all wells and IC50 fits of runs of this protocol.
                  </p>
                </div>
              )}
            </CollapsibleContent>
          </Collapsible>

          <SimilarProtocolsPanel
            draft={{
              name: preview.data?.name ?? "",
              protocol_type: form.watch("protocol_type") || null,
              target_ids: targetIds,
              readout_names: readoutValues
                .map((r) => r.name)
                .filter((n): n is string => Boolean(n)),
              facet_ids: Object.values(ontologyAnnotations)
                .flat()
                .map((t) => t.term_id),
            }}
            onLogRun={(protocolId) => {
              onOpenChange(false);
              onLogRun?.(protocolId);
            }}
          />
        </div>

        <DialogFooter className="sm:items-center">
          {draftKept && (
            <>
              <span className="text-sm text-muted-foreground sm:mr-auto">Draft kept</span>
              <Button type="button" variant="ghost" onClick={resetForm}>
                Clear
              </Button>
            </>
          )}
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {createMutation.isPending ? "Creating..." : "Create Protocol"}
          </Button>
        </DialogFooter>

        <AlertDialog open={pendingForm !== null} onOpenChange={(o) => !o && setPendingForm(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Replace your readouts with the form's?</AlertDialogTitle>
              <AlertDialogDescription>
                You changed the readouts. "{pendingForm?.name}" starts with{" "}
                {pendingForm?.readout_templates.map((t) => t.name).join(", ")}.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Keep mine</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => {
                  if (pendingForm) applyReadouts(pendingForm);
                  setPendingForm(null);
                }}
              >
                Replace
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </DialogContent>
    </Dialog>
  );
}
