"use client";

import { TagChip } from "@/shared/components/tag-chip";
import { Button } from "@/shared/components/ui/button";
import { Plus } from "lucide-react";
import { useState } from "react";
import { useAssignTag, useEntityTags, useUnassignTag } from "../hooks/use-entity-tags";
import type { TaggableEntity } from "../types";
import { TagAutocomplete } from "./tag-autocomplete";

interface TagEditorProps {
  entity: TaggableEntity;
  entityId: string;
  /** Read-only (e.g. viewers) hides the add form + remove buttons. */
  canEdit?: boolean;
}

export function TagEditor({ entity, entityId, canEdit = true }: TagEditorProps) {
  const { data: tags, isLoading } = useEntityTags(entity, entityId);
  const assign = useAssignTag(entity, entityId);
  const unassign = useUnassignTag(entity, entityId);
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");

  const add = async () => {
    if (!key.trim()) return;
    await assign.mutateAsync({ key: key.trim(), value: value.trim() || null });
    setKey("");
    setValue("");
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1">
        {isLoading && <span className="text-xs text-muted-foreground">Loading tags…</span>}
        {tags?.map((t) => (
          <TagChip
            key={t.id}
            tagKey={t.key}
            value={t.value}
            onRemove={canEdit ? () => unassign.mutate(t.id) : undefined}
          />
        ))}
        {!isLoading && tags?.length === 0 && !canEdit && (
          <span className="text-xs italic text-muted-foreground/60">No tags</span>
        )}
      </div>

      {canEdit && (
        <div className="flex items-end gap-2">
          <div className="w-40">
            <TagAutocomplete
              value={key}
              onChange={setKey}
              placeholder="key"
              field="key"
              onEnter={add}
            />
          </div>
          <span className="pb-1.5 text-muted-foreground">=</span>
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
            variant="outline"
            onClick={add}
            disabled={!key.trim() || assign.isPending}
          >
            <Plus className="mr-1 h-3.5 w-3.5" /> Add
          </Button>
        </div>
      )}
    </div>
  );
}
