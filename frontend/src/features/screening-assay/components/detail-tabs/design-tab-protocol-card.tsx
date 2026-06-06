"use client";

import { useOntologySlots } from "@/features/workspace-config/hooks/use-ontology-slots";
import { OntologySearchInput, type OntologyTerm } from "@/shared/components/ontology-search-input";
import { Badge } from "@/shared/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useQueryClient } from "@tanstack/react-query";
import {
  invalidateProtocolTargetQueries,
  useAddProtocolTarget,
  useProtocolTargets,
  useRemoveProtocolTarget,
} from "../../hooks/use-protocol-targets";
import {
  useRemoveOntologyAnnotation,
  useSetOntologyAnnotation,
  useUpdateProtocol,
} from "../../hooks/use-protocols";
import {
  POS_CONTROL_SIGNAL_LABELS,
  type PosControlSignal,
  type Protocol,
  type ProtocolStatus,
} from "../../types";
import { TargetMultiSelect } from "../target-multi-select";

// ---------------------------------------------------------------------------
// DesignTabProtocolCard
// Renders the protocol-level metadata sections: Ontology Annotations and
// Control Convention. Both are "protocol-level" fields that live above the
// readout / condition / layout management sections.
// ---------------------------------------------------------------------------

interface DesignTabProtocolCardProps {
  protocol: Protocol;
  protocolId: string;
}

