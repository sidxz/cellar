"use client";

/**
 * DoseResponseChart — cellar's *editing* shell around the suite's shared
 * dose-response chart.
 *
 * The picture (plot, display toggles, PNG/SVG export, summary cards) lives in
 * `@structflo/components/dose-response` as `DoseResponseChartView`, so every
 * surface in every app draws the same curve the same way. This file adds only
 * what cellar's run page can do to a curve: enter an edit session, exclude
 * points by clicking them, preview the refit, constrain the fit, classify it,
 * and save with a reason.
 *
 * A read-only surface should render `DoseResponseChartView` directly (see the
 * campaign expand dialog or the search compound sheet) — it needs none of the
 * hooks below.
 */

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/shared/components/ui/resizable";
import {
  refitDoseResponseCurveApiV1DoseResponseCurvesCurveIdRefitPost,
  useGetCurveEditHistoryApiV1DoseResponseCurvesCurveIdEditHistoryGet,
} from "@/shared/lib/api/readout-data/readout-data";
import { Plot } from "@/shared/lib/plotly";
import { useAuthz } from "@duar-auth/nextjs";
import {
  type CapturedPoint,
  DoseResponseChartView,
  type EditOverlay,
  buildCapturedPoints,
} from "@structflo/components/dose-response";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Redo2, RotateCcw, Undo2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DOSE_RESPONSE_KEY } from "../hooks/query-keys";
import { type DraftExclusion, useEditSession } from "../hooks/use-edit-session";
import { useClassifyDoseResponse, useRefitDoseResponse } from "../hooks/use-refit-dose-response";
import { useRefitPreview } from "../hooks/use-refit-preview";
import {
  type CurveConstraints,
  constraintsValid,
  defaultConstraintsFor,
} from "../lib/curve-constraints";
import type { DoseResponseConfig, DoseResponseCurve } from "../types";
import { CurveControls } from "./curve-controls";
import { CurveEditHistory } from "./curve-edit-history";
import { DoseResponsePointInventory } from "./dose-response-point-inventory";
import {
  type ExclusionReason as SaveExclusionReason,
  SaveExclusionsDialog,
} from "./save-exclusions-dialog";

interface DoseResponseChartProps {
  curves: DoseResponseCurve[];
  className?: string;
  isInteractive?: boolean;
  /** Protocol's dose-response config for the readout being plotted. When
   *  provided, the per-curve Fit Constraints accordion seeds its
   *  Free/Range/Lock toggles from these values — so a user who set Top ∈
   *  [85, 110] at the protocol level sees Range pre-selected here, instead
   *  of a misleading "Free". Per-curve edits remain independent overrides. */
  protocolConfig?: DoseResponseConfig | null;
  /** Normalization of the Y readout (looked up from
   *  ``protocol.readout_definitions`` by the parent). Used to decide
   *  whether seeding the [85,110]/[-10,10]/[0.9,1.1] percent-scale
   *  defaults makes sense — those bounds are only meaningful for
   *  percent-scale readouts. Pass null/undefined to disable seeding. */
  yReadoutNormalization?: string | null;
  /** When the parent Run is approved / locked, BE write paths (commit-refit
   *  + classify) will return Failure on submit. Surfacing the lock as a
   *  disabled Edit-Points button + a "Locked" badge avoids the chemist
   *  entering edit mode, making changes, then eating a 4xx on save. */
  runIsLocked?: boolean;
  /** Test-only override for the /refit-preview call. Production callers
   *  rely on the orval-generated default inside ``useRefitPreview``. */
  previewFn?: PreviewFnOverride;
}

type PreviewFnOverride = NonNullable<Parameters<typeof useRefitPreview>[0]>["previewFn"];

