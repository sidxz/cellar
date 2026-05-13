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

  const updateProtocol = useUpdateProtocol(protocolId);
  const setOntologyAnnotation = useSetOntologyAnnotation(protocolId);
  const removeOntologyAnnotation = useRemoveOntologyAnnotation(protocolId);

  const { data: ontologySlots } = useOntologySlots();

  return (
    <>
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
