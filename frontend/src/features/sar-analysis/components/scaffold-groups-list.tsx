"use client";

import { memo, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useVirtualizer } from "@tanstack/react-virtual";
import { Search } from "lucide-react";

import { StructureThumbnail } from "@/shared/components/chemistry";
import { cn } from "@/shared/lib/utils";
import { stashScaffoldSearch } from "@/features/research-organization/lib/scaffold-search-handoff";

import {
  NO_SCAFFOLD_SENTINEL,
  type ScaffoldTreeNode,
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

// Each row is an 80px thumbnail + py-1 padding ≈ 88px tall. Used both as the
// virtualizer's size estimate and for windowing math.
const ROW_HEIGHT = 88;

// Soft cap on the number of chemotype rows shown before the chemist opts into
// the full list. A 5K-mol collection produces ~2.6K distinct scaffolds — a flat
// scan that long is unusable, and the frequency sort already floats the cluster
// heads to the top. Virtualization keeps even the full list cheap, so this is a
// usability guard, not a perf one. Cycle the Min-members pill to prune instead.
const DEFAULT_CAP = 250;

/**
 * Path B: flat frequency-sorted, virtualized list of distinct Murcko scaffolds.
 *
 * The chemist default. Each row is ONE chemotype — a scaffold SMILES that
 * is the direct Bemis-Murcko of at least `minMembers` molecules in the
 * result set. Rows sorted by molecule_count DESC so cluster heads land at
 * the top of the scan path. Phantom intermediates emitted by RDKit (where
 * molecule_count == 0) are excluded by construction — only scaffolds that
 * actually host molecules show up.
 *
 * The list is virtualized: only on-screen rows mount, so we never fire
 * thousands of synchronous RDKit thumbnail renders at once (that froze the
 * tab on large collections). Above `DEFAULT_CAP` rows we render the top slice
 * with a "show all" affordance.
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
  const parentRef = useRef<HTMLDivElement | null>(null);
  const [showAll, setShowAll] = useState(false);
  // jsdom (and only jsdom) reports clientHeight 0 — the one case where we
  // render every row non-virtualized for tests. In a real browser this stays
  // false so the first paint never mass-mounts hundreds of RDKit thumbnails.
  const [noLayout, setNoLayout] = useState(false);

  useEffect(() => {
    const el = parentRef.current;
    if (!el) return;
    const measure = () => setNoLayout(el.clientHeight === 0);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

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

  const capped = !showAll && groups.length > DEFAULT_CAP;
  const visible = useMemo(
    () => (capped ? groups.slice(0, DEFAULT_CAP) : groups),
    [groups, capped],
  );

  const virtualizer = useVirtualizer({
    count: visible.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 6,
  });

  // Fall back to rendering every visible row ONLY in jsdom (no layout). Gating
  // on virtualItems.length === 0 instead would also fire on the first real
  // browser render (ref not attached yet) and mass-mount up to DEFAULT_CAP
  // thumbnails before windowing engages.
  const virtualItems = virtualizer.getVirtualItems();
  const useFallback = noLayout && visible.length > 0;

  const renderRow = (g: ScaffoldTreeNode) => {
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

        {/* Loop-closer action — faintly visible at rest, brightens on row
            hover or keyboard focus. Opens /search filtered to this
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
            className={cn("h-1.5 w-6 rounded shrink-0", BIN_COLORS[colorBin])}
          />
        )}
      </div>
    );
  };

  if (groups.length === 0) {
    return (
      <div className="p-4 text-xs text-muted-foreground">
        No chemotypes shared by ≥ {minMembers}{" "}
        {minMembers === 1 ? "molecule" : "molecules"}.
      </div>
    );
  }

  return (
    <div ref={parentRef} className="h-full overflow-y-auto">
      <div className="px-2 py-1 text-xs text-muted-foreground tabular-nums">
        {groups.length} {groups.length === 1 ? "chemotype" : "chemotypes"}
        {capped && <> · showing top {DEFAULT_CAP}</>}
      </div>

      {useFallback ? (
        <div className="flex flex-col">{visible.map((g) => renderRow(g))}</div>
      ) : (
        <div
          style={{
            height: `${virtualizer.getTotalSize()}px`,
            position: "relative",
            width: "100%",
          }}
        >
          {virtualItems.map((vRow) => {
            const g = visible[vRow.index];
            return (
              <div
                key={g.scaffold_smiles}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: `${vRow.size}px`,
                  transform: `translateY(${vRow.start}px)`,
                }}
              >
                {renderRow(g)}
              </div>
            );
          })}
        </div>
      )}

      {capped && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="w-full px-2 py-2 text-xs text-primary hover:underline"
        >
          Show all {groups.length} chemotypes
        </button>
      )}
    </div>
  );
}

export const ScaffoldGroupsList = memo(ScaffoldGroupsListInner);
