"use client";

import { MemberName } from "@/shared/components/entity-name";
import { Button } from "@/shared/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/shared/components/ui/collapsible";
import { resolveCategoryColor } from "@/shared/lib/category-colors";
import { formatDateTime, formatRelativeDate } from "@/shared/lib/format-date";
import { cn } from "@/shared/lib/utils";
import { Check, ChevronRight, Plus, X } from "lucide-react";
import { useState } from "react";
import { useAssignTag, useEntityTags, useUnassignTag } from "../hooks/use-entity-tags";
import type { TaggableEntity } from "../types";
import { TagAutocomplete } from "./tag-autocomplete";

interface TagTableProps {
  entity: TaggableEntity;
  entityId: string;
  /** Read-only (e.g. viewers) hides the add affordance + remove buttons. */
  canEdit?: boolean;
}

/**
 * Reusable colored-row tag editor for any taggable resource.
 * Collapsible (open by default); rows are tinted by the key's palette color.
 * Adding is an explicit gesture — "+ New tag" reveals an inline add-row.
 */
export function TagTable({ entity, entityId, canEdit = true }: TagTableProps) {
  const { data: tags, isLoading } = useEntityTags(entity, entityId);
  const assign = useAssignTag(entity, entityId);
  const unassign = useUnassignTag(entity, entityId);

  const [open, setOpen] = useState(true);
  const [adding, setAdding] = useState(false);
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");

  const count = tags?.length ?? 0;

  const add = async () => {
    if (!key.trim()) return;
    await assign.mutateAsync({ key: key.trim(), value: value.trim() || null });
    // Keep the row open for rapid multi-tagging; just clear the inputs.
    setKey("");
    setValue("");
  };

  const cancelAdd = () => {
    setAdding(false);
    setKey("");
    setValue("");
  };

  const startAdding = () => {
    setOpen(true);
    setAdding(true);
  };

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="overflow-hidden rounded-lg border bg-card"
    >
      <div className="flex items-center justify-between gap-2 px-3 py-2">
        <CollapsibleTrigger
          aria-label="Toggle tags"
          className="flex items-center gap-1.5 text-sm font-semibold text-foreground"
        >
          <ChevronRight
            className={cn(
              "h-4 w-4 text-muted-foreground transition-transform",
              open && "rotate-90",
            )}
          />
          Tags
          {count > 0 && (
            <span className="text-xs font-normal text-muted-foreground">({count})</span>
          )}
        </CollapsibleTrigger>

        {canEdit && !adding && (
          <Button type="button" size="sm" variant="outline" className="h-7" onClick={startAdding}>
            <Plus className="mr-1 h-3.5 w-3.5" /> New tag
          </Button>
        )}
      </div>

      <CollapsibleContent>
        <div className="border-t">
          {isLoading && <p className="px-3 py-2 text-xs text-muted-foreground">Loading tags…</p>}

          {!isLoading && count === 0 && !adding && (
            <p className="px-3 py-2 text-xs italic text-muted-foreground/70">
              {canEdit ? "No tags yet." : "No tags"}
            </p>
          )}

          <ul>
            {tags?.map((t) => {
              const color = resolveCategoryColor(t.key);
              const label = t.value ? `${t.key}=${t.value}` : t.key;
              return (
                <li key={t.id} className={cn("flex items-stretch", color.bg)}>
                  <span className={cn("w-1 shrink-0", color.dot)} aria-hidden />
                  <div className="flex flex-1 items-center gap-2 px-3 py-1.5 text-sm">
                    <span className={cn("font-semibold", color.text)}>{t.key}</span>
                    {t.value && (
                      <>
                        <span className="text-muted-foreground/60">=</span>
                        <span className="text-foreground/90">{t.value}</span>
                      </>
                    )}
                    <span
                      className="ml-auto flex items-center gap-1 whitespace-nowrap text-xs text-muted-foreground/80"
                      title={`Added ${formatDateTime(t.assigned_at)}`}
                    >
                      <span>{formatRelativeDate(t.assigned_at)}</span>
                      <span aria-hidden>·</span>
                      <MemberName id={t.assigned_by} />
                    </span>
                    {canEdit && (
                      <button
                        type="button"
                        aria-label={`Remove ${label}`}
                        onClick={() => unassign.mutate(t.id)}
                        className="rounded-full p-0.5 text-muted-foreground/60 hover:text-destructive"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </li>
              );
            })}

            {canEdit && adding && (
              <li className="flex items-center gap-2 border-t px-3 py-2">
                <div className="w-40">
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
                <div className="w-40">
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
                  className="h-8"
                  aria-label="Add tag"
                  onClick={add}
                  disabled={!key.trim() || assign.isPending}
                >
                  <Check className="h-3.5 w-3.5" />
                </Button>
                <button
                  type="button"
                  aria-label="Cancel"
                  onClick={cancelAdd}
                  className="rounded-full p-1 text-muted-foreground/60 hover:text-foreground"
                >
                  <X className="h-4 w-4" />
                </button>
              </li>
            )}
          </ul>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
