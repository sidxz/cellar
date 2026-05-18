import { memo, useMemo } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { cn } from "@/shared/lib/utils";

import {
  NO_SCAFFOLD_SENTINEL,
  type ScaffoldTreeResult,
} from "../types/scaffold-tree";
import type { ActivityRollupBin } from "../lib/scaffold-rollup";

type Props = {
  scaffoldSmiles: string;
  tree: ScaffoldTreeResult;
  /** Parent -> children map, computed once at the tree root */
  childIndex: Map<string, string[]>;
  /** Scaffold -> activity rollup color bin, computed once at the tree root */
  colorBins: Map<string, ActivityRollupBin>;
  /**
   * Set of scaffold SMILES that pass the min-members filter. Children are
   * pruned to this set so a deep subtree below the threshold collapses cleanly.
   * If undefined, no filtering is applied.
   */
  visibleNodes?: Set<string>;
  depth: number;
  expanded: Set<string>;
  selected: string | null;
  onToggle: (scaffoldSmiles: string) => void;
  onSelect: (scaffoldSmiles: string) => void;
};

const BIN_COLORS: Record<ActivityRollupBin, string> = {
  active_high: "bg-emerald-500",
  active_mid: "bg-amber-400",
  weak: "bg-orange-400",
  inactive: "bg-rose-400",
};

function ScaffoldTreeNodeInner(props: Props) {
  const {
    scaffoldSmiles,
    tree,
    childIndex,
    colorBins,
    visibleNodes,
    depth,
    expanded,
    selected,
    onToggle,
    onSelect,
  } = props;

  // Map lookup over tree.nodes is O(N) per node — for 30+ nodes recursing,
  // that's redundant. Build a smiles->node lookup once at the root, walk down.
  const nodesBySmiles = useMemo(() => {
    const m = new Map<string, ScaffoldTreeResult["nodes"][number]>();
    for (const n of tree.nodes) m.set(n.scaffold_smiles, n);
    return m;
  }, [tree]);

  const node = nodesBySmiles.get(scaffoldSmiles);
  if (!node) return null;
  // Defensive: a parent might pass us a smiles that doesn't pass the filter.
  if (visibleNodes && !visibleNodes.has(scaffoldSmiles)) return null;

  // Filter children to visible ones so a subtree below the threshold collapses
  // without rendering any of its rows.
  const allChildren = childIndex.get(scaffoldSmiles) ?? [];
  const children = visibleNodes
    ? allChildren.filter((c) => visibleNodes.has(c))
    : allChildren;
  const isExpanded = expanded.has(scaffoldSmiles);
  const isSelected = selected === scaffoldSmiles;
  const isBucket = scaffoldSmiles === NO_SCAFFOLD_SENTINEL;
  const colorBin = colorBins.get(scaffoldSmiles) ?? null;

  return (
    <div className="flex flex-col">
      <div
        data-testid={`scaffold-node-${scaffoldSmiles}`}
        onClick={() => onSelect(scaffoldSmiles)}
        className={cn(
          "flex items-center gap-2 rounded px-2 py-1 cursor-pointer hover:bg-muted",
          isSelected && "bg-muted",
        )}
        style={{ paddingLeft: `${8 + depth * 16}px` }}
      >
        {/* Expand / collapse caret — stopPropagation prevents row select */}
        {children.length > 0 ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggle(scaffoldSmiles);
            }}
            className="shrink-0 text-muted-foreground"
            aria-label={isExpanded ? "collapse" : "expand"}
          >
            {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
        ) : (
          <span className="inline-block w-3 shrink-0" aria-hidden />
        )}

        {/* Structure thumbnail (large — chemists read structures, not SMILES) or
            sentinel placeholder. Matches the card-grid recognition pattern. */}
        {isBucket ? (
          <div className="shrink-0 w-20 h-20 flex items-center justify-center rounded border border-dashed border-muted-foreground/40">
            <span className="text-xs italic text-muted-foreground">no scaffold</span>
          </div>
        ) : (
          <StructureThumbnail
            smiles={scaffoldSmiles}
            size={80}
            className="shrink-0 rounded border bg-background"
          />
        )}

        {/* Spacer pushes the count to the right edge */}
        <span className="flex-1" aria-hidden />

        {/* Molecule counts — bold and labeled so chemists can scan cluster
            heads at a glance. "9 mols" reads faster than "9". When a node
            aggregates descendants too, append the subtree count subtly. */}
        <span className="text-sm tabular-nums shrink-0 flex items-baseline gap-1">
          <span className="font-semibold">{node.molecule_count}</span>
          <span className="text-xs text-muted-foreground">
            {node.molecule_count === 1 ? "mol" : "mols"}
            {node.molecule_count !== node.subtree_molecule_count && (
              <> · {node.subtree_molecule_count} sub</>
            )}
          </span>
        </span>

        {/* Activity color band */}
        {colorBin && (
          <span
            aria-label={`activity ${colorBin}`}
            className={cn("h-1.5 w-6 rounded shrink-0", BIN_COLORS[colorBin])}
          />
        )}
      </div>

      {/* Recursive children */}
      {isExpanded && children.length > 0 && (
        <div>
          {children.map((c) => (
            <ScaffoldTreeNode
              key={c}
              scaffoldSmiles={c}
              tree={tree}
              childIndex={childIndex}
              colorBins={colorBins}
              visibleNodes={visibleNodes}
              depth={depth + 1}
              expanded={expanded}
              selected={selected}
              onToggle={onToggle}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// Memoize — recursive children re-render only when their actual props change,
// not on unrelated parent re-renders (e.g. when a sibling subtree is selected).
export const ScaffoldTreeNode = memo(ScaffoldTreeNodeInner);
