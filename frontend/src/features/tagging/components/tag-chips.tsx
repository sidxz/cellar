"use client";

/**
 * TagChips — compact one-line tag editor for a taggable entity.
 *
 * Renders the entity's tags as TagChip pills (× when editable) plus a small
 * "+ Tag" pill that opens a popover with the same key/value autocomplete the
 * TagTable uses. Adding is an explicit gesture (Add button / Enter). Renders
 * nothing at all when there are no tags and the viewer cannot edit, so it
 * costs zero height on untagged read-only pages.
 */

import { TagChip } from "@/shared/components/tag-chip";
import { Button } from "@/shared/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/shared/components/ui/popover";
import { formatDateTime } from "@/shared/lib/format-date";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useAssignTag, useEntityTags, useUnassignTag } from "../hooks/use-entity-tags";
import type { TaggableEntity } from "../types";
import { TagAutocomplete } from "./tag-autocomplete";

interface TagChipsProps {
  entity: TaggableEntity;
  entityId: string;
  canEdit?: boolean;
  className?: string;
}

const ADD_PILL =
  "inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary hover:bg-primary/20 transition-colors";

export function TagChips({ entity, entityId, canEdit = false, className }: TagChipsProps) {
  const { data: tags } = useEntityTags(entity, entityId);
  const assign = useAssignTag(entity, entityId);
  const unassign = useUnassignTag(entity, entityId);
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");

  const add = async () => {
    if (!key.trim()) return;
    await assign.mutateAsync({ key: key.trim(), value: value.trim() || null });
    // Keep the popover open for rapid multi-tagging; just clear the inputs.
    setKey("");
    setValue("");
  };

  const onOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) {
      setKey("");
      setValue("");
    }
  };

  if (!canEdit && (tags?.length ?? 0) === 0) return null;

  return (
    <div className={`flex flex-wrap items-center gap-1.5 ${className ?? ""}`}>
      {tags?.map((t) => (
        <TagChip
          key={t.id}
          tagKey={t.key}
          value={t.value}
          title={`Added ${formatDateTime(t.assigned_at)}`}
          onRemove={canEdit ? () => unassign.mutate(t.id) : undefined}
        />
      ))}
      {canEdit && (
        <Popover open={open} onOpenChange={onOpenChange}>
          <PopoverTrigger asChild>
            <button type="button" className={ADD_PILL}>
              <Plus className="h-3 w-3" /> Tag
            </button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-[360px] p-3">
            <div className="flex items-center gap-2">
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
                className="h-8"
                onClick={add}
                disabled={!key.trim() || assign.isPending}
              >
                Add
              </Button>
            </div>
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}
