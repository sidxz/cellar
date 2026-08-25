"use client";

import { EmptyState, ErrorState } from "@/shared/components/empty-state";
import { SkeletonList } from "@/shared/components/skeleton-list";
import { Badge } from "@/shared/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";
import { useAppConfig } from "@/shared/lib/app-config";
import { Crosshair, ExternalLink } from "lucide-react";
import { useTargets } from "../hooks/use-targets";
import { TARGET_TYPE_LABELS, type Target, type TargetType } from "../types";

/** Read-only mirror of prot-cellar's target catalog. Edits happen in
 *  prot-cellar; Admin → Targets pulls them across. */
export function TargetList() {
  const { data: targets, isLoading, error } = useTargets();
  const { protCellarUrl } = useAppConfig();

  if (isLoading) return <SkeletonList />;

  if (error) {
    return (
      <ErrorState
        message="Failed to load targets. Is the backend running?"
        details={error.message}
      />
    );
  }

  if (!targets?.length) {
    return (
      <EmptyState
        icon={Crosshair}
        title="No targets"
        description="Targets come from Prot-Cellar. Ask an admin to run Sync from Prot-Cellar (Admin → Targets)."
      />
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
            <TableHead>ChEMBL</TableHead>
            <TableHead className="w-12" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {targets.map((target: Target) => (
            <TableRow key={target.id}>
              <TableCell className="font-medium">{target.name}</TableCell>
              <TableCell>
                <Badge variant="outline">
                  {TARGET_TYPE_LABELS[target.target_type as TargetType] ?? target.target_type}
                </Badge>
              </TableCell>
              <TableCell>{target.organism ?? "—"}</TableCell>
              <TableCell className="font-mono text-sm">{target.chembl_id ?? "—"}</TableCell>
              <TableCell>
                <a
                  href={`${protCellarUrl}/targets/${target.id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`Open ${target.name} in Prot-Cellar`}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                </a>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
