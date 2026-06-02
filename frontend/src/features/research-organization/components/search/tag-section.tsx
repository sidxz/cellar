"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { TagFilter } from "@/features/tagging/components/tag-filter";
import type { SearchCriterion, TagCriterion } from "../../types";

export interface TagSectionValue {
  tagIds: string[];
  tagLogic: "any" | "all";
  negate: boolean;
}

export function defaultTagSectionValue(): TagSectionValue {
  return { tagIds: [], tagLogic: "any", negate: false };
}

interface TagSectionProps {
  value: TagSectionValue;
  onChange: (v: TagSectionValue) => void;
}

export function TagSection({ value, onChange }: TagSectionProps) {
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <span className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Tags
        </span>
      </div>
      <div className="flex items-center gap-2">
        <div className="w-28">
          <Select
            value={value.negate ? "not" : "in"}
            onValueChange={(v) => onChange({ ...value, negate: v === "not" })}
          >
            <SelectTrigger className="h-8 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="in">Tagged</SelectItem>
              <SelectItem value="not">Not tagged</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <TagFilter
          value={{ tagIds: value.tagIds, tagLogic: value.tagLogic }}
          onChange={(v) => onChange({ ...value, tagIds: v.tagIds, tagLogic: v.tagLogic })}
        />
      </div>
    </div>
  );
}

export function tagSectionToCriteria(v: TagSectionValue): SearchCriterion[] {
  if (v.tagIds.length === 0) return [];
  return [
    {
      type: "tag",
      tag_ids: v.tagIds,
      tag_logic: v.tagLogic,
      ...(v.negate ? { negate: true } : {}),
    } as SearchCriterion,
  ];
}

export function tagCriteriaToSection(criteria: SearchCriterion[]): TagSectionValue {
  const c = criteria.find(
    (x): x is TagCriterion & { negate?: boolean } => x.type === "tag",
  );
  return c
    ? { tagIds: [...c.tag_ids], tagLogic: c.tag_logic ?? "any", negate: !!c.negate }
    : defaultTagSectionValue();
}
