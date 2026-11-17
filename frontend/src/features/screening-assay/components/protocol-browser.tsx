"use client";

import { useProjects } from "@/features/research-organization/hooks/use-projects";
import { TagFilter, type TagFilterValue } from "@/features/tagging/components/tag-filter";
import { ErrorState } from "@/shared/components/empty-state";
import { SearchInput } from "@/shared/components/search-input";
import { Button } from "@/shared/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/shared/components/ui/tabs";
import { ListTree, Table2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useProtocolSummaries, useProtocols } from "../hooks/use-protocols";
import { type FacetSelections, filterProtocols, matchesProtocolText } from "../lib/protocol-facets";
import { PROTOCOL_STATUS_LABELS, PROTOCOL_TYPE_LABELS, type Protocol } from "../types";
import { ProtocolGrid } from "./protocol-grid";
import { ProtocolLibraryView } from "./protocol-library-view";

const ALL_PROJECTS = "__all__";
const VIEW_KEY = "cellar.protocols.view";
type View = "grid" | "library";

interface ProtocolBrowserProps {
  onSelect?: (protocolId: string) => void;
  onNewFrom?: (protocol: Protocol) => void;
}

export function ProtocolBrowser({ onSelect, onNewFrom }: ProtocolBrowserProps) {
  const [search, setSearch] = useState("");
  const [projectFilter, setProjectFilter] = useState<string>(ALL_PROJECTS);
  const [tagFilter, setTagFilter] = useState<TagFilterValue>({ tagIds: [], tagLogic: "any" });
  const [view, setView] = useState<View>("grid");
  // Shared across views so switching presentation never silently changes the scope.
  const [selections, setSelections] = useState<FacetSelections>({});

  useEffect(() => {
    try {
      const saved = localStorage.getItem(VIEW_KEY);
      if (saved === "grid" || saved === "library") setView(saved);
    } catch {
      /* The view still works when storage is unavailable. */
    }
  }, []);

  const onViewChange = (v: string) => {
    if (v !== "grid" && v !== "library") return;
    setView(v);
    try {
      localStorage.setItem(VIEW_KEY, v);
    } catch {
      /* Session-only preference. */
    }
  };

  const { data: projects } = useProjects();
  const {
    data: protocols,
    isLoading,
    error,
  } = useProtocols(projectFilter !== ALL_PROJECTS ? projectFilter : undefined, {
    tags: tagFilter.tagIds,
    tagLogic: tagFilter.tagLogic,
  });
  const { data: summaries, isPending: datesLoading, isError: datesError } = useProtocolSummaries();
  const datedProtocols = useMemo(() => {
    const dates = new Map(summaries?.map((p) => [p.id, p.last_run_date]));
    return protocols?.map((p) => ({ ...p, last_run_date: dates.get(p.id) }));
  }, [protocols, summaries]);
  const searchSource = useMemo(
    () => (datedProtocols ?? []).filter((p) => matchesProtocolText(p, search)),
    [datedProtocols, search],
  );
  const filtered = useMemo(
    () => filterProtocols(searchSource, selections),
    [searchSource, selections],
  );
  const hasFilters =
    !!search.trim() ||
    projectFilter !== ALL_PROJECTS ||
    tagFilter.tagIds.length > 0 ||
    Object.values(selections).some((s) => s && s.size > 0);
  const extraFacetCount = Object.entries(selections).filter(
    ([key, values]) => key !== "type" && key !== "status" && values && values.size > 0,
  ).length;
  const clearFilters = () => {
    setSearch("");
    setProjectFilter(ALL_PROJECTS);
    setTagFilter({ tagIds: [], tagLogic: "any" });
    setSelections({});
  };

  return (
    <div className="min-w-0 overflow-hidden rounded-xl border bg-card shadow-sm">
      <div className="flex flex-wrap items-center gap-2 border-b p-3">
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Search names, codes, targets…"
          className="min-w-56 flex-1"
          inputClassName="h-8"
        />
        {(["status", "type"] as const).map((dim) => {
          const selected = selections[dim];
          const value = selected?.size
            ? selected.size === 1
              ? [...selected][0]
              : "__multiple__"
            : "__all__";
          const labels = dim === "status" ? PROTOCOL_STATUS_LABELS : PROTOCOL_TYPE_LABELS;
          return (
            <Select
              key={dim}
              value={value}
              onValueChange={(v) =>
                setSelections((prev) => ({ ...prev, [dim]: new Set(v === "__all__" ? [] : [v]) }))
              }
            >
              <SelectTrigger
                size="sm"
                aria-label={dim === "status" ? "Protocol status" : "Assay type"}
                className={
                  dim === "status" ? "w-[calc(50%-4px)] sm:w-36" : "w-[calc(50%-4px)] sm:w-44"
                }
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">
                  {dim === "status" ? "All statuses" : "All assay types"}
                </SelectItem>
                {value === "__multiple__" && (
                  <SelectItem value="__multiple__" disabled>
                    Multiple {dim === "status" ? "statuses" : "types"}
                  </SelectItem>
                )}
                {Object.entries(labels)
                  .sort((a, b) => a[1].localeCompare(b[1]))
                  .map(([key, label]) => (
                    <SelectItem key={key} value={key}>
                      {label}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
          );
        })}
        {projects && projects.length > 0 && (
          <Select value={projectFilter} onValueChange={setProjectFilter}>
            <SelectTrigger size="sm" aria-label="Project" className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_PROJECTS}>All projects</SelectItem>
              {[...projects]
                .sort((a, b) =>
                  a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }),
                )
                .map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        )}
        <TagFilter value={tagFilter} onChange={setTagFilter} alphabetical />
        <Tabs value={view} onValueChange={onViewChange}>
          <TabsList
            aria-label="Protocol view"
            className="group-data-[orientation=horizontal]/tabs:h-8"
          >
            <TabsTrigger value="grid">
              <Table2 className="size-4" />
              Table
            </TabsTrigger>
            <TabsTrigger value="library">
              <ListTree className="size-4" />
              Library
            </TabsTrigger>
          </TabsList>
        </Tabs>
        {extraFacetCount > 0 && (
          <Button size="sm" variant="outline" onClick={() => onViewChange("library")}>
            {extraFacetCount} library {extraFacetCount === 1 ? "filter" : "filters"}
          </Button>
        )}
        {hasFilters && (
          <Button variant="ghost" size="sm" onClick={clearFilters}>
            Clear filters
          </Button>
        )}
        {view === "grid" && (
          <output className="ml-auto text-sm text-muted-foreground">
            {error ? (
              "Unable to load"
            ) : isLoading ? (
              "Loading protocols…"
            ) : (
              <>
                <strong className="font-semibold text-foreground">{filtered.length}</strong>{" "}
                {hasFilters ? "matching " : ""}
                {filtered.length === 1 ? "protocol" : "protocols"}
              </>
            )}
          </output>
        )}
      </div>
      {error ? (
        <ErrorState message="Could not load protocols. Please try again." />
      ) : view === "grid" ? (
        <ProtocolGrid
          protocols={filtered}
          isLoading={isLoading}
          onSelect={onSelect}
          isFiltered={hasFilters}
          datesLoading={datesLoading}
          datesError={datesError}
        />
      ) : isLoading || !protocols ? (
        <div className="py-12 text-center text-sm text-muted-foreground">Loading protocols…</div>
      ) : (
        <ProtocolLibraryView
          protocols={searchSource}
          onSelect={onSelect}
          search={search}
          onNewFrom={onNewFrom}
          selections={selections}
          onSelectionsChange={setSelections}
          datesLoading={datesLoading}
          datesError={datesError}
        />
      )}
    </div>
  );
}
