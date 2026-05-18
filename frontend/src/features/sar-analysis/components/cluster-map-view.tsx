"use client";

import { useCallback, useMemo, useState } from "react";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/shared/components/ui/resizable";
import type { Molecule } from "@/features/chemical-registration/types";

import { useUmapCluster } from "../hooks/use-umap-cluster";
import { usePickerConfig } from "../lib/use-picker-config";
import { useColorMode } from "../lib/use-color-mode";
import type { ColorOption } from "../lib/cluster-palette";
import { ClusterScatter } from "./cluster-scatter";
import { ClusterToolbar } from "./cluster-toolbar";
import { ClusterSelectionPane } from "./cluster-selection-pane";
import { ColorModePicker, type ProtocolOption } from "./color-mode-picker";
import { SaveSelectionDialog } from "./save-selection-dialog";

// ---------------------------------------------------------------------------
// react-resizable-panels v4: STRING = percent, NUMBER = pixels.
// Always use strings for percent-based layout. See feedback_react_resizable_panels_v4_pixels.md
// ---------------------------------------------------------------------------
const SCATTER_DEFAULT_PCT = "70%";
const SCATTER_MIN_PCT = "50%";
const SCATTER_MAX_PCT = "80%";
const PANE_DEFAULT_PCT = "30%";
const PANE_MIN_PCT = "20%";
const PANE_MAX_PCT = "50%";

// Minimum molecule count before UMAP is attempted. Below this the 2-D
// projection is degenerate and the hook would fail on the BE anyway.
const MIN_MOLS_FOR_UMAP = 10;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build a mol-id → pIC50 lookup for a given protocol from the activityData
 * shape used by the research-org search layer.
 *
 * activityData: Record<moleculeId, Record<protocolId, { pic50?: number | null }>>
 * Returns null for mols with no data for the requested protocol.
 */
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
    const perMol = activityData[mol.id];
    const entry = perMol?.[protocolId];
    // Prefer pic50; fall back to null so the scatter renders transparent.
    out[mol.id] = entry?.pic50 ?? entry?.pIC50 ?? null;
  }
  return out;
}

/**
 * Build a mol-id → scaffold SMILES (or null) lookup from molecules.
 * The Molecule type carries `bemis_murcko_smiles` set by the BE at
 * registration time; an empty string means "acyclic — no scaffold".
 */
