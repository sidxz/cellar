"use client";

import { OntologySearchInput, type OntologyTerm } from "@/shared/components/ontology-search-input";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Label } from "@/shared/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import { Textarea } from "@/shared/components/ui/textarea";
import { useEffect, useMemo, useState } from "react";
import { useProtocolFacetSlots } from "../hooks/use-protocol-facet-slots";
import { useProtocolNamePreview } from "../hooks/use-protocol-name-preview";
import { useProtocolTargets } from "../hooks/use-protocol-targets";
import { type CorrectProtocolInput, useCorrectProtocol } from "../hooks/use-protocols";
import { isFixedValueValid } from "../lib/conditions";
import type { Protocol } from "../types";
import { ConditionValueInput } from "./condition-fields";
import { DiscriminatorInput } from "./discriminator-input";
import { ProtocolCategoryInput } from "./protocol-category-input";
import {
  ProtocolNamePreview,
  isPreviewSavable,
  useRequiredNameSlots,
} from "./protocol-name-preview";
import { TargetMultiSelect } from "./target-multi-select";

/** Facet slots that feed the generated name. */
const NAME_SLOTS = ["organism", "strain", "cell_line", "assay_format"];

type Step = "choose" | "correct" | "new";

interface CorrectProtocolDialogProps {
  protocol: Protocol;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** "The assay changed": the caller opens a new protocol prefilled from this one. */
  onNewAssay?: () => void;
}

const sameIds = (a: string[], b: string[]) =>
  a.length === b.length && [...a].sort().join() === [...b].sort().join();
const termIds = (terms: OntologyTerm[] | undefined) => (terms ?? []).map((t) => t.term_id);
const fixedById = (protocol: Protocol) =>
  Object.fromEntries(protocol.condition_definitions.map((cd) => [cd.id, cd.fixed_value ?? ""]));

/** A published protocol's facts were wrong (correction, same code), or the assay itself
 *  changed (a new protocol). */
