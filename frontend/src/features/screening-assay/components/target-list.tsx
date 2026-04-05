"use client";

import { useState } from "react";
import { Crosshair, Pencil, Trash2 } from "lucide-react";
import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useDeleteTarget, useTargets } from "../hooks/use-targets";
import { EditTargetDialog } from "./edit-target-dialog";
import {
  TARGET_TYPE_LABELS,
  type Target,
  type TargetType,
} from "../types";

export function TargetList() {
  const { data: targets, isLoading, error } = useTargets();
  const deleteMutation = useDeleteTarget();
  const [editTarget, setEditTarget] = useState<Target | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-dashed border-destructive/50 p-8 text-center">
        <p className="text-sm text-destructive">Failed to load targets. Is the backend running?</p>
        <p className="mt-1 text-xs text-muted-foreground">{error.message}</p>
      </div>
    );
  }

  if (!targets?.length) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
        <Crosshair className="h-12 w-12 text-muted-foreground/40" />
        <h3 className="mt-4 text-lg font-semibold">No targets</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Create your first target to associate with protocols.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Type</TableHead>
            <TableHead>Organism</TableHead>
            <TableHead>Gene</TableHead>
            <TableHead>UniProt</TableHead>
            <TableHead className="w-20" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {targets.map((target: Target) => (
            <TableRow key={target.id}>
              <TableCell className="font-medium">{target.name}</TableCell>
              <TableCell>
                <Badge variant="outline">
                  {TARGET_TYPE_LABELS[target.target_type as TargetType] ??
                    target.target_type}
                </Badge>
              </TableCell>
              <TableCell>{target.organism ?? "\u2014"}</TableCell>
              <TableCell>{target.gene_name ?? "\u2014"}</TableCell>
              <TableCell className="font-mono text-sm">
                {target.uniprot_id ?? "\u2014"}
              </TableCell>
              <TableCell>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => setEditTarget(target)}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-muted-foreground hover:text-destructive"
                    onClick={() => deleteMutation.mutate(target.id)}
                    disabled={deleteMutation.isPending}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {editTarget && (
        <EditTargetDialog
          target={editTarget}
          open={!!editTarget}
          onOpenChange={(open) => { if (!open) setEditTarget(null); }}
        />
      )}
    </div>
  );
}
