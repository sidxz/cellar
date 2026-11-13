"use client";

import { StatusBadge } from "@/shared/components/status-badge";
import { Button } from "@/shared/components/ui/button";
import { Checkbox } from "@/shared/components/ui/checkbox";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useWorkspaceMembers } from "@/shared/hooks/use-workspace-members";
import { shortId } from "@/shared/lib/utils";
import { useMemo } from "react";
import { useCurvePositions } from "../../hooks/use-curve-positions";
import { type CurveRunInfo, runHeading, sameDateTags } from "../../lib/curve-plot";
import { MAX_CURVE_RUNS, toggleRun } from "../../lib/curve-selection";
import { RUN_STATUS_LABELS, type RunStatus } from "../../types";
import { MultiRunCurves } from "../multi-run-curves";

const NO_FILTER = {};

/** The protocol's runs that have curves, to choose from, and the curve viewer
 *  over the chosen ones. */
export function CurvesTab({
  protocolId,
  runIds,
  onRunIdsChange,
}: {
  protocolId: string;
  runIds: readonly string[];
  onRunIdsChange: (ids: string[]) => void;
}) {
  // No filter: the runs that have curves (any status, newest first), no positions.
  const { data, isLoading, error } = useCurvePositions(protocolId, NO_FILTER);
  const { data: members } = useWorkspaceMembers();

  const runs = useMemo<CurveRunInfo[]>(
    () =>
      (data?.runs ?? []).map((r) => ({
        runId: r.run_id,
        runDate: r.run_date,
        operator: r.operator,
        status: r.status,
        notes: r.notes,
      })),
    [data],
  );
  const tags = useMemo(() => sameDateTags(runs), [runs]);
  const scientistOf = (userId: string) =>
    members?.find((m) => m.user_id === userId)?.name ?? "Scientist unavailable";

  if (isLoading) return <Skeleton data-testid="curves-tab-loading" className="h-[400px] w-full" />;
  if (error || !data) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Could not load the runs. Reload the page and try again.
      </p>
    );
  }

  const chosen = new Set(runIds);
  const full = runIds.length >= MAX_CURVE_RUNS;
  const countOf = new Map(data.runs.map((r) => [r.run_id, r.position_count]));

  return (
    <div className="space-y-4">
      <div className="rounded-md border">
        <div className="flex items-center gap-3 border-b px-3 py-2 text-sm">
          <span className="font-medium">Runs with traces</span>
          {full && <span className="text-muted-foreground">At most 8 runs at once</span>}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="ml-auto"
            disabled={runIds.length === 0}
            onClick={() => onRunIdsChange([])}
          >
            Clear
          </Button>
        </div>
        <ul aria-label="Runs with traces" className="max-h-64 divide-y overflow-y-auto">
          {runs.map((run) => {
            const scientist = scientistOf(run.operator);
            const tag = tags.get(run.runId);
            const count = countOf.get(run.runId) ?? 0;
            const disabled = full && !chosen.has(run.runId);
            return (
              <li key={run.runId}>
                <label
                  htmlFor={`curve-run-${run.runId}`}
                  className={`flex items-center gap-3 px-3 py-1.5 text-sm ${disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}
                >
                  <Checkbox
                    id={`curve-run-${run.runId}`}
                    checked={chosen.has(run.runId)}
                    disabled={disabled}
                    aria-label={runHeading(run, { scientist, tag })}
                    onCheckedChange={() => onRunIdsChange(toggleRun(runIds, run.runId))}
                  />
                  <span className="font-mono">{run.runDate}</span>
                  <span>{scientist}</span>
                  <StatusBadge
                    status={run.status}
                    label={RUN_STATUS_LABELS[run.status as RunStatus]}
                  />
                  <span className="text-muted-foreground">
                    {count} {count === 1 ? "position" : "positions"}
                  </span>
                  {tag && <span className="truncate text-muted-foreground">{tag}</span>}
                </label>
              </li>
            );
          })}
        </ul>
      </div>

      {runIds.length === 0 ? (
        <div className="rounded-md border border-dashed py-12 text-center text-sm text-muted-foreground">
          Choose runs above to see their traces
        </div>
      ) : (
        <MultiRunCurves
          protocolId={protocolId}
          filter={{ runIds }}
          initial={{
            select: "none",
            showReferences: false,
            colour: { mode: "group", groupBy: "run" },
          }}
          exportName={`traces-protocol-${shortId(protocolId)}`}
          empty={
            <p className="py-8 text-center text-sm text-muted-foreground">
              None of the chosen runs has traces.
            </p>
          }
        />
      )}
    </div>
  );
}
