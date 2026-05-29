"use client";

import { useMemo, useRef, useState, useEffect } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { FolderOpen } from "lucide-react";
import { MoleculeCard } from "./molecule-card";
import type { Molecule } from "@/features/chemical-registration/types";

export interface CardGridProps {
  molecules: Molecule[];
  selectedIds: Set<string>;
  onSelectChange: (moleculeId: string, selected: boolean) => void;
  onOpen: (moleculeId: string) => void;
  isLoading?: boolean;
  /** Min tile width in px (responsive grid uses auto-fill, minmax(min,1fr)). */
  minTileWidth?: number;
  /** Approximate tile height in px (used for windowing math). */
  rowHeight?: number;
  /** Scroll container height — defaults to "100%" (fills parent). Callers
   *  embedding CardGrid directly under a block-flow parent (no defined height)
   *  MUST supply a height (e.g. "calc(100vh - 14rem)") or wrap it in a sized
   *  container, otherwise the grid collapses to 0. */
  height?: string;
  /** Optional protocol test counts keyed by molecule ID. Passed to each card. */
  testCounts?: Record<string, number>;
}

function CardSkeleton() {
  return (
    <div
      data-testid="card-skeleton"
      className="aspect-[3/4] animate-pulse rounded-lg border bg-muted/30"
    />
  );
}

export function CardGrid({
  molecules,
  selectedIds,
  onSelectChange,
  onOpen,
  isLoading = false,
  minTileWidth = 220,
  rowHeight = 290,
  height = "100%",
  testCounts,
}: CardGridProps) {
  const parentRef = useRef<HTMLDivElement | null>(null);
  const [columnCount, setColumnCount] = useState(1);
  // Whether the scroll container has real layout. In jsdom (and only there)
  // clientWidth/Height are 0 — that's the ONLY case where we render every row
  // non-virtualized. In a real browser this stays false, so we never mass-mount
  // the full set on the first paint (see useFallback below).
  const [noLayout, setNoLayout] = useState(false);

  useEffect(() => {
    const el = parentRef.current;
    if (!el) return;
    const measure = () => {
      const width = el.clientWidth;
      // In jsdom clientWidth is 0 — fall back to 1 column so all items render.
      const cols = width > 0 ? Math.max(1, Math.floor(width / minTileWidth)) : 1;
      setColumnCount(cols);
      setNoLayout(width === 0 && el.clientHeight === 0);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [minTileWidth]);

  const rowCount = Math.ceil(molecules.length / columnCount);
  const rows = useMemo(() => {
    const out: Molecule[][] = [];
    for (let i = 0; i < rowCount; i++) {
      out.push(molecules.slice(i * columnCount, (i + 1) * columnCount));
    }
    return out;
  }, [molecules, rowCount, columnCount]);

  const virtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 2,
  });

  // In jsdom, getVirtualItems() is empty because there is no scroll-container
  // height to intersect against. Fall back to rendering all rows so tests can
  // assert on tile content without needing a real browser layout engine.
  //
  // CRITICAL: gate the fallback on `noLayout` (jsdom), NOT on
  // `virtualItems.length === 0`. The latter is also true on the FIRST real
  // browser render (parentRef isn't attached yet), which would mass-mount
  // every card — 5000 RDKit renders — and freeze the tab before windowing
  // engages. In a browser the virtualizer fills in on the next frame.
  const virtualItems = virtualizer.getVirtualItems();
  const useFallback = noLayout && rows.length > 0;

  // Always render the scroll container with parentRef attached so the
  // ResizeObserver effect can measure its width on first render (even when
  // isLoading=true). Without this the ref is null when the effect runs and
  // columnCount stays at 1 until a remount.
  return (
    <div ref={parentRef} style={{ height, overflow: "auto" }} className="p-1">
      {isLoading ? (
        <div
          className="grid gap-3"
          style={{
            gridTemplateColumns: `repeat(auto-fill, minmax(${minTileWidth}px, 1fr))`,
          }}
        >
          {Array.from({ length: 12 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      ) : !molecules.length ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
          <FolderOpen className="h-10 w-10 text-muted-foreground/40" />
          <p className="mt-3 text-sm text-muted-foreground">
            No molecules to display.
          </p>
        </div>
      ) : useFallback ? (
        <>
          {rows.map((row, rowIdx) => (
            <div
              key={rowIdx}
              style={{
                gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))`,
              }}
              className="grid gap-3 mb-3"
            >
              {row.map((m) => (
                <MoleculeCard
                  key={m.id}
                  molecule={m}
                  selected={selectedIds.has(m.id)}
                  onSelectChange={onSelectChange}
                  onOpen={onOpen}
                  protocolCount={testCounts?.[m.id]}
                />
              ))}
            </div>
          ))}
        </>
      ) : (
        <div
          style={{
            height: `${virtualizer.getTotalSize()}px`,
            position: "relative",
            width: "100%",
          }}
        >
          {virtualItems.map((vRow) => {
            const row = rows[vRow.index];
            return (
              <div
                key={vRow.key}
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  width: "100%",
                  height: `${vRow.size}px`,
                  transform: `translateY(${vRow.start}px)`,
                }}
                className="grid gap-3"
              >
                <div
                  style={{
                    gridTemplateColumns: `repeat(${columnCount}, minmax(0, 1fr))`,
                  }}
                  className="grid gap-3"
                >
                  {row.map((m) => (
                    <MoleculeCard
                      key={m.id}
                      molecule={m}
                      selected={selectedIds.has(m.id)}
                      onSelectChange={onSelectChange}
                      onOpen={onOpen}
                      protocolCount={testCounts?.[m.id]}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
