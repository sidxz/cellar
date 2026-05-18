"use client";

import { Button } from "@/shared/components/ui/button";
import { Label } from "@/shared/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/components/ui/select";
import { Plus, Search } from "lucide-react";
import { useState } from "react";
import {
  defaultActivityCriterion,
  defaultBatchCriterion,
  defaultCollectionCriterion,
  defaultCustomFieldCriterion,
  defaultGroupCriterion,
  defaultKeywordListCriterion,
  defaultProjectCriterion,
  defaultPropertyCriterion,
  defaultRunDateCriterion,
  defaultScaffoldCriterion,
  defaultSelectivityCriterion,
  defaultStructureCriterion,
  defaultTextCriterion,
} from "../lib/search-query-config";
import type { SearchCriterion, SearchQuery } from "../types";
import {
  ActivityCriterionRow,
  BatchCriterionRow,
  CollectionCriterionRow,
  CustomFieldCriterionRow,
  GroupCriterionRow,
  KeywordListCriterionRow,
  ProjectCriterionRow,
  PropertyCriterionRow,
  RunDateCriterionRow,
  ScaffoldCriterionRow,
  SelectivityCriterionRow,
  StructureCriterionRow,
  TextCriterionRow,
} from "./criterion-rows";

// ─── NegateToggle ────────────────────────────────────────────────────────────

function NegateToggle({
  negate,
  onToggle,
}: {
  negate: boolean;
  onToggle: (v: boolean) => void;
}) {
  return (
    <Button
      type="button"
      variant={negate ? "destructive" : "outline"}
      size="sm"
      className="h-7 px-2 text-xs shrink-0 self-end mb-0.5"
      onClick={() => onToggle(!negate)}
      title={negate ? "Click to remove NOT" : "Click to negate this criterion"}
    >
      {negate ? "NOT" : "IS"}
    </Button>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────

interface SearchQueryBuilderProps {
  initialQuery?: SearchQuery;
  onSearch: (query: SearchQuery) => void;
  isLoading?: boolean;
}

export function SearchQueryBuilder({ initialQuery, onSearch, isLoading }: SearchQueryBuilderProps) {
  const [criteria, setCriteria] = useState<SearchCriterion[]>(initialQuery?.criteria ?? []);
  const [logic, setLogic] = useState<"and" | "or">(initialQuery?.logic ?? "and");

  function updateCriterion(index: number, updated: SearchCriterion) {
    setCriteria((prev) => prev.map((c, i) => (i === index ? updated : c)));
  }

  function removeCriterion(index: number) {
    setCriteria((prev) => prev.filter((_, i) => i !== index));
  }

  function handleSearch() {
    onSearch({ criteria, logic });
  }

  return (
    <div className="space-y-4 rounded-lg border p-4">
      {/* Logic toggle + add buttons */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Label className="text-sm text-muted-foreground">Match</Label>
          <Select value={logic} onValueChange={(v) => setLogic(v as "and" | "or")}>
            <SelectTrigger className="h-8 w-20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="and">AND</SelectItem>
              <SelectItem value="or">OR</SelectItem>
            </SelectContent>
          </Select>
          <Label className="text-sm text-muted-foreground">of the following criteria</Label>
        </div>
        <Select
          value=""
          onValueChange={(v) => {
            const factories: Record<string, () => SearchCriterion> = {
              text: defaultTextCriterion,
              property: defaultPropertyCriterion,
              structure: defaultStructureCriterion,
              scaffold: defaultScaffoldCriterion,
              activity: defaultActivityCriterion,
              collection: defaultCollectionCriterion,
              keyword_list: defaultKeywordListCriterion,
              run_date: defaultRunDateCriterion,
              batch: defaultBatchCriterion,
              project: defaultProjectCriterion,
              selectivity: defaultSelectivityCriterion,
              custom_field: defaultCustomFieldCriterion,
              group: defaultGroupCriterion,
            };
            const factory = factories[v];
            if (factory) setCriteria([...criteria, factory()]);
          }}
        >
          <SelectTrigger className="h-8 w-44">
            <Plus className="mr-1 h-3.5 w-3.5" />
            <SelectValue placeholder="Add criterion..." />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="text">Text</SelectItem>
            <SelectItem value="property">Property</SelectItem>
            <SelectItem value="structure">Structure</SelectItem>
            <SelectItem value="activity">Activity</SelectItem>
            <SelectItem value="batch">Batch</SelectItem>
            <SelectItem value="collection">Collection</SelectItem>
            <SelectItem value="project">Project</SelectItem>
            <SelectItem value="scaffold">Scaffold</SelectItem>
            <SelectItem value="keyword_list">Keyword List</SelectItem>
            <SelectItem value="run_date">Run Date</SelectItem>
            <SelectItem value="selectivity">Selectivity</SelectItem>
            <SelectItem value="custom_field">Custom Field</SelectItem>
            <SelectItem value="group">Group (nested)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Criteria rows */}
      {criteria.length === 0 && (
        <p className="py-4 text-center text-sm text-muted-foreground">
          Add criteria to build your search query.
        </p>
      )}

      <div className="space-y-3">
        {criteria.map((criterion, index) => {
          const key = `${criterion.type}-${index}`;
          const negate = criterion.negate ?? false;
          const toggleNegate = (v: boolean) =>
            updateCriterion(index, { ...criterion, negate: v || undefined });

          const wrapWithNegate = (row: React.ReactNode) => (
            <div
              key={key}
              className={`flex items-start gap-2 ${negate ? "ring-1 ring-destructive/30 rounded-md p-1" : ""}`}
            >
              <NegateToggle negate={negate} onToggle={toggleNegate} />
              <div className="flex-1">{row}</div>
            </div>
          );

          switch (criterion.type) {
            case "text":
              return wrapWithNegate(
                <TextCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />,
              );
            case "property":
              return wrapWithNegate(
                <PropertyCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />,
              );
            case "structure":
              return wrapWithNegate(
                <StructureCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />,
              );
            case "activity":
              return wrapWithNegate(
                <ActivityCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />,
              );
            case "collection":
              return wrapWithNegate(
                <CollectionCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />,
              );
            case "keyword_list":
              return wrapWithNegate(
                <KeywordListCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />,
              );
            case "run_date":
              return wrapWithNegate(
                <RunDateCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />,
              );
            case "batch":
              return wrapWithNegate(
                <BatchCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />,
              );
            case "project":
              return wrapWithNegate(
                <ProjectCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />,
              );
            case "scaffold":
              return wrapWithNegate(
                <ScaffoldCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />,
              );
            case "selectivity":
              return wrapWithNegate(
                <SelectivityCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />,
              );
            case "custom_field":
              return wrapWithNegate(
                <CustomFieldCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                />,
              );
            case "group":
              return wrapWithNegate(
                <GroupCriterionRow
                  criterion={criterion}
                  onChange={(c) => updateCriterion(index, { ...c, negate: criterion.negate })}
                  onRemove={() => removeCriterion(index)}
                  depth={0}
                />,
              );
          }
        })}
      </div>

      {/* Search button */}
      <div className="flex justify-end">
        <Button onClick={handleSearch} disabled={criteria.length === 0 || isLoading}>
          <Search className="mr-2 h-4 w-4" />
          {isLoading ? "Searching..." : "Search"}
        </Button>
      </div>
    </div>
  );
}