export function CorrectProtocolDialog({
  protocol,
  open,
  onOpenChange,
  onNewAssay,
}: CorrectProtocolDialogProps) {
  const [step, setStep] = useState<Step>("choose");
  const [choice, setChoice] = useState<"correct" | "new" | "">("");
  const slots = useProtocolFacetSlots().filter((s) => NAME_SLOTS.includes(s.name));
  const { data: richTargets } = useProtocolTargets(protocol.id);
  const directIds = useMemo(
    () => (richTargets ?? []).filter((t) => t.is_direct).map((t) => t.id),
    [richTargets],
  );
  const original = protocol.ontology_annotations ?? {};

  const [category, setCategory] = useState(protocol.category ?? "");
  const needs = useRequiredNameSlots(category);
  const [discriminator, setDiscriminator] = useState(protocol.discriminator ?? "");
  const [annotations, setAnnotations] = useState<Record<string, OntologyTerm[]>>(original);
  const [targetIds, setTargetIds] = useState<string[]>(directIds);
  const [fixed, setFixed] = useState<Record<string, string>>(() => fixedById(protocol));
  const [reason, setReason] = useState("");
  const correct = useCorrectProtocol(protocol.id);

  // Targets follow the server until the user edits them; every opening forgets edits.
  const [targetsTouched, setTargetsTouched] = useState(false);
  const directKey = directIds.join(",");
  useEffect(() => {
    if (!targetsTouched) setTargetIds(directKey ? directKey.split(",") : []);
  }, [directKey, targetsTouched]);

  // Every opening starts from the protocol as it is now.
  useEffect(() => {
    if (!open) return;
    setStep("choose");
    setChoice("");
    setCategory(protocol.category ?? "");
    setDiscriminator(protocol.discriminator ?? "");
    setAnnotations(protocol.ontology_annotations ?? {});
    setFixed(fixedById(protocol));
    setTargetsTouched(false);
    setReason("");
  }, [open, protocol]);

  const preview = useProtocolNamePreview(
    open && step === "correct"
      ? {
          category: category || null,
          target_ids: targetIds,
          ontology_annotations: annotations,
          discriminator: discriminator.trim() || null,
          protocol_id: protocol.id,
        }
      : null,
  );

  const changes = (): CorrectProtocolInput => {
    const body: CorrectProtocolInput = { reason: reason.trim() };
    if (category !== (protocol.category ?? "")) body.category = category || null;
    if (discriminator.trim() !== (protocol.discriminator ?? ""))
      body.discriminator = discriminator.trim() || null;
    const changedSlots = NAME_SLOTS.filter(
      (slot) => !sameIds(termIds(annotations[slot]), termIds(original[slot])),
    );
    if (changedSlots.length > 0)
      body.ontology_annotations = Object.fromEntries(
        changedSlots.map((slot) => [slot, annotations[slot] ?? []]),
      );
    if (!sameIds(targetIds, directIds)) body.target_ids = targetIds;
    const changedFixed = protocol.condition_definitions.filter(
      (cd) => (fixed[cd.id] ?? "").trim() !== (cd.fixed_value ?? ""),
    );
    if (changedFixed.length > 0)
      body.condition_fixed_values = Object.fromEntries(
        changedFixed.map((cd) => [cd.id, (fixed[cd.id] ?? "").trim() || null]),
      );
    return body;
  };

  const fixedValid = protocol.condition_definitions.every((cd) =>
    isFixedValueValid({ ...cd, fixed_value: fixed[cd.id] }),
  );
  const canSave =
    !!reason.trim() && fixedValid && isPreviewSavable(preview.data) && !correct.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Correct details of {protocol.code ?? protocol.name}</DialogTitle>
          <DialogDescription>
            The name comes from these facts, so changing them renames the protocol.
          </DialogDescription>
        </DialogHeader>

        {step === "choose" && (
          <RadioGroup
            value={choice}
            onValueChange={(v) => setChoice(v as "correct" | "new")}
            className="grid gap-3 py-2"
          >
            <div className="flex items-start gap-2">
              <RadioGroupItem value="correct" id="choice-correct" className="mt-1" />
              <Label htmlFor="choice-correct" className="grid gap-1 font-normal">
                <span className="font-medium">Correction: it was always this</span>
                <span className="text-xs text-muted-foreground">
                  The recorded facts were wrong. Same code; past results keep their protocol.
                </span>
              </Label>
            </div>
            <div className="flex items-start gap-2">
              <RadioGroupItem value="new" id="choice-new" className="mt-1" />
              <Label htmlFor="choice-new" className="grid gap-1 font-normal">
                <span className="font-medium">The assay changed</span>
                <span className="text-xs text-muted-foreground">
                  A different experiment. It gets a new protocol and code; this one keeps its name
                  and data.
                </span>
              </Label>
            </div>
          </RadioGroup>
        )}

        {step === "correct" && (
          <div className="grid gap-4 py-2">
            <div className="grid gap-2">
              <Label>Category</Label>
              <ProtocolCategoryInput value={category} onChange={setCategory} />
            </div>
            {slots.map((slot) => (
              <div key={slot.name} className="grid gap-2">
                <Label>{slot.label}</Label>
                <OntologySearchInput
                  ontologySources={slot.ontology_sources}
                  rootConceptId={slot.root_concept_id}
                  slot={slot.name}
                  value={annotations[slot.name] ?? []}
                  onChange={(terms) => setAnnotations((a) => ({ ...a, [slot.name]: terms }))}
                  allowFreeText={slot.allow_free_text}
                />
              </div>
            ))}
            <div className="grid gap-2">
              <Label>Targets</Label>
              <TargetMultiSelect
                value={targetIds}
                onChange={(ids) => {
                  setTargetsTouched(true);
                  setTargetIds(ids);
                }}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="correct-discriminator">
                Discriminator{needs.has("discriminator") ? "" : " (optional)"}
              </Label>
              <DiscriminatorInput
                id="correct-discriminator"
                value={discriminator}
                onChange={setDiscriminator}
                base={preview.data?.base ?? null}
              />
            </div>
            {protocol.condition_definitions.length > 0 && (
              <div className="grid gap-2">
                <Label>Fixed condition values</Label>
                <p className="text-xs text-muted-foreground">
                  A fixed value defines the protocol; leave one empty when it varies per run.
                </p>
                {protocol.condition_definitions.map((cd) => {
                  const label = cd.unit ? `${cd.name} (${cd.unit})` : cd.name;
                  return (
                    <div key={cd.id} className="grid gap-1">
                      <span className="text-xs">{label}</span>
                      <ConditionValueInput
                        def={cd}
                        value={fixed[cd.id] ?? ""}
                        onChange={(v) => setFixed((f) => ({ ...f, [cd.id]: v }))}
                        noneLabel="(varies per run)"
                        aria-label={label}
                      />
                    </div>
                  );
                })}
                {!fixedValid && (
                  <p className="text-xs text-destructive">
                    Each fixed value must fit its condition: a number, or one of its values.
                  </p>
                )}
              </div>
            )}
            <ProtocolNamePreview
              preview={preview.data}
              isFetching={preview.isFetching}
              code={protocol.code}
            />
            <div className="grid gap-2">
              <Label htmlFor="correction-reason">Reason</Label>
              <Textarea
                id="correction-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. The strain was misrecorded at creation"
                rows={2}
              />
            </div>
          </div>
        )}

        {step === "new" && (
          <p className="py-2 text-sm text-muted-foreground">
            We'll open a new protocol with this one's fields filled in. Change what is different;
            the name updates as you go.
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          {step === "choose" && (
            <Button disabled={!choice} onClick={() => setStep(choice as Step)}>
              Continue
            </Button>
          )}
          {step === "correct" && (
            <Button
              disabled={!canSave}
              onClick={() => correct.mutate(changes(), { onSuccess: () => onOpenChange(false) })}
            >
              Save correction
            </Button>
          )}
          {step === "new" && (
            <Button
              onClick={() => {
                onOpenChange(false);
                onNewAssay?.();
              }}
            >
              Create new protocol from this one
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
