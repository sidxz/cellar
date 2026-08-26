"use client";

import { CHART_COLORS } from "@/shared/lib/chart-colors";
import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";
import type { CustomNodeElementProps, RawNodeDatum } from "react-d3-tree";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { useStorageLocations } from "../hooks/use-storage-locations";
import { PlateGroupCard } from "./plate-group-card";
import { legendEntries, stateColor, subtreePlateCount } from "./plate-group-tree-utils";

// react-d3-tree touches window/d3 at module scope — client-only.
const Tree = dynamic(() => import("react-d3-tree"), { ssr: false });

export interface PlateGroupTreeViewProps {
  /** The one root group shown at a time (legacy: one library per view). */
  root: PlateGroupNode;
  selectedId: string | null;
  onSelect: (node: PlateGroupNode) => void;
  onRequestLoan: (node: PlateGroupNode) => void;
}

interface GroupDatum extends RawNodeDatum {
  attributes: { id: string };
  children?: GroupDatum[];
}

const NODE_SIZE = { x: 380, y: 300 };
const CIRCLE_R = 25;
const ROOT_R = 30;

function toDatum(node: PlateGroupNode): GroupDatum {
  return {
    name: node.name,
    attributes: { id: node.id },
    children: (node.children ?? []).map(toDatum),
  };
}

function indexNodes(root: PlateGroupNode): Map<string, PlateGroupNode> {
  const map = new Map<string, PlateGroupNode>();
  const walk = (n: PlateGroupNode) => {
    map.set(n.id, n);
    (n.children ?? []).forEach(walk);
  };
  walk(root);
  return map;
}

export function PlateGroupTreeView({
  root,
  selectedId,
  onSelect,
  onRequestLoan,
}: PlateGroupTreeViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [translate, setTranslate] = useState({ x: 400, y: 90 });
  const { data: locations } = useStorageLocations();
  const locationName = (id: string | null | undefined) =>
    id ? (locations?.find((l) => l.id === id)?.name ?? null) : null;

  // Memoize on the root: react-d3-tree resets expand/collapse whenever `data`
  // changes identity, so selection re-renders must not rebuild it.
  const nodesById = useMemo(() => indexNodes(root), [root]);
  const data = useMemo<GroupDatum>(() => toDatum(root), [root]);
  const legend = useMemo(() => legendEntries([root]), [root]);

  useEffect(() => {
    const el = containerRef.current;
    if (el && el.clientWidth > 0) setTranslate({ x: el.clientWidth / 2, y: 90 });
  }, []);

  const renderNode = ({ nodeDatum, toggleNode, hierarchyPointNode }: CustomNodeElementProps) => {
    const id = (nodeDatum.attributes as unknown as GroupDatum["attributes"]).id;
    const node = nodesById.get(id);
    if (!node) return <g />;
    const isRoot = hierarchyPointNode.depth === 0;
    const r = isRoot ? ROOT_R : CIRCLE_R;
    const fill = isRoot ? CHART_COLORS.primary : stateColor(node.state);
    return (
      <g>
        <circle
          r={r}
          style={{ fill }}
          className={id === selectedId ? "stroke-primary" : "stroke-border"}
          strokeWidth={id === selectedId ? 3 : 1}
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
          data-testid={`tree-toggle-${id}`}
        />
        {isRoot ? (
          <foreignObject x={36} y={-28} width={300} height={70}>
            <div>
              <button
                type="button"
                onClick={() => onSelect(node)}
                className="block text-left text-lg font-semibold"
              >
                {node.name}
              </button>
              <div className="text-sm text-muted-foreground">
                {subtreePlateCount(node)} plates in this library
              </div>
            </div>
          </foreignObject>
        ) : (
          <foreignObject x={r + 8} y={-20} width={300} height={200}>
            <PlateGroupCard
              node={node}
              locationName={locationName(node.storage_location_id)}
              subtreePlates={subtreePlateCount(node)}
              selected={id === selectedId}
              onSelect={() => onSelect(node)}
              onRequestLoan={() => onRequestLoan(node)}
            />
          </foreignObject>
        )}
      </g>
    );
  };

  return (
    // Chrome above this box measures ~260px at 1600×900 (top nav + PageHeader +
    // tabs) — 16.25rem, not the old 12rem, per docs/backlog/plate-groups-tree-viewport-overflow-baseline.md.
    <div className="flex h-[calc(100vh-16.25rem)] min-h-[480px] flex-col gap-2">
      {legend.states.length + legend.types.length > 0 ? (
        <div
          className="flex shrink-0 flex-wrap gap-x-6 gap-y-1"
          data-testid="plate-group-tree-legend"
        >
          <LegendRow title="State" entries={legend.states} />
          <LegendRow title="Type" entries={legend.types} />
        </div>
      ) : null}
      <div
        ref={containerRef}
        className="min-h-0 w-full flex-1 rounded-md border bg-card"
        data-testid="plate-group-tree"
      >
        <Tree
          data={data}
          orientation="vertical"
          pathFunc="elbow"
          translate={translate}
          initialDepth={5}
          zoom={0.8}
          scaleExtent={{ min: 0.2, max: 1.5 }}
          separation={{ siblings: 1, nonSiblings: 1.5 }}
          collapsible
          zoomable
          nodeSize={NODE_SIZE}
          renderCustomNodeElement={renderNode}
        />
      </div>
    </div>
  );
}

function LegendRow({
  title,
  entries,
}: { title: string; entries: { label: string; color: string }[] }) {
  if (entries.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      <span className="font-medium">{title}</span>
      {entries.map((e) => (
        <span key={e.label} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: e.color }} />
          {e.label}
        </span>
      ))}
    </div>
  );
}
