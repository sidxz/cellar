import { ChevronDown, ChevronRight } from "lucide-react";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { cn } from "@/shared/lib/utils";

import {
  NO_SCAFFOLD_SENTINEL,
  type ScaffoldTreeResult,
} from "../types/scaffold-tree";
import { buildChildIndex, collectSubtreeMolIds } from "../lib/scaffold-tree-math";
import { classifyActivity, medianPic50ForMols } from "../lib/scaffold-rollup";

type Props = {
  scaffoldSmiles: string;
  tree: ScaffoldTreeResult;
  depth: number;
  expanded: Set<string>;
  selected: string | null;
  onToggle: (scaffoldSmiles: string) => void;
  onSelect: (scaffoldSmiles: string) => void;
  colorByProtocolId: string | null;
  activity: Record<string, Record<string, any>> | undefined;
};

const BIN_COLORS: Record<string, string> = {
  active_high: "bg-emerald-500",
  active_mid: "bg-amber-400",
  weak: "bg-orange-400",
  inactive: "bg-rose-400",
};

export function ScaffoldTreeNode(props: Props) {
  const {
    scaffoldSmiles,
    tree,
    depth,
    expanded,
    selected,
    onToggle,
    onSelect,
    colorByProtocolId,
    activity,
  } = props;

  const node = tree.nodes.find((n) => n.scaffold_smiles === scaffoldSmiles);
  if (!node) return null;

  const children = buildChildIndex(tree).get(scaffoldSmiles) ?? [];
  const isExpanded = expanded.has(scaffoldSmiles);
  const isSelected = selected === scaffoldSmiles;
  const isBucket = scaffoldSmiles === NO_SCAFFOLD_SENTINEL;

  let colorBin: string | null = null;
  if (colorByProtocolId && activity) {
    const ids = collectSubtreeMolIds(scaffoldSmiles, tree);
    colorBin = classifyActivity(medianPic50ForMols(ids, activity, colorByProtocolId));
  }

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

        {/* Structure thumbnail (32px) or sentinel label */}
        {isBucket ? null : (
          <StructureThumbnail smiles={scaffoldSmiles} size={32} className="shrink-0 rounded" />
        )}

        {/* Label */}
        {isBucket ? (
          <span className="text-xs italic text-muted-foreground">no scaffold</span>
        ) : (
          <span className="text-xs font-mono truncate flex-1 text-muted-foreground">
            {scaffoldSmiles}
          </span>
        )}

        {/* Molecule counts */}
        <span className="text-xs tabular-nums text-muted-foreground ml-auto shrink-0">
          {node.molecule_count === node.subtree_molecule_count
            ? node.molecule_count
            : `${node.molecule_count} · ${node.subtree_molecule_count}`}
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
              depth={depth + 1}
              expanded={expanded}
              selected={selected}
              onToggle={onToggle}
              onSelect={onSelect}
              colorByProtocolId={colorByProtocolId}
              activity={activity}
            />
          ))}
        </div>
      )}
    </div>
  );
}
