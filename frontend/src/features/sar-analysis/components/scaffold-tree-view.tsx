"use client";

import { cancelScaffoldTreeJobApiV1ScaffoldTreeJobsJobIdCancelPost } from "@/shared/lib/api/scaffold-tree/scaffold-tree";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import type { Molecule } from "@/features/chemical-registration/types";
import { CardGrid } from "@/features/research-organization/components/results/card-grid";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/shared/components/ui/resizable";
import { cn } from "@/shared/lib/utils";

import { useCollectionScaffoldSearch } from "../hooks/use-collection-scaffold-search";
import { useScaffoldTree } from "../hooks/use-scaffold-tree";
import { collectSubtreeScaffolds } from "../lib/collect-subtree-scaffolds";
import {
  type ActivityRollupBin,
  classifyActivity,
  medianPic50ForMols,
} from "../lib/scaffold-rollup";
import { buildChildIndex, buildSubtreeMolIdMap, rootNodes } from "../lib/scaffold-tree-math";
import { useTreeSubMode } from "../lib/use-tree-sub-mode";
import type { ScaffoldTreeNode as ScaffoldTreeNodeType } from "../types/scaffold-tree";
import { NO_SCAFFOLD_SENTINEL } from "../types/scaffold-tree";
import { ScaffoldColorPicker } from "./scaffold-color-picker";
import { ScaffoldGroupsList } from "./scaffold-groups-list";
import { ScaffoldTreeNode } from "./scaffold-tree-node";

type Props = {
  molecules: Molecule[];
  activityData: Record<string, Record<string, any>>;
  /**
   * When set, the scaffold tree is computed against the FULL membership of
   * this collection on the BE (bypassing the search endpoint's 200-row
   * pagination cap). The right-pane CardGrid still uses the paginated
   * `molecules` for visual rendering. When unset, the tree falls back to
   * the visible molecule IDs (suitable for ad-hoc result sets).
   */
  collectionId?: string;
  /** Called when a molecule tile is opened. Defaults to routing to /compounds/{id}. */
  onOpen?: (moleculeId: string) => void;
};

// Shared toast id — exported so tests can reference the same constant and
// avoid silent rot if the id is ever renamed.
export const SCAFFOLD_TREE_TOAST_ID = "scaffold-tree-job";

// react-resizable-panels v4 interprets NUMBER props as pixels and STRING
// props as percentages. We want percent-based layout that scales with the
// container, so all size props below are strings.
const TREE_DEFAULT_PCT = "15";
const TREE_MIN_PCT = "12";
const TREE_MAX_PCT = "50";
const CARDS_DEFAULT_PCT = "85";

const MIN_MEMBERS_CYCLE = [1, 2, 3, 5, 10] as const;

function SubModeToggle({
  value,
  onChange,
}: {
  value: "groups" | "hierarchy";
  onChange: (next: "groups" | "hierarchy") => void;
}) {
  // Tiny segmented control. Groups (default) = flat list of distinct
  // chemotypes by frequency; Hierarchy = Schuffenhauer DAG with Path A's
  // sort + filters. Chemists scan in Groups, drill in Hierarchy.
  const base =
    "px-2 py-1 text-xs first:rounded-l-md last:rounded-r-md border-y border-r first:border-l shrink-0 transition-colors";
  return (
    <div role="group" aria-label="Scaffold view mode" className="inline-flex items-stretch text-xs">
      <button
        type="button"
        onClick={() => onChange("groups")}
        aria-pressed={value === "groups"}
        className={cn(
          base,
          value === "groups"
            ? "bg-primary text-primary-foreground border-primary"
            : "bg-background hover:bg-muted border-border",
        )}
      >
        Groups
      </button>
      <button
        type="button"
        onClick={() => onChange("hierarchy")}
        aria-pressed={value === "hierarchy"}
        className={cn(
          base,
          value === "hierarchy"
            ? "bg-primary text-primary-foreground border-primary"
            : "bg-background hover:bg-muted border-border",
        )}
      >
        Hierarchy
      </button>
    </div>
  );
}

function MinMembersPill({
  value,
  onChange,
}: {
  value: number;
  onChange: (next: number) => void;
}) {
  const cycle = () => {
    const idx = MIN_MEMBERS_CYCLE.indexOf(value as (typeof MIN_MEMBERS_CYCLE)[number]);
    const next = MIN_MEMBERS_CYCLE[(idx + 1) % MIN_MEMBERS_CYCLE.length] ?? 1;
    onChange(next);
  };
  return (
    <button
      type="button"
      onClick={cycle}
      title="Cycle minimum members threshold"
      className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded border bg-background hover:bg-muted shrink-0 tabular-nums"
    >
      <span className="text-muted-foreground">Min</span>
      <span className="font-semibold">{value}</span>
    </button>
  );
}

