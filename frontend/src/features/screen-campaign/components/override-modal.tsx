"use client";

/**
 * OverrideModal — shared across ResultsGrid (legacy V1) and ResultsGridV2.
 *
 * Allows the user to manually override a single campaign measurement cell:
 * qualifier / value / unit / reason (B8: reason required when the value
 * differs from the auto-resolved one).
 */

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useOverrideResultCellApiV1CampaignsCampaignIdResultsResultIdCellsChannelIdPatch } from "@/shared/lib/api/campaigns/campaigns";
import { formatMeasurementValue } from "@/shared/lib/format-number";

import { campaignKeys } from "../hooks/use-campaigns";
import type {
  CampaignChannelResponse,
  CampaignMeasurementResponse,
  CampaignResultResponse,
} from "../types";

// ── OverrideModal ─────────────────────────────────────────────────────────────

export interface OverrideModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaignId: string;
  result: CampaignResultResponse;
  channel: CampaignChannelResponse;
  measurement?: CampaignMeasurementResponse;
}

export function OverrideModal({
  open,
  onOpenChange,
  campaignId,
  result,
  channel,
  measurement,
}: OverrideModalProps) {
  const qc = useQueryClient();
  const [value, setValue] = useState(String(measurement?.value ?? ""));
  const [qualifier, setQualifier] = useState(measurement?.value_qualifier ?? "=");
  const [unit, setUnit] = useState(measurement?.unit ?? "");
  const [reason, setReason] = useState(measurement?.override_reason ?? "");

  const isPlaceholderQualifier = qualifier === "nd" || qualifier === "excluded";

  const handleQualifierChange = (v: string) => {
    setQualifier(v);
    // B7: when qualifier flips to ND/excluded, clear value + unit on the
    // same gesture — avoids a reactive side-effect after the render.
    if (v === "nd" || v === "excluded") {
      setValue("");
      setUnit("");
    }
  };

  // B8: reason is required when the override changes the auto-resolved value.
  const valueDiffersFromAuto = (() => {
    if (!measurement) return true;
    const numValue = value !== "" ? Number(value) : null;
    return (
      numValue !== (measurement.value ?? null) ||
      qualifier !== measurement.value_qualifier ||
      (!isPlaceholderQualifier && unit !== measurement.unit)
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
          onOpenChange(false);
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
        value: isPlaceholderQualifier ? null : value !== "" ? Number(value) : undefined,
        value_qualifier: qualifier,
        unit: isPlaceholderQualifier ? "" : unit,
        reason: reason.trim() || undefined,
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
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
              {measurement.is_manual_override && (
                <Badge variant="secondary" className="ml-2 text-xs">
                  overridden
                </Badge>
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
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[
                    { v: "=", label: "= (exact)" },
                    { v: "<", label: "< (less than)" },
                    { v: ">", label: "> (greater than)" },
                    { v: "nd", label: "nd (not determined)" },
                    { v: "excluded", label: "excluded" },
                  ].map((q) => (
                    <SelectItem key={q.v} value={q.v}>
                      {q.label}
                    </SelectItem>
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

          {/* B8: reason — required when value differs from auto-resolved */}
          <div className="space-y-1">
            <Label>
              Reason{" "}
              {reasonRequired ? (
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
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={overrideMutation.isPending || !reasonOk || !unitOk}
          >
            {overrideMutation.isPending ? "Saving..." : "Save Override"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
