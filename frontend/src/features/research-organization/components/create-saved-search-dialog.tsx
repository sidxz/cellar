"use client";

import { useEffect, useState } from "react";
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
import { useProjects } from "../hooks/use-projects";
import {
  useCreateSavedSearch,
  useUpdateSavedSearch,
} from "../hooks/use-saved-searches";
import type { SavedSearch, SearchVisibility } from "../types";

interface CreateSavedSearchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pass a saved search to switch to edit mode. */
  savedSearch?: SavedSearch;
  /** Pre-select a project (e.g., when creating from project detail). */
  defaultProjectId?: string;
}

const NO_SELECTION = "__none__";

export function CreateSavedSearchDialog({
  open,
  onOpenChange,
  savedSearch,
  defaultProjectId,
}: CreateSavedSearchDialogProps) {
  const isEdit = !!savedSearch;
  const createMutation = useCreateSavedSearch();
  const updateMutation = useUpdateSavedSearch(savedSearch?.id ?? "");

  const { data: projects } = useProjects();

  const [name, setName] = useState("");
  const [visibility, setVisibility] = useState<SearchVisibility>("private");
  const [projectId, setProjectId] = useState<string>(NO_SELECTION);
  const [query, setQuery] = useState("");
  const [columns, setColumns] = useState("");

  // Reset form when dialog opens / savedSearch changes
  useEffect(() => {
    if (open) {
      setName(savedSearch?.name ?? "");
      setVisibility(savedSearch?.visibility ?? "private");
      setProjectId(
        savedSearch?.project_id ?? defaultProjectId ?? NO_SELECTION
      );
      setQuery(
        savedSearch?.query ? JSON.stringify(savedSearch.query, null, 2) : ""
      );
      setColumns(
        savedSearch?.columns
          ? JSON.stringify(savedSearch.columns, null, 2)
          : ""
      );
    }
  }, [open, savedSearch, defaultProjectId]);

  const resetForm = () => {
    setName("");
    setVisibility("private");
    setProjectId(defaultProjectId ?? NO_SELECTION);
    setQuery("");
    setColumns("");
  };

  const mutation = isEdit ? updateMutation : createMutation;

  const isQueryValid = (() => {
    if (!query.trim()) return false;
    try {
      JSON.parse(query);
      return true;
    } catch {
      return false;
    }
  })();

  const isColumnsValid = (() => {
    if (!columns.trim()) return true; // optional
    try {
      JSON.parse(columns);
      return true;
    } catch {
      return false;
    }
  })();

  const canSubmit =
    name.trim() &&
    isQueryValid &&
    isColumnsValid &&
    (visibility === "private" || projectId !== NO_SELECTION) &&
    !mutation.isPending;

  const handleSubmit = () => {
    const payload = {
      name: name.trim(),
      visibility,
      project_id:
        visibility === "project" && projectId !== NO_SELECTION
          ? projectId
          : null,
      query: JSON.parse(query) as Record<string, unknown>,
      columns: columns.trim()
        ? (JSON.parse(columns) as Record<string, unknown>)
        : null,
    };

    mutation.mutate(payload, {
      onSuccess: () => {
        onOpenChange(false);
        resetForm();
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEdit ? "Edit Saved Search" : "New Saved Search"}
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update the saved search details."
              : "Save a search to quickly re-run it later."}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label>Name</Label>
            <Input
              placeholder="e.g., Active EGFR Hits"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && canSubmit) handleSubmit();
              }}
            />
          </div>

          <div className="grid gap-2">
            <Label>Visibility</Label>
            <Select
              value={visibility}
              onValueChange={(v) => setVisibility(v as SearchVisibility)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="private">Private</SelectItem>
                <SelectItem value="project">Project</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {visibility === "project" && (
            <div className="grid gap-2">
              <Label>Project</Label>
              <Select value={projectId} onValueChange={setProjectId}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a project" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_SELECTION}>Select a project</SelectItem>
                  {projects
                    ?.filter((p) => p.status === "active")
                    .map((p) => (
                      <SelectItem key={p.id} value={p.id}>
                        {p.name}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="grid gap-2">
            <Label>Query</Label>
            <Textarea
              placeholder="Search criteria (JSON)"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              rows={4}
              className="font-mono text-sm"
            />
            {query.trim() && !isQueryValid && (
              <p className="text-xs text-destructive">Invalid JSON</p>
            )}
          </div>

          <div className="grid gap-2">
            <Label>Columns (optional)</Label>
            <Textarea
              placeholder="Column preferences (JSON)"
              value={columns}
              onChange={(e) => setColumns(e.target.value)}
              rows={3}
              className="font-mono text-sm"
            />
            {columns.trim() && !isColumnsValid && (
              <p className="text-xs text-destructive">Invalid JSON</p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={mutation.isPending}
          >
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {mutation.isPending
              ? isEdit
                ? "Saving..."
                : "Creating..."
              : isEdit
                ? "Save Changes"
                : "Create Saved Search"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
