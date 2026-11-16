"use client";

import { EmptyState } from "@/shared/components/empty-state";
import { useCanEdit } from "@/shared/hooks/use-current-user";
import { ApiError } from "@/shared/lib/api/custom-instance";
import { AlertTriangle, ChartScatter } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { useSavedView } from "../hooks/use-saved-views";
import { errorText } from "../lib/api-errors";
import { migrateViewConfig } from "../lib/saved-view";
import { fromDatasetRequest } from "../lib/source-url";
import { OpenViewContext } from "../store/open-view-context";
import type { DatasetSource, Level } from "../types";
import { DeleteViewDialog } from "./save-view-dialog";
import { LoadingSkeleton, WorkbenchPage } from "./workbench-page";

/** A saved view at `/assays/visualize/<viewId>`: its source and level (each overridable by
 * the URL) opened on live data, with its plots and filters. */
export function SavedViewPage({
  viewId,
  sourceOverride,
  levelOverride,
}: {
  viewId: string;
  sourceOverride: DatasetSource | null;
  levelOverride: Level | null;
}) {
  const query = useSavedView(viewId);
  const router = useRouter();
  const canEdit = useCanEdit();
  const [deleting, setDeleting] = useState(false);
  // Bumped by "Reload view": the workbench remounts on the view as saved now.
  const [reloads, setReloads] = useState(0);
  const view = query.data;
  const { refetch } = query;
  const read = useMemo(() => view && migrateViewConfig(view.config), [view]);
  const open = useMemo(
    () =>
      view && read?.ok
        ? {
            view,
            config: read.config,
            reload: () => void refetch().then(() => setReloads((n) => n + 1)),
          }
        : null,
    [view, read, refetch],
  );

  if (query.isPending) return <LoadingSkeleton />;
  if (!view) {
    return query.error instanceof ApiError && query.error.status === 404 ? (
      <EmptyState icon={ChartScatter} title="This view doesn't exist or isn't shared with you." />
    ) : (
      <EmptyState
        icon={AlertTriangle}
        title="Couldn't load the view"
        description={errorText(query.error)}
        action={{ label: "Retry", onClick: () => void refetch() }}
      />
    );
  }
  if (!open) {
    const reason = read && !read.ok ? read.reason : "";
    return (
      <EmptyState icon={AlertTriangle} title="This view can't be opened" description={reason} />
    );
  }
  const source = sourceOverride ?? (view.dataset && fromDatasetRequest(view.dataset).source);
  if (!source) {
    return (
      <>
        <EmptyState
          icon={AlertTriangle}
          title="This view can't be opened"
          description={view.unresolved?.join(" ")}
          action={
            view.can_edit && canEdit
              ? { label: "Delete view", onClick: () => setDeleting(true) }
              : undefined
          }
        />
        {deleting && (
          <DeleteViewDialog
            view={view}
            open
            onOpenChange={setDeleting}
            onDeleted={() => router.replace("/assays")}
          />
        )}
      </>
    );
  }
  return (
    <OpenViewContext.Provider value={open}>
      <WorkbenchPage
        key={reloads}
        source={source}
        level={levelOverride ?? view.level}
        view={open}
      />
    </OpenViewContext.Provider>
  );
}