export function ScaffoldTreeView({ molecules, activityData, collectionId, onOpen }: Props) {
  const router = useRouter();
  const moleculeIds = useMemo(() => molecules.map((m) => m.id), [molecules]);
  // When the parent surface gave us a collection_id, prefer that — the BE will
  // expand to the full member list and we won't undercount on > 200-mol sets.
  // Otherwise (ad-hoc search results, sub-paged views) fall back to the
  // visible molecule IDs.
  const { tree, jobId, isStarting, isPolling, error } = useScaffoldTree(
    collectionId ? { collectionId } : { moleculeIds },
  );

  const { subMode, setSubMode } = useTreeSubMode();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedScaffold, setSelectedScaffold] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [colorBy, setColorBy] = useState<string | null>(null);
  const [minMembers, setMinMembers] = useState<number>(1);

  // Number of top roots to auto-expand on first arrival. Beyond this, chemists
  // expand explicitly. Keeps the initial visual scan to the cluster heads only.
  const DEFAULT_EXPAND_TOP_N = 3;

  const handleToggle = useCallback((scaffoldSmiles: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(scaffoldSmiles)) next.delete(scaffoldSmiles);
      else next.add(scaffoldSmiles);
      return next;
    });
  }, []);

  const handleSelect = useCallback((scaffoldSmiles: string) => {
    setSelectedScaffold((prev) => (prev === scaffoldSmiles ? null : scaffoldSmiles));
  }, []);

  const handleSelectChange = useCallback((moleculeId: string, selected: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (selected) next.add(moleculeId);
      else next.delete(moleculeId);
      return next;
    });
  }, []);

  const handleOpen = useCallback(
    (moleculeId: string) => {
      if (onOpen) {
        onOpen(moleculeId);
      } else {
        router.push(`/compounds/${moleculeId}`);
      }
    },
    [onOpen, router],
  );

  // Computed once per tree change. Recursive children would otherwise rebuild
  // these per node — O(N^2) work per render.
  const childIndex = useMemo(
    () => (tree ? buildChildIndex(tree) : new Map<string, string[]>()),
    [tree],
  );

  // smiles -> node lookup, built once at the root and threaded into the
  // recursive ScaffoldTreeNode children so each node skips an O(N) rebuild.
  const nodesBySmiles = useMemo(() => {
    const m = new Map<string, ScaffoldTreeNodeType>();
    if (tree) for (const n of tree.nodes) m.set(n.scaffold_smiles, n);
    return m;
  }, [tree]);

  // Every node's subtree molecule-id set, computed in ONE pass per tree.
  // Reused by both the color rollup and the in-memory subtree filter so we
  // never rebuild the node/child indexes per node (the old per-node
  // collectSubtreeMolIds call was O(N^2) and froze large collections).
  const subtreeMolIds = useMemo(
    () => (tree ? buildSubtreeMolIdMap(tree) : new Map<string, string[]>()),
    [tree],
  );

  // Pre-compute per-node activity rollup color once per (tree, colorBy,
  // activityData) change. Reads the prebuilt subtree map — no per-node DFS.
  const colorBins = useMemo(() => {
    const map = new Map<string, ActivityRollupBin>();
    if (!tree || !colorBy || !activityData) return map;
    for (const node of tree.nodes) {
      const ids = subtreeMolIds.get(node.scaffold_smiles) ?? [];
      const bin = classifyActivity(medianPic50ForMols(ids, activityData, colorBy));
      if (bin) map.set(node.scaffold_smiles, bin);
    }
    return map;
  }, [tree, colorBy, activityData, subtreeMolIds]);

  // V4 Path A: when a scaffold is selected on a collection page, fetch the
  // filtered set server-side via the new exact_match_in criterion. Avoids the
  // in-memory filter over the full collection load (which is capped at 10K).
  // When no scaffold is selected, OR when we're operating on an ad-hoc result
  // set (no collectionId), fall through to the existing in-memory path.
  const selectedScaffolds = useMemo<string[]>(() => {
    if (!tree || selectedScaffold == null) return [];
    // NO_SCAFFOLD_SENTINEL is not a real SMILES — RDKit can't parse it and
    // the BE `exact_match_in` clause silently drops unparseable inputs,
    // yielding zero rows. Acyclic mols belong to a different criterion
    // path (mode='acyclic_only'). For this bucket, fall through to the
    // in-memory filter — the acyclic set is bounded by the same 10K cap
    // as the "show all" pane and is typically <100 mols in practice.
    if (selectedScaffold === NO_SCAFFOLD_SENTINEL) return [];
    if (subMode === "groups") return [selectedScaffold];
    return collectSubtreeScaffolds(selectedScaffold, tree);
  }, [tree, selectedScaffold, subMode]);

  const serverFiltered = useCollectionScaffoldSearch({
    collectionId: collectionId ?? "",
    scaffoldSmiles: selectedScaffolds,
    enabled: Boolean(collectionId) && selectedScaffolds.length > 0,
  });

  const filteredMolecules = useMemo(() => {
    if (!tree || selectedScaffold == null) return molecules;

    // V4 Path A: server-side filtered result wins when we're on a collection
    // page AND a scaffold is selected. Use the server response directly —
    // it's the authoritative list (not clipped by the 10K parent-load cap).
    if (collectionId && selectedScaffolds.length > 0 && serverFiltered.data?.items) {
      return serverFiltered.data.items as typeof molecules;
    }

    // Fallback (ad-hoc result sets without collectionId, or while the server
    // call is in flight): in-memory filter of the already-loaded molecules.
    // In Hierarchy mode, selecting an inner node should show the whole subtree
    // (all descendant mols) — that's the SAR-pivot story. In Groups mode each
    // row IS a leaf chemotype, so we filter to its direct molecule_ids only —
    // chemists who pick "piperidine variant A" want THOSE compounds, not also
    // every other scaffold that happens to be a substructure.
    if (subMode === "groups") {
      const directIds = new Set(nodesBySmiles.get(selectedScaffold)?.molecule_ids ?? []);
      return molecules.filter((m) => directIds.has(m.id));
    }
    const ids = new Set(subtreeMolIds.get(selectedScaffold) ?? []);
    return molecules.filter((m) => ids.has(m.id));
  }, [
    molecules,
    tree,
    selectedScaffold,
    subMode,
    collectionId,
    selectedScaffolds,
    serverFiltered.data,
    nodesBySmiles,
    subtreeMolIds,
  ]);

  // Path A: visible nodes after the min-members filter. A node is visible
  // when its subtree_molecule_count >= minMembers. Applies recursively in
  // the tree — both as a root-level filter and as an inner-node guard.
  const visibleNodes = useMemo(() => {
    const s = new Set<string>();
    if (!tree) return s;
    for (const n of tree.nodes) {
      if (n.subtree_molecule_count >= minMembers) s.add(n.scaffold_smiles);
    }
    return s;
  }, [tree, minMembers]);

  // Path A: root-level node sort. Cluster heads (largest subtree_count) first;
  // ties by direct molecule_count, then alphabetical for determinism. Also drops
  // phantom-parent roots — nodes RDKit emitted as intermediates that nobody's
  // molecule actually belongs to (molecule_count=0) AND that don't aggregate
  // anything meaningful (subtree_count <= 1). Those are visual noise.
  const sortedRoots = useMemo(() => {
    if (!tree) return [];
    const roots = rootNodes(tree)
      .filter(
        (r) =>
          visibleNodes.has(r.scaffold_smiles) &&
          // hide phantom-parent roots: no direct members + trivial subtree
          !(r.molecule_count === 0 && r.subtree_molecule_count <= 1),
      )
      .sort((a, b) => {
        if (b.subtree_molecule_count !== a.subtree_molecule_count) {
          return b.subtree_molecule_count - a.subtree_molecule_count;
        }
        if (b.molecule_count !== a.molecule_count) {
          return b.molecule_count - a.molecule_count;
        }
        return a.scaffold_smiles.localeCompare(b.scaffold_smiles);
      });
    return roots;
  }, [tree, visibleNodes]);

  // Path A: default-expand only the top-N roots once the tree arrives.
  // Previously we expanded ALL roots — visually overwhelming for diverse sets.
  useEffect(() => {
    if (sortedRoots.length > 0) {
      setExpanded(
        new Set(sortedRoots.slice(0, DEFAULT_EXPAND_TOP_N).map((n) => n.scaffold_smiles)),
      );
    }
    // Intentionally only re-runs when the tree identity changes; user expansion
    // state survives min-members filter tweaks.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tree]);

  // Sonner toast for long-running async compute. After 3 seconds in a
  // pending state, show a loading toast with a Cancel action. Dismiss on
  // terminal status (tree arrives or error fires). The inline caption
  // below stays as a backstop for screens where toasts may be off.
  //
  // toastScheduledRef: only dismiss when a toast was actually shown — avoids
  // calling toast.dismiss on every idle render (e.g. the initial mount).
  const toastScheduledRef = useRef(false);
  useEffect(() => {
    const isWorking = isStarting || (isPolling && !tree);
    if (!isWorking) {
      if (toastScheduledRef.current) {
        toast.dismiss(SCAFFOLD_TREE_TOAST_ID);
        toastScheduledRef.current = false;
      }
      return;
    }
    const timer = window.setTimeout(() => {
      // Same-tick race guard: if the component transitioned to idle in the
      // same tick that the timer fired, skip the toast entirely.
      if (!isWorking) return;
      toastScheduledRef.current = true;
      toast.loading("Computing scaffold tree…", {
        id: SCAFFOLD_TREE_TOAST_ID,
        duration: Number.POSITIVE_INFINITY,
        action: {
          label: "Cancel",
          onClick: () => {
            if (jobId) {
              void cancelScaffoldTreeJobApiV1ScaffoldTreeJobsJobIdCancelPost(jobId);
            }
            toast.dismiss(SCAFFOLD_TREE_TOAST_ID);
            // id makes the success toast idempotent — rapid double-clicks
            // replace rather than stack a second notification.
            toast.success("Scaffold tree cancelled", { id: SCAFFOLD_TREE_TOAST_ID });
            toastScheduledRef.current = false;
          },
        },
      });
    }, 3000);
    return () => {
      window.clearTimeout(timer);
    };
  }, [isStarting, isPolling, tree, jobId]);

  const protocolOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const perMol of Object.values(activityData ?? {})) {
      for (const protocolId of Object.keys(perMol ?? {})) {
        if (!seen.has(protocolId)) {
          seen.set(protocolId, protocolId);
        }
      }
    }
    return [...seen.entries()].map(([id, name]) => ({ id, name }));
  }, [activityData]);

  if (error) {
    return (
      <div className="p-6 text-sm text-rose-600">Scaffold tree failed to load: {error.message}</div>
    );
  }

  if (isStarting || (isPolling && !tree)) {
    return <div className="p-6 text-sm text-muted-foreground">Computing scaffold tree…</div>;
  }

  if (!tree || tree.nodes.length === 0) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        {molecules.length === 0
          ? "Add molecules to see the scaffold tree."
          : "These molecules are all acyclic — no scaffolds to display."}
      </div>
    );
  }

  // The group needs an explicit height because `h-full` cascades to 0 inside
  // the parent's `flex flex-col gap-3/4` (no defined height). Claim the full
  // viewport below the page chrome (title row + collection header strip +
  // gaps ≈ 14rem); min-h floor keeps short screens usable.
  return (
    <ResizablePanelGroup
      orientation="horizontal"
      className="h-[calc(100vh-14rem)] min-h-[480px] rounded-md border"
    >
      <ResizablePanel defaultSize={TREE_DEFAULT_PCT} minSize={TREE_MIN_PCT} maxSize={TREE_MAX_PCT}>
        <div className="flex flex-col h-full">
          <div className="p-2 border-b flex flex-wrap items-center gap-2">
            <SubModeToggle value={subMode} onChange={setSubMode} />
            <MinMembersPill value={minMembers} onChange={setMinMembers} />
            <ScaffoldColorPicker
              protocols={protocolOptions}
              value={colorBy}
              onChange={setColorBy}
            />
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto p-1">
            {subMode === "groups" ? (
              <ScaffoldGroupsList
                tree={tree}
                colorBins={colorBins}
                minMembers={minMembers}
                selected={selectedScaffold}
                onSelect={handleSelect}
              />
            ) : sortedRoots.length === 0 ? (
              <div className="p-4 text-xs text-muted-foreground">
                No scaffolds match the current filter.
                {minMembers > 1 && (
                  <>
                    {" "}
                    Try{" "}
                    <button type="button" className="underline" onClick={() => setMinMembers(1)}>
                      Min mols = 1
                    </button>
                    .
                  </>
                )}
              </div>
            ) : (
              sortedRoots.map((root) => (
                <ScaffoldTreeNode
                  key={root.scaffold_smiles}
                  scaffoldSmiles={root.scaffold_smiles}
                  nodesBySmiles={nodesBySmiles}
                  childIndex={childIndex}
                  colorBins={colorBins}
                  visibleNodes={visibleNodes}
                  depth={0}
                  expanded={expanded}
                  selected={selectedScaffold}
                  onToggle={handleToggle}
                  onSelect={handleSelect}
                />
              ))
            )}
          </div>
        </div>
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel defaultSize={CARDS_DEFAULT_PCT}>
        {/* CardGrid must own a DEFINITE-height scroll container or its
            virtualizer can't window — a percentage-height (`h-full`) chain
            through a flex-stretched ResizablePanel resolves to content height,
            so the grid renders every molecule (5000 RDKit thumbnails) and
            freezes the tab. Give it the same explicit height the grid view
            uses; the panel group is sized to exactly this. */}
        <CardGrid
          molecules={filteredMolecules}
          selectedIds={selectedIds}
          onSelectChange={handleSelectChange}
          onOpen={handleOpen}
          height="calc(100vh - 14rem)"
        />
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
