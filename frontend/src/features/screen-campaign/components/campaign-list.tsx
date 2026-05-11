"use client";

import Link from "next/link";
import { Loader2 } from "lucide-react";

import { Button } from "@/shared/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";

import { useCampaignsByProject } from "../lib/hooks";
import { CampaignStatusChip } from "./campaign-status-chip";

interface CampaignListProps {
  projectId: string;
}

/**
 * Per-project campaign list.
 *
 * Renders a table of campaigns scoped to `projectId`. Loading, error, and
 * empty states are handled inline. Mutation entry points (create dialog, etc.)
 * will be wired in Phase 8.
 */
export function CampaignList({ projectId }: CampaignListProps) {
  const { data, isLoading, error } = useCampaignsByProject(projectId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-destructive py-4">
        Failed to load campaigns. Please refresh the page.
      </p>
    );
  }

  if (!data?.length) {
    return (
      <div
        data-testid="campaign-list-empty"
        className="flex flex-col items-center justify-center py-12 text-center"
      >
        <p className="mb-4 text-muted-foreground">No campaigns yet.</p>
        {/* Wire to <CreateCampaignDialog /> in Phase 8 */}
        <Button>Create campaign</Button>
      </div>
    );
  }

  return (
    <Table data-testid="campaign-list">
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Channels</TableHead>
          <TableHead>Compounds</TableHead>
          <TableHead>Closed</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.map((c) => (
          <TableRow key={c.id} data-testid={`campaign-row-${c.id}`}>
            <TableCell>
              <Link
                href={`/projects/${projectId}/campaigns/${c.id}`}
                className="text-primary hover:underline"
              >
                {c.name}
              </Link>
            </TableCell>
            <TableCell>
              <CampaignStatusChip status={c.status} />
            </TableCell>
            <TableCell>{c.channels?.length ?? 0}</TableCell>
            <TableCell>{c.results?.length ?? 0}</TableCell>
            <TableCell>
              {c.closed_at
                ? new Date(c.closed_at as string).toLocaleDateString()
                : "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
