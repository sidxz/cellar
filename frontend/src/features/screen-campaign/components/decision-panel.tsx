"use client";

/**
 * DecisionPanel — Task 8.5
 *
 * Right pane. Shows focused row's measurements, decision radio, decision_reason
 * textarea, notes textarea. PATCHes on change with 300ms debounce.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Label } from "@/shared/components/ui/label";
import { Textarea } from "@/shared/components/ui/textarea";
import { Badge } from "@/shared/components/ui/badge";
import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import { MoleculeThumbnail } from "@/shared/components/molecule-thumbnail";
import { formatMeasurementValue } from "@/shared/lib/format-number";
import { useSetResultDecisionApiV1CampaignsCampaignIdResultsResultIdPatch } from "@/shared/lib/api/campaigns/campaigns";
import { useCompoundCurves } from "@/features/screening-assay/hooks/use-compound-curves";
import { DoseResponseChart } from "@/features/screening-assay/components/dose-response-chart";
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

// ── CurveBlock — fetches + renders a single DR curve for one channel ─────────

interface CurveBlockProps {
  channelLabel: string;
  protocolId: string;
  moleculeId: string;
  sourceCurveId: string;
}

function CurveBlock({
  channelLabel,
  protocolId,
  moleculeId,
  sourceCurveId,
}: CurveBlockProps) {
  const { data: curves, isLoading } = useCompoundCurves(protocolId, moleculeId);
  const curve = curves?.find((c) => c.id === sourceCurveId) ?? curves?.[0];

  return (
    <div className="space-y-1">
      <h4 className="text-xs uppercase text-muted-foreground font-medium">
        {channelLabel} — dose response
      </h4>
      {isLoading ? (
        <div className="h-32 rounded border bg-muted/20 flex items-center justify-center text-xs text-muted-foreground">
          Loading curve…
        </div>
      ) : !curve ? (
        <div className="h-20 rounded border border-dashed bg-muted/20 flex items-center justify-center text-xs text-muted-foreground">
          No curve found for this measurement.
        </div>
      ) : (
        <div className="rounded border bg-background overflow-hidden">
          <DoseResponseChart curves={[curve]} isInteractive={false} />
        </div>
      )}
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

interface DecisionPanelProps {
  campaignId: string;
  result: CampaignResultResponse;
  /** All channels on the campaign; the panel uses these to resolve protocol_id
   *  per measurement (needed for DR-curve fetches). */
  channels: CampaignChannelResponse[];
  onUpdate?: () => void;
}

export function DecisionPanel({ campaignId, result, channels, onUpdate }: DecisionPanelProps) {
  const channelById = useMemo(
    () => new Map(channels.map((c) => [c.id, c] as const)),
    [channels],
  );
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
                  {m.value != null ? formatMeasurementValue(m.value) : "ND"}
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

      {/* Dose-response curves — one per DR-source measurement (B2) */}
      {result.measurements
        .filter((m) => {
          if (!m.source_curve_id) return false;
          const ch = channelById.get(m.channel_id);
          return ch?.source_kind === "dose_response_curve";
        })
        .map((m) => {
          const ch = channelById.get(m.channel_id);
          if (!ch) return null;
          return (
            <CurveBlock
              key={m.id}
              channelLabel={ch.label}
              protocolId={ch.protocol_id}
              moleculeId={result.molecule_id}
              sourceCurveId={m.source_curve_id as string}
            />
          );
        })}

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
