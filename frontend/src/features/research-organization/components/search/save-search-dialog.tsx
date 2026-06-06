"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/components/ui/dialog";
import { Input } from "@/shared/components/ui/input";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Textarea } from "@/shared/components/ui/textarea";
import { useEffect, useState } from "react";
import { useProjects } from "../../hooks/use-projects";
import { useCreateSavedSearch, useUpdateSavedSearch } from "../../hooks/use-saved-searches";
import { aggregationModeToWire, useAggregationMode } from "../../lib/use-aggregation-mode";
import type { ReportConfig, SavedSearch, SearchQuery, SearchVisibility } from "../../types";

// ─── Props ──────────────────────────────────────────────────────────────────

interface SaveSearchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  query: SearchQuery;
  protocolColumns: string[];
  reportConfig: ReportConfig;
  existingSearch?: SavedSearch;
}

// ─── Component ──────────────────────────────────────────────────────────────

export function SaveSearchDialog({
  open,
  onOpenChange,
  query,
  protocolColumns,
  reportConfig,
  existingSearch,
}: SaveSearchDialogProps) {
  const isUpdate = !!existingSearch;

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<SearchVisibility>("private");
  const [projectId, setProjectId] = useState<string | null>(null);

  const { data: projects = [] } = useProjects();
  const createMutation = useCreateSavedSearch();
  const updateMutation = useUpdateSavedSearch(existingSearch?.id ?? "");
  // Aggregation mode is stored inside the query JSONB blob so saved
  // searches round-trip the active selection rule alongside their
  // filter criteria (Task 14).
  const { mode: aggregationMode } = useAggregationMode();

  const isSaving = createMutation.isPending || updateMutation.isPending;

  // Pre-populate when editing an existing search
  useEffect(() => {
    if (open && existingSearch) {
      setName(existingSearch.name);
      setDescription(existingSearch.description ?? "");
      setVisibility(existingSearch.visibility);
      setProjectId(existingSearch.project_id);
    } else if (open) {
      setName("");
      setDescription("");
      setVisibility("private");
      setProjectId(null);
    }
  }, [open, existingSearch]);

  function handleSave() {
    const columns = {
      reportConfig,
      protocolColumns,
    };

    // Embed the current aggregation rule inside the query JSONB so the
    // saved search restores it on load. Always written (even for the
    // default "latest") so an older saved search edited under a
    // non-default mode is unambiguous after re-save.
    const queryWithAggregation = {
      ...(query as unknown as Record<string, unknown>),
      aggregation: aggregationModeToWire(aggregationMode),
    };

    if (isUpdate) {
      updateMutation.mutate(
        {
          name,
          description: description || null,
          query: queryWithAggregation,
          columns,
          visibility,
          project_id: visibility === "project" ? projectId : null,
        },
        { onSuccess: () => onOpenChange(false) },
      );
    } else {
      createMutation.mutate(
        {
          name,
          description: description || null,
          query: queryWithAggregation,
          columns,
          visibility,
          project_id: visibility === "project" ? projectId : null,
        },
        { onSuccess: () => onOpenChange(false) },
      );
    }
  }

  const canSave = name.trim().length > 0 && !isSaving;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isUpdate ? "Update Saved Search" : "Save Search"}</DialogTitle>
          <DialogDescription>
            {isUpdate
              ? "Update the saved search with the current query and display settings."
              : "Save the current search query and display settings for quick access later."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Name */}
          <div className="space-y-2">
            <Label htmlFor="search-name">Name</Label>
            <Input
              id="search-name"
              placeholder="e.g. Active compounds against Target X"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>

          {/* Description */}
          <div className="space-y-2">
            <Label htmlFor="search-description">
              Description <span className="text-muted-foreground font-normal">(optional)</span>
            </Label>
            <Textarea
              id="search-description"
              placeholder="Brief description of what this search finds..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </div>

          {/* Visibility */}
          <div className="space-y-2">
            <Label htmlFor="search-visibility">Visibility</Label>
            <Select
              value={visibility}
              onValueChange={(v) => {
                setVisibility(v as SearchVisibility);
                if (v === "private") {
                  setProjectId(null);
                }
              }}
            >
              <SelectTrigger id="search-visibility">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="private">Private</SelectItem>
                <SelectItem value="project">Project</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Project (shown only when visibility = project) */}
          {visibility === "project" && (
            <div className="space-y-2">
              <Label htmlFor="search-project">Project</Label>
              <Select value={projectId ?? ""} onValueChange={(v) => setProjectId(v || null)}>
                <SelectTrigger id="search-project">
                  <SelectValue placeholder="Select a project..." />
                </SelectTrigger>
                <SelectContent>
                  {projects.map((project) => (
                    <SelectItem key={project.id} value={project.id}>
                      {project.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={!canSave}>
            {isSaving ? (isUpdate ? "Updating..." : "Saving...") : isUpdate ? "Update" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
