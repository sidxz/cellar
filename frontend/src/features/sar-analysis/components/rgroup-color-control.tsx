"use client";

import { AggregationControl } from "@/features/research-organization/components/search/aggregation-control";
/**
 * Activity "Color by:" control for the SAR R-group table.
 *
 * Renders two inline Selects (protocol → readout/intercept) plus the
 * `AggregationControl` summarise dropdown. When a readout is picked the
 * `onChange(SarColorSpec)` callback fires so the parent can re-color the
 * heatmap. Mirrors the compact styling of `color-mode-picker.tsx`.
 */
import { buildActivityWhereOptions } from "@/features/research-organization/lib/activity-where-options";
import type { AggregationMode } from "@/features/research-organization/lib/use-aggregation-mode";
import { useProtocol, useProtocolSummaries } from "@/features/screening-assay/hooks/use-protocols";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useState } from "react";
import type { SarColorSpec } from "../lib/sar-color-spec";
import { whereOptionToColorSpec } from "../lib/sar-color-spec";

export interface RgroupColorControlProps {
  projectIds?: string[];
  value: SarColorSpec | null;
  onChange: (spec: SarColorSpec | null) => void;
  aggregationMode: AggregationMode;
  onAggregationChange: (m: AggregationMode) => void;
}

export function RgroupColorControl({
  projectIds,
  value,
  onChange,
  aggregationMode,
  onAggregationChange,
}: RgroupColorControlProps) {
  // Track selected protocol id in local state — initialise from current spec
  // so the control is coherent when re-mounted with an existing value.
  const [selectedProtocolId, setSelectedProtocolId] = useState<string>(value?.protocolId ?? "");

  // Protocol summaries for the protocol picker
  const { data: summaries } = useProtocolSummaries(projectIds, { includeAll: true });
  const protocols = summaries ?? [];

  // Full protocol (with readout_definitions) for the readout picker
  const { data: protocol } = useProtocol(selectedProtocolId || undefined);

  // Build readout options — filter out curve_class (non-scalar)
  const allOptions = buildActivityWhereOptions(protocol);
  const readoutOptions = allOptions.filter((o) => o.group !== "curve_class");

  // Track selected where-option id in local state
  const [selectedOptionId, setSelectedOptionId] = useState<string>(
    value?.column
      ? // Reverse-map the column back to a WhereOption id so the Select
        // shows the right label on mount with an existing spec.
        (readoutOptions.find(
          (o) => whereOptionToColorSpec(selectedProtocolId, "", o).column === value.column,
        )?.id ?? "")
      : "",
  );

  function handleProtocolChange(protocolId: string) {
    setSelectedProtocolId(protocolId);
    setSelectedOptionId("");
    // Clear the spec when the protocol changes — the readout is not yet picked
    onChange(null);
  }

  function handleReadoutChange(optionId: string) {
    setSelectedOptionId(optionId);
    const opt = readoutOptions.find((o) => o.id === optionId);
    if (!opt) {
      onChange(null);
      return;
    }
    const protocolName = protocols.find((p) => p.id === selectedProtocolId)?.name ?? "";
    onChange(whereOptionToColorSpec(selectedProtocolId, protocolName, opt));
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="text-muted-foreground">Color by:</span>

      {/* Protocol picker */}
      <Select value={selectedProtocolId} onValueChange={handleProtocolChange}>
        <SelectTrigger className="h-7 w-40 text-xs" aria-label="Protocol">
          <SelectValue placeholder="Protocol…" />
        </SelectTrigger>
        <SelectContent>
          {protocols.map((p) => (
            <SelectItem key={p.id} value={p.id} className="text-xs">
              {p.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Readout / intercept picker — only visible once a protocol is chosen
          and the protocol has been loaded (readoutOptions non-empty). */}
      {selectedProtocolId && readoutOptions.length > 0 && (
        <Select value={selectedOptionId} onValueChange={handleReadoutChange}>
          <SelectTrigger className="h-7 w-40 text-xs" aria-label="Readout">
            <SelectValue placeholder="Readout…" />
          </SelectTrigger>
          <SelectContent>
            {readoutOptions.map((o) => (
              <SelectItem key={o.id} value={o.id} className="text-xs">
                {o.label}
                {o.unit ? ` (${o.unit})` : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {/* Aggregation rule */}
      <AggregationControl mode={aggregationMode} onChange={onAggregationChange} />
    </div>
  );
}
