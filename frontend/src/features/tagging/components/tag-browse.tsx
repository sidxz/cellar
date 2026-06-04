"use client";

import { TagFilter, type TagFilterValue } from "@/features/tagging/components/tag-filter";
import { type TaggedEntity, useTagEntities } from "@/features/tagging/hooks/use-tag-entities";
import { PageHeader } from "@/shared/components/page-header";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

// Verified against backend tag_browse_repository.py (entity_type literals) and
// app/(dashboard)/ route dirs. Keys must match the backend's emitted entity_type
// strings exactly. `null` => no detail route constructable from {type,id} alone.
const ROUTE_PREFIX: Record<string, string | null> = {
  Molecule: "/compounds", // /compounds/[id]
  Protocol: "/assays/protocols", // /assays/protocols/[id]
  Project: "/projects", // /projects/[id]
  Collection: "/collections", // /collections/[id]
  Run: "/assays/runs", // /assays/runs/[id]
  // Campaign detail route is nested (/projects/[projectId]/campaigns/[campaignId])
  // and needs a projectId the browse row does not provide — non-linkable in v1.
  Campaign: null,
  Batch: "/inventory/batches", // /inventory/batches/[id]
  Plate: "/inventory/plates", // /inventory/plates/[id]
};

function hrefFor(row: TaggedEntity): string | null {
  const prefix = ROUTE_PREFIX[row.entity_type];
  return prefix ? `${prefix}/${row.entity_id}` : null;
}

export function TagBrowse() {
  const params = useSearchParams();
  const initialTag = params.get("tag");
  const [filter, setFilter] = useState<TagFilterValue>({
    tagIds: initialTag ? [initialTag] : [],
    tagLogic: "any",
  });
  const activeTag = filter.tagIds[0];
  const { data, isLoading } = useTagEntities(activeTag);

  const grouped = useMemo(() => {
    const out = new Map<string, TaggedEntity[]>();
    for (const row of data ?? []) {
      const list = out.get(row.entity_type) ?? [];
      list.push(row);
      out.set(row.entity_type, list);
    }
    return [...out.entries()];
  }, [data]);

  return (
    <div className="space-y-6">
      <PageHeader title="Browse by Tag" subtitle="Pick a tag to see everything that carries it.">
        <TagFilter value={filter} onChange={setFilter} />
      </PageHeader>

      {!activeTag && <p className="text-muted-foreground">Pick a tag to see what carries it.</p>}
      {activeTag && isLoading && <p className="text-muted-foreground">Loading…</p>}
      {activeTag && !isLoading && grouped.length === 0 && (
        <p className="text-muted-foreground">Nothing carries this tag yet.</p>
      )}
      {grouped.map(([type, rows]) => (
        <section key={type} className="space-y-1">
          <h2 className="text-sm font-medium text-muted-foreground">
            {type} ({rows.length})
          </h2>
          <ul className="divide-y rounded-md border">
            {rows.map((row) => {
              const href = hrefFor(row);
              return (
                <li key={`${row.entity_type}:${row.entity_id}`}>
                  {href ? (
                    <Link href={href} className="block px-3 py-2 hover:bg-accent">
                      {row.label}
                    </Link>
                  ) : (
                    <span className="block px-3 py-2 text-muted-foreground">{row.label}</span>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
