"use client";

import { useProjects } from "@/features/research-organization/hooks/use-projects";
import { Alert } from "@/shared/components/ui/alert";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/shared/components/ui/alert-dialog";
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
import { RadioGroup, RadioGroupItem } from "@/shared/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Textarea } from "@/shared/components/ui/textarea";
import { isStaleEdit } from "@/shared/lib/api/custom-instance";
import { useRouter } from "next/navigation";
import { type FormEvent, useId, useMemo, useState } from "react";
import {
  useCreateSavedView,
  useDeleteSavedView,
  useUpdateSavedView,
} from "../hooks/use-saved-views";
import { errorText } from "../lib/api-errors";
import type { DerivedSpec } from "../lib/derived";
import { buildViewConfig, tooLargeToSave } from "../lib/saved-view";
import { toDatasetRequest } from "../lib/source-url";
import { useWorkbench } from "../store/workbench-context";
import type { Dataset, DatasetSource, Level, SavedView } from "../types";

type Visibility = "private" | "project";

/** "Save view…" / "Save as new view…" (``create``: the source, level, plots and filters, then
 * the new view's page) or "Edit name and sharing…" (``details``: name, description and who
 * sees it, from the version ``view`` was opened at; a stale edit goes to ``onStale``).
 * Mount it only while open, so each opening starts from ``view``. */
export function SaveViewDialog({
  mode,
  view,
  source,
  level,
  ds,
  derived,
  open,
  onOpenChange,
  onStale,
}: {
  mode: "create" | "details";
  view?: SavedView;
  source: DatasetSource;
  level: Level;
  ds: Dataset;
  derived: DerivedSpec[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onStale?: () => void;
}) {
  const details = mode === "details" && view !== undefined;
  const ids = useId();
  const router = useRouter();
  const panels = useWorkbench((s) => s.panels);
  const filters = useWorkbench((s) => s.filters);
  const { data: projects } = useProjects();
  const create = useCreateSavedView();
  const update = useUpdateSavedView(view?.id ?? "");
  const mutation = details ? update : create;

  const [name, setName] = useState(details ? view.name : "");
  const [description, setDescription] = useState((details && view.description) || "");
  const [visibility, setVisibility] = useState<Visibility>(details ? view.visibility : "private");
  const [projectId, setProjectId] = useState((details && view.project_id) || "");

  const config = useMemo(
    () => (details ? null : buildViewConfig({ panels, filters }, ds, derived)),
    [details, panels, filters, ds, derived],
  );
  const tooLarge = config && tooLargeToSave(config);
  const ready = name.trim() !== "" && (visibility === "private" || projectId !== "");

  const save = (e: FormEvent) => {
    e.preventDefault();
    const fields = {
      name: name.trim(),
      description: description.trim() || null,
      visibility,
      project_id: visibility === "project" ? projectId : null,
    };
    if (details) {
      update.mutate(
        { expected_version: view.version, ...fields },
        {
          onSuccess: () => onOpenChange(false),
          onError: (err) => {
            if (!isStaleEdit(err, { race: true })) return;
            onOpenChange(false);
            onStale?.();
          },
        },
      );
    } else if (config) {
      create.mutate(
        { ...fields, dataset: toDatasetRequest(source, level), config },
        {
          onSuccess: (created) => {
            onOpenChange(false);
            router.replace(`/assays/visualize/${created.id}`);
          },
        },
      );
    }
  };

  const notes = details
    ? []
    : [
        "Saves the plots, filters and level — never the data. Opening it loads current data.",
        filters.some((f) => f.kind === "rows") && "Filter to selection isn't saved.",
        derived.length > 0 && "Chemistry columns are computed again each time the view opens.",
        source.kind === "protocol" &&
          !source.runIds &&
          "Runs added to the protocol later will be included.",
      ].filter((n): n is string => typeof n === "string");
  const refused =
    mutation.error && !isStaleEdit(mutation.error, { race: true })
      ? errorText(mutation.error)
      : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={save} className="space-y-4">
          <DialogHeader>
            <DialogTitle>
              {details ? "Edit name and sharing" : view ? "Save as new view" : "Save view"}
            </DialogTitle>
            <DialogDescription>
              {details
                ? "Name the view and choose who sees it."
                : "A named view you and others can open again."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1">
            <Label htmlFor={`${ids}-name`}>Name</Label>
            <Input
              id={`${ids}-name`}
              autoFocus
              maxLength={255}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`${ids}-description`}>Description</Label>
            <Textarea
              id={`${ids}-description`}
              rows={2}
              maxLength={2000}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <fieldset className="space-y-2">
            <legend className="mb-1 text-sm font-medium">Who sees it</legend>
            <RadioGroup
              value={visibility}
              onValueChange={(v) => setVisibility(v as Visibility)}
              className="gap-2"
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem id={`${ids}-private`} value="private" />
                <Label htmlFor={`${ids}-private`} className="font-normal">
                  Private — only you
                </Label>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <RadioGroupItem id={`${ids}-project`} value="project" />
                <Label htmlFor={`${ids}-project`} className="font-normal">
                  Project — members of
                </Label>
                <Select
                  value={projectId}
                  onValueChange={(id) => {
                    setProjectId(id);
                    setVisibility("project");
                  }}
                >
                  <SelectTrigger size="sm" className="min-w-40" aria-label="Project">
                    <SelectValue placeholder="Choose a project" />
                  </SelectTrigger>
                  <SelectContent>
                    {projects
                      ?.filter((p) => p.status === "active" || p.id === projectId)
                      .map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.name}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>
            </RadioGroup>
          </fieldset>
          {notes.length > 0 && (
            <ul className="space-y-0.5 text-xs text-muted-foreground">
              {notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          )}
          {(tooLarge || refused) && (
            <Alert variant="destructive" className="py-2 text-sm">
              {tooLarge ?? refused}
            </Alert>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!ready || Boolean(tooLarge) || mutation.isPending}>
              {details ? "Save changes" : "Save view"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Confirms, then deletes ``view``; ``onDeleted`` says where the chemist goes next. */
export function DeleteViewDialog({
  view,
  open,
  onOpenChange,
  onDeleted,
}: {
  view: SavedView;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDeleted: () => void;
}) {
  const remove = useDeleteSavedView();
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete view</AlertDialogTitle>
          <AlertDialogDescription>
            {`Delete “${view.name}”? People it's shared with lose it too. The data isn't affected.`}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          {/* A plain button: the dialog stays open until the delete is through. */}
          <Button
            variant="destructive"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(view.id, {
                onSuccess: () => {
                  onOpenChange(false);
                  onDeleted();
                },
              })
            }
          >
            Delete view
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
