"use client";

import { useCallback, useMemo, useState } from "react";

import type { Molecule } from "@/features/chemical-registration/types";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/shared/components/ui/resizable";

import { useCherrypickBasket } from "../hooks/use-cherrypick-basket";
import { useRegionDiversePick } from "../hooks/use-region-diverse-pick";
import { useUmapCluster } from "../hooks/use-umap-cluster";
import type { ColorOption } from "../lib/cluster-palette";
import { useColorMode } from "../lib/use-color-mode";
import { usePickerConfig } from "../lib/use-picker-config";
import { ClusterBasketBar } from "./cluster-basket-bar";
import { ClusterScatter } from "./cluster-scatter";
import { ClusterSelectionPane } from "./cluster-selection-pane";
import { ClusterToolbar } from "./cluster-toolbar";
import { ColorModePicker, type ProtocolOption } from "./color-mode-picker";
import { RegionActionBar } from "./region-action-bar";
import { SaveSelectionDialog } from "./save-selection-dialog";

// react-resizable-panels v4: STRING = percent, NUMBER = pixels.
const SCATTER_DEFAULT_PCT = "70%";
const SCATTER_MIN_PCT = "50%";
const SCATTER_MAX_PCT = "80%";
const PANE_DEFAULT_PCT = "30%";
const PANE_MIN_PCT = "20%";
const PANE_MAX_PCT = "50%";

const MIN_MOLS_FOR_UMAP = 10;
const DEFAULT_REGION_N = 12;

export interface ClusterMapViewProps {
  molecules: Molecule[];
  collectionId?: string;
  protocols: ProtocolOption[];
  defaultColorProtocolId: string | null;
  onSaveCollection: (args: {
    name: string;
    projectId: string | null;
    moleculeIds: string[];
  }) => Promise<void>;
  projects: { id: string; name: string }[];
  defaultProjectId: string | null;
  sourceLabel: string;
}

function buildActivityPic50(
  molecules: Molecule[],
  activityData: Record<string, Record<string, any>>,
  protocolId: string | null,
): Record<string, number | null> {
  const out: Record<string, number | null> = {};
  for (const mol of molecules) {
    if (!protocolId) {
      out[mol.id] = null;
      continue;
    }
    const entry = activityData[mol.id]?.[protocolId];
    out[mol.id] = entry?.pic50 ?? entry?.pIC50 ?? null;
  }
  return out;
}

function buildScaffoldByMol(molecules: Molecule[]): Record<string, string | null> {
  const out: Record<string, string | null> = {};
  for (const mol of molecules) {
    const s = (mol as any).bemis_murcko_smiles;
    out[mol.id] = typeof s === "string" && s.length > 0 ? s : null;
  }
  return out;
}

