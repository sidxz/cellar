"use client";

import { OutlierFlagPopover } from "@/features/screening-assay/components/outlier-flag-popover";
import { useFlagOutliers } from "@/features/screening-assay/hooks/use-flag-outliers";
import { apiReason } from "@/features/screening-assay/hooks/use-instrument-import-wizard";
import type { Run } from "@/features/screening-assay/types";
import { Button } from "@/shared/components/ui/button";
import { useCanEdit } from "@/shared/hooks/use-current-user";
import { showError, showSuccess, showWarning } from "@/shared/lib/toast";
import { useMemo } from "react";
import { usePassMask } from "../hooks/use-pass-mask";
import { actionSet } from "../lib/action-set";
import { LEVELS } from "../lib/levels";
import { outlierTargets } from "../lib/outliers";
import { useWorkbench } from "../store/workbench-context";
import type { Dataset } from "../types";

const fmt = (n: number) => n.toLocaleString();
const wellsText = (n: number) => `${fmt(n)} ${n === 1 ? "well" : "wells"}`;

/** Runs whose outlier flags can change: unlocked, and draft, in progress or completed
 * (with a reason) — the API refuses the others. */
const FLAGGABLE = new Set(["draft", "in_progress", "completed"]);

/** Flag the selected wells as outliers, or remove their flag — only the wells of runs
 * whose flags can change. Each run is recalculated and the dataset reloads. */
function OutlierActions({ ds, rows, runs }: { ds: Dataset; rows: number[]; runs: Run[] }) {
  const canEdit = useCanEdit();
  const flag = useFlagOutliers();
  const targets = useMemo(() => {
    const editable = new Set(
      runs.filter((r) => !r.is_locked && FLAGGABLE.has(r.status)).map((r) => r.id),
    );
    return outlierTargets(ds, rows, editable);
  }, [ds, rows, runs]);
  const completed = new Set(runs.filter((r) => r.status === "completed").map((r) => r.id));
  const needsReason = (byRun: Map<string, string[]>) =>
    [...byRun.keys()].some((id) => completed.has(id));
  if (!canEdit || ds.level !== "wells") return null;

  const count = (byRun: Map<string, string[]>) =>
    [...byRun.values()].reduce((n, wells) => n + wells.length, 0);
  async function apply(byRun: Map<string, string[]>, outlier: boolean, reason: string | null) {
    let changed = 0;
    try {
      for (const [runId, well_ids] of byRun) {
        const out = await flag.mutateAsync({ runId, well_ids, outlier, reason });
        changed += out.wells_changed;
        if (out.compute_warning) showWarning(out.compute_warning);
      }
      showSuccess(
        outlier
          ? `${wellsText(changed)} flagged as outliers`
          : `${wellsText(changed)} no longer outliers`,
      );
    } catch (e) {
      showError(apiReason(e));
    }
  }

  const toFlag = count(targets.flag);
  const toUnflag = count(targets.unflag);
  return (
    <>
      {toFlag > 0 && (
        <OutlierFlagPopover
          flagged={false}
          title={wellsText(toFlag)}
          pending={flag.isPending}
          reasonRequired={needsReason(targets.flag)}
          onSubmit={(reason) => apply(targets.flag, true, reason)}
        >
          <Button size="sm" variant="outline" className="h-7">
            Flag as outlier
          </Button>
        </OutlierFlagPopover>
      )}
      {toUnflag > 0 && (
        <OutlierFlagPopover
          flagged
          title={wellsText(toUnflag)}
          pending={flag.isPending}
          reasonRequired={needsReason(targets.unflag)}
          onSubmit={(reason) => apply(targets.unflag, false, reason)}
        >
          <Button size="sm" variant="outline" className="h-7">
            Remove flag
          </Button>
        </OutlierFlagPopover>
      )}
    </>
  );
}

/** Above the table while something is selected: how many selected rows the filters
 * show and hide, with Clear and Filter to selection — and, on Wells, the outlier flags of
 * ``runs`` (the source's runs). */
export function SelectionStrip({ ds, runs = [] }: { ds: Dataset; runs?: Run[] }) {
  const selection = useWorkbench((s) => s.selection);
  const clearSelection = useWorkbench((s) => s.clearSelection);
  const filterToSelection = useWorkbench((s) => s.filterToSelection);
  const mask = usePassMask(ds);
  const set = useMemo(
    () => (selection.size > 0 ? actionSet(ds, selection, mask) : null),
    [ds, selection, mask],
  );
  if (!set) return null;

  const visible = set.rows.length;
  const total = visible + set.hiddenSelected;
  const { one, many } = LEVELS[ds.level];
  return (
    <div className="flex shrink-0 items-center gap-2 border-b bg-primary/5 px-3 py-1 text-sm">
      <output>
        <b>{fmt(total)}</b> {total === 1 ? one : many} selected · <b>{fmt(visible)}</b> visible ·{" "}
        <b>{fmt(set.hiddenSelected)}</b> hidden by filters
      </output>
      <div className="ml-auto" />
      <OutlierActions ds={ds} rows={set.rows} runs={runs} />
      <Button size="sm" variant="outline" className="h-7" onClick={clearSelection}>
        Clear
      </Button>
      <Button size="sm" variant="outline" className="h-7" onClick={filterToSelection}>
        Filter to selection
      </Button>
    </div>
  );
}
