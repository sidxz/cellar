"use client";

import { TagAutocomplete } from "@/features/tagging/components/tag-autocomplete";
import {
  useAssignTag,
  useEntityTags,
  useUnassignTag,
} from "@/features/tagging/hooks/use-entity-tags";
import { TagChip } from "@/shared/components/tag-chip";
import { Button } from "@/shared/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { formatRelativeDate } from "@/shared/lib/format-date";
import { useQueryClient } from "@tanstack/react-query";
import { Check, Pencil, Plus } from "lucide-react";
import { type ReactNode, useState } from "react";
import {
  invalidateRunCollectionQueries,
  useAddRunCollection,
  useRemoveRunCollection,
} from "../hooks/use-run-collections";
import {
  invalidateRunTargetQueries,
  useAddRunTarget,
  useRemoveRunTarget,
} from "../hooks/use-run-targets";
import type { Protocol, Run } from "../types";
import { CollectionMultiSelect } from "./collection-multi-select";
import { CoverageChip } from "./coverage-chip";
import { CoverageGapDialog } from "./coverage-gap-dialog";
import { TargetChips } from "./target-chips";
import { TargetMultiSelect } from "./target-multi-select";

// ─── Shared bits ──────────────────────────────────────────────────────────────

function RelLabel({ children }: { children: ReactNode }) {
  return (
    <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
      {children}
    </span>
  );
}

/** Compact popover trigger for a relation. Shows "+ Add" when the relation is
 *  empty (so the call-to-action is discoverable), and a bare pencil otherwise. */
function EditTrigger({ empty, label }: { empty: boolean; label: string }) {
  return (
    <PopoverTrigger asChild>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        aria-label={empty ? `Add ${label}` : `Edit ${label}`}
        className="h-6 gap-1 rounded-full border border-dashed px-2 text-xs text-muted-foreground hover:text-foreground"
      >
        {empty ? (
          <>
            <Plus className="h-3 w-3" /> Add
          </>
        ) : (
          <Pencil className="h-3 w-3" />
        )}
      </Button>
    </PopoverTrigger>
  );
}

// ─── Targets ────────────────────────────────────────────────────────────────────

export function TargetsRelation({ run, canEdit }: { run: Run; canEdit: boolean }) {
  const qc = useQueryClient();
  const addTarget = useAddRunTarget(run.id);
  const removeTarget = useRemoveRunTarget(run.id);
  const pending = addTarget.isPending || removeTarget.isPending;

  const apply = async (ids: string[]) => {
    // Diff against the current set, dispatch as one awaited batch with a single
    // invalidation pass. The select is disabled while in flight so a rapid
    // second toggle can't diff against a stale list.
    const current = run.targets.map((t) => t.id);
    const mutations = [
      ...ids.filter((id) => !current.includes(id)).map((id) => addTarget.mutateAsync(id)),
      ...current.filter((id) => !ids.includes(id)).map((id) => removeTarget.mutateAsync(id)),
    ];
    try {
      await Promise.all(mutations);
    } catch {
      // surfaced by the mutations' error toasts
    } finally {
      await invalidateRunTargetQueries(qc, run.id);
    }
  };

  return (
    <span className="inline-flex items-center gap-2">
      <RelLabel>Targets</RelLabel>
      <TargetChips targets={run.targets} max={6} />
      {canEdit && (
        <Popover>
          <EditTrigger empty={run.targets.length === 0} label="targets" />
          <PopoverContent align="start" className="w-72">
            <TargetMultiSelect
              value={run.targets.map((t) => t.id)}
              onChange={apply}
              placeholder="Add a target…"
              disabled={pending}
            />
          </PopoverContent>
        </Popover>
      )}
    </span>
  );
}

// ─── Collections (coverage) ─────────────────────────────────────────────────────

