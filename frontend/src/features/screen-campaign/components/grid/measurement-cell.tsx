"use client";

import { useState } from "react";
import { Pencil } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import type { CampaignMeasurementResponse } from "../../types";

interface MeasurementCellProps {
  measurement: CampaignMeasurementResponse | undefined;
  readOnly: boolean;
  onEdit: () => void;
}

function HitChip({ call }: { call: string | null | undefined }) {
  if (!call) return null;
  const cls =
    call === "hit"
      ? "border-green-500/40 bg-green-500/10 text-green-700 dark:text-green-300"
      : call === "miss"
      ? "border-zinc-500/40 bg-zinc-500/10 text-zinc-600 dark:text-zinc-400"
      : "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300";
  return (
    <span className={`ml-1 rounded-sm border px-1 py-px text-[10px] ${cls}`}>
      {call}
    </span>
  );
}

export function MeasurementCell({
  measurement,
  readOnly,
  onEdit,
}: MeasurementCellProps) {
  const [hover, setHover] = useState(false);

  if (!measurement)
    return <span className="text-muted-foreground">&mdash;</span>;

  const q = measurement.value_qualifier;
  if (q === "nd" || q === "excluded") {
    return (
      <span className="text-muted-foreground italic">{q}</span>
    );
  }

  const prefix = q === "<" || q === ">" ? `${q} ` : "";

  return (
    <div
      className="flex items-center gap-1"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <span className="text-sm">
        {prefix}
        {measurement.value} {measurement.unit}
      </span>
      <HitChip call={measurement.hit_call} />
      {measurement.is_manual_override && (
        <Badge
          variant="outline"
          className="text-[10px]"
          title={measurement.override_reason ?? "Manually overridden"}
        >
          OVR
        </Badge>
      )}
      {!readOnly && hover && (
        <button
          type="button"
          onClick={onEdit}
          className="ml-1 text-muted-foreground hover:text-foreground"
        >
          <Pencil className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}
