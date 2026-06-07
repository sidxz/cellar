"use client";

import {
  Avatar,
  AvatarFallback,
  AvatarGroup,
  AvatarGroupCount,
} from "@/shared/components/ui/avatar";
import { Badge } from "@/shared/components/ui/badge";
import { useWorkspaceMembers } from "@/shared/hooks/use-workspace-members";
import { timeAgo } from "@/shared/lib/time-ago";
import { cn } from "@/shared/lib/utils";
import { FolderKanban, Star } from "lucide-react";
import type { ProjectScopeStats } from "../hooks/use-project-scope-stats";
import { projectIdentityColor } from "../lib/project-identity";
import type { Project } from "../types";

function initials(nameOrEmail: string): string {
  const base = nameOrEmail.trim();
  const parts = base.split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return base.slice(0, 2).toUpperCase();
}

interface ProjectCardProps {
  project: Project;
  stats?: ProjectScopeStats;
  favorited: boolean;
  onToggleFavorite: (project: Project, favorited: boolean) => void;
  onOpen: (project: Project) => void;
}

export function ProjectCard({
  project,
  stats,
  favorited,
  onToggleFavorite,
  onOpen,
}: ProjectCardProps) {
  const color = projectIdentityColor(project);
  const { data: members } = useWorkspaceMembers();
  const archived = project.status === "archived";

  const memberIds = stats?.member_ids ?? [];
  const resolved = memberIds
    .map((id) => members?.find((m) => m.user_id === id))
    .filter((m): m is NonNullable<typeof m> => Boolean(m));
  const overflow = (stats?.member_count ?? memberIds.length) - Math.min(resolved.length, 3);

  return (
    <div
      className={cn(
        "group relative flex flex-col overflow-hidden rounded-lg border bg-card shadow-sm transition-shadow hover:shadow-md",
        archived && "opacity-60",
      )}
    >
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1", color.dot)} />

      {!archived && (
        <button
          type="button"
          aria-label={favorited ? "Unpin project" : "Pin project"}
          aria-pressed={favorited}
          onClick={(e) => {
            e.stopPropagation();
            onToggleFavorite(project, favorited);
          }}
          className={cn(
            "absolute top-2 right-2 z-10 rounded p-1 transition-opacity hover:text-foreground",
            favorited
              ? "text-amber-500 opacity-100"
              : "text-muted-foreground opacity-0 group-hover:opacity-100",
          )}
        >
          <Star className={cn("h-4 w-4", favorited && "fill-current")} />
        </button>
      )}

      <button
        type="button"
        onClick={() => onOpen(project)}
        className="flex flex-1 flex-col gap-3 p-4 pl-5 text-left"
      >
        <div className="flex items-start gap-2">
          <span
            className={cn(
              "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded",
              color.bg,
            )}
          >
            <FolderKanban className={cn("h-4 w-4", color.text)} />
          </span>
          <div className="min-w-0 pr-6">
            <div className="truncate font-semibold leading-tight">{project.name}</div>
            <div className="truncate text-xs text-muted-foreground">
              {project.description?.trim() || "No description"}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 divide-x rounded-md border bg-muted/30 text-center">
          <div className="px-2 py-2">
            <div className="font-semibold tabular-nums">{stats ? stats.molecule_count : "—"}</div>
            <div className="text-[11px] text-muted-foreground">compounds</div>
          </div>
          <div className="px-2 py-2">
            <div className="font-semibold tabular-nums">{stats ? stats.campaign_count : "—"}</div>
            <div className="text-[11px] text-muted-foreground">
              {stats && stats.campaign_count === 0 ? "no campaigns" : "campaigns"}
            </div>
          </div>
        </div>

        <div className="mt-auto flex items-center justify-between">
          {resolved.length > 0 ? (
            <AvatarGroup>
              {resolved.slice(0, 3).map((m) => (
                <Avatar key={m.user_id} size="sm">
                  <AvatarFallback>{initials(m.name || m.email)}</AvatarFallback>
                </Avatar>
              ))}
              {overflow > 0 && <AvatarGroupCount>+{overflow}</AvatarGroupCount>}
            </AvatarGroup>
          ) : (
            <span />
          )}
          {archived ? (
            <Badge variant="outline">Archived</Badge>
          ) : (
            <span className="text-xs text-muted-foreground">
              {timeAgo(stats?.last_activity_at)}
            </span>
          )}
        </div>
      </button>
    </div>
  );
}
