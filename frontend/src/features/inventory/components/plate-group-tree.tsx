"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import type { CustomNodeElementProps, RawNodeDatum } from "react-d3-tree";
import type { PlateGroupNode, PlateGroupTree } from "../hooks/use-plate-groups";
import { groupTypeColor, legendEntries, truncateLabel } from "./plate-group-tree-utils";

// react-d3-tree touches window/d3 at module scope — client-only.
const Tree = dynamic(() => import("react-d3-tree"), { ssr: false });

export interface PlateGroupTreeViewProps {
  tree: PlateGroupTree;
  selectedId: string | null;
  onSelect: (node: PlateGroupNode) => void;
}

interface GroupDatum extends RawNodeDatum {
  attributes: { id: string; plate_count: number; group_type: string };
  children?: GroupDatum[];
}

function toDatum(node: PlateGroupNode): GroupDatum {
  return {
    name: node.name,
    attributes: {
      id: node.id,
      plate_count: node.plate_count,
      group_type: node.group_type ?? "",
    },
    children: (node.children ?? []).map(toDatum),
  };
}

/** Index every node by id so a d3 click (which hands back the datum, not our
 *  domain node) can be resolved to the original PlateGroupNode. */
function indexNodes(roots: PlateGroupNode[]): Map<string, PlateGroupNode> {
  const map = new Map<string, PlateGroupNode>();
  const walk = (n: PlateGroupNode) => {
    map.set(n.id, n);
    (n.children ?? []).forEach(walk);
  };
  roots.forEach(walk);
  return map;
}

export function PlateGroupTreeView({ tree, selectedId, onSelect }: PlateGroupTreeViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [translate, setTranslate] = useState({ x: 80, y: 200 });

  // Memoize so the datum reference is stable across selection re-renders.
  // react-d3-tree regenerates its tree (resetting expand/collapse state)
  // whenever the `data` reference changes; keying on `tree` means the tree
  // only resets when the underlying data actually refetches — not when the
  // user merely clicks a node to select it.
  const nodesById = useMemo(() => indexNodes(tree.roots), [tree]);

  // Legend only earns its space when there's more than one distinct color on
  // the canvas (a lone type, or an all-untyped tree, both render as a single
  // uniform color — nothing to key against).
  const legend = useMemo(() => legendEntries(tree.roots), [tree]);

  // react-d3-tree wants exactly one root; wrap multiple roots in a synthetic
  // org node (clickable-noop) so a forest still renders.
  const data = useMemo<GroupDatum>(
    () =>
      tree.roots.length === 1
        ? toDatum(tree.roots[0])
        : {
            name: "All groups",
            attributes: { id: "__root__", plate_count: 0, group_type: "" },
            children: tree.roots.map(toDatum),
          },
    [tree],
  );

  useEffect(() => {
    // Center vertically once the container has a real size.
    const el = containerRef.current;
    if (el && el.clientHeight > 0) {
      setTranslate({ x: 80, y: el.clientHeight / 2 });
    }
  }, []);

  const renderNode = ({ nodeDatum, toggleNode }: CustomNodeElementProps) => {
    const attrs = nodeDatum.attributes as unknown as GroupDatum["attributes"];
    const isSynthetic = attrs.id === "__root__";
    const isSelected = attrs.id === selectedId;

    // isSynthetic is never selected (the "__root__" wrapper is never handed
    // to onSelect below), so the stroke ring only ever activates on real nodes.
    const handleSelect = () => {
      if (isSynthetic) return;
      const node = nodesById.get(attrs.id);
      if (node) onSelect(node);
    };

    return (
      <g>
        <circle
          r={10}
          className={`${isSynthetic ? "fill-muted " : ""}${isSelected ? "stroke-primary" : "stroke-border"}`}
          style={isSynthetic ? undefined : { fill: groupTypeColor(attrs.group_type) }}
          strokeWidth={isSelected ? 3 : 1}
          role="button"
          tabIndex={0}
          onClick={(e) => {
            e.stopPropagation();
            toggleNode();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              e.stopPropagation();
              toggleNode();
            }
          }}
          data-testid={`tree-toggle-${attrs.id}`}
        />
        {/* No role="button" here: biome's useSemanticElements flags role+children
            on a non-void element (its only fix, a real <button>, isn't valid SVG).
            tabIndex + onClick/onKeyDown still make it fully keyboard-operable. */}
        <g
          className="cursor-pointer"
          tabIndex={0}
          onClick={handleSelect}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              handleSelect();
            }
          }}
          data-testid={`tree-node-${attrs.id}`}
        >
          <title>{nodeDatum.name}</title>
          <text x={16} dy={-2} className="fill-foreground text-sm font-medium" strokeWidth={0}>
            {truncateLabel(nodeDatum.name)}
          </text>
          <text x={16} dy={14} className="fill-muted-foreground text-xs" strokeWidth={0}>
            {attrs.plate_count} plate{attrs.plate_count === 1 ? "" : "s"}
            {attrs.group_type ? ` · ${attrs.group_type}` : ""}
          </text>
        </g>
      </g>
    );
  };

  return (
    <div className="space-y-2">
      {legend.length > 1 && (
        <div className="flex flex-wrap gap-3" data-testid="plate-group-tree-legend">
          {legend.map((entry) => (
            <span
              key={entry.label}
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
            >
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: entry.color }} />
              {entry.label}
            </span>
          ))}
        </div>
      )}
      <div
        ref={containerRef}
        className="h-[calc(100vh-12rem)] min-h-[420px] w-full rounded-md border bg-card"
        data-testid="plate-group-tree"
      >
        <Tree
          data={data}
          orientation="horizontal"
          translate={translate}
          collapsible
          zoomable
          separation={{ siblings: 0.6, nonSiblings: 0.8 }}
          nodeSize={{ x: 260, y: 56 }}
          renderCustomNodeElement={renderNode}
          pathFunc="step"
        />
      </div>
    </div>
  );
}
