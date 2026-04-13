"use client";

import { Checkbox } from "@/shared/components/ui/checkbox";
import { ScrollArea } from "@/shared/components/ui/scroll-area";
import { useProjects } from "../../hooks/use-projects";

interface ProjectSidebarProps {
  selectedIds: string[];
  onChange: (ids: string[]) => void;
}

export function ProjectSidebar({ selectedIds, onChange }: ProjectSidebarProps) {
  const { data: projects, isLoading } = useProjects();

  const activeProjects = (projects ?? []).filter((p) => p.status === "active");

  function toggle(id: string) {
    if (selectedIds.includes(id)) {
      onChange(selectedIds.filter((sid) => sid !== id));
    } else {
      onChange([...selectedIds, id]);
    }
  }

  return (
    <div className="w-56 shrink-0 border-r">
      <div className="px-3 py-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Projects
        </h3>
      </div>
      <ScrollArea className="h-[calc(100vh-200px)]">
        <div className="space-y-1 px-3 pb-3">
          {isLoading && (
            <p className="text-xs text-muted-foreground">Loading...</p>
          )}
          {!isLoading && activeProjects.length === 0 && (
            <p className="text-xs text-muted-foreground">No active projects</p>
          )}
          {activeProjects.map((project) => (
            <label
              key={project.id}
              className="flex cursor-pointer items-center gap-2 rounded px-1 py-1.5 text-sm hover:bg-muted/50"
            >
              <Checkbox
                checked={selectedIds.includes(project.id)}
                onCheckedChange={() => toggle(project.id)}
              />
              <span className="truncate">{project.name}</span>
            </label>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
