"use client";

import { useProjects } from "@/features/research-organization/hooks/use-projects";
import { TagFilter, type TagFilterValue } from "@/features/tagging/components/tag-filter";
import { ErrorState } from "@/shared/components/empty-state";
import { SearchInput } from "@/shared/components/search-input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { LayoutGrid, ListTree } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useProtocols } from "../hooks/use-protocols";
import { matchesProtocolText } from "../lib/protocol-facets";
import { ProtocolGrid } from "./protocol-grid";
import { ProtocolLibraryView } from "./protocol-library-view";

const ALL_PROJECTS = "__all__";
const VIEW_KEY = "cellar.protocols.view";
type View = "grid" | "library";

interface ProtocolBrowserProps {
  onSelect?: (protocolId: string) => void;
}

export function ProtocolBrowser({ onSelect }: ProtocolBrowserProps) {
  const [search, setSearch] = useState("");
  const [projectFilter, setProjectFilter] = useState<string>(ALL_PROJECTS);
  const [tagFilter, setTagFilter] = useState<TagFilterValue>({ tagIds: [], tagLogic: "any" });
  const [view, setView] = useState<View>("grid");

  // Restore persisted view after mount (avoids SSR/localStorage hydration mismatch).
  useEffect(() => {
    const saved = localStorage.getItem(VIEW_KEY);
    if (saved === "grid" || saved === "library") setView(saved);
  }, []);

  const onViewChange = (v: string) => {
    const next = v as View;
    setView(next);
    localStorage.setItem(VIEW_KEY, next);
  };

  const { data: projects } = useProjects();
  const effectiveProjectId = projectFilter !== ALL_PROJECTS ? projectFilter : undefined;
  const {
    data: protocols,
    isLoading,
    error,
  } = useProtocols(effectiveProjectId, {
    tags: tagFilter.tagIds,
    tagLogic: tagFilter.tagLogic,
  });

  // Derive text-filtered source for library view; memoized over loaded protocols + search.
  const librarySource = useMemo(
    () => (protocols ?? []).filter((p) => matchesProtocolText(p, search)),
    [protocols, search],
  );

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
        {projects && projects.length > 0 && (
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
        <Tabs value={view} onValueChange={onViewChange} className="ml-auto">
          <TabsList>
            <TabsTrigger value="grid" aria-label="Grid view">
              <LayoutGrid className="h-4 w-4" />
            </TabsTrigger>
            <TabsTrigger value="library" aria-label="Library view">
              <ListTree className="h-4 w-4" />
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {error ? (
        <ErrorState
          message="Failed to load protocols. Is the backend running?"
          details={error.message}
        />
      ) : view === "grid" ? (
        <ProtocolGrid
          protocols={protocols}
          isLoading={isLoading}
          error={error}
          quickFilterText={search}
          onSelect={onSelect}
        />
      ) : isLoading || !protocols ? (
        <div className="py-12 text-center text-sm text-muted-foreground">Loading protocols…</div>
      ) : (
        <ProtocolLibraryView protocols={librarySource} onSelect={onSelect} />
      )}
    </div>
  );
}
