"use client";

/**
 * StageTargetSelect — "which stage do these runs / columns go to?", shared by
 * add-from-runs, mirror protocol and add readout. Stages are picked by name in
 * funnel order; campaign-level is offered only as "Other columns".
 */

import { useMemo } from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { stagesInFunnelOrder } from "../lib/stage-column-groups";
import type { CampaignStageResponse } from "../types";

// Radix Select forbids an empty item value, hence the sentinels. "" = nothing
// picked yet.
export const NEW_STAGE = "__new_stage__";
export const OTHER_COLUMNS_TARGET = "__other_columns__";

/** The `stage_id` a target sends: the picked stage, else null. */
export function stageIdOf(target: string): string | null {
  return target && target !== NEW_STAGE && target !== OTHER_COLUMNS_TARGET ? target : null;
}

export function StageTargetSelect({
  stages,
  value,
  onChange,
  allowNewStage = false,
}: {
  stages: CampaignStageResponse[];
  value: string;
  onChange: (target: string) => void;
  /** Offer "New stage…" (the `stage_name` path). */
  allowNewStage?: boolean;
}) {
  const ordered = useMemo(() => stagesInFunnelOrder(stages), [stages]);
  return (
    <Select value={value} onValueChange={onChange}>
      {/* Full width: a fit-to-content trigger would jump as the pick changes. */}
      <SelectTrigger aria-label="Stage" className="w-full">
        <SelectValue placeholder="Choose a stage…" />
      </SelectTrigger>
      <SelectContent>
        {ordered.map((s) => (
          <SelectItem key={s.id} value={s.id}>
            {s.name}
          </SelectItem>
        ))}
        {allowNewStage && <SelectItem value={NEW_STAGE}>New stage…</SelectItem>}
        <SelectItem value={OTHER_COLUMNS_TARGET}>Other columns (not judged by a stage)</SelectItem>
      </SelectContent>
    </Select>
  );
}
