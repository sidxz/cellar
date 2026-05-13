"use client";

import Link from "next/link";
import { Loader2, Plus } from "lucide-react";

import { Button } from "@/shared/components/ui/button";
import { formatDate } from "@/shared/lib/format-date";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/shared/components/ui/table";

import { useCampaigns } from "../hooks/use-campaigns";
import { useProject } from "@/features/research-organization/hooks/use-projects";
import { useBreadcrumbTrail } from "@/shared/components/layout/breadcrumb-context";
import { CampaignStatusChip } from "./campaign-status-chip";
import { CreateCampaignDialog } from "./create-campaign-dialog";

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
  const { data, isLoading, error } = useCampaigns(projectId);
  const { data: project } = useProject(projectId);

  useBreadcrumbTrail([
    { label: "Projects", href: "/projects" },
    { label: project?.name ?? "", href: `/projects/${projectId}` },
    { label: "Campaigns" },
  ]);

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
        <CreateCampaignDialog
          projectId={projectId}
          trigger={
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Create campaign
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <>
      <div className="mb-4 flex justify-end">
        <CreateCampaignDialog
          projectId={projectId}
          trigger={
            <Button size="sm">
              <Plus className="mr-2 h-4 w-4" />
              New Campaign
            </Button>
          }
        />
      </div>
    <Table data-testid="campaign-list">
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Channels</TableHead>
          <TableHead>Compounds</TableHead>
          <TableHead>Created</TableHead>
          <TableHead>Closed</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.map((c) => (
          <TableRow key={c.id} data-testid={`campaign-row-${c.id}`} className="align-top">
            <TableCell className="max-w-xs">
              <Link
                href={`/projects/${projectId}/campaigns/${c.id}`}
                className="text-primary hover:underline font-medium"
              >
                {c.name}
              </Link>
              {c.description && (
                <p
                  className="mt-0.5 text-xs text-muted-foreground line-clamp-2"
                  title={c.description}
                >
                  {c.description}
                </p>
              )}
            </TableCell>
            <TableCell>
              <CampaignStatusChip status={c.status} />
            </TableCell>
            <TableCell>{c.channels?.length ?? 0}</TableCell>
            <TableCell>{c.results?.length ?? 0}</TableCell>
            <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
              {c.created_at ? formatDate(c.created_at as string) : "—"}
            </TableCell>
            <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
              {c.closed_at ? formatDate(c.closed_at as string) : "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
    </>
  );
}