function buildScaffoldByMol(molecules: Molecule[]): Record<string, string | null> {
  const out: Record<string, string | null> = {};
  for (const mol of molecules) {
    const s = (mol as any).bemis_murcko_smiles;
    out[mol.id] = typeof s === "string" && s.length > 0 ? s : null;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

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
  // --- Picker & color URL state ---
  // Size-adaptive default N: ~10% of the compound set, clamped to [5, 50].
  // For a 22-mol collection the default is 5 (not the old hardcoded 50).
  const { picker, n, threshold, setPicker, setN, setThreshold } =
    usePickerConfig({ collectionSize: molecules.length });
  const { mode: colorMode, protocolId: colorProtocolId, setMode: setColorMode } =
    useColorMode({
      defaultMode: defaultColorProtocolId ? "activity" : "cluster",
    });

  // --- Lasso + subset state ---
  // Plotly's onSelected gives us the selected molecule IDs directly (more
  // reliable than reconstructing the polygon + running point-in-polygon).
  const [lassoedIds, setLassoedIds] = useState<Set<string>>(new Set());
  // When user hits Diversify with a lasso active, snapshot those IDs into
  // pendingSubset to scope re-computation to the selection.
  const [pendingSubset, setPendingSubset] = useState<string[] | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  // --- Committed picker config ---
  // Toolbar (`picker`, `n`, `threshold` from URL state) holds the PENDING
  // config the chemist is composing. The map only re-fetches when the chemist
  // hits Diversify, which commits pending → committed below. Auto-fetch on
  // every keystroke would burn server compute + cache slots; the explicit
  // Diversify trigger matches the brainstormed interaction model.
  const [committedPicker, setCommittedPicker] = useState(picker);
  const [committedN, setCommittedN] = useState(n);
  const [committedThreshold, setCommittedThreshold] = useState(threshold);
  const isDirty =
    committedPicker !== picker ||
    (picker === "maxmin" && committedN !== n) ||
    committedThreshold !== threshold;

  // --- All mol IDs (for the hook) ---
  const allIds = useMemo(() => molecules.map((m) => m.id), [molecules]);

  // --- UMAP hook ---
  // API contract: exactly one of collection_id / molecule_ids. Send collection_id
  // for full-collection compute (server expands membership); send molecule_ids
  // for /search or for a lasso-scoped subset.
  const useCollectionSource = !pendingSubset && Boolean(collectionId);
  const { result, loading, error, cancel } = useUmapCluster({
    collectionId: useCollectionSource ? collectionId : undefined,
    moleculeIds: useCollectionSource ? undefined : (pendingSubset ?? allIds),
    picker: committedPicker,
    n: committedN,
    threshold: committedThreshold,
    enabled: molecules.length >= MIN_MOLS_FOR_UMAP,
  });

  // --- Derived selection state ---

  // Representatives from the cluster result.
  const repIds: Set<string> = useMemo(
    () => new Set((result?.representatives ?? []).map((r) => r.moleculeId)),
    [result],
  );

  // Selection precedence: an active lasso wins over the auto-Diversify picks.
  // No lasso → show the picks. Lasso around empty space → still show the picks
  // (chemist can retry; they didn't lose context).
  const selectedIds: Set<string> = useMemo(() => {
    if (lassoedIds.size > 0) return lassoedIds;
    return repIds;
  }, [lassoedIds, repIds]);

  const selectedMolecules = useMemo(
    () => molecules.filter((m) => selectedIds.has(m.id)),
    [molecules, selectedIds],
  );

  // --- Color derivations for ClusterScatter ---

  // activityData is not threaded in at this component level — color-by-activity
  // uses the protocol's pic50 values from the molecules themselves. For now
  // we build a null map; callers that want live activity colors should extend
  // ClusterMapViewProps with an `activityData` prop (see V3 follow-up plan).
  const activityPic50 = useMemo(
    () => buildActivityPic50(molecules, {}, colorProtocolId),
    [molecules, colorProtocolId],
  );

  const scaffoldByMol = useMemo(
    () => buildScaffoldByMol(molecules),
    [molecules],
  );

  // Chemist-readable hover label: prefer "reg_number · name" → reg_number → name
  // → short id. UUIDs are never shown.
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
    if (colorMode === "activity" && colorProtocolId) {
      return { mode: "activity", protocolId: colorProtocolId };
    }
    if (colorMode === "scaffold") return { mode: "scaffold" };
    if (colorMode === "none") return { mode: "none" };
    return { mode: "cluster" };
  }, [colorMode, colorProtocolId]);

  // --- Handlers ---

  const handleLassoSelected = useCallback(
    (ids: string[] | null) => {
      setLassoedIds(new Set(ids ?? []));
    },
    [],
  );

  const handlePointClick = useCallback((_moleculeId: string) => {
    // Future: open molecule detail panel. No-op for now.
  }, []);

  const handleDiversify = useCallback(() => {
    // Commit pending picker config → committed (triggers refetch).
    setCommittedPicker(picker);
    setCommittedN(n);
    setCommittedThreshold(threshold);
    // Snapshot lasso into pendingSubset to re-scope computation; clear the
    // lasso so the next interaction starts fresh.
    setPendingSubset(lassoedIds.size > 0 ? [...lassoedIds] : null);
    setLassoedIds(new Set());
  }, [lassoedIds, picker, n, threshold]);

  const handleSave = useCallback(() => {
    if (selectedIds.size === 0) return;
    setPreviewOpen(true);
  }, [selectedIds]);

  const defaultName = `Diversify-${selectedIds.size} from ${sourceLabel}`;

  // --- Not enough molecules ---
  if (molecules.length < MIN_MOLS_FOR_UMAP) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        Need at least {MIN_MOLS_FOR_UMAP} molecules to compute a cluster map.
        This set has {molecules.length}.
      </div>
    );
  }

  // --- Error state ---
  if (error) {
    return (
      <div className="p-6 text-sm text-rose-600">
        Cluster map failed: {error}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-14rem)] min-h-[480px]">
      {/* Toolbar — picker controls + color-by + action buttons */}
      <ClusterToolbar
        picker={picker}
        n={n}
        threshold={threshold}
        selectedCount={selectedIds.size}
        onPickerChange={setPicker}
        onNChange={setN}
        onThresholdChange={setThreshold}
        onDiversify={handleDiversify}
        diversifyDirty={isDirty}
        onSave={handleSave}
        colorPicker={
          <ColorModePicker
            mode={colorMode}
            protocolId={colorProtocolId}
            protocols={protocols}
            onChange={setColorMode}
          />
        }
      />

      {/* Status row — disambiguates picks vs chemotype clusters so the chemist
          isn't surprised when N=2 shows 8 colors on the map. */}
      {result && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b bg-muted/30 px-3 py-1.5 text-xs text-muted-foreground">
          <span>
            <span className="font-medium text-foreground">
              {result.clusterCount}
            </span>{" "}
            chemotype{result.clusterCount === 1 ? "" : "s"} (Butina @{" "}
            {committedThreshold.toFixed(2)})
          </span>
          <span className="text-border">·</span>
          <span>
            <span className="font-medium text-foreground">
              {result.representatives.length}
            </span>{" "}
            representative
            {result.representatives.length === 1 ? "" : "s"} (
            {committedPicker === "maxmin"
              ? `MaxMin N=${committedN}`
              : "Butina medoids"}
            )
          </span>
          <span className="text-border">·</span>
          <span>
            {lassoedIds.size > 0
              ? `Lasso: ${lassoedIds.size} selected`
              : "Drag on the map to lasso a region"}
          </span>
        </div>
      )}

      {/* Split pane — scatter left, selection pane right */}
      <ResizablePanelGroup
        orientation="horizontal"
        className="flex-1 rounded-md border"
      >
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
          <ClusterSelectionPane
            allMolecules={molecules}
            selectedIds={selectedIds}
          />
        </ResizablePanel>
      </ResizablePanelGroup>

      {/* Save-as-collection dialog */}
      <SaveSelectionDialog
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        onSave={async (args) => {
          await onSaveCollection(args);
          setPreviewOpen(false);
        }}
        selectedMolecules={selectedMolecules}
        defaultName={defaultName}
        projects={projects}
        defaultProjectId={defaultProjectId}
      />
    </div>
  );
}
