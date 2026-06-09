"use client";

import { CollectionTypeIcon } from "@/features/research-organization/components/collection/collection-type-icon";
import type { CollectionType } from "@/features/research-organization/types";
import { Badge } from "@/shared/components/ui/badge";
import type { CollectionCoverage } from "../types";

const fmt = (n: number) => n.toLocaleString("en-US");

/**
 * Compact per-collection coverage chips for dense surfaces (grid cells, list
 * rows). Each chip shows the collection-type icon + coverage percentage, with
 * the full `covered / total` in the tooltip. Overflow past `max` collapses to a
 * `+N` chip naming the hidden collections.
 */
export function CollectionCoverageChips({
  collections,
  max = 2,
}: {
  collections: CollectionCoverage[] | null | undefined;
  max?: number;
}) {
  if (!collections || collections.length === 0) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
  const shown = collections.slice(0, max);
  const hidden = collections.slice(max);
  return (
    <div className="flex flex-wrap items-center gap-1">
      {shown.map((c) => {
        const pct = c.fraction === null ? "—" : `${Math.round(c.fraction * 100)}%`;
        return (
          <Badge
            key={c.id}
            variant="secondary"
            className="gap-1 font-normal text-[10px]"
            title={`${c.name}: ${fmt(c.covered)} / ${fmt(c.total)}`}
          >
            <CollectionTypeIcon type={c.type as CollectionType} className="h-3 w-3" />
            {pct}
          </Badge>
        );
      })}
      {hidden.length > 0 && (
        <Badge
          variant="outline"
          className="font-normal text-[10px] text-muted-foreground"
          title={hidden.map((c) => c.name).join(", ")}
        >
          +{hidden.length}
        </Badge>
      )}
    </div>
  );
}