export function DoseResponseChart({
  curves,
  className,
  isInteractive = false,
  protocolConfig = null,
  yReadoutNormalization = null,
  runIsLocked = false,
  previewFn,
}: DoseResponseChartProps) {
  const { mutate: refit, isPending: isRefitting } = useRefitDoseResponse();
  const { mutate: classify, isPending: isClassifying } = useClassifyDoseResponse();

  // Auth: needed for the edit-session's authorId field. Falls back to
  // empty string in non-authenticated test renders — the session's draft
  // toggle still works locally; only the BE rejects empty authors at save.
  const { user } = useAuthz();
  const authorId = user?.userId ?? "";

  // Edit mode toggle — prevents accidental point exclusion
  const [editMode, setEditMode] = useState(false);

  // Save dialog state (opened from the edit-mode banner's Save button)
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);

  // ── Edit-session state ────────────────────────────────────────────────────
  // Edit mode only operates on the FIRST curve — multi-curve editing is a
  // follow-up. The run-page comparison view + the search detail drawer both
  // pass a single curve in the common interactive case.
  const editCurve = curves[0];
  // The wire type for `excluded_points` is a loose Record<string, unknown>[]
  // so per-bounded-context (search-grid, campaign, etc.) consumers can re-shape;
  // the BE owns the canonical `DraftExclusion` JSONB shape (migration 041) and
  // the FE seeds the session by trusting that shape.
  const editSeed = useMemo(
    () =>
      editCurve
        ? {
            excluded_points: (editCurve.excluded_points as DraftExclusion[] | null) ?? null,
          }
        : null,
    [editCurve],
  );
  const editSession = useEditSession(editSeed, {
    authorId,
    curveId: editCurve?.id,
  });
  const refitPreview = useRefitPreview({ previewFn });

  // Captured-set view of the edit curve — keyed by capturedIdx. Used by
  // the inventory side panel + the mutation handler (which enriches
  // outgoing exclusions with concentration/response so the BE persists
  // them on excluded_points; otherwise the BE writes null coords and the
  // next reload has nothing to render the X marker from).
  const editCurveCaptured = useMemo<CapturedPoint[]>(() => {
    if (!editCurve) return [];
    return buildCapturedPoints(editCurve.raw_data, editCurve.excluded_points);
  }, [editCurve]);
  const editCurveCapturedByIdx = useMemo<Map<number, CapturedPoint>>(() => {
    const m = new Map<number, CapturedPoint>();
    for (const p of editCurveCaptured) m.set(p.capturedIdx, p);
    return m;
  }, [editCurveCaptured]);

  // Audit-trail of prior point-exclusion edits for the curve under edit.
  // Hook is unconditionally invoked (React rules), but the query is gated
  // on `enabled: !!editCurve?.id` so non-interactive renders never fetch.
  const editHistoryQuery = useGetCurveEditHistoryApiV1DoseResponseCurvesCurveIdEditHistoryGet(
    editCurve?.id ?? "",
    { query: { enabled: !!editCurve?.id } },
  );

  // constraints per curve id
  const [constraintsMap, setConstraintsMap] = useState<Record<string, CurveConstraints>>({});

  // debounce refs per curve id
  const debounceRefs = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // ── React Query: commit-path mutation for /refit ──────────────────────────
  // Uses the orval-generated client directly (rich payload — exclusions[] +
  // save_reason + save_note). The legacy useRefitDoseResponse hook stays
  // available for the constraint-edit flow below.
  const queryClient = useQueryClient();
  const refitCommitMutation = useMutation({
    mutationFn: ({
      curveId,
      exclusions,
      saveReason,
      saveNote,
    }: {
      curveId: string;
      exclusions: DraftExclusion[];
      saveReason: SaveExclusionReason;
      saveNote: string | null;
    }) =>
      refitDoseResponseCurveApiV1DoseResponseCurvesCurveIdRefitPost(curveId, {
        exclusions: exclusions
          .filter((e) => e.idx !== null)
          .map((e) => {
            // Enrich each entry with concentration/response from the
            // captured-set lookup so the BE persists coords on the
            // excluded_points entry. Without this the next reload has
            // raw_data = active-only AND an excluded entry with null
            // coords — the chart can't reconstruct where the X marker
            // should sit. e.idx is a capturedIdx.
            const cp = editCurveCapturedByIdx.get(e.idx as number);
            return {
              idx: e.idx,
              source: e.source,
              excluded: e.excluded,
              reason: e.reason,
              note: e.note,
              concentration: e.concentration ?? cp?.concentration ?? null,
              response: e.response ?? cp?.response ?? null,
            };
          }),
        save_reason: saveReason,
        save_note: saveNote,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: DOSE_RESPONSE_KEY });
      setSaveDialogOpen(false);
      setEditMode(false);
      refitPreview.reset();
      editSession.resetToSaved();
    },
  });

  // ── Live preview wiring ────────────────────────────────────────────────────
  // Whenever the draft changes (in edit mode for the active curve), fire a
  // debounced preview request. The hook collapses bursts into a single call;
  // an `AbortController` cancels stale flights.
  const draftExcludedIndices = useMemo(
    () =>
      editSession.draft.exclusions
        .filter((e) => e.excluded && e.idx !== null)
        .map((e) => e.idx as number),
    [editSession.draft.exclusions],
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: refitPreview.requestPreview is stable across renders (useCallback); depending on editMode + editCurve.id + draftExcludedIndices is enough.
  useEffect(() => {
    if (!editMode || !editCurve) return;
    refitPreview.requestPreview(editCurve.id, draftExcludedIndices);
  }, [editMode, editCurve?.id, draftExcludedIndices]);

  // Returns the set of currently-draft-excluded captured-set indices for the
  // given curve. Outside edit mode (or for non-edit curves) this is empty —
  // the server already has the persisted exclusions, no need to round-trip
  // them on a constraint refit.
  const getExcluded = useCallback(
    (curveId: string): Set<number> => {
      if (!editMode || curveId !== editCurve?.id) return new Set();
      const ids = new Set<number>();
      for (const e of editSession.draft.exclusions) {
        if (e.excluded && e.idx !== null) ids.add(e.idx);
      }
      return ids;
    },
    [editMode, editCurve?.id, editSession.draft.exclusions],
  );

  // Seed per-curve UI from the protocol's config when provided so the
  // accordion reflects what the protocol is actually doing — a user who
  // set Top ∈ [85, 110] at the protocol level should see Range here, not
  // a misleading "Free". Editing a per-curve value sends an explicit
  // override; "Reset" clears the override and resnaps to these defaults.
  const getConstraints = useCallback(
    (curve: DoseResponseCurve): CurveConstraints =>
      constraintsMap[curve.id] ??
      defaultConstraintsFor(curve, protocolConfig, yReadoutNormalization),
    [constraintsMap, protocolConfig, yReadoutNormalization],
  );

  const callRefit = useCallback(
    (curve: DoseResponseCurve, excluded: Set<number>, constraints: CurveConstraints) => {
      // Send `override_<param>` so the backend treats this curve's settings
      // as authoritative for that param (Free included). Only the values
      // for the active mode ship — the rest go null.
      refit({
        curveId: curve.id,
        input: {
          excluded_point_indices: Array.from(excluded),
          hill_slope_constraint:
            constraints.hillSlope !== "unconstrained" ? constraints.hillSlope : null,
          override_top: true,
          top_constraint: constraints.topMode === "lock" ? constraints.topValue : null,
          top_constraint_min: constraints.topMode === "range" ? constraints.topMin : null,
          top_constraint_max: constraints.topMode === "range" ? constraints.topMax : null,
          override_bottom: true,
          bottom_constraint: constraints.bottomMode === "lock" ? constraints.bottomValue : null,
          bottom_constraint_min: constraints.bottomMode === "range" ? constraints.bottomMin : null,
          bottom_constraint_max: constraints.bottomMode === "range" ? constraints.bottomMax : null,
          override_hill: true,
          hill_slope_min: constraints.hillCustomRange ? constraints.hillMin : null,
          hill_slope_max: constraints.hillCustomRange ? constraints.hillMax : null,
        },
      });
    },
    [refit],
  );

  const handleConstraintChange = useCallback(
    (curve: DoseResponseCurve, patch: Partial<CurveConstraints>) => {
      const current = getConstraints(curve);
      const next = { ...current, ...patch };
      setConstraintsMap((prev) => ({ ...prev, [curve.id]: next }));

      if (debounceRefs.current[curve.id]) {
        clearTimeout(debounceRefs.current[curve.id]);
      }
      // Only fire refit when the active mode's required values are
      // populated and consistent — otherwise we'd ship NaN/null to the
      // backend and provoke a 500.
      if (!constraintsValid(next)) return;
      debounceRefs.current[curve.id] = setTimeout(() => {
        callRefit(curve, getExcluded(curve.id), next);
      }, 500);
    },
    [getConstraints, getExcluded, callRefit],
  );

  const handleReset = useCallback(
    (curve: DoseResponseCurve) => {
      setConstraintsMap((prev) => ({
        ...prev,
        [curve.id]: defaultConstraintsFor(curve, protocolConfig, yReadoutNormalization),
      }));
      // Reset = clear per-curve overrides, fall back to protocol's config.
      refit({ curveId: curve.id, input: { excluded_point_indices: [] } });
    },
    [refit, protocolConfig, yReadoutNormalization],
  );

  const handleClassify = useCallback(
    (curveId: string, curveClass: string) => {
      classify({ curveId, input: { curve_class: curveClass } });
    },
    [classify],
  );

  // ── Edit-mode lifecycle ───────────────────────────────────────────────────
  const handleCancelEdit = useCallback(() => {
    if (editSession.dirtyCount > 0) {
      // V1 simplicity — window.confirm is keyboard-accessible and free.
      const ok =
        typeof window === "undefined"
          ? true
          : window.confirm(
              `You have ${editSession.dirtyCount} unsaved change${editSession.dirtyCount === 1 ? "" : "s"}. Discard them?`,
            );
      if (!ok) return;
    }
    editSession.resetToSaved();
    refitPreview.reset();
    setEditMode(false);
  }, [editSession, refitPreview]);

  // ── Keyboard shortcuts (edit mode only) ────────────────────────────────────
  // Cmd/Ctrl+Z = undo, Cmd/Ctrl+Shift+Z (or Cmd/Ctrl+Y) = redo, Esc = cancel.
  // Listener attaches at the document level only while editMode is true so
  // non-editing renders never see the global handler. The textarea/input guard
  // lets the save dialog's note field handle native Cmd+Z text-editing
  // unaffected.
  useEffect(() => {
    if (!editMode) return;
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable
      ) {
        return;
      }
      const isMac = navigator.platform.toLowerCase().includes("mac");
      const ctrlOrCmd = isMac ? e.metaKey : e.ctrlKey;
      const key = e.key.toLowerCase();

      if (ctrlOrCmd && key === "z" && !e.shiftKey) {
        e.preventDefault();
        editSession.undo();
      } else if (ctrlOrCmd && ((key === "z" && e.shiftKey) || key === "y")) {
        e.preventDefault();
        editSession.redo();
      } else if (e.key === "Escape") {
        e.preventDefault();
        handleCancelEdit();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [editMode, editSession, handleCancelEdit]);

  const handleSaveSubmit = useCallback(
    ({ reason, note }: { reason: SaveExclusionReason; note: string | null }) => {
      if (!editCurve) return;
      refitCommitMutation.mutate({
        curveId: editCurve.id,
        exclusions: editSession.draft.exclusions,
        saveReason: reason,
        saveNote: note,
      });
    },
    [editCurve, editSession.draft.exclusions, refitCommitMutation],
  );

  const dirtyCount = editSession.dirtyCount;
  const isSaving = refitCommitMutation.isPending;
  const isEditing = editMode && editCurve != null;

  // The "after" fit from the preview hook, overlaid dashed on the committed
  // fit so the chemist sees before-vs-after before saving anything.
  const previewFit = useMemo(() => {
    if (!isEditing || !refitPreview.data) return null;
    return {
      top: refitPreview.data.top,
      bottom: refitPreview.data.bottom,
      fitted_value: refitPreview.data.fitted_value,
      hill_slope: refitPreview.data.hill_slope,
    };
  }, [isEditing, refitPreview.data]);

  const draftExcluded = useMemo(() => new Set(draftExcludedIndices), [draftExcludedIndices]);

  const edit: EditOverlay | undefined = isEditing
    ? {
        curveId: editCurve.id,
        draftExcluded,
        draftExcludedCount: editSession.draft.exclusions.filter((e) => e.excluded).length,
        previewFit,
        onPointClick: (_curveId, capturedIdx) => editSession.toggleExclusion(capturedIdx),
      }
    : undefined;

  return (
    <DoseResponseChartView
      curves={curves}
      plot={Plot}
      className={className}
      interactive={isInteractive}
      edit={edit}
      onClassify={isInteractive ? handleClassify : undefined}
      isClassifying={isClassifying}
      controlsSlot={
        isInteractive ? (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEditMode(true)}
              disabled={runIsLocked}
              title={runIsLocked ? "Unapprove run to edit curves" : undefined}
            >
              Edit Points
            </Button>
            {runIsLocked && (
              <Badge
                variant="outline"
                className="text-xs"
                title="Run is approved — DR curves are read-only. Unapprove the run to edit."
              >
                Locked
              </Badge>
            )}
            <CurveEditHistory
              events={editHistoryQuery.data?.events ?? []}
              isLoading={editHistoryQuery.isLoading}
            />
          </>
        ) : undefined
      }
      barSlot={
        isEditing ? (
          <div className="flex items-center gap-2 flex-wrap rounded-md border border-primary/40 bg-primary/5 px-3 py-2">
            <span className="text-sm font-medium">
              Editing — {dirtyCount} unsaved change{dirtyCount === 1 ? "" : "s"}
            </span>
            <div className="ml-auto flex items-center gap-1.5">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2"
                onClick={editSession.undo}
                disabled={!editSession.canUndo || isSaving}
                title="Undo (Cmd+Z)"
                aria-label="Undo"
              >
                <Undo2 className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2"
                onClick={editSession.redo}
                disabled={!editSession.canRedo || isSaving}
                title="Redo (Cmd+Shift+Z)"
                aria-label="Redo"
              >
                <Redo2 className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={editSession.resetToSaved}
                disabled={dirtyCount === 0 || isSaving}
                title="Reset to saved"
              >
                <RotateCcw className="mr-1 h-3.5 w-3.5" />
                Reset
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-7 px-3 text-xs"
                onClick={handleCancelEdit}
                disabled={isSaving}
              >
                Cancel
              </Button>
              <Button
                variant="default"
                size="sm"
                className="h-7 px-3 text-xs"
                onClick={() => setSaveDialogOpen(true)}
                disabled={dirtyCount === 0 || isSaving}
              >
                Save{dirtyCount > 0 ? ` ${dirtyCount}` : ""}
              </Button>
            </div>
          </div>
        ) : undefined
      }
      plotWrapper={
        isEditing
          ? (plot) => (
              <ResizablePanelGroup orientation="horizontal" className="h-[420px] rounded-md border">
                <ResizablePanel defaultSize={65} minSize={40} maxSize={80}>
                  {plot}
                </ResizablePanel>
                <ResizableHandle withHandle />
                <ResizablePanel defaultSize={35} minSize={20} maxSize={60}>
                  <div className="h-full overflow-auto p-3" aria-label="Point inventory">
                    {/* Inventory rows are keyed by capturedIdx — the same
                        domain the BE consumes, so row positions match its
                        build_points_with_exclusions ordering (concentration
                        ascending across the merged raw_data + excluded_points
                        set), NOT position-in-raw_data. */}
                    <DoseResponsePointInventory
                      rawData={editCurveCaptured.map((p) => ({
                        concentration: p.concentration,
                        response: p.response,
                      }))}
                      exclusions={editSession.draft.exclusions}
                      onToggle={editSession.toggleExclusion}
                    />
                  </div>
                </ResizablePanel>
              </ResizablePanelGroup>
            )
          : undefined
      }
      footerSlot={
        <>
          {editCurve && (
            <SaveExclusionsDialog
              open={saveDialogOpen}
              onOpenChange={setSaveDialogOpen}
              onSave={handleSaveSubmit}
              dirtyCount={dirtyCount}
              isSaving={isSaving}
            />
          )}
          {isInteractive && curves.length > 0 && (
            <div className="space-y-3">
              {curves.map((curve) => (
                <CurveControls
                  key={curve.id}
                  curve={curve}
                  excludedIndices={getExcluded(curve.id)}
                  constraints={getConstraints(curve)}
                  onConstraintChange={(patch) => handleConstraintChange(curve, patch)}
                  onReset={() => handleReset(curve)}
                  isPending={isRefitting}
                />
              ))}
            </div>
          )}
        </>
      }
    />
  );
}
