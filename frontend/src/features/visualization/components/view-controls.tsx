"use client";

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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/shared/components/ui/dropdown-menu";
import { useCanEdit } from "@/shared/hooks/use-current-user";
import { isStaleEdit } from "@/shared/lib/api/custom-instance";
import type { UpdateSavedVisualizationBody } from "@/shared/lib/api/model";
import { ChevronDown } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useUpdateSavedView } from "../hooks/use-saved-views";
import type { DerivedSpec } from "../lib/derived";
import type { Filter } from "../lib/filters";
import { buildViewConfig, sameDerived, sameSaved, tooLargeToSave } from "../lib/saved-view";
import { fromDatasetRequest, toDatasetRequest, visualizeHref } from "../lib/source-url";
import { type OpenView, useOpenView } from "../store/open-view-context";
import { useWorkbench } from "../store/workbench-context";
import { type PanelConfig, isDirty } from "../store/workbench-store";
import type { Dataset, DatasetSource, Level } from "../types";
import { DeleteViewDialog, SaveViewDialog } from "./save-view-dialog";

type Dialog = "create" | "details" | "delete" | "stale";
/** ``derived``: how the workbench's chemistry columns were computed (saved with the view). */
type Props = { source: DatasetSource; level: Level; ds: Dataset; derived: DerivedSpec[] };

/** Header controls for saving the workbench as a named view. No view open: "Save view…".
 * A view open: its name, a dot while there are unsaved changes, and — for its owner or an
 * admin — Save plus a menu (save as new, edit name and sharing, delete); anyone else can
 * save it as a new view. Viewers see the name only. Nothing is saved without a click. */
export function ViewControls(props: Props) {
  const open = useOpenView();
  const canEdit = useCanEdit();
  if (!open) return canEdit ? <Controls {...props} open={null} /> : null;
  return <Controls {...props} open={open} readOnly={!canEdit} />;
}

function Controls({
  source,
  level,
  ds,
  derived,
  open,
  readOnly = false,
}: Props & { open: OpenView | null; readOnly?: boolean }) {
  const router = useRouter();
  const panels = useWorkbench((s) => s.panels);
  const filters = useWorkbench((s) => s.filters);
  const changed = useWorkbench((s) => isDirty(s) && !sameSaved(s.baseline ?? s, s));
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const view = open?.view;

  const config = useMemo(
    () => buildViewConfig({ panels, filters }, ds, derived),
    [panels, filters, ds, derived],
  );
  const tooLarge = useMemo(() => tooLargeToSave(config), [config]);
  const saved = view?.dataset ? fromDatasetRequest(view.dataset).source : null;
  const savedDerived = open?.config.derived;
  const derivedChanged = useMemo(
    () => savedDerived !== undefined && !sameDerived(derived, savedDerived),
    [derived, savedDerived],
  );
  const dirty =
    view !== undefined &&
    (changed ||
      derivedChanged ||
      level !== view.level ||
      !saved ||
      visualizeHref(saved) !== visualizeHref(source));

  const closeDialog = (next: boolean) => !next && setDialog(null);
  // Unavailable yet focusable, so the title says why to keyboard users too.
  const saveAsNew = (
    <Button
      size="sm"
      variant="outline"
      className="h-8"
      aria-disabled={tooLarge !== null}
      title={tooLarge ?? undefined}
      onClick={() => tooLarge === null && setDialog("create")}
    >
      {view ? "Save as new view…" : "Save view…"}
    </Button>
  );

  return (
    <div className="ml-auto flex min-w-0 items-center gap-2">
      {view && (
        <span className="flex min-w-0 items-center gap-1.5 text-sm font-medium">
          <span className="truncate" title={view.name}>
            {view.name}
          </span>
          {dirty && !readOnly && (
            <span
              role="img"
              aria-label="Unsaved changes"
              title="Unsaved changes"
              className="h-2 w-2 shrink-0 rounded-full bg-primary"
            />
          )}
        </span>
      )}
      {!readOnly &&
        (view?.can_edit && open ? (
          <OwnerSave
            open={open}
            body={{ dataset: toDatasetRequest(source, level), config }}
            sent={{ panels, filters }}
            disabled={!dirty}
            tooLarge={tooLarge}
            onStale={() => setDialog("stale")}
            onMenu={setDialog}
          />
        ) : (
          saveAsNew
        ))}
      {(dialog === "create" || dialog === "details") && (
        <SaveViewDialog
          mode={dialog}
          view={view}
          source={source}
          level={level}
          ds={ds}
          derived={derived}
          open
          onOpenChange={closeDialog}
          onStale={() => setDialog("stale")}
        />
      )}
      {dialog === "delete" && view && (
        <DeleteViewDialog
          view={view}
          open
          onOpenChange={closeDialog}
          onDeleted={() => router.replace(visualizeHref(source, level), { scroll: false })}
        />
      )}
      {dialog === "stale" && open && (
        <AlertDialog open onOpenChange={closeDialog}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>This view changed since you opened it</AlertDialogTitle>
              <AlertDialogDescription>
                Someone saved a newer version. Reload it to see theirs — your unsaved changes are
                lost — or keep yours as a new view.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <Button variant="outline" onClick={() => setDialog("create")}>
                Save as new view…
              </Button>
              <Button onClick={open.reload}>Reload view</Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </div>
  );
}

/** "Save" (PATCH from the version the view was opened at; then what was sent reads as
 * saved) and the owner's menu. */
function OwnerSave({
  open,
  body,
  sent,
  disabled,
  tooLarge,
  onStale,
  onMenu,
}: {
  open: OpenView;
  body: Omit<UpdateSavedVisualizationBody, "expected_version">;
  sent: { panels: PanelConfig[]; filters: Filter[] };
  disabled: boolean;
  /** Why the settings can't be saved for their size, or null. */
  tooLarge: string | null;
  onStale: () => void;
  onMenu: (dialog: Dialog) => void;
}) {
  const update = useUpdateSavedView(open.view.id);
  const markSaved = useWorkbench((s) => s.markSaved);
  const save = () =>
    update.mutate(
      { expected_version: open.view.version, ...body },
      {
        onSuccess: () => markSaved(sent),
        onError: (err) => isStaleEdit(err, { race: true }) && onStale(),
      },
    );
  return (
    <span className="inline-flex">
      <Button
        size="sm"
        className="h-8 rounded-r-none"
        disabled={disabled || update.isPending}
        // Unavailable yet focusable, so the title says why to keyboard users too.
        aria-disabled={tooLarge !== null}
        title={tooLarge ?? undefined}
        onClick={() => tooLarge === null && save()}
      >
        Save
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            size="sm"
            className="h-8 rounded-l-none border-l border-primary-foreground/20 px-2"
            aria-label="More view actions"
          >
            <ChevronDown className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem disabled={tooLarge !== null} onSelect={() => onMenu("create")}>
            Save as new view…
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => onMenu("details")}>
            Edit name and sharing…
          </DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onSelect={() => onMenu("delete")}>
            Delete view…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </span>
  );
}
