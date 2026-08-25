"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { useCanEdit } from "@/shared/hooks/use-current-user";
import { useOrgs } from "@/shared/hooks/use-orgs";
import { formatDate } from "@/shared/lib/format-date";
import { useMemo } from "react";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { usePlates } from "../hooks/use-plates";
import { useStorageLocations } from "../hooks/use-storage-locations";
import { CommentFeed } from "./comment-feed";

/** "55 µL · 10 mM" — omits either half when absent. Exported for the group dashboard. */
export function formatInitial(
  volumeUl: number | null | undefined,
  concentrationMm: number | null | undefined,
): string {
  const parts: string[] = [];
  if (volumeUl != null) parts.push(`${volumeUl} µL`);
  if (concentrationMm != null) parts.push(`${concentrationMm} mM`);
  return parts.join(" · ");
}

export interface PlateGroupDetailsProps {
  node: PlateGroupNode;
  onAddChild?: () => void;
  onAddPlates?: () => void;
  onEdit?: () => void;
  onMove?: () => void;
  onDelete?: () => void;
  onRemovePlates?: (plateIds: string[]) => void;
}

export function PlateGroupDetails({
  node,
  onAddChild,
  onAddPlates,
  onEdit,
  onMove,
  onDelete,
  onRemovePlates,
}: PlateGroupDetailsProps) {
  const { data: orgs } = useOrgs();
  const orgName = useMemo(
    () => orgs?.find((o) => o.id === node.owner_org_id)?.name ?? "—",
    [orgs, node.owner_org_id],
  );
  const { data: plates, isLoading: platesLoading } = usePlates({ group_id: node.id });
  const canWrite = useCanEdit();
  const { data: locations } = useStorageLocations();
  const locationName = node.storage_location_id
    ? (locations?.find((l) => l.id === node.storage_location_id)?.name ?? "…")
    : null;

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4" data-testid="group-details">
      <div>
        <h2 className="text-lg font-semibold">{node.name}</h2>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          {node.group_type ? <Badge variant="secondary">{node.group_type}</Badge> : null}
          <span>{orgName}</span>
        </div>
        {node.description ? (
          <p className="mt-2 text-sm text-muted-foreground">{node.description}</p>
        ) : null}
      </div>

      <dl
        className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm"
        data-testid="group-metadata"
      >
        {node.state ? (
          <>
            <dt className="text-muted-foreground">State</dt>
            <dd>{node.state}</dd>
          </>
        ) : null}
        {node.plate_format ? (
          <>
            <dt className="text-muted-foreground">Format</dt>
            <dd>{node.plate_format === "mixed" ? "mixed" : `${node.plate_format}-well`}</dd>
          </>
        ) : null}
        {locationName ? (
          <>
            <dt className="text-muted-foreground">Location</dt>
            <dd>{locationName}</dd>
          </>
        ) : null}
        {node.scientist ? (
          <>
            <dt className="text-muted-foreground">Scientist</dt>
            <dd>{node.scientist}</dd>
          </>
        ) : null}
        {node.initial_volume_ul != null || node.initial_concentration_mm != null ? (
          <>
            <dt className="text-muted-foreground">Initial</dt>
            <dd>{formatInitial(node.initial_volume_ul, node.initial_concentration_mm)}</dd>
          </>
        ) : null}
        {node.compound_count != null ? (
          <>
            <dt className="text-muted-foreground">Compounds</dt>
            <dd>{node.compound_count.toLocaleString("en-US")}</dd>
          </>
        ) : null}
        <dt className="text-muted-foreground">Created</dt>
        <dd>{formatDate(node.created_at)}</dd>
      </dl>

      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={onAddChild}>
          Add child
        </Button>
        <Button size="sm" variant="outline" onClick={onAddPlates}>
          Add plates
        </Button>
        <Button size="sm" variant="outline" onClick={onEdit}>
          Edit
        </Button>
        <Button size="sm" variant="outline" onClick={onMove}>
          Move
        </Button>
        <Button size="sm" variant="destructive" onClick={onDelete}>
          Delete
        </Button>
      </div>

      <div>
        <div className="mb-2 flex items-center gap-2">
          <h3 className="text-sm font-medium">Plates</h3>
          <Badge variant="outline">{node.plate_count}</Badge>
        </div>
        {platesLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : !plates?.length ? (
          <p className="text-sm text-muted-foreground">No plates in this group.</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {plates.map((p) => (
              <li key={p.id} className="flex items-center justify-between px-3 py-2 text-sm">
                <span>
                  <span className="font-mono">{p.barcode}</span>
                  <span className="ml-2 text-muted-foreground">{p.plate_label}</span>
                </span>
                {onRemovePlates ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => onRemovePlates([p.id])}
                    aria-label={`Remove ${p.barcode} from group`}
                  >
                    Remove
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium">Comments</h3>
        <CommentFeed scope={{ targetType: "plate_group", targetId: node.id }} canWrite={canWrite} />
      </div>
    </div>
  );
}
