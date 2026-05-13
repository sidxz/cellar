"use client";

/**
 * OverrideModal — shared across ResultsGrid (legacy V1) and ResultsGridV2.
 *
 * Allows the user to manually override a single campaign measurement cell:
 * qualifier / value / unit / hit-call / reason (B8: reason required when
 * the value differs from the auto-resolved one).
 */

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
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
import { formatMeasurementValue } from "@/shared/lib/format-number";
import { useOverrideResultCellApiV1CampaignsCampaignIdResultsResultIdCellsChannelIdPatch } from "@/shared/lib/api/campaigns/campaigns";

import { campaignKeys } from "../hooks/use-campaigns";
import type {
  CampaignResultResponse,
  CampaignChannelResponse,
  CampaignMeasurementResponse,
} from "../types";

// ── HitCallChip (modal-only helper) ──────────────────────────────────────────

const HIT_COLORS: Record<string, string> = {
  hit: "bg-orange-100 text-orange-800",
  confirmed_hit: "bg-orange-200 text-orange-900",
  inactive: "bg-blue-50 text-blue-700",
  inconclusive: "bg-gray-100 text-gray-600",
};

function HitCallChip({ hitCall }: { hitCall: string }) {
  const cls = HIT_COLORS[hitCall] ?? "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${cls}`}>
      {hitCall.replace("_", " ")}
    </span>
  );
}

// ── OverrideModal ─────────────────────────────────────────────────────────────

export interface OverrideModalProps {
  open: boolean;
  onClose: () => void;
  campaignId: string;
  result: CampaignResultResponse;
  channel: CampaignChannelResponse;
  measurement?: CampaignMeasurementResponse;
}

export function OverrideModal({
  open,
  onClose,
  campaignId,
  result,
  channel,
  measurement,
}: OverrideModalProps) {
  const qc = useQueryClient();
  const [value, setValue] = useState(String(measurement?.value ?? ""));
  const [qualifier, setQualifier] = useState(measurement?.value_qualifier ?? "=");
  const [unit, setUnit] = useState(measurement?.unit ?? "");
  // Radix Select forbids empty-string item values, so use "none" as the
  // internal sentinel and translate to undefined on submit.
  const [hitCall, setHitCall] = useState<string>(
    (measurement?.hit_call as string | undefined) ?? "none",
  );
  const [reason, setReason] = useState(measurement?.override_reason ?? "");

  const isPlaceholderQualifier = qualifier === "nd" || qualifier === "excluded";

  const handleQualifierChange = (v: string) => {
    setQualifier(v);
    // B7: when qualifier flips to ND/excluded, clear value + unit on the
    // same gesture — avoids a reactive side-effect after the render.
    if (v === "nd" || v === "excluded") {
      setValue("");
      setUnit("");
      setHitCall("none");
    }
  };

  // B8: reason is required when the override changes the auto-resolved value.
  const valueDiffersFromAuto = (() => {
    if (!measurement) return true;
    const numValue = value !== "" ? Number(value) : null;
    return (
      numValue !== (measurement.value ?? null) ||
      qualifier !== measurement.value_qualifier ||
      (!isPlaceholderQualifier && unit !== measurement.unit) ||
      hitCall !== ((measurement.hit_call as string | undefined) ?? "none")
    );
  })();
  const reasonRequired = valueDiffersFromAuto;
  const reasonOk = !reasonRequired || reason.trim().length > 0;
  const unitOk = isPlaceholderQualifier || unit.trim().length > 0;

  const overrideMutation =
    useOverrideResultCellApiV1CampaignsCampaignIdResultsResultIdCellsChannelIdPatch({
      mutation: {
        onSuccess: () => {
          void qc.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) });
          onClose();
        },
      },
    });

  const handleSubmit = () => {
    if (!reasonOk || !unitOk) return;
    overrideMutation.mutate({
      campaignId,
      resultId: result.id,
      channelId: channel.id,
      data: {
        value: isPlaceholderQualifier
          ? null
          : value !== ""
            ? Number(value)
            : undefined,
        value_qualifier: qualifier,
        unit: isPlaceholderQualifier ? "" : unit,
        hit_call: isPlaceholderQualifier || hitCall === "none" ? undefined : hitCall,
        reason: reason.trim() || undefined,
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Override Cell — {channel.label}</DialogTitle>
        </DialogHeader>

        {measurement && (
          <div className="rounded bg-muted/50 p-3 text-sm space-y-1 mb-2">
            <p className="text-xs text-muted-foreground font-medium">Auto-resolved value</p>
            <p>
              {measurement.value_qualifier !== "=" ? measurement.value_qualifier : ""}
              {formatMeasurementValue(measurement.value)} {measurement.unit}
              {measurement.hit_call && (
                <span className="ml-2"><HitCallChip hitCall={measurement.hit_call as string} /></span>
              )}
              {measurement.is_manual_override && (
                <Badge variant="secondary" className="ml-2 text-xs">overridden</Badge>
              )}
            </p>
            <p className="text-xs text-muted-foreground">
              {measurement.protocol_name_snapshot} v{measurement.protocol_version_snapshot}
            </p>
            {measurement.override_reason && (
              <p className="text-xs text-muted-foreground italic">
                Previous reason: {measurement.override_reason}
              </p>
            )}
          </div>
        )}

        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <Label>Qualifier</Label>
              <Select value={qualifier} onValueChange={handleQualifierChange}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {[
                    { v: "=", label: "= (exact)" },
                    { v: "<", label: "< (less than)" },
                    { v: ">", label: "> (greater than)" },
                    { v: "nd", label: "nd (not determined)" },
                    { v: "excluded", label: "excluded" },
                  ].map((q) => (
                    <SelectItem key={q.v} value={q.v}>{q.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Value</Label>
              <Input
                type="number"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="0.00"
                disabled={isPlaceholderQualifier}
              />
            </div>
            <div className="space-y-1">
              <Label>Unit</Label>
              <Input
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
                placeholder="µM"
                disabled={isPlaceholderQualifier}
              />
            </div>
          </div>

          <div className="space-y-1">
            <Label>Hit call (optional)</Label>
            <Select
              value={hitCall}
              onValueChange={setHitCall}
              disabled={isPlaceholderQualifier}
            >
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                {["hit", "miss", "inconclusive"].map((h) => (
                  <SelectItem key={h} value={h}>{h}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* B8: reason — required when value differs from auto-resolved */}
          <div className="space-y-1">
            <Label>
              Reason {reasonRequired ? (
                <span className="text-destructive">*</span>
              ) : (
                <span className="text-muted-foreground text-xs">(optional)</span>
              )}
            </Label>
            <Input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={
                reasonRequired
                  ? "Required — why are you changing the auto-resolved value?"
                  : "Optional rationale"
              }
            />
            {reasonRequired && !reasonOk && (
              <p className="text-xs text-destructive">
                Required: explain the deviation for audit trail.
              </p>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>Cancel</Button>
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={
              overrideMutation.isPending || !reasonOk || !unitOk
            }
          >
            {overrideMutation.isPending ? "Saving..." : "Save Override"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
