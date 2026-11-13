"use client";

import { Button } from "@/shared/components/ui/button";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useCanEdit } from "@/shared/hooks/use-current-user";
import { cn, shortId } from "@/shared/lib/utils";
import { useMemo, useRef, useState } from "react";
import { type CurveView, useRunCurves } from "../hooks/use-run-curves";
import { curveSetFromRun } from "../lib/curve-plot";
import { EMPTY_SELECTION, type SelectionState } from "../lib/curve-selection";
import { labellingEditRefusal } from "../lib/position-edits";
import { DOSE_UNIT_LABELS, type DoseUnit, type Run } from "../types";
import { CurveViewer } from "./curve-viewer";
import { EditLabellingDialog } from "./edit-labelling-dialog";

const PLOT_HEIGHT = "h-[400px]";

/** The Curves tab: pick positions, overlay their curves for one signal with
 *  the instrument's reported values as lines, read a table of them, export
 *  the figure. */
export function RunCurvesPanel({
  runId,
  run,
}: {
  runId: string;
  /** Given, Edit labelling is offered to editors. */
  run?: Pick<Run, "id" | "status" | "is_locked">;
}) {
  const canEdit = useCanEdit();
  const [editOpen, setEditOpen] = useState(false);
  const [channel, setChannel] = useState<string | undefined>();
  const [view, setView] = useState<CurveView>("measured");
  // The committed window; undefined lets the API choose.
  const [derivativeWindow, setDerivativeWindow] = useState<number | undefined>();
  const {
    data: fetched,
    isLoading,
    isPlaceholderData,
    error,
    refetch,
  } = useRunCurves(runId, {
    channel,
    view,
    window: view === "derivative" ? derivativeWindow : undefined,
  });
  // A failed request keeps the last curves' toolbar on screen, so the user can
  // change the window or the view instead of being left with only an error.
  const lastGood = useRef(fetched);
  if (fetched) lastGood.current = fetched;
  const data = fetched ?? lastGood.current;
  const failed = !!error && !fetched;

  const [selection, setSelection] = useState<SelectionState>(EMPTY_SELECTION);
  const [showReferences, setShowReferences] = useState(false);
  const set = useMemo(() => (data ? curveSetFromRun(data) : null), [data]);

  if (isLoading && !data) return <Skeleton className={cn("w-full", PLOT_HEIGHT)} />;
  if (!data || !set) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">Could not load the traces.</p>
    );
  }

  const doseUnit = DOSE_UNIT_LABELS[data.dose_unit as DoseUnit] ?? data.dose_unit;
  const editRefusal = run ? labellingEditRefusal(run) : null;

  return (
    <CurveViewer
      set={set}
      showReferences={showReferences}
      onShowReferencesChange={setShowReferences}
      selection={selection}
      onSelectionChange={setSelection}
      onChannelChange={setChannel}
      onViewChange={setView}
      onWindowChange={setDerivativeWindow}
      pending={isPlaceholderData}
      failed={failed}
      exportName={`run-traces-${shortId(data.run_id)}`}
      selectorAction={
        run &&
        canEdit && (
          <>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!!editRefusal}
              title={editRefusal ?? undefined}
              onClick={() => setEditOpen(true)}
            >
              Edit labelling
            </Button>
            <EditLabellingDialog
              run={run}
              positions={data.positions}
              doseUnit={doseUnit}
              open={editOpen}
              onOpenChange={setEditOpen}
              onReload={refetch}
            />
          </>
        )
      }
    />
  );
}
