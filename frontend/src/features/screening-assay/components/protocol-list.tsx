"use client";

import { useProjects } from "@/features/research-organization/hooks/use-projects";
import { TagFilter, type TagFilterValue } from "@/features/tagging/components/tag-filter";
import { SearchInput } from "@/shared/components/search-input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { useState } from "react";
import { useProtocols } from "../hooks/use-protocols";
import { ProtocolGrid } from "./protocol-grid";

interface ProtocolListProps {
  onSelect?: (protocolId: string) => void;
  /** When provided, locks the list to this project (hides the project filter). */
  projectId?: string;
}

const ALL_PROJECTS = "__all__";

export function ProtocolList({ onSelect, projectId }: ProtocolListProps) {
  const [search, setSearch] = useState("");
  const [projectFilter, setProjectFilter] = useState<string>(ALL_PROJECTS);
  const [tagFilter, setTagFilter] = useState<TagFilterValue>({ tagIds: [], tagLogic: "any" });
  const { data: projects } = useProjects();
  const effectiveProjectId =
    projectId ?? (projectFilter !== ALL_PROJECTS ? projectFilter : undefined);
  const {
    data: protocols,
    isLoading,
    error,
  } = useProtocols(effectiveProjectId, {
    tags: tagFilter.tagIds,
    tagLogic: tagFilter.tagLogic,
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search protocols..."
          className="max-w-sm flex-1"
        />
        <TagFilter value={tagFilter} onChange={setTagFilter} />
        {!projectId && projects && projects.length > 0 && (
          <>
            <span className="shrink-0 text-sm text-muted-foreground">Project:</span>
            <Select value={projectFilter} onValueChange={setProjectFilter}>
              <SelectTrigger className="w-[220px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_PROJECTS}>All projects</SelectItem>
                {projects.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </>
        )}
      </div>

      <ProtocolGrid
        protocols={protocols}
        isLoading={isLoading}
        error={error}
        quickFilterText={search}
        onSelect={onSelect}
      />
    </div>
  );
}
