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
import type { Protocol } from "../types";
import { DiscriminatorInput } from "./discriminator-input";
import { ProtocolCategoryInput } from "./protocol-category-input";
import { ProtocolNamePreview, isPreviewSavable } from "./protocol-name-preview";
import { TargetMultiSelect } from "./target-multi-select";

/** Facet slots that feed the generated name. */
const NAME_SLOTS = ["organism", "cell_line", "assay_format"];

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
  const [discriminator, setDiscriminator] = useState(protocol.discriminator ?? "");
  const [annotations, setAnnotations] = useState<Record<string, OntologyTerm[]>>(original);
  const [targetIds, setTargetIds] = useState<string[]>(directIds);
  const [reason, setReason] = useState("");
  const correct = useCorrectProtocol(protocol.id);

  // Every opening starts from the protocol as it is now.
  useEffect(() => {
    if (!open) return;
    setStep("choose");
    setChoice("");
    setCategory(protocol.category ?? "");
    setDiscriminator(protocol.discriminator ?? "");
    setAnnotations(protocol.ontology_annotations ?? {});
    setReason("");
  }, [open, protocol]);
  // Keyed by value: a refetch that returns the same targets must not reset edits.
  const directKey = directIds.join(",");
  useEffect(() => setTargetIds(directKey ? directKey.split(",") : []), [directKey]);

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
    return body;
  };

  const canSave = !!reason.trim() && isPreviewSavable(preview.data) && !correct.isPending;

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
                  value={annotations[slot.name] ?? []}
                  onChange={(terms) => setAnnotations((a) => ({ ...a, [slot.name]: terms }))}
                  allowFreeText={slot.allow_free_text}
                />
              </div>
            ))}
            <div className="grid gap-2">
              <Label>Targets</Label>
              <TargetMultiSelect value={targetIds} onChange={setTargetIds} />
            </div>
            <div className="grid gap-2">
              <Label>Discriminator (optional)</Label>
              <DiscriminatorInput
                value={discriminator}
                onChange={setDiscriminator}
                base={preview.data?.base ?? null}
              />
            </div>
            <ProtocolNamePreview preview={preview.data} isFetching={preview.isFetching} />
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
