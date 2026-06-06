"use client";

import { useOrganizations } from "@/features/workspace-config/hooks/use-organizations";
import { SearchableSelect } from "@/shared/components/searchable-select";
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
import { useCreateCollection, useUpdateCollection } from "../hooks/use-collections";
import { useProjects } from "../hooks/use-projects";
import { COLLECTION_TYPE_OPTIONS, type Collection } from "../types";

// ── Schema ────────────────────────────────────────────────────────────────────

const formSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
  visibility: z.enum(["private", "shared"]),
  type: z.enum(["generic", "reference_set", "library", "hit_list", "series", "distribution_set"]),
  // null = no project selected; stored as null in the form
  project_id: z.string().nullable(),
  org_id: z.string().nullable(),
});

type FormValues = z.infer<typeof formSchema>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeDefaultValues(defaultProjectId?: string): FormValues {
  return {
    name: "",
    description: "",
    visibility: "private",
    type: "generic",
    project_id: defaultProjectId ?? null,
    org_id: null,
  };
}

function toFormValues(collection: Collection, defaultProjectId?: string): FormValues {
  return {
    name: collection.name,
    description: collection.description ?? "",
    visibility: collection.visibility ?? "private",
    type: collection.type ?? "generic",
    project_id: collection.project_id ?? defaultProjectId ?? null,
    org_id: collection.owned_by_org_id ?? null,
  };
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface CreateCollectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pass a collection to switch to edit mode. */
  collection?: Collection;
  /** Pre-select a project (e.g., when creating from project detail). */
  defaultProjectId?: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function CreateCollectionDialog({
  open,
  onOpenChange,
  collection,
  defaultProjectId,
}: CreateCollectionDialogProps) {
  const isEdit = !!collection;
  const createMutation = useCreateCollection();
  const updateMutation = useUpdateCollection(collection?.id ?? "");

  const { data: projects } = useProjects();
  const { data: orgs } = useOrganizations();

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: makeDefaultValues(defaultProjectId),
  });

  // Reset form when dialog opens / collection changes
  useEffect(() => {
    if (open) {
      form.reset(
        collection
          ? toFormValues(collection, defaultProjectId)
          : makeDefaultValues(defaultProjectId),
      );
    }
  }, [open, collection, defaultProjectId, form]);

  const mutation = isEdit ? updateMutation : createMutation;

  const onSubmit = (values: FormValues) => {
    const payload = {
      name: values.name.trim(),
      description: values.description?.trim() || null,
      project_id: values.project_id,
      owned_by_org_id: values.org_id,
      visibility: values.visibility,
      type: values.type,
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
          <DialogTitle>{isEdit ? "Edit Collection" : "New Collection"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update the collection details."
              : "Create a collection to group related molecules."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(onSubmit)}>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Name</Label>
              <Input
                placeholder="e.g., EGFR Hit Series A"
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
              <Label>Description (optional)</Label>
              <Textarea
                placeholder="Brief description of the collection..."
                {...form.register("description")}
                rows={3}
              />
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
                      <SelectItem value="shared">Shared</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </div>

            <div className="grid gap-2">
              <Label>Type</Label>
              <Controller
                name="type"
                control={form.control}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {COLLECTION_TYPE_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>

            <div className="grid gap-2">
              <Label>Project (optional)</Label>
              <Controller
                name="project_id"
                control={form.control}
                render={({ field }) => (
                  <SearchableSelect
                    options={
                      projects
                        ?.filter((p) => p.status === "active")
                        .map((p) => ({ value: p.id, label: p.name })) ?? []
                    }
                    value={field.value}
                    onValueChange={(v) => field.onChange(v ?? null)}
                    placeholder="No project"
                    searchPlaceholder="Search projects..."
                  />
                )}
              />
            </div>

            <div className="grid gap-2">
              <Label>Organization (optional)</Label>
              <Controller
                name="org_id"
                control={form.control}
                render={({ field }) => (
                  <SearchableSelect
                    options={orgs?.map((o) => ({ value: o.id, label: o.name })) ?? []}
                    value={field.value}
                    onValueChange={(v) => field.onChange(v ?? null)}
                    placeholder="No organization"
                    searchPlaceholder="Search organizations..."
                  />
                )}
              />
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
                  : "Create Collection"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
