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
import { ChevronDown, Loader2, Plus, Sparkles, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import {
  type ConditionSuggestion,
  useMethodSuggestionsEnabled,
  useSuggestFromMethod,
} from "../hooks/use-method-suggestions";
import { useProtocolFacetSlots } from "../hooks/use-protocol-facet-slots";
import { useProtocolNamePreview } from "../hooks/use-protocol-name-preview";
import { useAssignProtocolToProject } from "../hooks/use-protocol-projects";
import { useCreateProtocol, useProtocols } from "../hooks/use-protocols";
import { isFixedValueValid } from "../lib/conditions";
import { ontologyAnnotationsPayload } from "../lib/ontology-annotations-payload";
import {
  conditionDefinitionsPayload,
  readoutDefinitionsPayload,
} from "../lib/protocol-create-payload";
import {
  applyFormFacets,
  conditionsFromForm,
  formsForCategory,
  pickFormForCategory,
  readoutsFromForm,
} from "../lib/protocol-form-apply";
import { METHOD_PLACEHOLDER } from "../lib/protocol-method";
import { prefillFromProtocol } from "../lib/protocol-prefill";
import { isReservedReadoutName } from "../lib/readout-constants";
import {
  DOSE_UNIT_LABELS,
  PROTOCOL_TYPE_LABELS,
  type Protocol,
  type ProtocolReference,
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
import {
  FacetField,
  NameFacts,
  factSlots,
  hidesFacet,
  settledSlots,
} from "./create-protocol/required-facts";
import {
  SiblingDiscriminators,
  type SiblingValues,
  siblingDiscriminatorsPayload,
} from "./create-protocol/sibling-discriminators";
import { StartsFrom } from "./create-protocol/starts-from";
import { SuggestedConditions } from "./create-protocol/suggested-conditions";
import { DiscriminatorInput } from "./discriminator-input";
import { ProtocolCategoryInput } from "./protocol-category-input";
import { ProtocolNamePreview, isPreviewSavable, useNameSlots } from "./protocol-name-preview";
import { ReferencesEditor } from "./protocol-references";
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
  const router = useRouter();
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
  const [references, setReferences] = useState<ProtocolReference[]>([]);
  const [siblingValues, setSiblingValues] = useState<SiblingValues>({});
  const [showDiscriminator, setShowDiscriminator] = useState(false);
  // What the method suggested (null: not asked). Shown for review, never added on its own.
  const [suggested, setSuggested] = useState<ConditionSuggestion[] | null>(null);
  const suggestionsOn = useMethodSuggestionsEnabled();
  const suggest = useSuggestFromMethod();

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
    setReferences([]);
    setSiblingValues({});
    setShowDiscriminator(false);
    setSuggested(null);
    setDraftKept(false);
  };

  // A new assay starts from the protocol it replaces: same facts, its own discriminator.
  useEffect(() => {
    if (!open || !prefill) return;
    const start = prefillFromProtocol(prefill);
    form.reset(start.values);
    setAppliedReadouts(JSON.stringify(form.getValues("readouts")));
    setOntologyAnnotations(start.ontologyAnnotations);
    setReferences(start.references);
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

  // A new assay needs its own discriminator, or its strain when the pattern has no discriminator
  // field showing: focus whichever is there once it renders (the portal mounts a tick after
  // open, so this checks on every render until it lands).
  const focusTarget = showDiscriminatorField
    ? "discriminator"
    : nameFactSlots.includes("strain")
      ? "strain"
      : null;
  const focused = useRef(false);
  useEffect(() => {
    if (!open || !prefill) {
      focused.current = false;
      return;
    }
    if (focused.current || !focusTarget) return;
    const el =
      focusTarget === "discriminator"
        ? document.getElementById("protocol-discriminator")
        : document.querySelector<HTMLElement>('[data-facet-slot="strain"] input');
    el?.focus();
    focused.current = !!el;
  });

  // Facts the pattern does not place, assay format first. Ones a cell-free type settles are left
  // out unless required or already holding a value (a prefill).
  const settled = settledSlots(form.watch("protocol_type"));
  const moreSlots = facetSlots
    .filter((s) => !nameFactSlots.includes(s.name))
    .filter((s) => !hidesFacet(s, settled, ontologyAnnotations[s.name]))
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
  const methodValue = form.watch("description");
  // TanStack runs a mutate call's own callbacks for the latest call only: a slower earlier
  // answer never replaces a newer one.
  const suggestFromMethod = () =>
    suggest.mutate(methodValue.trim(), { onSuccess: (r) => setSuggested(r.conditions) });
  const listedConditions = new Set(conditionValues.map((cd) => cd.name.trim().toLowerCase()));
  const openSuggestions = (suggested ?? []).filter(
    (s) => !listedConditions.has(s.name.toLowerCase()),
  );
  const addSuggestion = (s: ConditionSuggestion) =>
    appendCondition({
      ...defaultCondition(),
      name: s.name,
      data_type: s.data_type,
      unit: s.unit ?? "",
    });
  const dismissSuggestion = (s: ConditionSuggestion) =>
    setSuggested((prev) => prev?.filter((x) => x.name !== s.name) ?? null);

  const canSubmit =
    validReadouts.length > 0 &&
    !hasEmptyPickList &&
    !hasInvalidFixedValue &&
    !hasReservedReadoutName &&
    isPreviewSavable(preview.data) &&
    !createMutation.isPending;

  // ---- submit handler ----

  const handleSubmit = form.handleSubmit((values) => {
    const readout_definitions = readoutDefinitionsPayload(values.readouts);
    const condition_definitions = conditionDefinitionsPayload(values.conditions);

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
        references,
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
          // Straight on to the draft: its remaining setup and Publish live there.
          if (protocol?.id) router.push(`/assays/protocols/${protocol.id}`);
        },
      },
    );
  });

  // ---- render ----

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        onOpenAutoFocus={(e) => prefill && e.preventDefault()}
        className="w-[min(95vw,1100px)] max-w-[1100px] sm:max-w-[1100px] max-h-[90vh] overflow-y-auto"
      >
        <DialogHeader>
          <DialogTitle>
            {prefill ? `New protocol from ${prefill.code ?? prefill.name}` : "New Protocol"}
          </DialogTitle>
          <DialogDescription>
            Say what you measure, on what, and how; the name and readouts follow. The rest can be
            set on the draft.
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
                Distinguished by{discriminatorInName ? "" : " (optional)"}
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
                    conditions={conditionValues}
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

          {/* Before any more effort: maybe this is a run of an existing protocol. */}
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

          <div className="grid gap-2">
            <Label htmlFor="protocol-method">Method</Label>
            <Textarea
              id="protocol-method"
              className="min-h-40"
              placeholder={METHOD_PLACEHOLDER}
              {...form.register("description")}
            />
            <div className="flex items-start justify-between gap-2">
              <p className="text-xs text-muted-foreground">
                How the assay is run, so a colleague can repeat it. You can refine it on the draft.
              </p>
              {suggestionsOn && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="shrink-0"
                  disabled={!methodValue.trim() || suggest.isPending}
                  onClick={suggestFromMethod}
                >
                  {suggest.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="mr-2 h-4 w-4" />
                  )}
                  {suggest.isPending ? "Reading the method…" : "Suggest from method"}
                </Button>
              )}
            </div>
          </div>

          <div className="grid gap-2">
            <div className="flex items-center justify-between">
              <Label>Assay conditions</Label>
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
            <p className="text-xs text-muted-foreground">
              What each run records, so its runs can be told apart: concentrations, times,
              temperatures. Together they define the protocol.
            </p>
            <SuggestedConditions
              suggestions={openSuggestions}
              onAdd={addSuggestion}
              onDismiss={dismissSuggestion}
            />
            {suggested?.length === 0 && (
              <p className="text-xs text-muted-foreground">Nothing to suggest from this method.</p>
            )}
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
              <div className="grid gap-2">
                <Label>References</Label>
                <ReferencesEditor
                  references={references}
                  onAdd={(r) => setReferences((prev) => [...prev, r])}
                  onRemove={(r) => setReferences((prev) => prev.filter((x) => x !== r))}
                  canEdit
                />
              </div>
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
