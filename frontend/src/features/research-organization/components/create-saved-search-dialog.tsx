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
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { useProjects } from "../hooks/use-projects";
import { useCreateSavedSearch, useUpdateSavedSearch } from "../hooks/use-saved-searches";
import type { SavedSearch } from "../types";

// ── Schema ────────────────────────────────────────────────────────────────────

const isValidJson = (s: string) => {
  try {
    JSON.parse(s);
    return true;
  } catch {
    return false;
  }
};

const NO_SELECTION = "__none__";

const formSchema = z
  .object({
    name: z.string().min(1, "Name is required"),
    visibility: z.enum(["private", "project"]),
    project_id: z.string(),
    query: z.string().min(1, "Query is required").refine(isValidJson, "Invalid JSON"),
    columns: z
      .string()
      .optional()
      .refine((s) => !s?.trim() || isValidJson(s), "Invalid JSON"),
  })
  .superRefine((data, ctx) => {
    if (data.visibility === "project" && data.project_id === NO_SELECTION) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Select a project",
        path: ["project_id"],
      });
    }
  });

type FormValues = z.infer<typeof formSchema>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeDefaultValues(defaultProjectId?: string): FormValues {
  return {
    name: "",
    visibility: "private",
    project_id: defaultProjectId ?? NO_SELECTION,
    query: "",
    columns: "",
  };
}

function toFormValues(savedSearch: SavedSearch, defaultProjectId?: string): FormValues {
  return {
    name: savedSearch.name,
    visibility: savedSearch.visibility ?? "private",
    project_id: savedSearch.project_id ?? defaultProjectId ?? NO_SELECTION,
    query: savedSearch.query ? JSON.stringify(savedSearch.query, null, 2) : "",
    columns: savedSearch.columns ? JSON.stringify(savedSearch.columns, null, 2) : "",
  };
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface CreateSavedSearchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pass a saved search to switch to edit mode. */
  savedSearch?: SavedSearch;
  /** Pre-select a project (e.g., when creating from project detail). */
  defaultProjectId?: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

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

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: makeDefaultValues(defaultProjectId),
  });

  // Reset form when dialog opens / savedSearch changes
  useEffect(() => {
    if (open) {
      form.reset(
        savedSearch
          ? toFormValues(savedSearch, defaultProjectId)
          : makeDefaultValues(defaultProjectId),
      );
    }
  }, [open, savedSearch, defaultProjectId, form]);

  const mutation = isEdit ? updateMutation : createMutation;
  const watchedVisibility = form.watch("visibility");

  const onSubmit = (values: FormValues) => {
    const payload = {
      name: values.name.trim(),
      visibility: values.visibility,
      project_id:
        values.visibility === "project" && values.project_id !== NO_SELECTION
          ? values.project_id
          : null,
      query: JSON.parse(values.query) as Record<string, unknown>,
      columns: values.columns?.trim()
        ? (JSON.parse(values.columns) as Record<string, unknown>)
        : null,
    };

    mutation.mutate(payload, {
      onSuccess: () => {
        onOpenChange(false);
        form.reset(makeDefaultValues(defaultProjectId));
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Saved Search" : "New Saved Search"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update the saved search details."
              : "Save a search to quickly re-run it later."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(onSubmit)}>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Name</Label>
              <Input
                placeholder="e.g., Active EGFR Hits"
                {...form.register("name")}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !mutation.isPending) {
                    void form.handleSubmit(onSubmit)();
                  }
                }}
              />
              {form.formState.errors.name && (
                <p className="text-xs text-destructive">{form.formState.errors.name.message}</p>
              )}
            </div>

            <div className="grid gap-2">
              <Label>Visibility</Label>
              <Controller
                name="visibility"
                control={form.control}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="private">Private</SelectItem>
                      <SelectItem value="project">Project</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </div>

            {watchedVisibility === "project" && (
              <div className="grid gap-2">
                <Label>Project</Label>
                <Controller
                  name="project_id"
                  control={form.control}
                  render={({ field }) => (
                    <Select value={field.value} onValueChange={field.onChange}>
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
                  )}
                />
                {form.formState.errors.project_id && (
                  <p className="text-xs text-destructive">
                    {form.formState.errors.project_id.message}
                  </p>
                )}
              </div>
            )}

            <div className="grid gap-2">
              <Label>Query</Label>
              <Textarea
                placeholder="Search criteria (JSON)"
                {...form.register("query")}
                rows={4}
                className="font-mono text-sm"
              />
              {form.formState.errors.query && (
                <p className="text-xs text-destructive">{form.formState.errors.query.message}</p>
              )}
            </div>

            <div className="grid gap-2">
              <Label>Columns (optional)</Label>
              <Textarea
                placeholder="Column preferences (JSON)"
                {...form.register("columns")}
                rows={3}
                className="font-mono text-sm"
              />
              {form.formState.errors.columns && (
                <p className="text-xs text-destructive">{form.formState.errors.columns.message}</p>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={form.formState.isSubmitting || mutation.isPending}>
              {mutation.isPending
                ? isEdit
                  ? "Saving..."
                  : "Creating..."
                : isEdit
                  ? "Save Changes"
                  : "Create Saved Search"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
