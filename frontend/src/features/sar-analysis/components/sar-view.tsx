"use client";

import type { Molecule } from "@/features/chemical-registration/types";
import { useCreateCollection } from "@/features/research-organization/hooks/use-collections";
import type { AggregationMode } from "@/features/research-organization/lib/use-aggregation-mode";
import { Button } from "@/shared/components/ui/button";
import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import { showError } from "@/shared/lib/toast";
import { useState } from "react";
import { channelFromColorSpec, useActivityProjection } from "../hooks/use-activity-projection";
import { useDecompositionRun } from "../hooks/use-decomposition-run";
import { useSaveDecompositionCollection } from "../hooks/use-save-decomposition-collection";
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

type SaveRow = { id: string; label: string };

type SaveIntent =
  | { mode: "selection"; rows: SaveRow[] }
  | { mode: "all"; count: number; filter?: Record<string, unknown>; projectionId?: string | null };

export function SarView(props: SarViewProps) {
  // Prefer the collection (full membership, server-expanded) over the loaded page.
  const moleculeIds = props.molecules.map((m) => m.id);
  const source = props.collectionId ? { collectionId: props.collectionId } : { moleculeIds };

  const createCollection = useCreateCollection();
  const saveCollection = useSaveDecompositionCollection();
  const [core, setCore] = useState<string | null>(() => readSarHandoff()?.coreSmiles ?? null);
  const [saveIntent, setSaveIntent] = useState<SaveIntent | null>(null);
  const [colorSpec, setColorSpec] = useState<SarColorSpec | null>(null);
  const [aggMode, setAggMode] = useState<AggregationMode>("latest");
  const [sub, setSub] = useState<"table" | "heatmap">("table");

  const run = useDecompositionRun({ ...source, coreSmiles: core });
  const channel = colorSpec ? channelFromColorSpec(colorSpec, aggMode) : null;
  const projection = useActivityProjection({ ...source, channel });

  const ready = run.status === "ready" && run.runId != null;
  const projectionReady = projection.status === "ready" && projection.projectionId != null;
  const heatmapEnabled = ready && run.labels.length >= 2 && colorSpec != null && projectionReady;
  const showHeatmap = sub === "heatmap" && heatmapEnabled;

  return (
    <div className="flex flex-col gap-3">
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
        matchedCount={run.counts?.matched}
        totalCount={run.counts?.total}
      />

      {(run.isStarting || run.isPolling) && (
        <p className="text-xs text-muted-foreground">Decomposing…</p>
      )}
      {colorSpec != null && (projection.isStarting || projection.isPolling) && (
        <p className="text-xs text-muted-foreground">Computing activity…</p>
      )}
      {run.error && (
        <p className="text-xs text-destructive">Decomposition failed: {run.error.message}</p>
      )}

      {ready && (
        <div
          role="group"
          aria-label="SAR result view"
          className="inline-flex items-center gap-1 self-start rounded-md border border-input p-0.5"
        >
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
            className="h-7 gap-1.5 px-2"
            aria-label="Heatmap view"
            aria-pressed={showHeatmap}
            disabled={!heatmapEnabled}
            title={!heatmapEnabled ? "Pick an activity and a core with ≥2 R-positions" : undefined}
            onClick={() => setSub("heatmap")}
          >
            <span className="text-xs">Heatmap</span>
          </Button>
        </div>
      )}

      {ready && run.runId && (
        <p className="text-xs text-muted-foreground">
          {run.counts?.matched ?? 0} matched of {run.counts?.total ?? 0} (
          {run.counts?.unmatched ?? 0} unmatched)
        </p>
      )}

      {ready &&
        run.runId &&
        (showHeatmap && colorSpec && projection.projectionId ? (
          <RGroupHeatmap
            runId={run.runId}
            projectionId={projection.projectionId}
            labels={run.labels}
            colorSpec={colorSpec}
          />
        ) : (
          <RGroupTable
            runId={run.runId}
            projectionId={projectionReady ? projection.projectionId : null}
            labels={run.labels}
            colorSpec={colorSpec}
            matchedCount={run.counts?.matched}
            onSaveSelection={(rows) => setSaveIntent({ mode: "selection", rows })}
            onSaveAll={({ count, filter, projectionId }) =>
              setSaveIntent({ mode: "all", count, filter, projectionId })
            }
          />
        ))}

      <SaveSelectionDialog
        open={saveIntent != null}
        onOpenChange={(o) => !o && setSaveIntent(null)}
        onSave={async ({ name, projectId }) => {
          if (saveIntent?.mode === "all") {
            try {
              await saveCollection.saveAll({
                runId: run.runId as string,
                name,
                projectId,
                filter: saveIntent.filter,
                projectionId: saveIntent.projectionId,
              });
              setSaveIntent(null);
            } catch {
              showError("Could not save the collection. Please retry.");
            }
            return;
          }
          const selectedIds =
            saveIntent?.mode === "selection" ? saveIntent.rows.map((r) => r.id) : [];
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
            setSaveIntent(null);
          } catch {
            showError("Collection created, but adding compounds failed. Please retry.");
          }
        }}
        count={
          saveIntent?.mode === "all"
            ? saveIntent.count
            : saveIntent?.mode === "selection"
              ? saveIntent.rows.length
              : 0
        }
        preview={
          saveIntent?.mode === "selection"
            ? saveIntent.rows.map((r) => ({ id: r.id, reg_number: r.label, name: r.label }))
            : undefined
        }
        defaultName={`SAR selection from ${props.sourceLabel}`}
        projects={props.projects}
        defaultProjectId={props.defaultProjectId}
      />
    </div>
  );
}
