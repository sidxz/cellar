"use client";

/**
 * DecisionPanel — Task 8.5
 *
 * Right pane. Shows focused row's measurements, decision radio, decision_reason
 * textarea, notes textarea. PATCHes on change with 300ms debounce.
 */

import { useEffect, useRef, useState } from "react";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { Badge } from "@/shared/components/ui/badge";
import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import { MoleculeThumbnail } from "@/shared/components/molecule-thumbnail";
import { useSetResultDecisionApiV1CampaignsCampaignIdResultsResultIdPatch } from "@/shared/lib/api/campaigns/campaigns";
import { useMoleculesByIds } from "../lib/hooks";
import type {
  CampaignResultResponse,
  CampaignChannelResponse,
  CampaignMeasurementResponse,
} from "../types";

// ── 300ms debounce hook ───────────────────────────────────────────────────────

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// ── Component ─────────────────────────────────────────────────────────────────

interface DecisionPanelProps {
  campaignId: string;
  result: CampaignResultResponse;
  /** The channel corresponding to the first measurement (informational). */
  channel: CampaignChannelResponse | null;
  onUpdate?: () => void;
}

export function DecisionPanel({ campaignId, result, onUpdate }: DecisionPanelProps) {
  const [decision, setDecision] = useState(result.decision);
  const [reason, setReason] = useState((result.decision_reason as string | undefined) ?? "");
  const [notes, setNotes] = useState((result.notes as string | undefined) ?? "");

  // Sync with externally-updated result (e.g. after a refresh)
  useEffect(() => {
    setDecision(result.decision);
    setReason((result.decision_reason as string | undefined) ?? "");
    setNotes((result.notes as string | undefined) ?? "");
  }, [result.id, result.decision, result.decision_reason, result.notes]);

  const debouncedDecision = useDebounce(decision, 300);
  const debouncedReason = useDebounce(reason, 300);
  const debouncedNotes = useDebounce(notes, 300);

  const mutation = useSetResultDecisionApiV1CampaignsCampaignIdResultsResultIdPatch();

  // Track last-patched values to avoid unnecessary requests
  const lastPatched = useRef({ decision: result.decision, reason, notes });

  useEffect(() => {
    const prev = lastPatched.current;
    if (
      debouncedDecision === prev.decision &&
      debouncedReason === prev.reason &&
      debouncedNotes === prev.notes
    )
      return;

    lastPatched.current = {
      decision: debouncedDecision,
      reason: debouncedReason,
      notes: debouncedNotes,
    };

    mutation.mutate(
      {
        campaignId,
        resultId: result.id,
        data: {
          decision: debouncedDecision,
          reason: debouncedReason || undefined,
          notes: debouncedNotes || null,
        },
      },
      { onSuccess: () => onUpdate?.() },
    );
  // mutation is stable; onUpdate intentionally omitted from deps to avoid loop
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId, debouncedDecision, debouncedReason, debouncedNotes, result.id]);

  const { data: moleculesPage } = useMoleculesByIds([result.molecule_id]);
  const mol = moleculesPage?.items?.[0];

  return (
    <div className="p-4 space-y-5">
      <div className="flex flex-col items-start gap-2">
        <MoleculeThumbnail
          smiles={mol?.structure?.smiles ?? null}
          size="md"
          fallback={mol?.registration_number ?? "no structure"}
        />
        <div>
          <h3 className="text-sm font-semibold">
            {mol?.registration_number ?? "Compound"}
          </h3>
          {mol?.name && (
            <p className="text-xs text-muted-foreground">{mol.name}</p>
          )}
        </div>
      </div>

      {/* Measurements read-only list */}
      {result.measurements.length > 0 && (
        <div>
          <h4 className="text-xs uppercase text-muted-foreground font-medium mb-2">
            Measurements
          </h4>
          <div className="space-y-1.5">
            {result.measurements.map((m: CampaignMeasurementResponse) => (
              <div key={m.id} className="text-xs flex items-start gap-2">
                <span className="text-muted-foreground shrink-0 w-5">
                  {m.value_qualifier !== "=" ? m.value_qualifier : ""}
                </span>
                <span className="font-medium">
                  {m.value != null ? String(m.value) : "ND"}
                  {m.unit && m.unit !== "-" && (
                    <span className="text-muted-foreground ml-0.5">{m.unit}</span>
                  )}
                </span>
                {m.hit_call && (
                  <Badge variant="secondary" className="text-[10px] px-1 py-0">
                    {m.hit_call as string}
                  </Badge>
                )}
                {m.is_manual_override && (
                  <Badge variant="outline" className="text-[9px] px-1 py-0">
                    OVR
                  </Badge>
                )}
                <span className="text-muted-foreground ml-auto shrink-0">
                  {m.protocol_name_snapshot}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Decision */}
      <div>
        <Label className="text-xs uppercase text-muted-foreground font-medium">
          Decision
        </Label>
        <RadioGroup
          value={decision}
          onValueChange={setDecision}
          className="mt-2 space-y-1.5"
        >
          {[
            { value: "selected", label: "Selected", color: "text-green-700" },
            { value: "deferred", label: "Deferred", color: "text-yellow-700" },
            { value: "rejected", label: "Rejected", color: "text-red-700" },
          ].map((opt) => (
            <div key={opt.value} className="flex items-center gap-2">
              <RadioGroupItem
                id={`decision-${result.id}-${opt.value}`}
                value={opt.value}
              />
              <label
                htmlFor={`decision-${result.id}-${opt.value}`}
                className={`text-sm cursor-pointer font-medium ${opt.color}`}
              >
                {opt.label}
              </label>
            </div>
          ))}
        </RadioGroup>
      </div>

      {/* Reason */}
      <div className="space-y-1.5">
        <Label htmlFor={`reason-${result.id}`} className="text-xs">
          Reason (optional)
        </Label>
        <Textarea
          id={`reason-${result.id}`}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Why was this decision made?"
          rows={2}
          className="text-sm"
        />
      </div>

      {/* Notes */}
      <div className="space-y-1.5">
        <Label htmlFor={`notes-${result.id}`} className="text-xs">
          Notes (optional)
        </Label>
        <Textarea
          id={`notes-${result.id}`}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Freeform notes..."
          rows={3}
          className="text-sm"
        />
        {mutation.isPending && (
          <p className="text-xs text-muted-foreground">Saving...</p>
        )}
      </div>
    </div>
  );
}
