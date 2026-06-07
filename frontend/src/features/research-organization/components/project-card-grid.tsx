"use client";

import { EmptyState } from "@/shared/components/empty-state";
import { FolderKanban, Plus, Star } from "lucide-react";
import type { ProjectScopeStats } from "../hooks/use-project-scope-stats";
import type { Project } from "../types";
import { ProjectCard } from "./project-card";

export type ProjectSort = "recent" | "name" | "size";

interface ProjectCardGridProps {
  projects: Project[];
  statsById: Record<string, ProjectScopeStats>;
  favorites: Set<string>;
  sort: ProjectSort;
  onToggleFavorite: (project: Project, favorited: boolean) => void;
  onOpen: (project: Project) => void;
  onCreate: () => void;
}

function sortProjects(
  projects: Project[],
  statsById: Record<string, ProjectScopeStats>,
  sort: ProjectSort,
): Project[] {
  const copy = [...projects];
  if (sort === "name") {
    copy.sort((a, b) => a.name.localeCompare(b.name));
  } else if (sort === "size") {
    copy.sort(
      (a, b) => (statsById[b.id]?.molecule_count ?? 0) - (statsById[a.id]?.molecule_count ?? 0),
    );
  } else {
    copy.sort((a, b) => {
      const ta = statsById[a.id]?.last_activity_at;
      const tb = statsById[b.id]?.last_activity_at;
      return (tb ? new Date(tb).getTime() : 0) - (ta ? new Date(ta).getTime() : 0);
    });
  }
  return copy;
}

export function ProjectCardGrid({
  projects,
  statsById,
  favorites,
  sort,
  onToggleFavorite,
  onOpen,
  onCreate,
}: ProjectCardGridProps) {
  if (projects.length === 0) {
    return (
      <EmptyState
        icon={FolderKanban}
        title="No projects"
        description="Create your first research project to get started."
        action={{ label: "New Project", onClick: onCreate, icon: Plus }}
      />
    );
  }

  const pinned = sortProjects(
    projects.filter((p) => favorites.has(p.id)),
    statsById,
    sort,
  );
  const rest = sortProjects(
    projects.filter((p) => !favorites.has(p.id)),
    statsById,
    sort,
  );

  const grid = (list: Project[]) => (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {list.map((p) => (
        <ProjectCard
          key={p.id}
          project={p}
          stats={statsById[p.id]}
          favorited={favorites.has(p.id)}
          onToggleFavorite={onToggleFavorite}
          onOpen={onOpen}
        />
      ))}
    </div>
  );

  return (
    <div className="flex flex-col gap-6">
      {pinned.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Star className="h-3.5 w-3.5 fill-current text-amber-500" /> Pinned
          </h2>
          {grid(pinned)}
        </section>
      )}
      <section className="flex flex-col gap-2">
        {pinned.length > 0 && (
          <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            All projects
          </h2>
        )}
        {grid(rest)}
      </section>
    </div>
  );
}
