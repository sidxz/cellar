"use client";

import * as React from "react";
import { X, Plus } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { Checkbox } from "@/shared/components/ui/checkbox";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/shared/components/ui/command";
import { useProjects } from "../../hooks/use-projects";

// ─── Props ───────────────────────────────────────────────────────────────────

interface ProjectFilterProps {
  selectedIds: string[];
  onChange: (ids: string[]) => void;
}

// ─── Component ───────────────────────────────────────────────────────────────

export function ProjectFilter({ selectedIds, onChange }: ProjectFilterProps) {
  const { data: projects } = useProjects();
  const [open, setOpen] = React.useState(false);

  const activeProjects = React.useMemo(
    () => (projects ?? []).filter((p) => p.status === "active"),
    [projects],
  );

  const selectedSet = React.useMemo(() => new Set(selectedIds), [selectedIds]);

  const selectedProjects = React.useMemo(
    () => (projects ?? []).filter((p) => selectedSet.has(p.id)),
    [projects, selectedSet],
  );

  function removeProject(id: string) {
    onChange(selectedIds.filter((sid) => sid !== id));
  }

  function toggleProject(id: string) {
    if (selectedSet.has(id)) {
      onChange(selectedIds.filter((sid) => sid !== id));
    } else {
      onChange([...selectedIds, id]);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {/* Selected project chips */}
      {selectedProjects.map((project) => (
        <span
          key={project.id}
          className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/10 px-2.5 py-0.5 text-xs text-primary"
        >
          {project.name}
          <button
            type="button"
            aria-label={`Remove ${project.name}`}
            onClick={() => removeProject(project.id)}
            className="inline-flex items-center justify-center rounded-full text-primary/70 hover:text-primary/80 focus:outline-none"
          >
            <X className="size-3" />
          </button>
        </span>
      ))}

      {/* Add button with popover */}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/20 transition-colors"
          >
            <Plus className="size-3" />
            Add
          </button>
        </PopoverTrigger>

        <PopoverContent
          align="start"
          className="w-56 p-0"
          onOpenAutoFocus={(e) => e.preventDefault()}
        >
          <Command>
            <CommandInput placeholder="Search projects…" className="h-8 text-xs" />
            <CommandList>
              <CommandEmpty>No projects found.</CommandEmpty>
              <CommandGroup>
                {activeProjects.map((project) => {
                  const checked = selectedSet.has(project.id);
                  return (
                    <CommandItem
                      key={project.id}
                      value={project.name}
                      onSelect={() => toggleProject(project.id)}
                      className="text-xs"
                    >
                      <Checkbox
                        checked={checked}
                        className="mr-1.5"
                        tabIndex={-1}
                        aria-label={project.name}
                      />
                      <span className="truncate">{project.name}</span>
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}
