"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { useCreateCollection } from "@/features/research-organization/hooks/use-collections";
import type { AggregationMode } from "@/features/research-organization/lib/use-aggregation-mode";
import { Button } from "@/shared/components/ui/button";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showError } from "@/shared/lib/toast";
import { cn } from "@/shared/lib/utils";
import { useEffect, useState } from "react";
import { useRGroupDecomposition } from "../hooks/use-rgroup-decomposition";
import { useSarActivity } from "../hooks/use-sar-activity";
import type { SarColorSpec } from "../lib/sar-color-spec";
import { readSarHandoff } from "../lib/sar-handoff";
import { RGroupColorControl } from "./rgroup-color-control";
import { RGroupCorePicker } from "./rgroup-core-picker";
import { RGroupHeatmap } from "./rgroup-heatmap";
import { RGroupTable } from "./rgroup-table";
import { SaveSelectionDialog } from "./save-selection-dialog";

export interface SarViewProps {
  molecules: Molecule[];
  collectionId?: string;
  projects: { id: string; name: string }[];
  defaultProjectId: string | null;
  sourceLabel: string;
}

/**
 * R-group SAR view: a core picker, a decomposition table keyed off the chosen
 * core, and a "save selection → new collection" path that mirrors the cluster
 * view's create-then-bulk-add flow.
 *
 * B5 additions:
 *   - `RGroupColorControl` — protocol + readout picker + aggregation rule.
 *     Renders above the result area so the chemist can pre-pick an activity
 *     before decomposing; it is always visible (not gated on a result).
 *   - `useSarActivity` — fetches activity for the loaded molecules whenever a
 *     `colorSpec` is set; passes the result into both the table and heatmap.
 *   - Sub-toggle (Table / Heatmap) — shown once a decomposition result exists.
 *     The Heatmap button is disabled when there are fewer than 2 R-positions or
 *     no colorSpec (title explains the requirement). Switching to `heatmap`
 *     while those guards are false falls back silently to `table`.
 */
export function SarView(props: SarViewProps) {
  const moleculeIds = props.molecules.map((m) => m.id);
  const decompose = useRGroupDecomposition();
  const createCollection = useCreateCollection();
  const [core, setCore] = useState<string | null>(() => readSarHandoff()?.coreSmiles ?? null);
  const [saveIds, setSaveIds] = useState<string[] | null>(null);

  // B5 state ----------------------------------------------------------------
  const [colorSpec, setColorSpec] = useState<SarColorSpec | null>(null);
  const [aggMode, setAggMode] = useState<AggregationMode>("latest");
  const [sub, setSub] = useState<"table" | "heatmap">("table");

  // Re-run decomposition whenever the chosen core changes.
  // NOTE (v1 limitation): decomposes the currently-loaded `molecules` (the
  // visible page from the host). For collections larger than one page this
  // analyses the loaded subset; full-member decomposition is a follow-up.
  // biome-ignore lint/correctness/useExhaustiveDependencies: re-run only when the core or the source collection changes; `moleculeIds`/`decompose` would re-fire on every render (fresh array/mutation identity) — they're read from the latest closure, not tracked.
  useEffect(() => {
    if (!core) return;
    decompose.mutate({ moleculeIds, coreSmiles: core });
  }, [core, props.collectionId]);

  // Activity fetch — wired by colorSpec; returns {} when no spec is set.
  const { activityByMolecule } = useSarActivity({
    moleculeIds,
    colorSpec,
    aggregationMode: aggMode,
  });

  const result = decompose.data;

  // Heatmap is only valid with ≥2 R-positions and an active colorSpec.
  const heatmapEnabled = result != null && result.rgroup_labels.length >= 2 && colorSpec != null;

  // If the current result drops below the heatmap threshold (e.g. a new
  // decomposition with only 1 R-group), silently fall back to table rather
  // than rendering a broken heatmap.
  const showHeatmap = sub === "heatmap" && heatmapEnabled;

  return (
    <div className="flex flex-col gap-3">
      {/* Activity color-by control — always visible so the chemist can
          pre-pick a protocol before choosing a core. */}
      <RGroupColorControl
        projectIds={undefined}
        value={colorSpec}
        onChange={setColorSpec}
        aggregationMode={aggMode}
        onAggregationChange={setAggMode}
      />

      <RGroupCorePicker
        collectionId={props.collectionId}
        moleculeIds={moleculeIds}
        coreSmiles={core}
        onCoreChange={setCore}
        matchedCount={result?.assignments.length}
        totalCount={result ? result.assignments.length + result.unmatched_ids.length : undefined}
      />

      {decompose.isPending && <p className="text-xs text-muted-foreground">Decomposing…</p>}

      {/* Sub-toggle — only shown when a decomposition result is available. */}
      {result && (
        <fieldset className="inline-flex items-center gap-1 self-start rounded-md border border-input p-0.5">
          <Button
            type="button"
            variant={!showHeatmap ? "default" : "ghost"}
            size="sm"
            className="h-7 gap-1.5 px-2"
            aria-label="Table view"
            aria-pressed={!showHeatmap}
            onClick={() => setSub("table")}
          >
            <span className="text-xs">Table</span>
          </Button>
          <Button
            type="button"
            variant={showHeatmap ? "default" : "ghost"}
            size="sm"
            className={cn("h-7 gap-1.5 px-2")}
            aria-label="Heatmap view"
            aria-pressed={showHeatmap}
            disabled={!heatmapEnabled}
            title={!heatmapEnabled ? "Pick an activity and a core with ≥2 R-positions" : undefined}
            onClick={() => setSub("heatmap")}
          >
            <span className="text-xs">Heatmap</span>
          </Button>
        </fieldset>
      )}

      {/* Result area */}
      {result &&
        (showHeatmap ? (
          <RGroupHeatmap
            decomposition={result}
            activityByMolecule={activityByMolecule}
            colorSpec={colorSpec}
            molecules={props.molecules}
          />
        ) : (
          <RGroupTable
            decomposition={result}
            molecules={props.molecules}
            onSaveSelection={setSaveIds}
            colorSpec={colorSpec}
            activityByMolecule={activityByMolecule}
          />
        ))}

      <SaveSelectionDialog
        open={saveIds != null}
        onOpenChange={(o) => !o && setSaveIds(null)}
        onSave={async ({ name, projectId, moleculeIds: selectedIds }) => {
          // create errors are surfaced by useCreateCollection's own onError toast
          const created = await new Promise<{ id: string }>((resolve, reject) =>
            createCollection.mutate(
              { name, project_id: projectId },
              { onSuccess: (c) => resolve(c as { id: string }), onError: (err) => reject(err) },
            ),
          );
          try {
            if (selectedIds.length > 0) {
              await customInstance({
                url: `${API_V1}/collections/${created.id}/molecules`,
                method: "POST",
                data: { references: selectedIds.map((id) => ({ value: id, ref_type: "uuid" })) },
              });
            }
            setSaveIds(null);
          } catch {
            // collection was created but adding compounds failed — keep the dialog
            // open so the user can retry, and tell them why.
            showError("Collection created, but adding compounds failed. Please retry.");
          }
        }}
        selectedMolecules={props.molecules.filter((m) => saveIds?.includes(m.id))}
        defaultName={`SAR selection from ${props.sourceLabel}`}
        projects={props.projects}
        defaultProjectId={props.defaultProjectId}
      />
    </div>
  );
}
