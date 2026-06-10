import { ChevronDown, ChevronRight, FlaskConical, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { memo } from "react";

import { stashScaffoldSearch } from "@/features/research-organization/lib/scaffold-search-handoff";
import { StructureThumbnail } from "@/shared/components/chemistry";
import { cn } from "@/shared/lib/utils";

import { stashSarHandoff } from "../lib/sar-handoff";
import type { ActivityRollupBin } from "../lib/scaffold-rollup";
import {
  NO_SCAFFOLD_SENTINEL,
  type ScaffoldTreeNode as ScaffoldTreeNodeData,
} from "../types/scaffold-tree";

type Props = {
  scaffoldSmiles: string;
  /** smiles -> node lookup, built once at the tree root (not per node) */
  nodesBySmiles: Map<string, ScaffoldTreeNodeData>;
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
  /** When provided, "Open in SAR" routes to /collections/{id}?view=sar */
  collectionId?: string;
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
    nodesBySmiles,
    childIndex,
    colorBins,
    visibleNodes,
    depth,
    expanded,
    selected,
    onToggle,
    onSelect,
    collectionId,
  } = props;

  const router = useRouter();

  const handleOpenInSearch = (e: React.MouseEvent) => {
    e.stopPropagation();
    const stashed = scaffoldSmiles === NO_SCAFFOLD_SENTINEL ? "" : scaffoldSmiles;
    stashScaffoldSearch(stashed);
    router.push("/search");
  };

  const handleOpenInSar = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (scaffoldSmiles === NO_SCAFFOLD_SENTINEL) return; // no core to seed SAR
    const currentNode = nodesBySmiles.get(scaffoldSmiles);
    if (!currentNode) return;
    stashSarHandoff({ coreSmiles: scaffoldSmiles, moleculeIds: currentNode.molecule_ids });
    router.push(collectionId ? `/collections/${collectionId}?view=sar` : "?view=sar");
  };

  const node = nodesBySmiles.get(scaffoldSmiles);
  if (!node) return null;
  // Defensive: a parent might pass us a smiles that doesn't pass the filter.
  if (visibleNodes && !visibleNodes.has(scaffoldSmiles)) return null;

  // Filter children to visible ones so a subtree below the threshold collapses
  // without rendering any of its rows.
  const allChildren = childIndex.get(scaffoldSmiles) ?? [];
  const children = visibleNodes ? allChildren.filter((c) => visibleNodes.has(c)) : allChildren;
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
          "group flex items-center gap-2 rounded px-2 py-1 cursor-pointer hover:bg-muted",
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

        {/* Molecule counts sit adjacent to the thumbnail — chemist's natural
            pair (structure → "how many?"). Bold + labeled so cluster heads
            scan at a glance. When a node aggregates descendants too, append
            the subtree count subtly. */}
        <span className="text-sm tabular-nums shrink-0 flex items-baseline gap-1">
          <span className="font-semibold">{node.molecule_count}</span>
          <span className="text-xs text-muted-foreground">
            {node.molecule_count === 1 ? "mol" : "mols"}
            {node.molecule_count !== node.subtree_molecule_count && (
              <> · {node.subtree_molecule_count} sub</>
            )}
          </span>
        </span>

        {/* Action buttons — faintly visible at rest; brighten on row hover or
            keyboard focus. Search opens /search filtered to this scaffold's
            compounds; SAR seeds the SAR view with this scaffold as core. */}
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={handleOpenInSearch}
            className="opacity-30 group-hover:opacity-100 focus-visible:opacity-100 text-muted-foreground hover:text-foreground transition-opacity"
            aria-label="Find compounds with this scaffold"
            title="Find compounds with this scaffold"
          >
            <Search size={14} />
          </button>
          {scaffoldSmiles !== NO_SCAFFOLD_SENTINEL && (
            <button
              type="button"
              onClick={handleOpenInSar}
              className="opacity-30 group-hover:opacity-100 focus-visible:opacity-100 text-muted-foreground hover:text-foreground transition-opacity"
              aria-label="Analyse SAR for this scaffold"
              title="Analyse SAR for this scaffold"
            >
              <FlaskConical size={14} />
            </button>
          )}
        </div>

        {/* Activity color band — pinned to the right edge as a status glyph */}
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
              nodesBySmiles={nodesBySmiles}
              childIndex={childIndex}
              colorBins={colorBins}
              visibleNodes={visibleNodes}
              depth={depth + 1}
              expanded={expanded}
              selected={selected}
              onToggle={onToggle}
              onSelect={onSelect}
              collectionId={collectionId}
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
