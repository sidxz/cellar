"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { useOrgs } from "@/shared/hooks/use-orgs";
import { useMemo } from "react";
import type { PlateGroupNode } from "../hooks/use-plate-groups";
import { usePlates } from "../hooks/use-plates";

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
    </div>
  );
}