export function CollectionsRelation({
  run,
  protocol,
  canEdit,
}: {
  run: Run;
  protocol: Protocol | undefined;
  canEdit: boolean;
}) {
  const qc = useQueryClient();
  const addCollection = useAddRunCollection(run.id);
  const removeCollection = useRemoveRunCollection(run.id);
  const pending = addCollection.isPending || removeCollection.isPending;
  const [gap, setGap] = useState<{ path: string; name: string } | null>(null);

  const collections = run.collections ?? [];

  const apply = async (ids: string[]) => {
    const current = collections.map((c) => c.id);
    const mutations = [
      ...ids.filter((id) => !current.includes(id)).map((id) => addCollection.mutateAsync(id)),
      ...current.filter((id) => !ids.includes(id)).map((id) => removeCollection.mutateAsync(id)),
    ];
    try {
      await Promise.all(mutations);
    } catch {
      // surfaced by the mutations' error toasts
    } finally {
      await invalidateRunCollectionQueries(qc, run.id);
    }
  };

  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      <RelLabel>{collections.length === 1 ? "Collection" : "Collections"}</RelLabel>
      {collections.length === 0 ? (
        <span className="text-xs text-muted-foreground">None</span>
      ) : (
        <span className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
          {collections.map((c) => (
            <CoverageChip
              key={c.id}
              coverage={c}
              onViewGap={() =>
                setGap({ path: `/runs/${run.id}/collections/${c.id}`, name: c.name })
              }
            />
          ))}
        </span>
      )}
      {canEdit && (
        <Popover>
          <EditTrigger empty={collections.length === 0} label="collections" />
          <PopoverContent align="start" className="w-72">
            <CollectionMultiSelect
              value={collections.map((c) => c.id)}
              projectIds={protocol?.project_ids?.length ? protocol.project_ids : undefined}
              onChange={apply}
              disabled={pending}
            />
          </PopoverContent>
        </Popover>
      )}
      {gap && (
        <CoverageGapDialog
          open
          onOpenChange={(o) => !o && setGap(null)}
          gapBasePath={gap.path}
          collectionName={gap.name}
        />
      )}
    </span>
  );
}

// ─── Tags ────────────────────────────────────────────────────────────────────────

export function TagsRelation({ runId, canEdit }: { runId: string; canEdit: boolean }) {
  const { data: tags } = useEntityTags("runs", runId);
  const assign = useAssignTag("runs", runId);
  const unassign = useUnassignTag("runs", runId);
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");

  const list = tags ?? [];

  const add = async () => {
    if (!key.trim()) return;
    await assign.mutateAsync({ key: key.trim(), value: value.trim() || null });
    // Keep the popover open for rapid multi-tagging; just clear the inputs.
    setKey("");
    setValue("");
  };

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <RelLabel>Tags</RelLabel>
      {list.length === 0 && (
        <span className="text-xs italic text-muted-foreground/70">No tags</span>
      )}
      {list.map((t) => (
        <TagChip
          key={t.id}
          tagKey={t.key}
          value={t.value}
          title={`${t.value ? `${t.key}=${t.value}` : t.key} · added ${formatRelativeDate(t.assigned_at)}`}
          onRemove={canEdit ? () => unassign.mutate(t.id) : undefined}
        />
      ))}
      {canEdit && (
        <Popover>
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label="Add tag"
              className="h-6 gap-1 rounded-full border border-dashed px-2 text-xs text-muted-foreground hover:text-foreground"
            >
              <Plus className="h-3 w-3" /> Tag
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-80 space-y-2">
            <p className="text-xs font-medium">Add a tag</p>
            <div className="flex items-center gap-1.5">
              <div className="flex-1">
                <TagAutocomplete
                  value={key}
                  onChange={setKey}
                  placeholder="key"
                  field="key"
                  onEnter={add}
                  autoFocus
                />
              </div>
              <span className="text-muted-foreground">=</span>
              <div className="flex-1">
                <TagAutocomplete
                  value={value}
                  onChange={setValue}
                  placeholder="value (optional)"
                  field="value"
                  onEnter={add}
                />
              </div>
              <Button
                type="button"
                size="sm"
                className="h-8 shrink-0"
                aria-label="Save tag"
                onClick={add}
                disabled={!key.trim() || assign.isPending}
              >
                <Check className="h-3.5 w-3.5" />
              </Button>
            </div>
          </PopoverContent>
        </Popover>
      )}
    </span>
  );
}
