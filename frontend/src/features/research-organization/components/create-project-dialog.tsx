"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
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
import { Textarea } from "@/shared/components/ui/textarea";
import { useCreateProject, useUpdateProject } from "../hooks/use-projects";
import type { Project } from "../types";

// ── Schema ────────────────────────────────────────────────────────────────────

const formSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
});

type FormValues = z.infer<typeof formSchema>;

// ── Helpers ───────────────────────────────────────────────────────────────────

const defaultValues: FormValues = { name: "", description: "" };

function toFormValues(project: Project): FormValues {
  return {
    name: project.name,
    description: project.description ?? "",
  };
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface CreateProjectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Pass a project to switch to edit mode. */
  project?: Project;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function CreateProjectDialog({
  open,
  onOpenChange,
  project,
}: CreateProjectDialogProps) {
  const isEdit = !!project;
  const createMutation = useCreateProject();
  const updateMutation = useUpdateProject(project?.id ?? "");

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues,
  });

  // Reset form when dialog opens / project changes
  useEffect(() => {
    if (open) {
      form.reset(project ? toFormValues(project) : defaultValues);
    }
  }, [open, project, form]);

  const mutation = isEdit ? updateMutation : createMutation;

  const onSubmit = (values: FormValues) => {
    const payload = {
      name: values.name.trim(),
      description: values.description?.trim() || null,
    };

    mutation.mutate(payload, {
      onSuccess: () => {
        onOpenChange(false);
        form.reset(defaultValues);
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Project" : "New Project"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update the project name or description."
              : "Create a research project to organize collections and saved searches."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(onSubmit)}>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Name</Label>
              <Input
                placeholder="e.g., EGFR Inhibitor Program"
                {...form.register("name")}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !mutation.isPending) {
                    void form.handleSubmit(onSubmit)();
                  }
                }}
              />
              {form.formState.errors.name && (
                <p className="text-xs text-destructive">
                  {form.formState.errors.name.message}
                </p>
              )}
            </div>

            <div className="grid gap-2">
              <Label>Description (optional)</Label>
              <Textarea
                placeholder="Brief description of the project goals..."
                {...form.register("description")}
                rows={3}
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
            <Button
              type="submit"
              disabled={form.formState.isSubmitting || mutation.isPending}
            >
              {mutation.isPending
                ? isEdit
                  ? "Saving..."
                  : "Creating..."
                : isEdit
                  ? "Save Changes"
                  : "Create Project"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