export function DesignTabProtocolCard({ protocol, protocolId }: DesignTabProtocolCardProps) {
  const status = protocol.status as ProtocolStatus;
  const isRetired = status === "retired";
  const isDraft = status === "draft";
  const isLocked = protocol.is_locked;
  // Destructive / structural ops — strict DRAFT only. Lock blocks DRAFT too.
  const canStructurallyEdit = isDraft && !isLocked;
  // Metadata-like ops (targets, annotations) — allowed post-publish, blocked
  // only by lock or retirement (mirrors the backend add/remove-target guard).
  const canEditTargets = !isLocked && !isRetired;

  const qc = useQueryClient();
  const updateProtocol = useUpdateProtocol(protocolId);
  const setOntologyAnnotation = useSetOntologyAnnotation(protocolId);
  const removeOntologyAnnotation = useRemoveOntologyAnnotation(protocolId);
  const addProtocolTarget = useAddProtocolTarget(protocolId);
  const removeProtocolTarget = useRemoveProtocolTarget(protocolId);

  const { data: ontologySlots } = useOntologySlots();

  // Provenance (is_direct / run_count) only exists on the rich
  // GET /protocols/{id}/targets payload — protocol.targets is the
  // lightweight effective list without it.
  const { data: richTargets } = useProtocolTargets(protocolId);
  const directTargets = (richTargets ?? []).filter((t) => t.is_direct);
  const inheritedTargets = (richTargets ?? []).filter((t) => !t.is_direct);
  const directTargetIds = directTargets.map((t) => t.id);
  const targetMutationPending = addProtocolTarget.isPending || removeProtocolTarget.isPending;

  // Explicit gesture: each select/deselect persists immediately. Diffing the
  // new id set against the current direct ids dispatches the adds/removes as
  // one awaited batch with a single invalidation pass — and the select stays
  // disabled until the refetch settles, so a rapid second toggle can't diff
  // against a stale list and get silently swallowed.
  const handleDirectTargetsChange = async (ids: string[]) => {
    const mutations = [
      ...ids
        .filter((id) => !directTargetIds.includes(id))
        .map((id) => addProtocolTarget.mutateAsync(id)),
      ...directTargetIds
        .filter((id) => !ids.includes(id))
        .map((id) => removeProtocolTarget.mutateAsync(id)),
    ];
    try {
      await Promise.all(mutations);
    } catch {
      // Failures already surfaced by the mutations' error toasts.
    } finally {
      await invalidateProtocolTargetQueries(qc, protocolId);
    }
  };

  return (
    <>
      {/* ── Targets ─────────────────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Targets</CardTitle>
          <CardDescription>
            Biological targets for this protocol. Direct targets stay attached even when no run
            references them; inherited targets come from this protocol&apos;s runs and prune
            automatically when their last referencing run drops them.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {inheritedTargets.length > 0 && (
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">Inherited from runs</Label>
              <div className="flex flex-wrap gap-1">
                {inheritedTargets.map((t) => (
                  <Badge key={t.id} variant="outline" className="font-normal text-muted-foreground">
                    {t.name}
                    <span className="ml-1 text-[10px]">
                      · from {t.run_count} run{t.run_count === 1 ? "" : "s"}
                    </span>
                  </Badge>
                ))}
              </div>
            </div>
          )}
          <div className="space-y-1">
            <Label className="text-xs">Direct targets</Label>
            {canEditTargets ? (
              <TargetMultiSelect
                value={directTargetIds}
                onChange={handleDirectTargetsChange}
                placeholder="Add a target…"
                disabled={targetMutationPending}
              />
            ) : directTargets.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {directTargets.map((t) => (
                  <Badge key={t.id} variant="secondary" className="font-normal">
                    {t.name}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No direct targets.</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* ── 1. Ontology Annotations ─────────────────────────────────────── */}
      {ontologySlots && ontologySlots.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Ontology Annotations</CardTitle>
            <CardDescription>Controlled vocabulary terms for this protocol.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {ontologySlots.map((slot) => {
              const currentTerms = protocol.ontology_annotations?.[slot.name] ?? [];
              return (
                <div key={slot.id} className="space-y-1">
                  <Label className="text-sm font-medium">
                    {slot.label}
                    {slot.is_required && <span className="ml-1 text-destructive">*</span>}
                  </Label>

                  {canStructurallyEdit ? (
                    <OntologySearchInput
                      ontologySources={slot.ontology_sources}
                      rootConceptId={slot.root_concept_id}
                      allowFreeText={slot.allow_free_text}
                      value={currentTerms.map((t) => ({
                        term_id: t.term_id,
                        label: t.label,
                        ontology_source: t.ontology_source,
                        uri: t.uri,
                      }))}
                      onChange={(terms: OntologyTerm[]) => {
                        if (terms.length === 0) {
                          removeOntologyAnnotation.mutate(slot.name);
                        } else {
                          setOntologyAnnotation.mutate({
                            slot: slot.name,
                            terms: terms.map((t) => ({
                              term_id: t.term_id,
                              label: t.label,
                              ontology_source: t.ontology_source,
                              uri: t.uri,
                            })),
                          });
                        }
                      }}
                    />
                  ) : currentTerms.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {currentTerms.map((t) => (
                        <Badge key={t.term_id} variant="secondary">
                          {t.label}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">No terms assigned.</p>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {/* ── Control Convention ──────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Control Convention</CardTitle>
          <CardDescription>
            Tells the calculation engine which control well produces high raw signal. Drives %
            Inhibition / % Activation / % Control / Z-Score formula dispatch and the heatmap legend.
            Editable after publish — re-run Recompute on each run after changing.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-end gap-3">
            <div className="space-y-1">
              <Label className="text-xs">POS control signal</Label>
              <Select
                value={protocol.pos_control_signal}
                onValueChange={(v) => {
                  if (v === protocol.pos_control_signal) return;
                  updateProtocol.mutate({
                    pos_control_signal: v as PosControlSignal,
                  });
                }}
                disabled={isRetired || updateProtocol.isPending}
              >
                <SelectTrigger className="w-[420px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(["high", "low"] as PosControlSignal[]).map((v) => (
                    <SelectItem key={v} value={v}>
                      {POS_CONTROL_SIGNAL_LABELS[v]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {updateProtocol.isPending && (
              <span className="pb-2 text-xs text-muted-foreground">Saving…</span>
            )}
          </div>
        </CardContent>
      </Card>
    </>
  );
}