export function ClusterMapView({
  molecules,
  collectionId,
  protocols,
  defaultColorProtocolId,
  onSaveCollection,
  projects,
  defaultProjectId,
  sourceLabel,
}: ClusterMapViewProps) {
  const { picker, n, threshold, setPicker, setN, setThreshold } = usePickerConfig({
    collectionSize: molecules.length,
  });
  const {
    mode: colorMode,
    protocolId: colorProtocolId,
    setMode: setColorMode,
  } = useColorMode({
    defaultMode: defaultColorProtocolId ? "activity" : "cluster",
  });

  // Lasso region (transient).
  const [lassoedIds, setLassoedIds] = useState<Set<string>>(new Set());
  const [regionN, setRegionN] = useState(DEFAULT_REGION_N);
  const [saveOpen, setSaveOpen] = useState(false);

  // Committed picker config — the map only recomputes on Diversify.
  const [committedPicker, setCommittedPicker] = useState(picker);
  const [committedN, setCommittedN] = useState(n);
  const [committedThreshold, setCommittedThreshold] = useState(threshold);
  const isDirty =
    committedPicker !== picker ||
    (picker === "maxmin" && committedN !== n) ||
    committedThreshold !== threshold;

  const allIds = useMemo(() => molecules.map((m) => m.id), [molecules]);

  // --- Map UMAP (must be called BEFORE useRegionDiversePick for the test's
  //     mock.calls[0] ordering). Diversify is decoupled from the lasso: the
  //     map always computes over the whole collection / set.
  const { result, loading, error, cancel } = useUmapCluster({
    collectionId: collectionId ?? undefined,
    moleculeIds: collectionId ? undefined : allIds,
    picker: committedPicker,
    n: committedN,
    threshold: committedThreshold,
    enabled: molecules.length >= MIN_MOLS_FOR_UMAP,
  });

  // --- Cherry-pick basket (persistent) + region diverse-pick (on-demand).
  const basket = useCherrypickBasket(collectionId);
  const region = useRegionDiversePick();

  const repIds: Set<string> = useMemo(
    () => new Set((result?.representatives ?? []).map((r) => r.moleculeId)),
    [result],
  );

  // --- Color derivations.
  const activityPic50 = useMemo(
    () => buildActivityPic50(molecules, {}, colorProtocolId),
    [molecules, colorProtocolId],
  );
  const scaffoldByMol = useMemo(() => buildScaffoldByMol(molecules), [molecules]);

  const labelByMolId = useMemo(() => {
    const map: Record<string, string> = {};
    for (const m of molecules) {
      const reg = (m as { reg_number?: string | null }).reg_number ?? null;
      const name = (m as { name?: string | null }).name ?? null;
      if (reg && name) map[m.id] = `${reg} · ${name}`;
      else if (reg) map[m.id] = reg;
      else if (name) map[m.id] = name;
      else map[m.id] = m.id.slice(0, 8);
    }
    return map;
  }, [molecules]);

  const colorOption: ColorOption = useMemo(() => {
    if (colorMode === "activity" && colorProtocolId)
      return { mode: "activity", protocolId: colorProtocolId };
    if (colorMode === "scaffold") return { mode: "scaffold" };
    if (colorMode === "none") return { mode: "none" };
    return { mode: "cluster" };
  }, [colorMode, colorProtocolId]);

  // --- Handlers.
  const handleLassoSelected = useCallback(
    (ids: string[] | null) => {
      setLassoedIds(new Set(ids ?? []));
      // When the lasso clears (double-click deselect / empty drag), also drop
      // any region-pick candidates — otherwise the violet stars stay stuck on
      // the map with no RegionActionBar left to clear them.
      if (!ids || ids.length === 0) region.reset();
    },
    [region.reset],
  );

  const handlePointClick = useCallback((_moleculeId: string) => {
    // Future: open molecule detail panel.
  }, []);

  const handleDiversify = useCallback(() => {
    setCommittedPicker(picker);
    setCommittedN(n);
    setCommittedThreshold(threshold);
  }, [picker, n, threshold]);

  const handlePickDiverse = useCallback(() => {
    if (lassoedIds.size > 0) region.pick([...lassoedIds], regionN);
  }, [lassoedIds, regionN, region.pick]);

  const handleAddPicks = useCallback(() => {
    basket.addMany([...region.pickedIds]);
    region.reset();
  }, [basket.addMany, region.pickedIds, region.reset]);

  const handleAddAll = useCallback(() => {
    basket.addMany([...lassoedIds]);
  }, [basket.addMany, lassoedIds]);

  const handleRemoveRegion = useCallback(() => {
    basket.removeMany([...lassoedIds]);
  }, [basket.removeMany, lassoedIds]);

  const handleClearRegion = useCallback(() => {
    setLassoedIds(new Set());
    region.reset();
  }, [region.reset]);

  const handleAddRepPicks = useCallback(() => {
    basket.addMany([...repIds]);
  }, [basket.addMany, repIds]);

  const handleSave = useCallback(() => {
    if (basket.size > 0) setSaveOpen(true);
  }, [basket.size]);

  const basketMolecules = useMemo(
    () => molecules.filter((m) => basket.ids.has(m.id)),
    [molecules, basket.ids],
  );
  const defaultName = `cherrypick-${basket.size} from ${sourceLabel}`;

  if (molecules.length < MIN_MOLS_FOR_UMAP) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        Need at least {MIN_MOLS_FOR_UMAP} molecules to compute a cluster map. This set has{" "}
        {molecules.length}.
      </div>
    );
  }

  if (error) {
    return <div className="p-6 text-sm text-rose-600">Cluster map failed: {error}</div>;
  }

  return (
    <div className="flex flex-col h-[calc(100vh-14rem)] min-h-[480px]">
      <ClusterToolbar
        picker={picker}
        n={n}
        threshold={threshold}
        onPickerChange={setPicker}
        onNChange={setN}
        onThresholdChange={setThreshold}
        onDiversify={handleDiversify}
        diversifyDirty={isDirty}
        colorPicker={
          <ColorModePicker
            mode={colorMode}
            protocolId={colorProtocolId}
            protocols={protocols}
            onChange={setColorMode}
          />
        }
      />

      <ClusterBasketBar
        count={basket.size}
        repCount={repIds.size}
        onAddRepPicks={handleAddRepPicks}
        onSave={handleSave}
        onClear={basket.clear}
      />

      {result && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b bg-muted/30 px-3 py-1.5 text-xs text-muted-foreground">
          <span>
            <span className="font-medium text-foreground">{result.clusterCount}</span> chemotype
            {result.clusterCount === 1 ? "" : "s"} (Butina @ {committedThreshold.toFixed(2)})
          </span>
          <span className="text-border">·</span>
          <span>
            <span className="font-medium text-foreground">{result.representatives.length}</span>{" "}
            representative{result.representatives.length === 1 ? "" : "s"} (
            {committedPicker === "maxmin" ? `MaxMin N=${committedN}` : "Butina medoids"})
          </span>
          <span className="text-border">·</span>
          {lassoedIds.size > 0 ? (
            <RegionActionBar
              regionCount={lassoedIds.size}
              n={regionN}
              onNChange={setRegionN}
              onPickDiverse={handlePickDiverse}
              picking={region.loading}
              pickCount={region.pickedIds.size}
              onAddPicks={handleAddPicks}
              onAddAll={handleAddAll}
              onRemove={handleRemoveRegion}
              onClear={handleClearRegion}
            />
          ) : (
            <span>Drag on the map to lasso a region</span>
          )}
        </div>
      )}

      <ResizablePanelGroup orientation="horizontal" className="flex-1 rounded-md border">
        <ResizablePanel
          defaultSize={SCATTER_DEFAULT_PCT}
          minSize={SCATTER_MIN_PCT}
          maxSize={SCATTER_MAX_PCT}
        >
          <div className="h-full relative">
            {loading && (
              <div className="absolute inset-0 flex items-center justify-center bg-background/60 z-10 text-sm text-muted-foreground">
                <div className="flex flex-col items-center gap-2">
                  <span>Computing cluster map…</span>
                  <button
                    type="button"
                    onClick={cancel}
                    className="text-xs underline text-muted-foreground"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
            {result && (
              <ClusterScatter
                points={result.points}
                clusters={result.clusters}
                representatives={result.representatives}
                colorMode={colorOption}
                activityPic50={activityPic50}
                scaffoldByMol={scaffoldByMol}
                labelByMolId={labelByMolId}
                lassoedIds={lassoedIds}
                basketIds={basket.ids}
                regionPickIds={region.pickedIds}
                onSelected={handleLassoSelected}
                onPointClick={handlePointClick}
              />
            )}
            {!loading && !result && (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                No cluster data available.
              </div>
            )}
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        <ResizablePanel
          defaultSize={PANE_DEFAULT_PCT}
          minSize={PANE_MIN_PCT}
          maxSize={PANE_MAX_PCT}
        >
          <ClusterSelectionPane allMolecules={molecules} basketIds={basket.ids} />
        </ResizablePanel>
      </ResizablePanelGroup>

      <SaveSelectionDialog
        open={saveOpen}
        onOpenChange={setSaveOpen}
        onSave={async (args) => {
          await onSaveCollection(args);
          setSaveOpen(false);
        }}
        selectedMolecules={basketMolecules}
        defaultName={defaultName}
        projects={projects}
        defaultProjectId={defaultProjectId}
      />
    </div>
  );
}
