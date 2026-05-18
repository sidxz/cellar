"use client";

import { useMemo, useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/shared/components/ui/resizable";
import { CardGrid } from "@/features/research-organization/components/results/card-grid";
import type { Molecule } from "@/features/chemical-registration/types";

import { useScaffoldTree } from "../hooks/use-scaffold-tree";
import { ScaffoldTreeNode } from "./scaffold-tree-node";
import { ScaffoldColorPicker } from "./scaffold-color-picker";
import { collectSubtreeMolIds, rootNodes } from "../lib/scaffold-tree-math";

type Props = {
  molecules: Molecule[];
  activityData: Record<string, Record<string, any>>;
  /** Called when a molecule tile is opened. Defaults to routing to /compounds/{id}. */
  onOpen?: (moleculeId: string) => void;
};

const DEFAULT_TREE_PCT = 30;

export function ScaffoldTreeView({ molecules, activityData, onOpen }: Props) {
  const router = useRouter();
  const moleculeIds = useMemo(() => molecules.map((m) => m.id), [molecules]);
  const { tree, isStarting, isPolling, error } = useScaffoldTree({
    moleculeIds,
  });

  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedScaffold, setSelectedScaffold] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [colorBy, setColorBy] = useState<string | null>(null);

  // Default-expand root nodes once the tree arrives.
  useEffect(() => {
    if (tree?.nodes.length) {
      const roots = rootNodes(tree).map((n) => n.scaffold_smiles);
      setExpanded(new Set(roots));
    }
  }, [tree]);

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

  const handleSelectChange = useCallback(
    (moleculeId: string, selected: boolean) => {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        if (selected) next.add(moleculeId);
        else next.delete(moleculeId);
        return next;
      });
    },
    [],
  );

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

  const filteredMolecules = useMemo(() => {
    if (!tree || selectedScaffold == null) return molecules;
    const ids = new Set(collectSubtreeMolIds(selectedScaffold, tree));
    return molecules.filter((m) => ids.has(m.id));
  }, [molecules, tree, selectedScaffold]);

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
      <div className="p-6 text-sm text-rose-600">
        Scaffold tree failed to load: {error.message}
      </div>
    );
  }

  if (isStarting || (isPolling && !tree)) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        Computing scaffold tree…
      </div>
    );
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

  const roots = rootNodes(tree);

  return (
    <ResizablePanelGroup orientation="horizontal" className="h-full">
      <ResizablePanel
        defaultSize={DEFAULT_TREE_PCT}
        minSize={20}
        maxSize={50}
      >
        <div className="flex flex-col h-full">
          <div className="p-2 border-b">
            <ScaffoldColorPicker
              protocols={protocolOptions}
              value={colorBy}
              onChange={setColorBy}
            />
          </div>
          <div className="flex-1 overflow-y-auto p-1">
            {roots.map((root) => (
              <ScaffoldTreeNode
                key={root.scaffold_smiles}
                scaffoldSmiles={root.scaffold_smiles}
                tree={tree}
                depth={0}
                expanded={expanded}
                selected={selectedScaffold}
                onToggle={handleToggle}
                onSelect={handleSelect}
                colorByProtocolId={colorBy}
                activity={activityData}
              />
            ))}
          </div>
        </div>
      </ResizablePanel>
      <ResizableHandle />
      <ResizablePanel defaultSize={100 - DEFAULT_TREE_PCT}>
        <div className="h-full overflow-auto">
          <CardGrid
            molecules={filteredMolecules}
            selectedIds={selectedIds}
            onSelectChange={handleSelectChange}
            onOpen={handleOpen}
          />
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
