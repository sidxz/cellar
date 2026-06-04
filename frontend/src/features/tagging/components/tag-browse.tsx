"use client";

import { DataGrid } from "@/shared/components/data-grid/data-grid";
import { PageHeader } from "@/shared/components/page-header";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { formatDate } from "@/shared/lib/format-date";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import { AlertTriangle } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { type TaggedEntity, useTagEntities } from "../hooks/use-tag-entities";
import { TagFilter, type TagFilterValue } from "./tag-filter";

// Verified against backend tag_browse_repository.py (entity_type literals) and
// app/(dashboard)/ route dirs. `null` => no detail route constructable from
// {type, id} alone (Campaign's route is nested under a project).
const ROUTE_PREFIX: Record<string, string | null> = {
  Molecule: "/compounds",
  Protocol: "/assays/protocols",
  Project: "/projects",
  Collection: "/collections",
  Run: "/assays/runs",
  Campaign: null,
  Batch: "/inventory/batches",
  Plate: "/inventory/plates",
};

/** Detail-page href for a tagged entity, or null when it isn't directly linkable. */
export function hrefFor(row: { entity_type: string; entity_id: string }): string | null {
  const prefix = ROUTE_PREFIX[row.entity_type];
  return prefix ? `${prefix}/${row.entity_id}` : null;
}

// Per-type tint so the Type column reads at a glance.
const TYPE_STYLE: Record<string, string> = {
  Molecule: "bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300",
  Protocol: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  Project: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  Collection: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  Run: "bg-cyan-100 text-cyan-700 dark:bg-cyan-950 dark:text-cyan-300",
  Campaign: "bg-pink-100 text-pink-700 dark:bg-pink-950 dark:text-pink-300",
  Batch: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300",
  Plate: "bg-teal-100 text-teal-700 dark:bg-teal-950 dark:text-teal-300",
};

function FacetChip({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant={active ? "default" : "outline"}
      className="h-7 rounded-full px-3 text-xs"
      onClick={onClick}
    >
      {label}
      <span className="ml-1.5 opacity-70">{count}</span>
    </Button>
  );
}

export function TagBrowse() {
  const router = useRouter();
  const params = useSearchParams();
  const initialTag = params.get("tag");
  const [filter, setFilter] = useState<TagFilterValue>({
    tagIds: initialTag ? [initialTag] : [],
    tagLogic: "any",
  });
  const [typeFilter, setTypeFilter] = useState<string | null>(null);

  const hasTags = filter.tagIds.length > 0;
  const { data, isLoading, error } = useTagEntities(filter.tagIds, filter.tagLogic);

  const counts = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of data ?? []) m.set(r.entity_type, (m.get(r.entity_type) ?? 0) + 1);
    return m;
  }, [data]);

  const rows = useMemo(
    () => (data ?? []).filter((r) => !typeFilter || r.entity_type === typeFilter),
    [data, typeFilter],
  );

  const columnDefs = useMemo<ColDef<TaggedEntity>[]>(
    () => [
      {
        headerName: "Type",
        field: "entity_type",
        width: 150,
        cellRenderer: ({ value }: ICellRendererParams<TaggedEntity>) => (
          <Badge variant="secondary" className={`font-normal ${TYPE_STYLE[value as string] ?? ""}`}>
            {value}
          </Badge>
        ),
      },
      {
        headerName: "Name",
        field: "label",
        flex: 1,
        minWidth: 220,
        cellRenderer: ({ data: row }: ICellRendererParams<TaggedEntity>) => {
          if (!row) return null;
          const href = hrefFor(row);
          return href ? (
            <Link href={href} className="text-primary hover:underline">
              {row.label}
            </Link>
          ) : (
            <span className="text-muted-foreground">{row.label}</span>
          );
        },
      },
      {
        headerName: "Tagged on",
        field: "assigned_at",
        width: 170,
        valueFormatter: (p) => formatDate(p.value as string),
      },
    ],
    [],
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Browse by Tag"
        subtitle="Pick one or more tags to see everything that carries them."
      >
        <TagFilter
          value={filter}
          onChange={(v) => {
            setFilter(v);
            setTypeFilter(null);
          }}
        />
      </PageHeader>

      {!hasTags && (
        <div className="rounded-md border border-dashed py-12 text-center text-sm text-muted-foreground">
          Select one or more tags above to see every molecule, protocol, run, batch, plate and more
          that carries them.
        </div>
      )}

      {hasTags && error && (
        <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          Couldn’t load tagged items: {(error as Error).message}
        </div>
      )}

      {hasTags && !error && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-1 text-sm text-muted-foreground">
              {data
                ? `${data.length} item${data.length === 1 ? "" : "s"} across ${counts.size} type${
                    counts.size === 1 ? "" : "s"
                  }`
                : ""}
            </span>
            <FacetChip
              label="All"
              count={data?.length ?? 0}
              active={!typeFilter}
              onClick={() => setTypeFilter(null)}
            />
            {[...counts.entries()].map(([type, n]) => (
              <FacetChip
                key={type}
                label={type}
                count={n}
                active={typeFilter === type}
                onClick={() => setTypeFilter(type)}
              />
            ))}
          </div>

          <DataGrid<TaggedEntity>
            rowData={rows}
            columnDefs={columnDefs}
            loading={isLoading}
            onRowClick={(row) => {
              const href = hrefFor(row);
              if (href) router.push(href);
            }}
            height={560}
            searchPlaceholder="Filter results…"
            emptyState={
              <p className="py-10 text-center text-sm text-muted-foreground">
                Nothing carries {filter.tagIds.length > 1 ? "these tags" : "this tag"} yet.
              </p>
            }
          />
        </div>
      )}
    </div>
  );
}
