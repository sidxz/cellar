"use client";

import { memo, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Search } from "lucide-react";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { cn } from "@/shared/lib/utils";
import { stashScaffoldSearch } from "@/features/research-organization/lib/scaffold-search-handoff";

import {
  NO_SCAFFOLD_SENTINEL,
  type ScaffoldTreeResult,
} from "../types/scaffold-tree";
import type { ActivityRollupBin } from "../lib/scaffold-rollup";

type Props = {
  tree: ScaffoldTreeResult;
  /** Scaffold -> activity rollup color bin (computed once at the tree root) */
  colorBins: Map<string, ActivityRollupBin>;
  /** Minimum molecule_count for a row to appear */
  minMembers: number;
  selected: string | null;
  onSelect: (scaffoldSmiles: string) => void;
};

const BIN_COLORS: Record<ActivityRollupBin, string> = {
  active_high: "bg-emerald-500",
  active_mid: "bg-amber-400",
  weak: "bg-orange-400",
  inactive: "bg-rose-400",
};

/**
 * Path B: flat frequency-sorted list of distinct Murcko scaffolds.
 *
 * The chemist default. Each row is ONE chemotype — a scaffold SMILES that
 * is the direct Bemis-Murcko of at least `minMembers` molecules in the
 * result set. Rows sorted by molecule_count DESC so cluster heads land at
 * the top of the scan path. Phantom intermediates emitted by RDKit (where
 * molecule_count == 0) are excluded by construction — only scaffolds that
 * actually host molecules show up.
 *
 * Click a row to filter the right pane to that scaffold's direct members.
 * No expand / collapse — it's a flat list, not a tree.
 */
function ScaffoldGroupsListInner({
  tree,
  colorBins,
  minMembers,
  selected,
  onSelect,
}: Props) {
  const router = useRouter();

  const handleOpenInSearch = (e: React.MouseEvent, scaffoldSmiles: string) => {
    e.stopPropagation();
    const stashed = scaffoldSmiles === NO_SCAFFOLD_SENTINEL ? "" : scaffoldSmiles;
    stashScaffoldSearch(stashed);
    router.push("/search");
  };

  const groups = useMemo(() => {
    return tree.nodes
      .filter((n) => n.molecule_count >= minMembers)
      .sort((a, b) => {
        if (b.molecule_count !== a.molecule_count) {
          return b.molecule_count - a.molecule_count;
        }
        return a.scaffold_smiles.localeCompare(b.scaffold_smiles);
      });
  }, [tree, minMembers]);

  if (groups.length === 0) {
    return (
      <div className="p-4 text-xs text-muted-foreground">
        No chemotypes shared by ≥ {minMembers}{" "}
        {minMembers === 1 ? "molecule" : "molecules"}.
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {groups.map((g) => {
        const isBucket = g.scaffold_smiles === NO_SCAFFOLD_SENTINEL;
        const isSelected = selected === g.scaffold_smiles;
        const colorBin = colorBins.get(g.scaffold_smiles) ?? null;
        return (
          <div
            key={g.scaffold_smiles}
            data-testid={`scaffold-group-${g.scaffold_smiles}`}
            onClick={() => onSelect(g.scaffold_smiles)}
            className={cn(
              "group flex items-center gap-2 rounded px-2 py-1 cursor-pointer hover:bg-muted",
              isSelected && "bg-muted",
            )}
          >
            {isBucket ? (
              <div className="shrink-0 w-20 h-20 flex items-center justify-center rounded border border-dashed border-muted-foreground/40">
                <span className="text-xs italic text-muted-foreground">
                  no scaffold
                </span>
              </div>
            ) : (
              <StructureThumbnail
                smiles={g.scaffold_smiles}
                size={80}
                className="shrink-0 rounded border bg-background"
              />
            )}

            <span className="text-sm tabular-nums shrink-0 flex items-baseline gap-1">
              <span className="font-semibold">{g.molecule_count}</span>
              <span className="text-xs text-muted-foreground">
                {g.molecule_count === 1 ? "mol" : "mols"}
              </span>
            </span>

            {/* Loop-closer action — faintly visible at rest, brightens on
                row hover or keyboard focus. Opens /search filtered to this
                chemotype's compounds. Mirrors the same affordance on
                Hierarchy-mode rows in <ScaffoldTreeNode />. */}
            <button
              type="button"
              onClick={(e) => handleOpenInSearch(e, g.scaffold_smiles)}
              className="ml-auto opacity-30 group-hover:opacity-100 focus-visible:opacity-100 text-muted-foreground hover:text-foreground transition-opacity"
              aria-label="Find compounds with this scaffold"
              title="Find compounds with this scaffold"
            >
              <Search size={14} />
            </button>

            {colorBin && (
              <span
                aria-label={`activity ${colorBin}`}
                className={cn(
                  "h-1.5 w-6 rounded shrink-0",
                  BIN_COLORS[colorBin],
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

export const ScaffoldGroupsList = memo(ScaffoldGroupsListInner);
